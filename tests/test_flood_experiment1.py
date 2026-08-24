import json
import pytest
from pathlib import Path

from earth_one.flood_experiment1 import FloodExperiment1Spec, execute_flood_experiment1
from earth_one.flood import FloodEvidenceConfig


def test_flood_experiment1_spec_defaults():
    spec = FloodExperiment1Spec()
    assert spec.activation == "EMSR439"
    assert spec.country == "Bangladesh"
    assert spec.bbox == (91.3591, 22.3493, 91.4019, 22.3913)
    assert "S1A" in spec.s1_before_item
    assert "S1A" in spec.s1_event_item
    assert "S2B" in spec.s2_before_item
    assert "S2B" in spec.s2_event_item
    assert Path(spec.reference_shapefile).exists()
