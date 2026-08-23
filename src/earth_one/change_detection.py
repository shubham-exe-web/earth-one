from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import numpy as np
import rasterio
from .raster_utils import normalize_geotiff_profile


@dataclass
class ChangeResult:
    baseline: str
    comparison: str
    output: str
    threshold: float
    changed_fraction: float
    valid_fraction: float
    mean_delta: float | None
    median_delta: float | None
    processor_version: str = "0.5.0"


def detect_index_change(
    baseline_path: str | Path,
    comparison_path: str | Path,
    output_path: str | Path,
    threshold: float = 0.20,
) -> ChangeResult:
    """
    Detect absolute index change between two aligned single-band rasters.

    The result is a float32 delta raster:
        comparison - baseline

    Pixels are flagged as changed where:
        abs(delta) >= threshold

    The threshold is deliberately a parameter, not a universal scientific
    constant. It must be calibrated for the study area, seasonality, sensor
    preprocessing, and research question.
    """
    if threshold <= 0:
        raise ValueError("threshold must be > 0")

    baseline_path = Path(baseline_path)
    comparison_path = Path(comparison_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(baseline_path) as base, rasterio.open(comparison_path) as comp:
        if base.width != comp.width or base.height != comp.height:
            raise ValueError("Baseline and comparison rasters have different dimensions")
        if base.crs != comp.crs:
            raise ValueError("Baseline and comparison rasters have different CRS")
        if base.transform != comp.transform:
            raise ValueError("Baseline and comparison rasters are not on the same grid")

        a = base.read(1).astype(np.float32)
        b = comp.read(1).astype(np.float32)

        valid = np.isfinite(a) & np.isfinite(b)
        delta = np.full(a.shape, np.nan, dtype=np.float32)
        delta[valid] = b[valid] - a[valid]

        changed = valid & (np.abs(delta) >= threshold)

        profile = base.profile.copy()
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
            dst.write(delta, 1)
            dst.set_band_description(1, "INDEX_DELTA")
            dst.update_tags(
                EARTH_ONE_PROCESSOR_VERSION="0.5.0",
                EARTH_ONE_PRODUCT="temporal_change",
                EARTH_ONE_BASELINE=str(baseline_path),
                EARTH_ONE_COMPARISON=str(comparison_path),
                EARTH_ONE_THRESHOLD=str(threshold),
            )

        values = delta[valid]

        return ChangeResult(
            baseline=str(baseline_path),
            comparison=str(comparison_path),
            output=str(output_path),
            threshold=threshold,
            changed_fraction=float(changed.sum() / valid.sum()) if valid.any() else 0.0,
            valid_fraction=float(valid.mean()),
            mean_delta=float(values.mean()) if values.size else None,
            median_delta=float(np.median(values)) if values.size else None,
        )


def write_change_result(result: ChangeResult, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(result), indent=2),
        encoding="utf-8",
    )
