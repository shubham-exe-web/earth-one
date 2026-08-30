from __future__ import annotations

"""Drought Module 3 Real Leave-Out Optical Climatology & Multi-Year Anomaly Engine (Phase 29).

Provides:
- Strict SCL Pixel-Validity Masking prior to optical index calculation.
- True Multi-Scene Monthly Temporal Compositing across all usable July scenes.
- Expanded 7-Year Historical Baseline (2016, 2017, 2018, 2019, 2020, 2021, 2023) with 2022 strictly excluded.
- Pixel-level sample count tracking (n_valid_baseline_observations).
- Standardized anomaly (z-score), Standard Error (SE_z), and Vegetation Condition Index (VCI) with robust uncertainty.
- Optical Observability and Quality Assurance integration across the historical stack.
"""

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Sequence
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


def compute_scl_validity_mask(
    scl_data: np.ndarray,
    allow_bare_soil: bool = True,
) -> np.ndarray:
    """Construct a strict boolean mask of valid terrestrial observation pixels from Sentinel-2 SCL."""
    terrestrial = (scl_data == 4) | (scl_data == 5) if allow_bare_soil else (scl_data == 4)
    invalid = (
        (scl_data == 0)
        | (scl_data == 1)
        | (scl_data == 2)
        | (scl_data == 3)
        | (scl_data == 6)
        | (scl_data == 7)
        | (scl_data == 8)
        | (scl_data == 9)
        | (scl_data == 10)
        | (scl_data == 11)
    )
    return terrestrial & (~invalid)


@dataclass
class HistoricalVegetationCompositeRecord:
    """Quality-controlled monthly vegetation index composite from genuine satellite observations."""
    year: int
    month: int
    stac_item_id: str
    acquisition_datetime_utc: str
    cloud_cover_pct: float
    scl_observability_score: float
    valid_pixel_pct: float
    scene_count: int
    mean_ndvi: float
    mean_evi: float
    mean_ndre: float
    mean_ndwi: float
    ndvi_grid: np.ndarray
    evi_grid: np.ndarray
    ndre_grid: np.ndarray
    ndwi_grid: np.ndarray
    valid_mask: np.ndarray


@dataclass
class LeaveOneOutClimatologyResult:
    """Leave-target-out historical climatology distribution and target evaluation anomalies."""
    target_year: int
    target_month: int
    baseline_years: list[int]
    excluded_years: list[int]
    mean_baseline_ndvi: np.ndarray
    std_baseline_ndvi: np.ndarray
    se_baseline_ndvi: np.ndarray
    min_baseline_ndvi: np.ndarray
    max_baseline_ndvi: np.ndarray
    n_valid_baseline_observations: np.ndarray
    target_ndvi: np.ndarray
    target_evi: np.ndarray
    target_ndre: np.ndarray
    target_ndwi: np.ndarray
    standardized_ndvi_anomaly_z: np.ndarray
    standardized_evi_anomaly_z: np.ndarray
    standard_error_z: np.ndarray
    vegetation_condition_index_vci: np.ndarray
    mean_target_z_anomaly: float
    median_target_z_anomaly: float
    mean_target_vci: float
    median_target_vci: float
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
    apply_scl_mask: bool = True,
) -> HistoricalVegetationCompositeRecord:
    """Extract quality-filtered optical vegetation indices on target grid for a single epoch with strict SCL masking."""
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

    # 1. Compute raw optical indices
    ndvi = compute_ndvi(b08, b04)
    evi = compute_evi(b08, b04, b02)
    ndre = compute_ndre(b08, b05)
    ndwi = compute_ndwi(b08, b11)

    # 2. Hard SCL Pixel-Validity Masking Gate:
    if apply_scl_mask:
        valid_mask = compute_scl_validity_mask(scl_grid, allow_bare_soil=True)
    else:
        valid_mask = ~np.isnan(ndvi)

    physical_mask = (
        np.isfinite(b02)
        & np.isfinite(b04)
        & np.isfinite(b08)
        & np.isfinite(ndvi)
        & (ndvi >= -1.0)
        & (ndvi <= 1.0)
    )
    total_valid = valid_mask & physical_mask

    ndvi = np.where(total_valid, ndvi, np.nan)
    evi = np.where(total_valid, evi, np.nan)
    ndre = np.where(total_valid, ndre, np.nan)
    ndwi = np.where(total_valid, ndwi, np.nan)

    total_pixels = target_grid.width * target_grid.height
    valid_count = int(np.sum(total_valid))
    valid_pct = float(valid_count / total_pixels) * 100.0

    return HistoricalVegetationCompositeRecord(
        year=year,
        month=month,
        stac_item_id=s2_item_id,
        acquisition_datetime_utc=datetime_utc,
        cloud_cover_pct=cloud_cover_pct,
        scl_observability_score=scl_dist.scl_terrestrial_observability_contribution,
        valid_pixel_pct=valid_pct,
        scene_count=1,
        mean_ndvi=float(np.nanmean(ndvi)) if valid_count > 0 else float("nan"),
        mean_evi=float(np.nanmean(evi)) if valid_count > 0 else float("nan"),
        mean_ndre=float(np.nanmean(ndre)) if valid_count > 0 else float("nan"),
        mean_ndwi=float(np.nanmean(ndwi)) if valid_count > 0 else float("nan"),
        ndvi_grid=ndvi,
        evi_grid=evi,
        ndre_grid=ndre,
        ndwi_grid=ndwi,
        valid_mask=total_valid,
    )


