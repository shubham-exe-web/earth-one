import pytest
import numpy as np
from pathlib import Path

from earth_one.drought.spatial_harmonization import TargetAnalysisGrid
from earth_one.drought.real_climatology import (
    HistoricalVegetationCompositeRecord,
    LeaveOneOutClimatologyResult,
    compute_scl_validity_mask,
    compute_leave_out_climatology_and_anomalies,
)


def test_compute_scl_validity_mask():
    # SCL test array:
    # 4: Veg, 5: Soil, 3: Shadow, 8: Cloud, 0: No-data, 6: Water
    scl = np.array([[4, 5], [3, 8], [0, 6]], dtype=np.uint8)
    mask = compute_scl_validity_mask(scl, allow_bare_soil=True)
    expected = np.array([[True, True], [False, False], [False, False]])
    np.testing.assert_array_equal(mask, expected)


def test_leave_target_out_climatology_and_anomalies():
    grid_shape = (10, 10)
    valid_mask = np.ones(grid_shape, dtype=bool)
    
    # 3 baseline historical years: 2018, 2019, 2020
    comp_2018 = HistoricalVegetationCompositeRecord(
        year=2018,
        month=7,
        stac_item_id="S2_2018",
        acquisition_datetime_utc="2018-07-20T00:00:00Z",
        cloud_cover_pct=1.0,
        scl_observability_score=0.95,
        valid_pixel_pct=100.0,
        scene_count=1,
        mean_ndvi=0.60,
        mean_evi=0.45,
        mean_ndre=0.35,
        mean_ndwi=0.10,
        ndvi_grid=np.full(grid_shape, 0.60, dtype=np.float32),
        evi_grid=np.full(grid_shape, 0.45, dtype=np.float32),
        ndre_grid=np.full(grid_shape, 0.35, dtype=np.float32),
        ndwi_grid=np.full(grid_shape, 0.10, dtype=np.float32),
        valid_mask=valid_mask,
    )
    comp_2019 = HistoricalVegetationCompositeRecord(
        year=2019,
        month=7,
        stac_item_id="S2_2019",
        acquisition_datetime_utc="2019-07-20T00:00:00Z",
        cloud_cover_pct=0.5,
        scl_observability_score=0.98,
        valid_pixel_pct=100.0,
        scene_count=1,
        mean_ndvi=0.70,
        mean_evi=0.55,
        mean_ndre=0.40,
        mean_ndwi=0.15,
        ndvi_grid=np.full(grid_shape, 0.70, dtype=np.float32),
        evi_grid=np.full(grid_shape, 0.55, dtype=np.float32),
        ndre_grid=np.full(grid_shape, 0.40, dtype=np.float32),
        ndwi_grid=np.full(grid_shape, 0.15, dtype=np.float32),
        valid_mask=valid_mask,
    )
    comp_2020 = HistoricalVegetationCompositeRecord(
        year=2020,
        month=7,
        stac_item_id="S2_2020",
        acquisition_datetime_utc="2020-07-20T00:00:00Z",
        cloud_cover_pct=0.2,
        scl_observability_score=0.99,
        valid_pixel_pct=100.0,
        scene_count=1,
        mean_ndvi=0.80,
        mean_evi=0.65,
        mean_ndre=0.45,
        mean_ndwi=0.20,
        ndvi_grid=np.full(grid_shape, 0.80, dtype=np.float32),
        evi_grid=np.full(grid_shape, 0.65, dtype=np.float32),
        ndre_grid=np.full(grid_shape, 0.45, dtype=np.float32),
        ndwi_grid=np.full(grid_shape, 0.20, dtype=np.float32),
        valid_mask=valid_mask,
    )

    # Target 2022 observation (Drought stress: NDVI = 0.40, below all baseline years)
    comp_2022 = HistoricalVegetationCompositeRecord(
        year=2022,
        month=7,
        stac_item_id="S2_2022",
        acquisition_datetime_utc="2022-07-20T00:00:00Z",
        cloud_cover_pct=0.0,
        scl_observability_score=1.0,
        valid_pixel_pct=100.0,
        scene_count=1,
        mean_ndvi=0.40,
        mean_evi=0.30,
        mean_ndre=0.20,
        mean_ndwi=0.05,
        ndvi_grid=np.full(grid_shape, 0.40, dtype=np.float32),
        evi_grid=np.full(grid_shape, 0.30, dtype=np.float32),
        ndre_grid=np.full(grid_shape, 0.20, dtype=np.float32),
        ndwi_grid=np.full(grid_shape, 0.05, dtype=np.float32),
        valid_mask=valid_mask,
    )

    # Pass all 4 composites including 2022 to verify leave-2022-out guardrail
    res = compute_leave_out_climatology_and_anomalies(
        target_composite=comp_2022,
        baseline_composites=[comp_2018, comp_2019, comp_2020, comp_2022],
    )

    assert res.target_year == 2022
    assert 2022 not in res.baseline_years
    assert set(res.baseline_years) == {2018, 2019, 2020}
    assert 2022 in res.excluded_years

    # Baseline NDVI: [0.60, 0.70, 0.80] -> mean = 0.70, min = 0.60, max = 0.80
    np.testing.assert_allclose(res.mean_baseline_ndvi, 0.70, rtol=1e-4)
    np.testing.assert_allclose(res.min_baseline_ndvi, 0.60, rtol=1e-4)
    np.testing.assert_allclose(res.max_baseline_ndvi, 0.80, rtol=1e-4)

    # 2022 NDVI is 0.40 (negative anomaly):
    assert res.mean_target_z_anomaly < -3.0
    # VCI = 100 * (0.40 - 0.60) / (0.80 - 0.60) -> clipped to 0.0
    assert res.mean_target_vci == 0.0
    # Sample count is 3
    assert np.all(res.n_valid_baseline_observations == 3)


