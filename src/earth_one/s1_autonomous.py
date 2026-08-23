from __future__ import annotations

"""Autonomous Sentinel-1 scene matching, on-demand processing, and QC.

This module is deliberately stricter than the legacy s1_process.py:
- discover scenes first
- match by relative orbit / direction / mode / polarization / platform
- select a real product ID before processing
- request only the frozen AOI
- validate raster values immediately
- fail closed on empty/constant outputs
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import math
import os
import re
import tarfile
import io
from typing import Any

import numpy as np
import requests
import rasterio


TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOG_URL = "https://sh.dataspace.copernicus.eu/catalog/v1/search"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/process/v1"


@dataclass(frozen=True)
class S1Scene:
    id: str
    product_id: str
    datetime: str
    platform: str | None
    orbit_direction: str | None
    relative_orbit: int | None
    absolute_orbit: int | None
    acquisition_mode: str | None
    polarization: str | None
    slice_number: int | None
    bbox: list[float] | None
    geometry: dict[str, Any] | None
    properties: dict[str, Any]


def _first(props: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in props and props[key] is not None:
            return props[key]
    return None


def _normalize_polarization(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip().upper().replace(" ", "").replace(",", "+").replace("/", "+")
    if s in {"DV", "VV+VH", "VH+VV"}:
        return "DV"
    if s in {"SV", "VV"}:
        return "SV"
    if s in {"SH", "HH"}:
        return "SH"
    if s in {"DH", "HH+HV", "HV+HH"}:
        return "DH"
    return str(value)


def _parse_product(product_id: str) -> tuple[int | None, int | None, int | None]:
    """Return absolute orbit, derived relative orbit, and slice when available.

    Sentinel-1 product IDs contain absolute orbit. For S1A, the operational
    relative-orbit mapping is (absolute - 73) mod 175 + 1. For other platforms,
    the relative orbit must come from metadata when available.
    """
    parts = product_id.split("_")
    absolute = None
    for p in parts:
        if p.isdigit() and 5 <= len(p) <= 7:
            # The absolute orbit is the numeric token immediately after the
            # sensing end timestamp in normal S1 IDs. Avoid treating dates as orbit.
            if 1000 <= int(p) <= 99999:
                absolute = int(p)
    # Safer regex for the canonical S1 product name.
    m = re.search(r"_([0-9]{6})_[0-9A-F]{6}_[0-9A-F]{4}(?:\.SAFE)?$", product_id)
    if m:
        absolute = int(m.group(1))
    platform = product_id[:3]
    relative = None
    if absolute is not None and platform == "S1A":
        relative = (absolute - 73) % 175 + 1
    return absolute, relative, None


def normalize_scene(item: dict[str, Any]) -> S1Scene:
    props = item.get("properties", {})
    product_id = (
        props.get("s1:product_id")
        or props.get("productIdentifier")
        or item.get("id")
    )
    absolute, derived_relative, derived_slice = _parse_product(product_id)
    relative = _first(props, "s1:relative_orbit", "relativeOrbitNumber", "orbitNumber")
    if relative is None:
        relative = derived_relative
    slice_number = _first(props, "s1:slice_number", "sliceNumber", "slice_number")
    if slice_number is not None:
        try:
            slice_number = int(slice_number)
        except (TypeError, ValueError):
            slice_number = None
    return S1Scene(
        id=item.get("id", product_id),
        product_id=product_id,
        datetime=props.get("datetime") or props.get("start_datetime"),
        platform=_first(props, "platform", "constellation") or product_id[:3],
        orbit_direction=_first(props, "sat:orbit_state", "orbitDirection"),
        relative_orbit=int(relative) if relative is not None else None,
        absolute_orbit=absolute,
        acquisition_mode=_first(props, "sar:instrument_mode", "acquisitionMode"),
        polarization=_normalize_polarization(_first(props, "s1:polarization", "polarization")),
        slice_number=slice_number,
        bbox=item.get("bbox"),
        geometry=item.get("geometry"),
        properties=props,
    )


class S1AutonomousEngine:
    def __init__(self, timeout: int = 60, retries: int = 4, backoff: float = 2.0):
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.session = requests.Session()
        # Do not set Accept header for CDSE Catalog deployment

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        last = None
        for attempt in range(self.retries):
            try:
                r = self.session.request(method, url, timeout=self.timeout, **kwargs)
                r.raise_for_status()
                return r
            except requests.RequestException as exc:
                last = exc
                if attempt == self.retries - 1:
                    raise
                import time
                time.sleep(self.backoff ** attempt)
        raise RuntimeError(f"CDSE request failed after {self.retries} attempts: {last}") from last

    def discover(self, bbox: list[float], start: str, end: str, limit: int = 100) -> list[S1Scene]:
        # Catalog API requires OAuth authentication. The previous S1 worker
        # attempted the search before obtaining a token, which caused the live
        # Catalog request to fail. Obtain a token first and send it explicitly.
        token = self._token()
        payload = {
            "collections": ["sentinel-1-grd"],
            "bbox": bbox,
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
            "limit": limit,
        }
        # Follow the current CDSE Catalog POST contract closely. The official
        # examples require Authorization and Content-Type; do not force an
        # Accept media type because some deployments may reject it with 406.
        data = self._request(
            "POST",
            CATALOG_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
        ).json()
        scenes = [normalize_scene(item) for item in data.get("features", [])]
        # Deterministic ordering: acquisition time, then product id.
        return sorted(scenes, key=lambda s: (s.datetime or "", s.product_id))

    @staticmethod
    def match_pair(
        before: list[S1Scene],
        after: list[S1Scene],
        preferred_relative_orbit: int | None = None,
        max_days: int = 400,
    ) -> tuple[S1Scene, S1Scene]:
        """Choose the strongest geometry-matched temporal pair.

        Hard requirements: same orbit direction, same IW mode, same platform
        where possible, and same relative orbit. Polarization must overlap.
        Same slice is a strong bonus when available.
        """
        candidates: list[tuple[float, S1Scene, S1Scene]] = []
        for a in before:
            for b in after:
                if not a.datetime or not b.datetime:
                    continue
                try:
                    da = datetime.fromisoformat(a.datetime.replace("Z", "+00:00"))
                    db = datetime.fromisoformat(b.datetime.replace("Z", "+00:00"))
                except ValueError:
                    continue
                gap = abs((db - da).total_seconds()) / 86400.0
                if gap > max_days:
                    continue
                if a.orbit_direction != b.orbit_direction:
                    continue
                if a.acquisition_mode != b.acquisition_mode:
                    continue
                if a.relative_orbit is None or b.relative_orbit is None:
                    continue
                if a.relative_orbit != b.relative_orbit:
                    continue
                # Require dual-pol for the current production target.
                if a.polarization != "DV" or b.polarization != "DV":
                    continue
                pol_bonus = 2.0
                platform_bonus = 1.0 if a.platform == b.platform else 0.0
                slice_bonus = 2.0 if (a.slice_number is not None and a.slice_number == b.slice_number) else 0.0
                orbit_bonus = 3.0 if preferred_relative_orbit and a.relative_orbit == preferred_relative_orbit else 0.0
                # Prefer acquisitions near the same day-of-year while keeping
                # the one-year interval explicit.
                score = pol_bonus + platform_bonus + slice_bonus + orbit_bonus - abs(gap - 365.25) / 365.25
                candidates.append((score, a, b))
        if not candidates:
            raise RuntimeError("No geometry-matched Sentinel-1 pair found")
        candidates.sort(key=lambda x: (-x[0], x[1].product_id, x[2].product_id))
        return candidates[0][1], candidates[0][2]

    def _token(self) -> str:
        # Direct worker/CLI execution must load the local runtime environment.
        from .runtime_config import load_env_file
        load_env_file()
        cid = os.getenv("CDSE_CLIENT_ID")
        secret = os.getenv("CDSE_CLIENT_SECRET")
        if not cid or not secret:
            raise RuntimeError("CDSE_CLIENT_ID and CDSE_CLIENT_SECRET are required")
        r = self._request("POST", TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": cid,
            "client_secret": secret,
        })
        return r.json()["access_token"]

    @staticmethod
    def _evalscript(polarizations: list[str]) -> str:
        bands = ", ".join(f'"{p}"' for p in polarizations)
        outs = ", ".join(f"{p}: samples.{p}" for p in polarizations)
        return f'''//VERSION=3
function setup() {{
  return {{
    input: [{bands}],
    output: {{ bands: {len(polarizations)}, sampleType: "FLOAT32" }}
  }};
}}
function evaluatePixel(samples) {{
  return [{outs}];
}}
'''

    def process_exact_scene(
        self,
        scene: S1Scene,
        bbox: list[float],
        output_path: str | Path,
        width: int = 1024,
        height: int = 1024,
        polarizations: list[str] | None = None,
        backscatter: str = "GAMMA0_TERRAIN",
    ) -> dict[str, Any]:
        pols = polarizations or ["VV", "VH"]
        if not pols:
            raise ValueError("At least one polarization is required")
        if backscatter == "GAMMA0_TERRAIN":
            processing = {"backCoeff": "GAMMA0_TERRAIN", "orthorectify": "true", "demInstance": "COPERNICUS_30"}
        else:
            processing = {"backCoeff": backscatter, "orthorectify": "false"}
        dt = datetime.fromisoformat(scene.datetime.replace("Z", "+00:00"))
        start = (dt - timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = (dt + timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        inputs = ", ".join(repr(p) for p in pols)
        nbands = len(pols) + 1
        returns = ", ".join(f"s.{p}" for p in pols)
        evalscript = f'''//VERSION=3
function setup() {{
  return {{
    input: [{inputs}, "dataMask"],
    output: {{ id: "default", bands: {nbands}, sampleType: "FLOAT32" }},
    mosaicking: Mosaicking.ORBIT
  }};
}}
function updateOutputMetadata(scenes, inputMetadata, outputMetadata) {{
  outputMetadata.userData = {{ "scenes": scenes.orbits }};
}}
function evaluatePixel(samples) {{
  var s = samples[0];
  return [{returns}, s.dataMask];
}}
'''
        payload = {
            "input": {"bounds": {"bbox": bbox, "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}},
                      "data": [{"type": "sentinel-1-grd", "dataFilter": {
                          "timeRange": {"from": start, "to": end},
                          "acquisitionMode": "IW",
                          "orbitDirection": (scene.orbit_direction or "DESCENDING").upper(),
                          "polarization": scene.polarization or "DV",
                      }, "processing": processing}]},
            "output": {"width": width, "height": height, "responses": [
                {"identifier": "default", "format": {"type": "image/tiff", "compression": "DEFLATE"}},
                {"identifier": "userdata", "format": {"type": "application/json"}},
            ]},
            "evalscript": evalscript,
        }
        token = self._token()
        r = self._request("POST", PROCESS_URL, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/x-tar"}, json=payload)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        userdata: dict[str, Any] = {}
        try:
            with tarfile.open(fileobj=io.BytesIO(r.content)) as tf:
                members = tf.getmembers()
                tif_member = next((m for m in members if m.name.endswith("default.tif")), None)
                if tif_member is None:
                    tif_member = next((m for m in members if m.name.lower().endswith((".tif", ".tiff"))), None)
                if tif_member is None:
                    raise RuntimeError(f"Process response contained no TIFF; members={[m.name for m in members]}")
                extracted = tf.extractfile(tif_member)
                if extracted is None:
                    raise RuntimeError("Unable to extract Process API TIFF")
                out.write_bytes(extracted.read())
                user_member = next((m for m in members if m.name.endswith("userdata.json")), None)
                if user_member is not None:
                    f = tf.extractfile(user_member)
                    if f is not None:
                        userdata = json.load(f)
        except tarfile.TarError as exc:
            if r.headers.get("Content-Type", "").lower().startswith("image/tiff"):
                out.write_bytes(r.content)
            else:
                raise RuntimeError(f"Unexpected Process API response: {r.headers.get('Content-Type')}") from exc
        expected = scene.product_id.replace(".SAFE", "")
        if expected not in json.dumps(userdata, sort_keys=True):
            out.unlink(missing_ok=True)
            raise RuntimeError("Process API provenance mismatch: selected product not present in returned metadata")
        qc = validate_multiband_raster(out, expected_bands=len(pols))
        if not qc["valid"]:
            out.unlink(missing_ok=True)
            raise RuntimeError(f"S1 output failed QC: {qc}")
        return {"scene": asdict(scene), "output": str(out), "qc": qc, "backscatter": backscatter, "process_provenance": userdata}


def validate_multiband_raster(path: str | Path, expected_bands: int | None = None) -> dict[str, Any]:
    """Fail closed on empty, constant, non-finite, or unreadable raster bands."""
    p = Path(path)
    try:
        with rasterio.open(p) as ds:
            if expected_bands is not None and ds.count < expected_bands:
                return {"valid": False, "error": f"expected at least {expected_bands} bands, got {ds.count}"}
            bands=[]
            for band in range(1, ds.count + 1):
                count=0; vmin=math.inf; vmax=-math.inf; total=0.0
                for _, window in ds.block_windows(band):
                    arr=ds.read(band, window=window, masked=True).astype(np.float64)
                    vals=arr.compressed() if np.ma.isMaskedArray(arr) else arr.ravel()
                    vals=vals[np.isfinite(vals)]
                    if vals.size==0: continue
                    count += int(vals.size); vmin=min(vmin,float(vals.min())); vmax=max(vmax,float(vals.max())); total += float(vals.sum())
                bands.append({"band":band,"valid":bool(count>0 and vmin<vmax and not (vmin==0 and vmax==0)),"valid_pixels":count,"min":None if vmin==math.inf else vmin,"max":None if vmax==-math.inf else vmax,"mean":(total/count if count else None)})
            valid=all(b["valid"] for b in bands[:expected_bands or ds.count])
            result={"valid":valid,"width":ds.width,"height":ds.height,"count":ds.count,"crs":str(ds.crs),"nodata":ds.nodata,"bands":bands}
            if bands:
                result["min"]=bands[0]["min"]; result["max"]=bands[0]["max"]; result["mean"]=bands[0]["mean"]
            return result
    except Exception as exc:
        return {"valid":False,"error":str(exc)}


def validate_raster(path: str | Path) -> dict[str, Any]:
    """Backward-compatible single-band QC wrapper."""
    return validate_multiband_raster(path, expected_bands=1)


def run_matched_pair(
    bbox: list[float],
    before_start: str,
    before_end: str,
    after_start: str,
    after_end: str,
    output_dir: str | Path,
    preferred_relative_orbit: int | None = None,
    width: int = 1024,
    height: int = 1024,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Discover and match a real S1 temporal pair; optionally stop before processing."""
    engine = S1AutonomousEngine()
    before = engine.discover(bbox, before_start, before_end)
    after = engine.discover(bbox, after_start, after_end)
    a, b = engine.match_pair(before, after, preferred_relative_orbit=preferred_relative_orbit)
    if dry_run:
        return {
            "status": "matched_pair_only",
            "bbox": bbox,
            "before_candidates": len(before),
            "after_candidates": len(after),
            "before": asdict(a),
            "after": asdict(b),
            "matching": {
                "relative_orbit": a.relative_orbit,
                "orbit_direction": a.orbit_direction,
                "acquisition_mode": a.acquisition_mode,
                "platform": a.platform,
                "polarization": a.polarization,
                "slice_number_before": a.slice_number,
                "slice_number_after": b.slice_number,
            },
        }
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    a_result = engine.process_exact_scene(a, bbox, out / "before_vv_vh.tif", width, height)
    b_result = engine.process_exact_scene(b, bbox, out / "after_vv_vh.tif", width, height)
    manifest = {
        "schema": "earth_one_s1_matched_pair_v1.1",
        "bbox": bbox,
        "before": a_result,
        "after": b_result,
        "matching": {
            "relative_orbit": a.relative_orbit,
            "orbit_direction": a.orbit_direction,
            "acquisition_mode": a.acquisition_mode,
            "platform": a.platform,
            "polarization": a.polarization,
            "slice_number_before": a.slice_number,
            "slice_number_after": b.slice_number,
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
