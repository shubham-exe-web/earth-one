import numpy as np
from earth_one.drought.climatology import (
    compute_standardized_anomaly,
    compute_vegetation_condition_index,
    compute_empirical_percentile,
    build_synthetic_climatology,
    HistoricalClimatologyStore,
)
from earth_one.drought.anomalies import compute_multiwindow_anomalies


def test_standardized_anomaly_zscore():
    cur = np.array([0.40, 0.60, 0.80], dtype=np.float32)
    mu = np.array([0.60, 0.60, 0.60], dtype=np.float32)
    sigma = np.array([0.10, 0.10, 0.10], dtype=np.float32)

    z = compute_standardized_anomaly(cur, mu, sigma)
    assert np.isclose(z[0], -2.0)
    assert np.isclose(z[1], 0.0)
    assert np.isclose(z[2], +2.0)


def test_historical_climatology_store_fit():
    store = HistoricalClimatologyStore("precipitation_mm")
    # Simulate 5 years of historical July precipitation for a 5x5 region
    np.random.seed(42)
    hist_stack = np.random.normal(loc=100.0, scale=25.0, size=(5, 5, 5)).astype(np.float32)
    
    clim = store.fit_from_historical_stack(month=7, historical_stack=hist_stack)
    assert clim.sample_years == 5
    assert clim.mean.shape == (5, 5)
    assert clim.valid_sample_fraction == 1.0
    assert 80.0 <= np.mean(clim.mean) <= 120.0


def test_task_d13_leave_one_year_out_exclusion():
    """Task D-13: Prove climatological year exclusion actually removes the requested years from baseline."""
    store = HistoricalClimatologyStore("ndvi")
    shape = (4, 4)
    # 4 historical years: 2018 (0.60), 2019 (0.60), 2020 (0.60), 2021 (0.10 - extreme drought)
    years = [2018, 2019, 2020, 2021]
    hist_stack = np.zeros((4, shape[0], shape[1]), dtype=np.float32)
    hist_stack[0] = 0.60
    hist_stack[1] = 0.60
    hist_stack[2] = 0.60
    hist_stack[3] = 0.10  # Extreme outlier year 2021

    # 1. Fit with all 4 years included
    clim_all = store.fit_from_historical_stack(month=7, historical_stack=hist_stack, year_labels=years)
    assert clim_all.sample_years == 4
    # Mean of (0.60+0.60+0.60+0.10)/4 = 0.475
    assert np.isclose(float(np.mean(clim_all.mean)), 0.475)

    # 2. Fit with 2021 strictly excluded (Leave-One-Year-Out)
    clim_clean = store.fit_from_historical_stack(month=7, historical_stack=hist_stack, year_labels=years, excluded_years=[2021])
    assert clim_clean.sample_years == 3
    # Mean of (0.60+0.60+0.60)/3 = 0.600
    assert np.isclose(float(np.mean(clim_clean.mean)), 0.600)
    assert float(np.mean(clim_clean.std)) < 1e-4  # Zero variance among clean years!


def test_multiwindow_distinct_anomalies():
    shape = (10, 10)
    valid = np.ones(shape, dtype=bool)
    
    clim_v1 = build_synthetic_climatology(shape, "ndvi_1m", 7, 0.60, 0.10)
    clim_v3 = build_synthetic_climatology(shape, "ndvi_3m", 7, 0.58, 0.08)
    clim_v6 = build_synthetic_climatology(shape, "ndvi_6m", 7, 0.55, 0.07)

    clim_p1 = build_synthetic_climatology(shape, "pr1", 7, 80.0, 20.0)
    clim_p3 = build_synthetic_climatology(shape, "pr3", 7, 240.0, 45.0)
    clim_p6 = build_synthetic_climatology(shape, "pr6", 7, 480.0, 70.0)
    clim_s = build_synthetic_climatology(shape, "sms", 7, 0.30, 0.05)
    clim_rz = build_synthetic_climatology(shape, "smrz", 7, 0.32, 0.04)
    clim_t = build_synthetic_climatology(shape, "lst", 7, 298.0, 3.0)

    # Distinct multi-window vegetation and precip values
    anom = compute_multiwindow_anomalies(
        current_ndvi_1m=np.full(shape, 0.40, dtype=np.float32),  # -2.0 z
        current_ndvi_3m=np.full(shape, 0.50, dtype=np.float32),  # -1.0 z
        current_ndvi_6m=np.full(shape, 0.55, dtype=np.float32),  #  0.0 z
        current_precip_1m_mm=np.full(shape, 30.0, dtype=np.float32),
        current_precip_3m_mm=np.full(shape, 120.0, dtype=np.float32),
        current_precip_6m_mm=np.full(shape, 400.0, dtype=np.float32),
        current_sm_surf=np.full(shape, 0.20, dtype=np.float32),
        current_sm_rz=np.full(shape, 0.22, dtype=np.float32),
        current_lst_k=np.full(shape, 303.0, dtype=np.float32),
        clim_ndvi_1m=clim_v1,
        clim_ndvi_3m=clim_v3,
        clim_ndvi_6m=clim_v6,
        clim_precip_1m=clim_p1,
        clim_precip_3m=clim_p3,
        clim_precip_6m=clim_p6,
        clim_sm_surf=clim_s,
        clim_sm_rz=clim_rz,
        clim_lst=clim_t,
        valid_mask=valid,
    )

    # Verify that multi-window anomalies are genuine and distinct
    mean_z1 = float(np.mean(anom.veg_z_1m))
    mean_z3 = float(np.mean(anom.veg_z_3m))
    mean_z6 = float(np.mean(anom.veg_z_6m))

    assert mean_z1 < mean_z3 < mean_z6  # Distinct progression: -2.0 < -1.0 < 0.0
