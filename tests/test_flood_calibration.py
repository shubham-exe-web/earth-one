import numpy as np
import rasterio
from earth_one.flood_calibration import compute_expected_calibration_error, compute_event_level_uncertainty


def test_expected_calibration_error():
    y_true = np.array([0, 0, 0, 0, 1, 1, 1, 1, 1, 1])
    y_prob = np.array([0.1, 0.15, 0.2, 0.25, 0.8, 0.85, 0.9, 0.92, 0.95, 0.99])
    
    ece, mce, diagram = compute_expected_calibration_error(y_true, y_prob, n_bins=5)
    assert 0.0 <= ece <= 1.0
    assert 0.0 <= mce <= 1.0
    assert len(diagram) == 5


def test_event_level_uncertainty():
    shape = (50, 50)
    score = np.zeros(shape, dtype=np.float32)
    score[10:30, 10:30] = 0.85  # 20x20 event = 400 px = 16 ha
    obs = np.full(shape, 0.90, dtype=np.float32)
    valid = np.ones(shape, dtype=bool)
    
    t = rasterio.transform.from_bounds(0, 0, 1000, 1000, 50, 50)
    records = compute_event_level_uncertainty(score, obs, valid, t)
    
    assert len(records) >= 1
    ev = records[0]
    assert ev.area_expected_ha == 16.0
    assert ev.area_low_ha <= ev.area_expected_ha <= ev.area_high_ha
    assert ev.is_resolvable is True
