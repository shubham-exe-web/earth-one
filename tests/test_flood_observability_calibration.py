from pathlib import Path
from earth_one.flood_observability_validation import INDEPENDENT_VALIDATION_SPECS
from earth_one.flood_temporal_generalization import UNSEEN_TEMPORAL_SPECS


def test_calibration_specs():
    specs = list({s.activation: s for s in (INDEPENDENT_VALIDATION_SPECS + UNSEEN_TEMPORAL_SPECS)}.values())
    assert len(specs) >= 4
    
    activations = {s.activation for s in specs}
    assert "EMSR567" in activations  # Australia
    assert "EMSR357" in activations  # India
    assert "EMSR445" in activations  # Ukraine
    assert "EMSR286" in activations  # Colombia

    for spec in specs:
        assert Path(spec.reference_shapefile).exists(), f"Missing shapefile for {spec.activation}"
