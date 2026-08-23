from __future__ import annotations

import os
from pathlib import Path
import requests


TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/process/v1"


def _token() -> str:
    client_id = os.getenv("CDSE_CLIENT_ID")
    client_secret = os.getenv("CDSE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "CDSE_CLIENT_ID and CDSE_CLIENT_SECRET are required for Sentinel-1 Process API."
        )
    r = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def build_s1_request(
    bbox: list[float],
    start: str,
    end: str,
    width: int,
    height: int,
    polarizations: list[str] | None = None,
    backscatter: str = "GAMMA0_TERRAIN",
    orthorectify: bool = True,
    dem: str = "COPERNICUS_30",
    speckle_filter: dict | None = None,
) -> dict:
    pols = polarizations or ["VV", "VH"]

    invalid = set(pols) - {"VV", "VH", "HH", "HV"}
    if invalid:
        raise ValueError(f"Unsupported Sentinel-1 polarizations: {sorted(invalid)}")

    if backscatter not in {
        "BETA0",
        "SIGMA0_ELLIPSOID",
        "GAMMA0_ELLIPSOID",
        "GAMMA0_TERRAIN",
    }:
        raise ValueError("Unsupported Sentinel-1 backscatter coefficient")

    if backscatter == "GAMMA0_TERRAIN" and not orthorectify:
        raise ValueError("GAMMA0_TERRAIN requires orthorectification")

    processing = {
        "backCoeff": backscatter,
        "orthorectify": "TRUE" if orthorectify else "FALSE",
        "demInstance": dem,
    }
    if speckle_filter:
        processing["speckleFilter"] = speckle_filter

    bands = pols

    return {
        "input": {
            "bounds": {
                "bbox": bbox,
                "properties": {
                    "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
                },
            },
            "data": [{
                "type": "sentinel-1-grd",
                "dataFilter": {
                    "timeRange": {
                        "from": f"{start}T00:00:00Z",
                        "to": f"{end}T23:59:59Z",
                    }
                },
                "processing": processing,
            }],
        },
        "output": {
            "width": width,
            "height": height,
            "responses": [{
                "identifier": "default",
                "format": {
                    "type": "image/tiff",
                    "compression": "DEFLATE",
                },
            }],
        },
        "evalscript": _evalscript(bands),
    }


def _evalscript(bands: list[str]) -> str:
    inputs = ", ".join(f'"{b}"' for b in bands)
    outputs = ", ".join(f"{b}: samples.{b}" for b in bands)
    return f"""//VERSION=3
function setup() {{
  return {{
    input: [{inputs}],
    output: {{
      bands: {len(bands)},
      sampleType: "FLOAT32"
    }}
  }};
}}

function evaluatePixel(samples) {{
  return [{outputs}];
}}
"""


def request_s1(
    bbox: list[float],
    start: str,
    end: str,
    output_path: str | Path,
    width: int = 512,
    height: int = 512,
    polarizations: list[str] | None = None,
    backscatter: str = "GAMMA0_TERRAIN",
) -> dict:
    payload = build_s1_request(
        bbox=bbox,
        start=start,
        end=end,
        width=width,
        height=height,
        polarizations=polarizations,
        backscatter=backscatter,
    )
    token = _token()
    response = requests.post(
        PROCESS_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=300,
    )
    response.raise_for_status()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)

    return {
        "status": "downloaded",
        "output": str(output_path),
        "sensor": "sentinel-1",
        "polarizations": polarizations or ["VV", "VH"],
        "backscatter": backscatter,
        "orthorectified": backscatter == "GAMMA0_TERRAIN",
        "processor_version": "0.6.0",
    }
