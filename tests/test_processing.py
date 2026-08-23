import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from earth_one.processing import build_processing_record


def test_processing_contract():
    record = build_processing_record(
        {
            "id": "test-item",
            "collection": "sentinel-2-l2a",
            "datetime": "2026-01-01T00:00:00Z",
            "platform": "sentinel-2a",
            "cloud_cover": 5.0,
            "discovered_at": "2026-01-01T01:00:00Z",
        },
        "/tmp/example.zip",
    )
    assert record["schema_version"] == "earth-one-observation-0.1"
    assert record["processing"]["status"] == "pending"
    assert record["source"]["item_id"] == "test-item"
