
from __future__ import annotations

"""Earth One v2.3 autonomous Sentinel-2 worker."""

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import io, json, os, tarfile

import numpy as np
import rasterio
import requests

from .s1_autonomous import TOKEN_URL

CATALOG_URL = "https://stac.dataspace.copernicus.eu/v1/search"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/process/v1"

@dataclass(frozen=True)
class S2Scene:
    id: str
    product_id: str
    datetime: str
    platform: str | None
    cloud_cover: float | None
    bbox: list[float] | None
    geometry: dict[str, Any] | None
    properties: dict[str, Any]
    assets: dict[str, Any]

def _scene(item: dict[str, Any]) -> S2Scene:
    p=item.get("properties", {})
    product=p.get("s2:product_uri") or p.get("s2:product_id") or item.get("id")
    if product and str(product).endswith(".SAFE"):
        product=str(product)[:-5]
    cloud=p.get("eo:cloud_cover")
    return S2Scene(
        id=item.get("id", str(product)),
        product_id=str(product),
        datetime=p.get("datetime") or p.get("start_datetime"),
        platform=p.get("platform") or p.get("constellation"),
        cloud_cover=None if cloud is None else float(cloud),
        bbox=item.get("bbox"),
        geometry=item.get("geometry"),
        properties=p,
        assets=item.get("assets", {}),
    )

def discover_s2(bbox, start, end, max_cloud=50.0, limit=100, session=None):
    s=session or requests.Session()
    payload={
        "collections":["sentinel-2-l2a"],
        "bbox":bbox,
        "datetime": f"{_as_utc(start).isoformat().replace('+00:00', 'Z')}/{_as_utc(end).isoformat().replace('+00:00', 'Z')}",
        "limit":limit,
        "query":{"eo:cloud_cover":{"lte":max_cloud}},
    }
    r=s.post(CATALOG_URL,json=payload,timeout=60)
    r.raise_for_status()
    return [_scene(x) for x in r.json().get("features",[])]

def _as_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        # STAC target dates may be supplied as date-only/naive values.
        # Treat them as UTC so subtraction is always offset-aware.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def select_best_s2(scenes, target_date):
    if not scenes:
        raise RuntimeError("No Sentinel-2 L2A scene found")
    target=_as_utc(target_date)
    def key(s):
        dt=_as_utc(s.datetime)
        gap=abs((dt-target).total_seconds())/86400.0
        cloud=999.0 if s.cloud_cover is None else s.cloud_cover
        return (gap, cloud, s.product_id)
    return sorted(scenes,key=key)[0]

def _evalscript(target_product_id):
    """Build a deterministic Sentinel-2 L2A Process API evalscript.

    Contract:
      B02, B03, B04, B08, B11, B12 = reflectance
      SCL = scene classification layer
      dataMask = provider validity mask

    The selected Sentinel-2 product is enforced inside the Process API
    mosaicking stage so another tile/product cannot silently replace it.
    """
    product_id = str(target_product_id).replace("\\", "\\\\").replace('"', '\\"')

    return f"""//VERSION=3
function setup() {{
    return {{
        input: [{{
            bands: [
                "B02",
                "B03",
                "B04",
                "B08",
                "B11",
                "B12",
                "SCL",
                "dataMask"
            ],
            units: [
                "REFLECTANCE",
                "REFLECTANCE",
                "REFLECTANCE",
                "REFLECTANCE",
                "REFLECTANCE",
                "REFLECTANCE",
                "DN",
                "DN"
            ]
        }}],
        mosaicking: Mosaicking.TILE,
        output: {{
            bands: 8,
            sampleType: SampleType.FLOAT32
        }}
    }};
}}

function preProcessScenes(collections) {{
    collections.scenes.tiles = collections.scenes.tiles.filter(function(tile) {{
        return tile.sentinel2ProductId === "{product_id}";
    }});
    return collections;
}}

function updateOutputMetadata(scenes, inputMetadata, outputMetadata) {{
    outputMetadata.userData = {{
        "tiles": scenes.tiles,
        "selectedProductId": "{product_id}"
    }};
}}

function evaluatePixel(sample) {{
    return [
        sample.B02,
        sample.B03,
        sample.B04,
        sample.B08,
        sample.B11,
        sample.B12,
        sample.SCL,
        sample.dataMask
    ];
}}
"""