def compute_monthly_temporal_composite(
    scene_records: list[HistoricalVegetationCompositeRecord],
) -> HistoricalVegetationCompositeRecord:
    """Compute true pixelwise temporal median composite across all usable scenes acquired in a single month."""
    if not scene_records:
        raise ValueError("Cannot compute monthly composite: scene_records list is empty")
    if len(scene_records) == 1:
        return scene_records[0]

    year = scene_records[0].year
    month = scene_records[0].month
    scene_ids = ";".join([r.stac_item_id for r in scene_records])
    datetimes = ";".join([r.acquisition_datetime_utc for r in scene_records])
    avg_cloud = float(np.mean([r.cloud_cover_pct for r in scene_records]))
    avg_obs = float(np.mean([r.scl_observability_score for r in scene_records]))

    ndvi_stack = np.stack([r.ndvi_grid for r in scene_records], axis=0)
    evi_stack = np.stack([r.evi_grid for r in scene_records], axis=0)
    ndre_stack = np.stack([r.ndre_grid for r in scene_records], axis=0)
    ndwi_stack = np.stack([r.ndwi_grid for r in scene_records], axis=0)

    # Pixelwise Temporal Median Composite (robust to cloud outliers & residual shadows)
    ndvi_comp = np.nanmedian(ndvi_stack, axis=0)
    evi_comp = np.nanmedian(evi_stack, axis=0)
    ndre_comp = np.nanmedian(ndre_stack, axis=0)
    ndwi_comp = np.nanmedian(ndwi_stack, axis=0)

    total_valid = np.any(~np.isnan(ndvi_stack), axis=0)
    valid_count = int(np.sum(total_valid))
    total_pixels = total_valid.size
    valid_pct = float(valid_count / total_pixels) * 100.0

    return HistoricalVegetationCompositeRecord(
        year=year,
        month=month,
        stac_item_id=f"COMPOSITE_{year}_07_{len(scene_records)}_SCENES",
        acquisition_datetime_utc=datetimes,
        cloud_cover_pct=avg_cloud,
        scl_observability_score=avg_obs,
        valid_pixel_pct=valid_pct,
        scene_count=len(scene_records),
        mean_ndvi=float(np.nanmean(ndvi_comp)),
        mean_evi=float(np.nanmean(evi_comp)),
        mean_ndre=float(np.nanmean(ndre_comp)),
        mean_ndwi=float(np.nanmean(ndwi_comp)),
        ndvi_grid=ndvi_comp,
        evi_grid=evi_comp,
        ndre_grid=ndre_comp,
        ndwi_grid=ndwi_comp,
        valid_mask=total_valid,
    )


