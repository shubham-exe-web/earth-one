import sys
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from earth_one.validation_v08 import evaluate_predictions
from earth_one.uncertainty import confidence_to_uncertainty


def test_metrics():
    result = evaluate_predictions(
        np.array([1, 1, 2, 2]),
        np.array([1, 2, 2, 2]),
        labels=[1, 2],
    )
    assert result.n_test == 4
    assert 0 <= result.balanced_accuracy <= 1
    assert len(result.confusion_matrix) == 2


def test_uncertainty(tmp_path):
    confidence = tmp_path / "confidence.tif"
    uncertainty = tmp_path / "uncertainty.tif"
    profile = {
        "driver": "GTiff", "height": 2, "width": 2, "count": 1,
        "dtype": "float32", "crs": "EPSG:32644",
        "transform": from_origin(0, 20, 10, 10), "nodata": np.nan,
    }
    with rasterio.open(confidence, "w", **profile) as ds:
        ds.write(np.array([[0.2, 0.8], [1.0, np.nan]], dtype=np.float32), 1)

    result = confidence_to_uncertainty(confidence, uncertainty)
    assert result["valid_fraction"] == 0.75

    with rasterio.open(uncertainty) as ds:
        arr = ds.read(1)
    assert np.isclose(arr[0, 0], 0.8)
    assert np.isclose(arr[0, 1], 0.2)