class S2AutonomousEngine:
    def __init__(self, timeout=60, retries=4):
        self.timeout=timeout
        self.retries=retries
        self.session=requests.Session()

    def _token(self):
        # Workers may be called directly from the CLI, so load the local
        # runtime environment here instead of relying on the long-running
        # service wrapper to have loaded it already.
        from .runtime_config import load_env_file
        load_env_file()
        cid=os.getenv("CDSE_CLIENT_ID")
        secret=os.getenv("CDSE_CLIENT_SECRET")
        if not cid or not secret:
            raise RuntimeError("CDSE_CLIENT_ID and CDSE_CLIENT_SECRET are required")
        for attempt in range(self.retries):
            try:
                r=self.session.post(TOKEN_URL,data={
                    "grant_type":"client_credentials",
                    "client_id":cid,
                    "client_secret":secret,
                },timeout=self.timeout)
                r.raise_for_status()
                return r.json()["access_token"]
            except requests.RequestException:
                if attempt == self.retries-1:
                    raise
        raise RuntimeError("Unable to obtain CDSE token")

    def process_exact_scene(self, scene, bbox, output_path, width=512, height=512):
        """Acquire one Sentinel-2 L2A scene as an eight-band GeoTIFF.

        Band contract:
            1 B02 reflectance
            2 B03 reflectance
            3 B04 reflectance
            4 B08 reflectance
            5 B11 reflectance
            6 B12 reflectance
            7 SCL DN
            8 dataMask DN
        """
        dt = _as_utc(scene.datetime)
        start_time = (dt - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_time = (dt + timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")

        evalscript = """//VERSION=3
function setup() {
  return {
    input: [{
      bands: [
        "B02",
        "B03",
        "B04",
        "B08",
        "B11",
        "B12",
        "SCL",
        "dataMask"
      ],
      units: [
        "REFLECTANCE",
        "REFLECTANCE",
        "REFLECTANCE",
        "REFLECTANCE",
        "REFLECTANCE",
        "REFLECTANCE",
        "DN",
        "DN"
      ]
    }],
    output: {
      bands: 8,
      sampleType: SampleType.FLOAT32
    }
  };
}

function evaluatePixel(sample) {
  return [
    sample.B02,
    sample.B03,
    sample.B04,
    sample.B08,
    sample.B11,
    sample.B12,
    sample.SCL,
    sample.dataMask
  ];
}
"""

        payload = {
            "input": {
                "bounds": {
                    "properties": {
                        "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
                    },
                    "bbox": bbox
                },
                "data": [{
                    "type": "sentinel-2-l2a",
            "processing": {
                "upsampling": "BILINEAR",
                "downsampling": "BILINEAR"
            },
                    "dataFilter": {
                        "timeRange": {
                            "from": start_time,
                            "to": end_time
                        }
                    }
                }]
            },
            "output": {
                "width": width,
                "height": height,
                "responses": [
                    {
                        "identifier": "default",
                        "format": {"type": "image/tiff"}
                    }
                ]
            },
            "evalscript": evalscript
        }

        token = self._token()
        response = self.session.post(
            PROCESS_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "image/tiff"
            },
            timeout=max(self.timeout, 120),
        )

        if not response.ok:
            body = response.text[:8000]
            raise requests.HTTPError(
                f"CDSE Process API {response.status_code}: {body}",
                response=response,
            )

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(response.content)

        provenance = {
            "selected_scene": asdict(scene),
            "process_api": {
                "url": PROCESS_URL,
                "type": "sentinel-2-l2a",
                "bbox": bbox,
                "time_range": {"from": start_time, "to": end_time},
                "width": width,
                "height": height,
                "response_accept": "image/tiff",
                "band_contract": [
                {"index": 1, "name": "B02", "units": "REFLECTANCE"},
                {"index": 2, "name": "B03", "units": "REFLECTANCE"},
                {"index": 3, "name": "B04", "units": "REFLECTANCE"},
                {"index": 4, "name": "B08", "units": "REFLECTANCE"},
                {"index": 5, "name": "B11", "units": "REFLECTANCE"},
                {"index": 6, "name": "B12", "units": "REFLECTANCE"},
                {"index": 7, "name": "SCL", "units": "DN"},
                {"index": 8, "name": "dataMask", "units": "DN"},
            ],
            }
        }

        (out.parent / "process_provenance.json").write_text(
            json.dumps(provenance, indent=2), encoding="utf-8"
        )

        qc = self.validate(out)
        if not qc["valid"]:
            out.unlink(missing_ok=True)
            raise RuntimeError(f"S2 output failed QC: {qc}")

        result = {
            "success": True,
            "sensor": "sentinel-2",
            "scene": asdict(scene),
            "output": str(out),
            "qc": qc,
            "process_provenance": provenance,
        }
        (out.parent / "worker_result.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        return result

    @staticmethod
    def validate(path):
        try:
            with rasterio.open(path) as ds:
                # Earth One v2.3 eight-band Sentinel-2 contract:
                # 1 B02, 2 B03, 3 B04, 4 B08,
                # 5 B11, 6 B12, 7 SCL, 8 dataMask.
                if ds.count != 8:
                    return {
                        "valid": False,
                        "error": f"expected exactly 8 bands, got {ds.count}",
                    }

                spectral_stats = []
                for b in range(1, 7):
                    arr = ds.read(b, masked=True).astype(np.float64)
                    values = arr.compressed()
                    values = values[np.isfinite(values)]

                    if values.size == 0:
                        return {
                            "valid": False,
                            "error": f"band {b} empty",
                        }

                    spectral_stats.append({
                        "band": b,
                        "min": float(values.min()),
                        "max": float(values.max()),
                        "mean": float(values.mean()),
                        "valid_pixels": int(values.size),
                    })

                # Band 7 = SCL.
                scl = ds.read(7).astype(np.float64)
                scl = scl[np.isfinite(scl)]

                if scl.size == 0:
                    return {
                        "valid": False,
                        "error": "SCL band empty",
                    }

                if float(scl.min()) < 0 or float(scl.max()) > 11:
                    return {
                        "valid": False,
                        "error": (
                            "SCL outside expected 0..11 range: "
                            f"min={float(scl.min())}, "
                            f"max={float(scl.max())}"
                        ),
                    }

                # Band 8 = dataMask.
                mask = ds.read(8).astype(np.float64)
                mask = mask[np.isfinite(mask)]

                if mask.size == 0:
                    return {
                        "valid": False,
                        "error": "dataMask band empty",
                    }

                unique_mask = np.unique(mask)

                if not np.all(np.isin(unique_mask, [0, 1])):
                    return {
                        "valid": False,
                        "error": (
                            "dataMask contains values other than 0/1: "
                            f"{unique_mask[:20].tolist()}"
                        ),
                    }

                valid_fraction = float(np.mean(ds.read(8) > 0))

                if valid_fraction <= 0:
                    return {
                        "valid": False,
                        "error": "dataMask contains no valid pixels",
                    }

                return {
                    "valid": True,
                    "width": ds.width,
                    "height": ds.height,
                    "crs": str(ds.crs),
                    "count": ds.count,
                    "band_contract": [
                        "B02",
                        "B03",
                        "B04",
                        "B08",
                        "B11",
                        "B12",
                        "SCL",
                        "dataMask",
                    ],
                    "valid_fraction": valid_fraction,
                    "bands": spectral_stats,
                }
        except Exception as exc:
            return {"valid": False, "error": str(exc)}

    def discover_and_process(self,bbox,start,end,target_date,output_path,max_cloud=50.0):
        scenes=discover_s2(bbox,start,end,max_cloud=max_cloud)
        scene=select_best_s2(scenes,target_date)
        return self.process_exact_scene(scene,bbox,output_path)
