import numpy as np
from earth_one.drought.spatial_harmonization import (
    TargetAnalysisGrid,
    resample_raster_to_grid,
    harmonize_sensor_layer,
)


def test_target_analysis_grid_pixel_area():
    # 100m grid = 1.0 ha/pixel
    grid_100m = TargetAnalysisGrid(
        crs="EPSG:32615",
        transform=(400000.0, 100.0, 0.0, 4650000.0, 0.0, -100.0),
        width=50,
        height=50,
        pixel_size_x_m=100.0,
        pixel_size_y_m=-100.0,
    )
    assert grid_100m.pixel_area_ha == 1.0

    # 20m grid = 0.04 ha/pixel
    grid_20m = TargetAnalysisGrid(
        crs="EPSG:32615",
        transform=(400000.0, 20.0, 0.0, 4650000.0, 0.0, -20.0),
        width=250,
        height=250,
        pixel_size_x_m=20.0,
        pixel_size_y_m=-20.0,
    )
    assert grid_20m.pixel_area_ha == 0.04


def test_resample_coarse_to_fine_grid():
    # Simulate coarse GPM precipitation (4x4) resampled to 100m grid (16x16)
    coarse_precip = np.array([
        [10.0, 20.0, 30.0, 40.0],
        [15.0, 25.0, 35.0, 45.0],
        [20.0, 30.0, 40.0, 50.0],
        [25.0, 35.0, 45.0, 55.0],
    ], dtype=np.float32)

    grid = TargetAnalysisGrid(
        crs="EPSG:32615",
        transform=(400000.0, 100.0, 0.0, 4650000.0, 0.0, -100.0),
        width=16,
        height=16,
        pixel_size_x_m=100.0,
        pixel_size_y_m=-100.0,
    )

    layer = harmonize_sensor_layer(
        variable_name="precip_1m_mm",
        source_product="GPM_IMERG_FINAL",
        source_data=coarse_precip,
        source_resolution_m=10000.0,
        target_grid=grid,
        method="bilinear",
    )

    assert layer.data.shape == (16, 16)
    assert layer.valid_mask.shape == (16, 16)
    assert np.all(layer.valid_mask)
    assert layer.native_resolution_m == 10000.0
    assert 10.0 <= np.min(layer.data) <= np.max(layer.data) <= 55.0
