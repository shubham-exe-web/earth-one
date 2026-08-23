
from __future__ import annotations

"""Earth One v1.4 multimodal Sentinel-1 + Sentinel-2 fusion.

The fusion layer is deliberately conservative:
- every input must be readable and non-empty
- the target grid is chosen explicitly, never implicitly
- rasters are reprojected with an explicit resampling rule
- provenance is recorded for every feature
- all-zero / constant / invalid inputs are rejected before fusion
"""

from dataclasses import dataclass, asdict
from pathlib import Path
import json
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import reproject
from rasterio.enums import Resampling


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    path: str
    source: str
    band: int = 1
    resampling: str = "average"


def _resampling(name: str) -> Resampling:
    table = {
        "nearest": Resampling.nearest,
        "average": Resampling.average,
        "bilinear": Resampling.bilinear,
    }
    if name not in table:
        raise ValueError(f"Unsupported resampling: {name}")
    return table[name]


def inspect_feature(path: str | Path, band: int = 1) -> dict[str, Any]:
    p = Path(path)
    try:
        with rasterio.open(p) as ds:
            if band < 1 or band > ds.count:
                return {
                    "valid": False,
                    "path": str(p),
                    "error": f"band={band} outside raster band range 1..{ds.count}",
                }

            arr = ds.read(band, masked=True).astype(np.float64)
            vals = arr.compressed() if np.ma.isMaskedArray(arr) else arr.ravel()
            vals = vals[np.isfinite(vals)]
            if vals.size == 0:
                return {
                    "valid": False,
                    "path": str(p),
                    "error": "no finite pixels",
                }
            vmin = float(vals.min())
            vmax = float(vals.max())
            return {
                "valid": bool(vmin < vmax),
                "path": str(p),
                "crs": str(ds.crs),
                "width": ds.width,
                "height": ds.height,
                "count": ds.count,
                "nodata": ds.nodata,
                "min": vmin,
                "max": vmax,
                "mean": float(vals.mean()),
                "valid_pixels": int(vals.size),
            }
    except Exception as exc:
        return {"valid": False, "path": str(p), "error": str(exc)}


def build_multimodal_stack(
    features: list[FeatureSpec],
    output: str | Path,
    target_feature: str,
    result_json: str | Path | None = None,
) -> dict[str, Any]:
    if not features:
        raise ValueError("At least one feature is required.")

    by_name = {f.name: f for f in features}
    if target_feature not in by_name:
        raise ValueError(f"target_feature={target_feature!r} not found")

    inspections = {
        f.name: inspect_feature(f.path, f.band)
        for f in features
    }
    bad = {k: v for k, v in inspections.items() if not v.get("valid")}
    if bad:
        raise ValueError(f"Input feature QC failed: {bad}")

    ref_path = Path(by_name[target_feature].path)
    with rasterio.open(ref_path) as ref:
        profile = ref.profile.copy()
        width, height = ref.width, ref.height
        transform, crs = ref.transform, ref.crs

        arrays = []
        output_bands = []

        for spec in features:
            with rasterio.open(spec.path) as ds:
                if spec.band < 1 or spec.band > ds.count:
                    raise ValueError(
                        f"{spec.name} requests band {spec.band}, "
                        f"but {spec.path} has {ds.count} band(s)"
                    )

                dst = np.full((height, width), np.nan, dtype=np.float32)
                reproject(
                    source=rasterio.band(ds, spec.band),
                    destination=dst,
                    src_transform=ds.transform,
                    src_crs=ds.crs,
                    dst_transform=transform,
                    dst_crs=crs,
                    src_nodata=ds.nodata,
                    dst_nodata=np.nan,
                    resampling=_resampling(spec.resampling),
                )
                arrays.append(dst)
                output_bands.append(spec.name)

    profile.update(
        driver="GTiff",
        dtype="float32",
        count=len(arrays),
        compress="deflate",
        predictor=3,
        tiled=True,
        BIGTIFF="IF_SAFER",
        nodata=np.nan,
    )
    # Tiled GeoTIFF blocks must use dimensions divisible by 16.
    if width >= 16 and height >= 16:
        profile.update(blockxsize=min(256, max(16, (width // 16) * 16)),
                       blockysize=min(256, max(16, (height // 16) * 16)))
    else:
        profile.update(tiled=False)

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", **profile) as dst:
        for idx, array in enumerate(arrays, start=1):
            dst.write(array.astype(np.float32), idx)
            dst.set_band_description(idx, output_bands[idx - 1])

    # Validate the final stack before acceptance.
    with rasterio.open(out) as ds:
        band_qc = []
        for i in range(1, ds.count + 1):
            vals = ds.read(i, masked=True).compressed().astype(np.float64)
            vals = vals[np.isfinite(vals)]
            if vals.size == 0:
                raise ValueError(f"Output stack band {i} has no finite pixels")
            band_qc.append({
                "band": i,
                "name": ds.descriptions[i - 1],
                "min": float(vals.min()),
                "max": float(vals.max()),
                "mean": float(vals.mean()),
                "valid_pixels": int(vals.size),
                "valid": bool(vals.min() < vals.max()),
            })

    result = {
        "status": "accepted",
        "output": str(out),
        "target_feature": target_feature,
        "grid": {
            "width": width,
            "height": height,
            "crs": str(crs),
            "transform": tuple(transform),
        },
        "features": [asdict(f) for f in features],
        "input_qc": inspections,
        "output_qc": band_qc,
    }

    if result_json:
        rp = Path(result_json)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(result, indent=2), encoding="utf-8")

    return result
