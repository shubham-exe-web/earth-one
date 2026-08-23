from __future__ import annotations

from pathlib import Path
import numpy as np
import rasterio
from .raster_utils import normalize_geotiff_profile


def score_disturbance_candidates(
    change_path: str | Path,
    output_path: str | Path,
    threshold: float = 0.20,
) -> dict:
    """
    Convert absolute index change into a normalized 0-1 candidate score.

    This is an evidence score, not a classifier and not a probability.
    The scientific event classifier comes later after labeled validation data
    and multimodal features are available.
    """
    if threshold <= 0:
        raise ValueError("threshold must be > 0")

    with rasterio.open(change_path) as ds:
        delta = ds.read(1).astype(np.float32)
        profile = ds.profile.copy()

    valid = np.isfinite(delta)
    score = np.full(delta.shape, np.nan, dtype=np.float32)
    score[valid] = np.clip(np.abs(delta[valid]) / threshold, 0, 1)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

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

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(score, 1)
        dst.set_band_description(1, "DISTURBANCE_EVIDENCE_SCORE")
        dst.update_tags(
            EARTH_ONE_PROCESSOR_VERSION="0.6.0",
            EARTH_ONE_PRODUCT="disturbance_candidate_score",
            EARTH_ONE_THRESHOLD=str(threshold),
            EARTH_ONE_INTERPRETATION="evidence_score_not_probability",
        )

    return {
        "output": str(output_path),
        "valid_fraction": float(valid.mean()),
        "mean_score": float(np.nanmean(score)) if valid.any() else None,
        "high_evidence_fraction": float((score[valid] >= 1).mean()) if valid.any() else 0.0,
        "processor_version": "0.6.0",
    }
