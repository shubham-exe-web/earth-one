import numpy as np
from rasterio.transform import from_bounds
from earth_one.drought.spatial_harmonization import TargetAnalysisGrid
from earth_one.drought.geospatial_reprojection import (
    GeospatialSourceMetadata,
    reproject_geospatial_raster,
)


def test_geospatial_reprojection_epsg4326_to_epsg32615():
    # Coarse GPM Precipitation grid in EPSG:4326 (WGS84)
    # Covering Iowa bounding box [-95.0, 41.0, -93.0, 43.0] (8x8 cells)
    coarse_precip = np.array([
        [10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0],
        [12.0, 17.0, 22.0, 27.0, 32.0, 37.0, 42.0, 47.0],
        [14.0, 19.0, 24.0, 29.0, 34.0, 39.0, 44.0, 49.0],
        [16.0, 21.0, 26.0, 31.0, 36.0, 41.0, 46.0, 51.0],
        [18.0, 23.0, 28.0, 33.0, 38.0, 43.0, 48.0, 53.0],
        [20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0],
        [22.0, 27.0, 32.0, 37.0, 42.0, 47.0, 52.0, 57.0],
        [24.0, 29.0, 34.0, 39.0, 44.0, 49.0, 54.0, 59.0],
    ], dtype=np.float32)

    src_transform = from_bounds(-95.0, 41.0, -93.0, 43.0, 8, 8)
    src_meta = GeospatialSourceMetadata(
        sensor_name="GPM_IMERG",
        variable_name="precip_1m_mm",
        native_crs="EPSG:4326",
        native_transform=src_transform,
        native_shape=(8, 8),
        native_resolution_m=10000.0,
    )

    # Target UTM Zone 15N grid (EPSG:32615) at 100m resolution
    # UTM coordinates for Central Iowa (~400,000E, 4,650,000N)
    target_grid = TargetAnalysisGrid(
        crs="EPSG:32615",
        transform=(400000.0, 100.0, 0.0, 4650000.0, 0.0, -100.0),
        width=32,
        height=32,
        pixel_size_x_m=100.0,
        pixel_size_y_m=-100.0,
    )

    result = reproject_geospatial_raster(
        source_data=coarse_precip,
        source_meta=src_meta,
        target_grid=target_grid,
        resampling_contract="AREAL_CONSERVATION",
    )

    assert result.data.shape == (32, 32)
    assert result.valid_mask.shape == (32, 32)
    assert np.any(result.valid_mask)
    # Check that warped values are bounded within valid physical range
    valid_data = result.data[result.valid_mask]
    assert np.all(valid_data >= 0.0)
    assert len(result.provenance_hash) == 64
