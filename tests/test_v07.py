import sys
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from earth_one.router import ModelRouter
from earth_one.validation import validate_model_result


def _stack(path):
    profile = {
        "driver": "GTiff", "height": 3, "width": 3, "count": 4,
        "dtype": "float32", "crs": "EPSG:32644",
        "transform": from_origin(0, 30, 10, 10), "nodata": np.nan,
    }
    names = ["NDVI", "DELTA_NDVI", "VV", "VH"]
    with rasterio.open(path, "w", **profile) as dst:
        for i, name in enumerate(names, 1):
            dst.write(np.full((3, 3), i * 0.1, dtype=np.float32), i)
            dst.set_band_description(i, name)


def test_router_multimodal():
    decision = ModelRouter().route({"NDVI", "DELTA_NDVI", "VV", "VH"})
    assert decision.model_family == "multimodal_classifier"


def test_router_insufficient():
    decision = ModelRouter().route({"NDVI"})
    assert decision.model_family == "insufficient_evidence"


def test_router_optical_temporal():
    decision = ModelRouter().route({"NDVI", "DELTA_NDVI"})
    assert decision.model_family == "optical_temporal_classifier"
    assert decision.required_features == ("NDVI", "DELTA_NDVI")


def test_validation_gate():
    result = validate_model_result(
        {"balanced_accuracy": 0.72},
        minimum_balanced_accuracy=0.60,
    )
    assert result["status"] == "candidate"


def test_stack_contract(tmp_path):
    path = tmp_path / "stack.tif"
    _stack(path)
    with rasterio.open(path) as ds:
        assert list(ds.descriptions) == ["NDVI", "DELTA_NDVI", "VV", "VH"]
