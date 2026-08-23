from __future__ import annotations

from pathlib import Path
import numpy as np
import rasterio
from .raster_utils import normalize_geotiff_profile
from rasterio.warp import reproject
from rasterio.enums import Resampling


def build_optical_sar_stack(
    ndvi_path: str | Path,
    sar_vv_path: str | Path,
    sar_vh_path: str | Path | None,
    output_path: str | Path,
) -> dict:
    """
    Co-register Sentinel-1-derived rasters to the NDVI reference grid and build
    a compact disturbance feature stack.

    Output:
      band 1: NDVI
      band 2: VV
      band 3: VH (if supplied)

    SAR values are assumed to already be in a physically chosen backscatter
    coefficient and common projection. The function only performs spatial
    harmonization, not SAR calibration.
    """
    ndvi_path = Path(ndvi_path)
    sar_vv_path = Path(sar_vv_path)
    sar_vh_path = Path(sar_vh_path) if sar_vh_path else None
    output_path = Path(output_path)

    with rasterio.open(ndvi_path) as ref:
        profile = ref.profile.copy()
        ref_arr = ref.read(1).astype(np.float32)
        ref_crs = ref.crs
        ref_transform = ref.transform
        height, width = ref.height, ref.width

    arrays = [ref_arr]
    names = ["NDVI"]

    def align(path):
        with rasterio.open(path) as src:
            dst = np.full((height, width), np.nan, dtype=np.float32)
            reproject(
                source=src.read(1).astype(np.float32),
                destination=dst,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=ref_transform,
                dst_crs=ref_crs,
                resampling=Resampling.bilinear,
                dst_nodata=np.nan,
            )
            return dst

    arrays.append(align(sar_vv_path))
    names.append("VV")

    if sar_vh_path:
        arrays.append(align(sar_vh_path))
        names.append("VH")

    stack = np.stack(arrays, axis=0)

    profile.update(
        count=len(arrays),
        dtype="float32",
        nodata=np.nan,
        compress="deflate",
        predictor=3,
        tiled=True,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    profile = normalize_geotiff_profile(
        profile,
        width=profile["width"],
        height=profile["height"],
    )

    with rasterio.open(output_path, "w", **profile) as dst:
        for i, name in enumerate(names, 1):
            dst.write(stack[i - 1], i)
            dst.set_band_description(i, name)
        dst.update_tags(
            EARTH_ONE_PROCESSOR_VERSION="0.6.0",
            EARTH_ONE_PRODUCT="optical_sar_feature_stack",
            EARTH_ONE_REFERENCE_GRID=str(ndvi_path),
        )

    return {
        "output": str(output_path),
        "bands": names,
        "width": width,
        "height": height,
        "valid_fraction": float(np.all(np.isfinite(stack), axis=0).mean()),
        "processor_version": "0.6.0",
    }
