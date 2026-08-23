import pytest
from pathlib import Path
from earth_one.experiment2_strict import STRICT_AOI_SPECS, fit_frozen_b2_model, load_serialized_b2_model

def test_strict_aoi_specs():
    assert len(STRICT_AOI_SPECS) == 3
    keys = [s.key for s in STRICT_AOI_SPECS]
    assert keys == ["similipal", "satpura", "kumaon"]
    for s in STRICT_AOI_SPECS:
        assert len(s.bbox) == 4
        assert s.s2_before_item.startswith("S2")
        assert s.s2_after_item.startswith("S2")
        assert s.s1_before_item.startswith("S1")
        assert s.s1_after_item.startswith("S1")

def test_frozen_b2_model_contract():
    train_dir = Path("data/results/epoch_2024_2025")
    s1_pair_dir = Path("data/results/s1_pair")
    if train_dir.exists() and s1_pair_dir.exists():
        clf, feature_names = fit_frozen_b2_model(train_dir, s1_pair_dir)
        assert len(feature_names) == 6
        assert feature_names == ["NDVI_after", "DELTA_NDVI", "VV_after", "VH_after", "DELTA_VV_DB", "DELTA_VH_DB"]
        assert clf.n_estimators == 300
        assert clf.n_features_in_ == 6

def test_load_serialized_b2_model():
    model_path = Path("data/models/b2_model_frozen.joblib")
    if model_path.exists():
        clf, feature_names = load_serialized_b2_model(model_path)
        assert len(feature_names) == 6
        assert feature_names == ["NDVI_after", "DELTA_NDVI", "VV_after", "VH_after", "DELTA_VV_DB", "DELTA_VH_DB"]
        assert clf.n_estimators == 300
        assert clf.n_features_in_ == 6
