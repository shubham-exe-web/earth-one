from __future__ import annotations

from pathlib import Path
import numpy as np
import rasterio
from .raster_utils import normalize_geotiff_profile


def temporal_median(
    input_paths: list[str | Path],
    output_path: str | Path,
) -> dict:
    """
    Pixel-wise median composite for already aligned single-band rasters.

    Median is used as a robust baseline reducer. It does not itself remove all
    phenological or atmospheric effects, so the caller must construct sensible
    temporal windows.
    """
    if len(input_paths) < 2:
        raise ValueError("At least two observations are required for a temporal composite")

    input_paths = [Path(p) for p in input_paths]
    output_path = Path(output_path)

    with rasterio.open(input_paths[0]) as ref:
        profile = ref.profile.copy()
        reference_shape = (ref.height, ref.width)
        reference_crs = ref.crs
        reference_transform = ref.transform

    arrays = []
    for path in input_paths:
        with rasterio.open(path) as ds:
            if (ds.height, ds.width) != reference_shape:
                raise ValueError(f"Grid mismatch: {path}")
            if ds.crs != reference_crs or ds.transform != reference_transform:
                raise ValueError(f"CRS/transform mismatch: {path}")
            arrays.append(ds.read(1).astype(np.float32))

    stack = np.stack(arrays, axis=0)
    composite = np.nanmedian(stack, axis=0).astype(np.float32)

    profile.update(
        count=1,
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
        dst.write(composite, 1)
        dst.set_band_description(1, "TEMPORAL_MEDIAN")
        dst.update_tags(
            EARTH_ONE_PROCESSOR_VERSION="0.6.0",
            EARTH_ONE_PRODUCT="temporal_median",
            EARTH_ONE_INPUT_COUNT=str(len(input_paths)),
        )

    return {
        "output": str(output_path),
        "inputs": [str(p) for p in input_paths],
        "valid_fraction": float(np.isfinite(composite).mean()),
        "processor_version": "0.6.0",
    }
