from pathlib import Path
from earth_one.flood_observability_validation import INDEPENDENT_VALIDATION_SPECS


def test_independent_observability_validation_specs():
    assert len(INDEPENDENT_VALIDATION_SPECS) == 3
    
    activations = [s.activation for s in INDEPENDENT_VALIDATION_SPECS]
    assert "EMSR357" in activations
    assert "EMSR445" in activations
    assert "EMSR567" in activations
    
    for spec in INDEPENDENT_VALIDATION_SPECS:
        assert Path(spec.reference_shapefile).exists(), f"Missing shapefile for {spec.activation}"
