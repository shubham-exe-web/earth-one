from pathlib import Path
from earth_one.flood_multievent import FloodCohortEventSpec, COHORT_SPECS


def test_cohort_specs():
    assert len(COHORT_SPECS) == 3
    
    # Check all three activations exist and have valid shapefiles
    activations = {s.activation: s for s in COHORT_SPECS}
    assert "EMSR439" in activations
    assert "EMSR629" in activations
    assert "EMSR548" in activations

    for act, spec in activations.items():
        assert Path(spec.reference_shapefile).exists(), f"Reference shapefile missing for {act}"
        assert len(spec.bbox) == 4
        assert spec.grid_shape == (512, 512)
