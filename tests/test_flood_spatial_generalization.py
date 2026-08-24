from pathlib import Path
from earth_one.flood_spatial_generalization import UNSEEN_SPATIAL_SPECS
from earth_one.flood_unseen_validation import DEVELOPMENT_SPECS


def test_spatial_generalization_specs():
    assert len(DEVELOPMENT_SPECS) == 3
    assert len(UNSEEN_SPATIAL_SPECS) == 4

    # 7 activations across 3 continents
    all_specs = DEVELOPMENT_SPECS + UNSEEN_SPATIAL_SPECS
    assert len(all_specs) == 7
    
    countries = {s.country for s in all_specs}
    assert len(countries) >= 5
    assert "Mozambique" in countries
    assert "Germany" in countries
    assert "Vietnam" in countries

    for spec in all_specs:
        assert Path(spec.reference_shapefile).exists(), f"Missing shapefile for {spec.activation}"
