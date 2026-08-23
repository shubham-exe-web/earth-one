import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from earth_one.cli import parse_bbox


def test_bbox():
    assert parse_bbox("80,20,82,22") == [80.0, 20.0, 82.0, 22.0]
