import pytest
from pathlib import Path
from earth_one.experiment3_operational import (
    MonitoringAOI,
    FailureMode,
    load_frozen_b2,
    run_fault_injection_suite,
    discover_and_pair_stac_scenes,
)

def test_monitoring_aoi():
    aoi = MonitoringAOI(name="Satpura", region="Central Highlands", bbox=(78.10, 22.25, 78.45, 22.60))
    assert aoi.name == "Satpura"
    assert len(aoi.bbox) == 4
    assert aoi.min_clear_pixels == 10000

def test_frozen_b2_loading():
    model_path = Path("data/models/b2_model_frozen.joblib")
    if model_path.exists():
        clf, features = load_frozen_b2(model_path)
        assert len(features) == 6
        assert features == ["NDVI_after", "DELTA_NDVI", "VV_after", "VH_after", "DELTA_VV_DB", "DELTA_VH_DB"]
        assert clf.n_estimators == 300
        assert clf.n_features_in_ == 6

def test_fault_injection_fail_closed():
    model_path = Path("data/models/b2_model_frozen.joblib")
    if model_path.exists():
        clf, features = load_frozen_b2(model_path)
        aoi = MonitoringAOI(name="TestAOI", region="TestRegion", bbox=(78.10, 22.25, 78.45, 22.60))
        dummy_scenes = {
            "s2_after": "DUMMY_S2A",
            "s2_before": "DUMMY_S2B",
            "s1_after": "DUMMY_S1A",
            "s1_before": "DUMMY_S1B",
        }
        res = run_fault_injection_suite(aoi, dummy_scenes, clf, features)
        assert res["total_injections"] == 7
        assert res["successful_fail_closed_count"] == 7
        assert res["fail_closed_rate"] == 1.00
        assert res["all_failed_closed"] == True
