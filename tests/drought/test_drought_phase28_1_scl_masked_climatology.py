import pytest
import numpy as np
from pathlib import Path

from earth_one.drought.real_climatology import (
    HistoricalVegetationCompositeRecord,
    LeaveOneOutClimatologyResult,
    compute_scl_validity_mask,
    compute_leave_out_climatology_and_anomalies,
)


def test_scl_masking_invalidates_cloud_and_shadow_pixels():
    # 2x2 grid: pixel (0,0) is vegetation (4), (0,1) is bare soil (5), (1,0) is cloud (8), (1,1) is shadow (3)
    scl_grid = np.array([[4, 5], [8, 3]], dtype=np.uint8)
    valid_mask = compute_scl_validity_mask(scl_grid, allow_bare_soil=True)

    assert valid_mask[0, 0] is np.True_ or valid_mask[0, 0] == True
    assert valid_mask[0, 1] is np.True_ or valid_mask[0, 1] == True
    assert valid_mask[1, 0] is np.False_ or valid_mask[1, 0] == False
    assert valid_mask[1, 1] is np.False_ or valid_mask[1, 1] == False


def test_pixel_sample_count_and_uncertainty():
    grid_shape = (2, 2)

    # In year 2017: all 4 pixels valid
    v_2017 = np.array([[0.8, 0.8], [0.8, 0.8]], dtype=np.float32)
    # In year 2018: pixel (1,1) was cloudy (NaN)
    v_2018 = np.array([[0.7, 0.7], [0.7, np.nan]], dtype=np.float32)
    # In year 2019: pixel (1,0) was shadow (NaN)
    v_2019 = np.array([[0.85, 0.85], [np.nan, 0.85]], dtype=np.float32)

    c_2017 = HistoricalVegetationCompositeRecord(
        year=2017, month=7, stac_item_id="S2_2017", acquisition_datetime_utc="2017-07-20T00:00:00Z",
        cloud_cover_pct=0.0, scl_observability_score=1.0, valid_pixel_pct=100.0, scene_count=1,
        mean_ndvi=0.8, mean_evi=0.8, mean_ndre=0.8, mean_ndwi=0.8,
        ndvi_grid=v_2017, evi_grid=v_2017, ndre_grid=v_2017, ndwi_grid=v_2017,
        valid_mask=~np.isnan(v_2017),
    )
    c_2018 = HistoricalVegetationCompositeRecord(
        year=2018, month=7, stac_item_id="S2_2018", acquisition_datetime_utc="2018-07-20T00:00:00Z",
        cloud_cover_pct=0.0, scl_observability_score=0.75, valid_pixel_pct=75.0, scene_count=1,
        mean_ndvi=0.7, mean_evi=0.7, mean_ndre=0.7, mean_ndwi=0.7,
        ndvi_grid=v_2018, evi_grid=v_2018, ndre_grid=v_2018, ndwi_grid=v_2018,
        valid_mask=~np.isnan(v_2018),
    )
    c_2019 = HistoricalVegetationCompositeRecord(
        year=2019, month=7, stac_item_id="S2_2019", acquisition_datetime_utc="2019-07-20T00:00:00Z",
        cloud_cover_pct=0.0, scl_observability_score=0.75, valid_pixel_pct=75.0, scene_count=1,
        mean_ndvi=0.85, mean_evi=0.85, mean_ndre=0.85, mean_ndwi=0.85,
        ndvi_grid=v_2019, evi_grid=v_2019, ndre_grid=v_2019, ndwi_grid=v_2019,
        valid_mask=~np.isnan(v_2019),
    )

    # Target 2022
    v_2022 = np.array([[0.5, 0.5], [0.5, 0.5]], dtype=np.float32)
    c_2022 = HistoricalVegetationCompositeRecord(
        year=2022, month=7, stac_item_id="S2_2022", acquisition_datetime_utc="2022-07-20T00:00:00Z",
        cloud_cover_pct=0.0, scl_observability_score=1.0, valid_pixel_pct=100.0, scene_count=1,
        mean_ndvi=0.5, mean_evi=0.5, mean_ndre=0.5, mean_ndwi=0.5,
        ndvi_grid=v_2022, evi_grid=v_2022, ndre_grid=v_2022, ndwi_grid=v_2022,
        valid_mask=~np.isnan(v_2022),
    )

    res = compute_leave_out_climatology_and_anomalies(
        target_composite=c_2022,
        baseline_composites=[c_2017, c_2018, c_2019],
        min_valid_baseline_observations=2,
    )

    # Pixel (0,0) and (0,1) have 3 valid observations; (1,0) and (1,1) have 2 valid observations
    assert res.n_valid_baseline_observations[0, 0] == 3
    assert res.n_valid_baseline_observations[0, 1] == 3
    assert res.n_valid_baseline_observations[1, 0] == 2
    assert res.n_valid_baseline_observations[1, 1] == 2

    # Standard error of z-score SE_z = 1 / sqrt(N)
    assert abs(res.standard_error_z[0, 0] - 1.0 / np.sqrt(3.0)) < 1e-4
    assert abs(res.standard_error_z[1, 0] - 1.0 / np.sqrt(2.0)) < 1e-4