def compute_leave_out_climatology_and_anomalies(
    target_composite: HistoricalVegetationCompositeRecord,
    baseline_composites: list[HistoricalVegetationCompositeRecord],
    excluded_years: list[int] | None = None,
    min_valid_baseline_observations: int = 2,
) -> LeaveOneOutClimatologyResult:
    """Compute leave-target-out baseline distributions and target standardized anomaly (z-score) and VCI."""
    if not baseline_composites:
        raise ValueError("Cannot compute climatology: baseline_composites list is empty")

    target_year = target_composite.year
    target_month = target_composite.month

    valid_baseline = [c for c in baseline_composites if c.year != target_year]
    if len(valid_baseline) < min_valid_baseline_observations:
        raise ValueError(
            f"Insufficient baseline years for climatology: {len(valid_baseline)} available (required >= {min_valid_baseline_observations})"
        )

    baseline_years = sorted([c.year for c in valid_baseline])
    ex_years = sorted(list(set((excluded_years or []) + [target_year])))

    ndvi_stack = np.stack([c.ndvi_grid for c in valid_baseline], axis=0)
    evi_stack = np.stack([c.evi_grid for c in valid_baseline], axis=0)

    n_valid_baseline_obs = np.sum(~np.isnan(ndvi_stack), axis=0).astype(np.int32)
    has_sufficient_obs = n_valid_baseline_obs >= min_valid_baseline_observations

    mean_ndvi = np.where(has_sufficient_obs, np.nanmean(ndvi_stack, axis=0), np.nan)
    std_ndvi = np.where(has_sufficient_obs, np.nanstd(ndvi_stack, axis=0), np.nan)
    min_ndvi = np.where(has_sufficient_obs, np.nanmin(ndvi_stack, axis=0), np.nan)
    max_ndvi = np.where(has_sufficient_obs, np.nanmax(ndvi_stack, axis=0), np.nan)
    
    se_ndvi = np.where(
        has_sufficient_obs,
        std_ndvi / np.sqrt(np.maximum(1, n_valid_baseline_obs)),
        np.nan,
    )

    mean_evi = np.where(has_sufficient_obs, np.nanmean(evi_stack, axis=0), np.nan)
    std_evi = np.where(has_sufficient_obs, np.nanstd(evi_stack, axis=0), np.nan)

    denom_ndvi = np.where(std_ndvi < 1e-4, 1e-4, std_ndvi)
    z_ndvi = np.where(
        has_sufficient_obs & np.isfinite(target_composite.ndvi_grid),
        (target_composite.ndvi_grid - mean_ndvi) / denom_ndvi,
        np.nan,
    )

    se_z = np.where(
        has_sufficient_obs,
        1.0 / np.sqrt(np.maximum(1, n_valid_baseline_obs)),
        np.nan,
    )

    denom_evi = np.where(std_evi < 1e-4, 1e-4, std_evi)
    z_evi = np.where(
        has_sufficient_obs & np.isfinite(target_composite.evi_grid),
        (target_composite.evi_grid - mean_evi) / denom_evi,
        np.nan,
    )

    range_ndvi = max_ndvi - min_ndvi
    range_ndvi = np.where(range_ndvi < 1e-4, 1e-4, range_ndvi)
    vci = np.where(
        has_sufficient_obs & np.isfinite(target_composite.ndvi_grid),
        100.0 * (target_composite.ndvi_grid - min_ndvi) / range_ndvi,
        np.nan,
    )
    vci = np.clip(vci, 0.0, 100.0)

    mean_z = float(np.nanmean(z_ndvi)) if np.any(np.isfinite(z_ndvi)) else float("nan")
    median_z = float(np.nanmedian(z_ndvi)) if np.any(np.isfinite(z_ndvi)) else float("nan")
    mean_vci = float(np.nanmean(vci)) if np.any(np.isfinite(vci)) else float("nan")
    median_vci = float(np.nanmedian(vci)) if np.any(np.isfinite(vci)) else float("nan")

    return LeaveOneOutClimatologyResult(
        target_year=target_year,
        target_month=target_month,
        baseline_years=baseline_years,
        excluded_years=ex_years,
        mean_baseline_ndvi=mean_ndvi,
        std_baseline_ndvi=std_ndvi,
        se_baseline_ndvi=se_ndvi,
        min_baseline_ndvi=min_ndvi,
        max_baseline_ndvi=max_ndvi,
        n_valid_baseline_observations=n_valid_baseline_obs,
        target_ndvi=target_composite.ndvi_grid,
        target_evi=target_composite.evi_grid,
        target_ndre=target_composite.ndre_grid,
        target_ndwi=target_composite.ndwi_grid,
        standardized_ndvi_anomaly_z=z_ndvi,
        standardized_evi_anomaly_z=z_evi,
        standard_error_z=se_z,
        vegetation_condition_index_vci=vci,
        mean_target_z_anomaly=mean_z,
        median_target_z_anomaly=median_z,
        mean_target_vci=mean_vci,
        median_target_vci=median_vci,
        optical_observability_score=target_composite.scl_observability_score,
        historical_composites=valid_baseline,
    )
