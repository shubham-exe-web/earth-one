import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from earth_one.preprocessing import create_processing_spec, validate_spec


def test_valid_s2_spec():
    spec = create_processing_spec(
        "sentinel-2",
        "input.zip",
        "processed",
        target_crs="EPSG:32644",
        target_resolution_m=10,
    )
    assert spec.sensor == "sentinel-2"
    assert validate_spec(spec) == []


def test_invalid_resolution():
    spec = create_processing_spec(
        "sentinel-1",
        "input.zip",
        "processed",
    )
    spec.target_resolution_m = 0
    assert validate_spec(spec)
