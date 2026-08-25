from __future__ import annotations

"""Drought Module 3 Real Leave-Out Optical Climatology & Multi-Year Anomaly Engine (Phase 28).

Provides:
- Real Sentinel-2 Historical Baseline Acquisition across multi-year temporal frameworks.
- Strict Leave-Target-Out Climatology Guardrail (eval year strictly excluded from baseline statistics).
- Pixel-level standardized vegetation anomaly (z-score) and Vegetation Condition Index (VCI) computation.
- Optical Observability and Quality Assurance integration across the historical stack.
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from pyproj import Transformer

from .features import compute_ndvi, compute_evi, compute_ndre, compute_ndwi
from .spatial_harmonization import TargetAnalysisGrid
from .external_acquisition import (
    STACDiscoveryEngine,
    ExternalSatelliteAcquisitionSession,
    compute_scl_quality_distribution,
    SCLQualityDistribution,
)
from .data_staging import compute_file_sha256, write_geotiff_raster


@dataclass
class HistoricalVegetationCompositeRecord:
    """Quality-controlled monthly vegetation index composite from a genuine satellite observation."""
    year: int
    month: int
    stac_item_id: str
    acquisition_datetime_utc: str
    cloud_cover_pct: float
    scl_observability_score: float
    valid_pixel_pct: float
    mean_ndvi: float
    mean_evi: float
    mean_ndre: float
    mean_ndwi: float
    ndvi_grid: np.ndarray
    evi_grid: np.ndarray
    ndre_grid: np.ndarray
    ndwi_grid: np.ndarray


@dataclass
class LeaveOneOutClimatologyResult:
    """Leave-target-out historical climatology distribution and target evaluation anomalies."""
    target_year: int
    target_month: int
    baseline_years: list[int]
    excluded_years: list[int]
    mean_baseline_ndvi: np.ndarray
    std_baseline_ndvi: np.ndarray
    min_baseline_ndvi: np.ndarray
    max_baseline_ndvi: np.ndarray
    target_ndvi: np.ndarray
    target_evi: np.ndarray
    target_ndre: np.ndarray
    target_ndwi: np.ndarray
    standardized_ndvi_anomaly_z: np.ndarray
    standardized_evi_anomaly_z: np.ndarray
    vegetation_condition_index_vci: np.ndarray
    mean_target_z_anomaly: float
    mean_target_vci: float
    optical_observability_score: float
    historical_composites: list[HistoricalVegetationCompositeRecord]


def get_grid_bounds(grid: TargetAnalysisGrid) -> tuple[float, float, float, float]:
    """Calculate (min_x, min_y, max_x, max_y) from TargetAnalysisGrid geotransform."""
    min_x = grid.transform[0]
    max_x = min_x + grid.width * grid.pixel_size_x_m
    max_y = grid.transform[3]
    min_y = max_y - grid.height * grid.pixel_size_y_m
    return (min_x, min_y, max_x, max_y)


def crop_and_resample_band_to_grid(
    band_path: Path,
    target_grid: TargetAnalysisGrid,
) -> np.ndarray:
    """Crop native raster file to target grid bounding box and resample to analysis grid resolution."""
    bounds = get_grid_bounds(target_grid)
    out_shape = (target_grid.height, target_grid.width)

    with rasterio.open(band_path) as src:
        band_crs = src.crs.to_string() if src.crs else target_grid.crs
        if band_crs != target_grid.crs:
            trans = Transformer.from_crs(target_grid.crs, band_crs, always_xy=True)
            min_x, min_y = trans.transform(bounds[0], bounds[1])
            max_x, max_y = trans.transform(bounds[2], bounds[3])
        else:
            min_x, min_y, max_x, max_y = bounds

        win = from_bounds(min_x, min_y, max_x, max_y, src.transform)
        data = src.read(
            1,
            window=win,
            out_shape=out_shape,
            resampling=rasterio.enums.Resampling.bilinear,
        ).astype(np.float32)

    return data


def build_historical_vegetation_composite(
    year: int,
    month: int,
    session: ExternalSatelliteAcquisitionSession,
    target_grid: TargetAnalysisGrid,
    s2_item_id: str,
    datetime_utc: str,
    cloud_cover_pct: float,
) -> HistoricalVegetationCompositeRecord:
    """Extract quality-filtered optical vegetation indices on target grid for a single epoch."""
    b02_p = Path(session.verified_records["s2_b02"].local_cached_path)
    b04_p = Path(session.verified_records["s2_b04"].local_cached_path)
    b05_p = Path(session.verified_records["s2_b05"].local_cached_path)
    b08_p = Path(session.verified_records["s2_b08"].local_cached_path)
    b11_p = Path(session.verified_records["s2_b11"].local_cached_path)
    scl_p = Path(session.verified_records["s2_scl"].local_cached_path)

    b02 = crop_and_resample_band_to_grid(b02_p, target_grid)
    b04 = crop_and_resample_band_to_grid(b04_p, target_grid)
    b05 = crop_and_resample_band_to_grid(b05_p, target_grid)
    b08 = crop_and_resample_band_to_grid(b08_p, target_grid)
    b11 = crop_and_resample_band_to_grid(b11_p, target_grid)

    bounds = get_grid_bounds(target_grid)
    out_shape = (target_grid.height, target_grid.width)

    with rasterio.open(scl_p) as src_scl:
        min_x, min_y, max_x, max_y = bounds
        win = from_bounds(min_x, min_y, max_x, max_y, src_scl.transform)
        scl_grid = src_scl.read(
            1,
            window=win,
            out_shape=out_shape,
            resampling=rasterio.enums.Resampling.nearest,
        )

    scl_dist = compute_scl_quality_distribution(scl_grid)

    ndvi = compute_ndvi(b08, b04)
    evi = compute_evi(b08, b04, b02)
    ndre = compute_ndre(b08, b05)
    ndwi = compute_ndwi(b08, b11)

    total_pixels = target_grid.width * target_grid.height
    valid_mask = ~np.isnan(ndvi)
    valid_pct = float(np.sum(valid_mask) / total_pixels) * 100.0

    return HistoricalVegetationCompositeRecord(
        year=year,
        month=month,
        stac_item_id=s2_item_id,
        acquisition_datetime_utc=datetime_utc,
        cloud_cover_pct=cloud_cover_pct,
        scl_observability_score=scl_dist.scl_terrestrial_observability_contribution,
        valid_pixel_pct=valid_pct,
        mean_ndvi=float(np.nanmean(ndvi)),
        mean_evi=float(np.nanmean(evi)),
        mean_ndre=float(np.nanmean(ndre)),
        mean_ndwi=float(np.nanmean(ndwi)),
        ndvi_grid=ndvi,
        evi_grid=evi,
        ndre_grid=ndre,
        ndwi_grid=ndwi,
    )


def compute_leave_out_climatology_and_anomalies(
    target_composite: HistoricalVegetationCompositeRecord,
    baseline_composites: list[HistoricalVegetationCompositeRecord],
    excluded_years: list[int] | None = None,
) -> LeaveOneOutClimatologyResult:
    """Compute leave-target-out baseline distributions and target standardized anomaly (z-score) and VCI."""
    if not baseline_composites:
        raise ValueError("Cannot compute climatology: baseline_composites list is empty")

    target_year = target_composite.year
    target_month = target_composite.month

    valid_baseline = [c for c in baseline_composites if c.year != target_year]
    if len(valid_baseline) < 2:
        raise ValueError(
            f"Insufficient baseline years for climatology: {len(valid_baseline)} available (required >= 2)"
        )

    baseline_years = [c.year for c in valid_baseline]
    ex_years = excluded_years or [target_year]
    if target_year not in ex_years:
        ex_years.append(target_year)

    ndvi_stack = np.stack([c.ndvi_grid for c in valid_baseline], axis=0)
    evi_stack = np.stack([c.evi_grid for c in valid_baseline], axis=0)

    mean_ndvi = np.nanmean(ndvi_stack, axis=0)
    std_ndvi = np.nanstd(ndvi_stack, axis=0)
    min_ndvi = np.nanmin(ndvi_stack, axis=0)
    max_ndvi = np.nanmax(ndvi_stack, axis=0)

    mean_evi = np.nanmean(evi_stack, axis=0)
    std_evi = np.nanstd(evi_stack, axis=0)

    denom_ndvi = std_ndvi.copy()
    denom_ndvi[denom_ndvi < 1e-4] = 1e-4
    z_ndvi = (target_composite.ndvi_grid - mean_ndvi) / denom_ndvi

    denom_evi = std_evi.copy()
    denom_evi[denom_evi < 1e-4] = 1e-4
    z_evi = (target_composite.evi_grid - mean_evi) / denom_evi

    range_ndvi = max_ndvi - min_ndvi
    range_ndvi[range_ndvi < 1e-4] = 1e-4
    vci = 100.0 * (target_composite.ndvi_grid - min_ndvi) / range_ndvi
    vci = np.clip(vci, 0.0, 100.0)

    mean_z = float(np.nanmean(z_ndvi))
    mean_vci = float(np.nanmean(vci))

    return LeaveOneOutClimatologyResult(
        target_year=target_year,
        target_month=target_month,
        baseline_years=baseline_years,
        excluded_years=ex_years,
        mean_baseline_ndvi=mean_ndvi,
        std_baseline_ndvi=std_ndvi,
        min_baseline_ndvi=min_ndvi,
        max_baseline_ndvi=max_ndvi,
        target_ndvi=target_composite.ndvi_grid,
        target_evi=target_composite.evi_grid,
        target_ndre=target_composite.ndre_grid,
        target_ndwi=target_composite.ndwi_grid,
        standardized_ndvi_anomaly_z=z_ndvi,
        standardized_evi_anomaly_z=z_evi,
        vegetation_condition_index_vci=vci,
        mean_target_z_anomaly=mean_z,
        mean_target_vci=mean_vci,
        optical_observability_score=target_composite.scl_observability_score,
        historical_composites=valid_baseline,
    )