def test_strict_insufficient_baseline_guardrail():
    grid_shape = (5, 5)
    valid_mask = np.ones(grid_shape, dtype=bool)
    comp_2018 = HistoricalVegetationCompositeRecord(
        year=2018, month=7, stac_item_id="S2_2018", acquisition_datetime_utc="2018-07-20T00:00:00Z",
        cloud_cover_pct=1.0, scl_observability_score=0.95, valid_pixel_pct=100.0, scene_count=1,
        mean_ndvi=0.60, mean_evi=0.45, mean_ndre=0.35, mean_ndwi=0.10,
        ndvi_grid=np.full(grid_shape, 0.60, dtype=np.float32),
        evi_grid=np.full(grid_shape, 0.45, dtype=np.float32),
        ndre_grid=np.full(grid_shape, 0.35, dtype=np.float32),
        ndwi_grid=np.full(grid_shape, 0.10, dtype=np.float32),
        valid_mask=valid_mask,
    )
    comp_2022 = HistoricalVegetationCompositeRecord(
        year=2022, month=7, stac_item_id="S2_2022", acquisition_datetime_utc="2022-07-20T00:00:00Z",
        cloud_cover_pct=0.0, scl_observability_score=1.0, valid_pixel_pct=100.0, scene_count=1,
        mean_ndvi=0.40, mean_evi=0.30, mean_ndre=0.20, mean_ndwi=0.05,
        ndvi_grid=np.full(grid_shape, 0.40, dtype=np.float32),
        evi_grid=np.full(grid_shape, 0.30, dtype=np.float32),
        ndre_grid=np.full(grid_shape, 0.20, dtype=np.float32),
        ndwi_grid=np.full(grid_shape, 0.05, dtype=np.float32),
        valid_mask=valid_mask,
    )

    # Only 1 valid baseline year (2018) -> must raise ValueError
    with pytest.raises(ValueError, match="Insufficient baseline years for climatology"):
        compute_leave_out_climatology_and_anomalies(
            target_composite=comp_2022,
            baseline_composites=[comp_2018, comp_2022],
        )
