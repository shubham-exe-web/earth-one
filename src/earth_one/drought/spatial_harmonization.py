from __future__ import annotations

"""Drought Module 3 Multi-Sensor Spatial Grid Harmonization & Geotransform Layer (Task D-16).

Harmonizes heterogeneous multi-sensor footprints onto a unified Target Analysis Grid:
- Sentinel-2: Native ~10/20m
- MODIS / Landsat Thermal: Native ~1000m / 30m
- GPM IMERG: Native ~10,000m (0.1 deg)
- SMAP / ERA5-Land: Native ~9,000m - 36,000m
"""

import hashlib
from dataclasses import dataclass
from typing import Literal
import numpy as np
from scipy import ndimage


ResamplingMethod = Literal["bilinear", "nearest", "cubic", "area_average"]


@dataclass(frozen=True)
class TargetAnalysisGrid:
    """Geospatial definition of the target analysis raster grid."""
    crs: str
    transform: tuple[float, float, float, float, float, float]  # (x_min, dx, 0, y_max, 0, -dy)
    width: int
    height: int
    pixel_size_x_m: float
    pixel_size_y_m: float

    @property
    def pixel_area_ha(self) -> float:
        """Exact pixel area in hectares computed directly from geotransform."""
        return (abs(self.pixel_size_x_m) * abs(self.pixel_size_y_m)) / 10000.0


@dataclass
class HarmonizedRasterLayer:
    """Container for a harmonized raster layer aligned to the Target Analysis Grid."""
    variable_name: str
    source_product: str
    native_resolution_m: float
    resampling_applied: ResamplingMethod
    data: np.ndarray
    valid_mask: np.ndarray
    target_grid: TargetAnalysisGrid
    provenance_hash: str


def resample_raster_to_grid(
    source_data: np.ndarray,
    source_resolution_m: float,
    target_grid: TargetAnalysisGrid,
    method: ResamplingMethod = "bilinear",
) -> np.ndarray:
    """Resample an arbitrary native raster array to match target_grid dimensions."""
    target_shape = (target_grid.height, target_grid.width)
    if source_data.shape == target_shape:
        return source_data.astype(np.float32)

    src_h, src_w = source_data.shape
    zoom_factors = (target_grid.height / src_h, target_grid.width / src_w)

    order_map = {"nearest": 0, "bilinear": 1, "cubic": 3, "area_average": 1}
    order = order_map.get(method, 1)

    # Handle NaNs gracefully during interpolation
    nan_mask = ~np.isfinite(source_data)
    data_filled = np.where(nan_mask, np.nanmean(source_data) if np.any(~nan_mask) else 0.0, source_data)

    resampled = ndimage.zoom(data_filled, zoom=zoom_factors, order=order)
    
    # Resize exact shape if roundoff
    if resampled.shape != target_shape:
        resampled = resampled[:target_grid.height, :target_grid.width]

    return resampled.astype(np.float32)


def harmonize_sensor_layer(
    variable_name: str,
    source_product: str,
    source_data: np.ndarray,
    source_resolution_m: float,
    target_grid: TargetAnalysisGrid,
    method: ResamplingMethod = "bilinear",
) -> HarmonizedRasterLayer:
    """Harmonize a native satellite layer onto the declared Target Analysis Grid with provenance."""
    aligned_data = resample_raster_to_grid(
        source_data=source_data,
        source_resolution_m=source_resolution_m,
        target_grid=target_grid,
        method=method,
    )
    valid_mask = np.isfinite(aligned_data)

    prov = hashlib.sha256(
        f"HARMONIZE_{variable_name}_{source_product}_{source_resolution_m}_{target_grid.pixel_area_ha:.4f}".encode()
    ).hexdigest()

    return HarmonizedRasterLayer(
        variable_name=variable_name,
        source_product=source_product,
        native_resolution_m=source_resolution_m,
        resampling_applied=method,
        data=aligned_data,
        valid_mask=valid_mask,
        target_grid=target_grid,
        provenance_hash=prov,
    )
