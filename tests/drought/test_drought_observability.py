import numpy as np
from earth_one.drought.observability import compute_drought_observability


def test_clear_high_observability():
    valid = np.ones((20, 20), dtype=bool)
    ndvi = np.full((20, 20), 0.60, dtype=np.float32)
    obs = compute_drought_observability(valid, cloud_fraction=0.0, baseline_ndvi=ndvi)

    assert obs.mean_observability == 1.0
    assert obs.resolvable_fraction == 1.0
    assert obs.unresolved_fraction == 0.0
    assert obs.mean_attribution_ambiguity == 0.0


def test_cloud_blackout_observability():
    valid = np.ones((20, 20), dtype=bool)
    ndvi = np.full((20, 20), 0.60, dtype=np.float32)
    obs = compute_drought_observability(valid, cloud_fraction=0.40, baseline_ndvi=ndvi)

    # Cloud fraction == max_cloud_cover_fraction (0.40) drops T to 0.0
    assert obs.mean_observability == 0.0
    assert obs.resolvable_fraction == 0.0
    assert obs.unresolved_fraction == 1.0


def test_decoupled_attribution_ambiguity():
    valid = np.ones((20, 20), dtype=bool)
    ndvi = np.full((20, 20), 0.60, dtype=np.float32)
    harvest = np.ones((20, 20), dtype=bool)
    
    # In harvest, sensor observability O remains HIGH (1.0), but attribution ambiguity A is HIGH (0.85)
    obs = compute_drought_observability(valid, cloud_fraction=0.0, baseline_ndvi=ndvi, is_harvest_or_tillage=harvest)
    assert obs.mean_observability == 1.0
    assert obs.mean_attribution_ambiguity == 0.85
    assert np.all(obs.is_attribution_ambiguous)
