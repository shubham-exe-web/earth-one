import numpy as np
import pytest
from earth_one.regime_router import classify_biophysical_regime, RegimeRoutingResult


def test_classify_coastal_regime():
    h, w = 50, 50
    occ = np.zeros((h, w), dtype=np.float32)
    elev = np.full((h, w), 2.0, dtype=np.float32)
    slope = np.full((h, w), 0.5, dtype=np.float32)
    occ[:, :25] = 0.90  # Marine water

    res = classify_biophysical_regime(occ, elev, slope, centroid_lat=22.35, centroid_lon=91.38)
    assert isinstance(res, RegimeRoutingResult)
    assert res.regime == "COASTAL_ESTUARINE_TIDAL"
    assert res.confidence >= 0.70
    assert res.recommended_config.morphology_kernel_size == 2


def test_classify_inland_mega_riverine_regime():
    h, w = 50, 50
    occ = np.zeros((h, w), dtype=np.float32)
    elev = np.full((h, w), 45.0, dtype=np.float32)
    slope = np.full((h, w), 0.8, dtype=np.float32)

    res = classify_biophysical_regime(occ, elev, slope, centroid_lat=27.50, centroid_lon=68.20)
    assert res.regime == "INLAND_RIVERINE_MEGA"
    assert res.confidence >= 0.75
    assert res.recommended_config.weight_sar == 0.40


def test_classify_inland_pluvial_valley():
    h, w = 50, 50
    occ = np.zeros((h, w), dtype=np.float32)
    elev = np.linspace(20.0, 350.0, h * w).reshape((h, w)).astype(np.float32)
    slope = np.linspace(1.0, 22.0, h * w).reshape((h, w)).astype(np.float32)

    res = classify_biophysical_regime(occ, elev, slope, centroid_lat=37.45, centroid_lon=14.95)
    assert res.regime == "INLAND_RIVERINE_PLUVIAL"
    assert res.recommended_config.terrain_max_slope_deg == 6.0
