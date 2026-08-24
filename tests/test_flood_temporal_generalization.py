from pathlib import Path
from earth_one.flood_temporal_generalization import UNSEEN_TEMPORAL_SPECS


def test_temporal_generalization_specs():
    assert len(UNSEEN_TEMPORAL_SPECS) == 2
    
    activations = [s.activation for s in UNSEEN_TEMPORAL_SPECS]
    assert "EMSR348" in activations  # 2019
    assert "EMSR286" in activations  # 2018
    
    for spec in UNSEEN_TEMPORAL_SPECS:
        assert Path(spec.reference_shapefile).exists(), f"Missing shapefile for {spec.activation}"
