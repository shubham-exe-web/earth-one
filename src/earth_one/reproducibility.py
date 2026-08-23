
from __future__ import annotations
from pathlib import Path
import json
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import reproject
from rasterio.enums import Resampling


def _read_to_grid(src_path, ref_ds):
    with rasterio.open(src_path) as src:
        window = from_bounds(*ref_ds.bounds, transform=src.transform).round_offsets().round_lengths()
        arr = src.read(1, window=window, masked=True).astype(np.float64)
        out = np.full((ref_ds.height, ref_ds.width), np.nan, dtype=np.float64)
        src_arr = arr.filled(np.nan)
        reproject(
            source=src_arr,
            destination=out,
            src_transform=src.window_transform(window),
            src_crs=src.crs,
            dst_transform=ref_ds.transform,
            dst_crs=ref_ds.crs,
            src_nodata=np.nan,
            dst_nodata=np.nan,
            resampling=Resampling.nearest,
        )
        return out


def verify_change_reconstruction(
    baseline: str | Path,
    comparison: str | Path,
    archived_delta: str | Path,
    tolerance: float = 1e-6,
    output: str | Path | None = None,
):
    """Recompute a stored change raster on its own grid.

    This deliberately permits the archived delta to be a spatial subset of
    the source products. It is therefore suitable for Earth One products
    generated on a fixed AOI inside a larger source raster.
    """
    with rasterio.open(archived_delta) as d:
        if d.crs is None:
            raise ValueError("Archived delta has no CRS")
        with rasterio.open(baseline) as b, rasterio.open(comparison) as c:
            if b.crs != c.crs or b.crs != d.crs:
                raise ValueError("CRS mismatch")
            av = _read_to_grid(baseline, d)
            cv = _read_to_grid(comparison, d)
            dv = d.read(1, masked=True).astype(np.float64).filled(np.nan)
            valid = np.isfinite(av) & np.isfinite(cv) & np.isfinite(dv)
            if not valid.any():
                raise ValueError("No common valid pixels on archived-delta grid")
            expected = cv - av
            err = expected - dv
            e = err[valid]
            result = {
                "valid_pixels": int(valid.sum()),
                "rmse": float(np.sqrt(np.mean(e * e))),
                "mae": float(np.mean(np.abs(e))),
                "max_abs_error": float(np.max(np.abs(e))),
                "tolerance": tolerance,
                "pass": bool(np.max(np.abs(e)) <= tolerance),
                "target_grid": {
                    "width": d.width,
                    "height": d.height,
                    "crs": str(d.crs),
                    "bounds": [d.bounds.left, d.bounds.bottom, d.bounds.right, d.bounds.top],
                },
            }
    if output:
        p = Path(output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result, indent=2))
    return result
