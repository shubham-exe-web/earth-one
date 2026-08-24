from pathlib import Path
from earth_one.flood_unseen_validation import DEVELOPMENT_SPECS, UNSEEN_SPECS


def test_validation_cohorts():
    assert len(DEVELOPMENT_SPECS) == 3
    assert len(UNSEEN_SPECS) == 2

    for spec in DEVELOPMENT_SPECS + UNSEEN_SPECS:
        assert Path(spec.reference_shapefile).exists(), f"Missing shapefile for {spec.activation}"
        assert spec.grid_shape == (512, 512)
        assert len(spec.bbox) == 4
