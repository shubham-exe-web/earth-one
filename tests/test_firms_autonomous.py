import pytest
from earth_one.firms_autonomous import (
    FIRMSQueryConfig,
    deduplicate_active_fire_records,
    download_firms_holdout_dataset,
)


def test_firms_config():
    cfg = FIRMSQueryConfig()
    assert cfg.aoi_bbox == (82.60, 22.30, 82.80, 22.45)
    assert cfg.start_date == "2025-01-04"
    assert cfg.end_date == "2026-01-04"
    assert "VIIRS_SNPP_SP" in cfg.sources


def test_deduplicate_active_fire_records():
    records = [
        {"latitude": "22.350", "longitude": "82.650", "acq_date": "2025-03-01", "acq_time": "0700", "frp": "5.0"},
        # Duplicate: same point, 10 min later from different sensor, higher FRP
        {"latitude": "22.3501", "longitude": "82.6501", "acq_date": "2025-03-01", "acq_time": "0710", "frp": "12.0"},
        # Distinct point: 5km away
        {"latitude": "22.400", "longitude": "82.700", "acq_date": "2025-03-01", "acq_time": "0700", "frp": "3.0"},
    ]
    unique, dup_count = deduplicate_active_fire_records(records)
    assert len(unique) == 2
    assert dup_count == 1
    # Check that highest FRP was preserved
    assert unique[0]["frp"] == "12.0"


def test_missing_map_key_raises():
    with pytest.raises(ValueError, match="FIRMS_MAP_KEY is not set"):
        download_firms_holdout_dataset(map_key="")
