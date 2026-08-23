from __future__ import annotations

from pathlib import Path
import numpy as np
import rasterio
from .raster_utils import normalize_geotiff_profile


def confidence_to_uncertainty(
    confidence_path: str | Path,
    uncertainty_path: str | Path,
) -> dict:
    """
    Convert calibrated confidence to an uncertainty score:

        uncertainty = 1 - calibrated confidence

    This is an operational uncertainty indicator, not a physical error bar.
    """
    with rasterio.open(confidence_path) as ds:
        confidence = ds.read(1).astype(np.float32)
        profile = ds.profile.copy()

    valid = np.isfinite(confidence)
    uncertainty = np.full(confidence.shape, np.nan, dtype=np.float32)
    uncertainty[valid] = 1.0 - np.clip(confidence[valid], 0.0, 1.0)

    uncertainty_path = Path(uncertainty_path)
    uncertainty_path.parent.mkdir(parents=True, exist_ok=True)

    profile.update(
        count=1,
        dtype="float32",
        nodata=np.nan,
        compress="deflate",
        predictor=3,
        tiled=True,
    )

    profile = normalize_geotiff_profile(
        profile,
        width=profile["width"],
        height=profile["height"],
    )

    with rasterio.open(uncertainty_path, "w", **profile) as dst:
        dst.write(uncertainty, 1)
        dst.set_band_description(1, "MODEL_UNCERTAINTY")
        dst.update_tags(
            EARTH_ONE_PROCESSOR_VERSION="0.8.0",
            EARTH_ONE_PRODUCT="model_uncertainty_indicator",
            EARTH_ONE_INTERPRETATION="1 - calibrated confidence; not a physical error bar",
        )

    return {
        "output": str(uncertainty_path),
        "valid_fraction": float(valid.mean()),
        "mean_uncertainty": float(np.nanmean(uncertainty)) if valid.any() else None,
        "processor_version": "0.8.0",
    }
