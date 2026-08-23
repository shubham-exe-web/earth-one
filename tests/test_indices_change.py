import sys
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from earth_one.indices import calculate_indices
from earth_one.change_detection import detect_index_change


def _make_s2(path, red, nir):
    profile = {
        "driver": "GTiff",
        "height": 2,
        "width": 2,
        "count": 4,
        "dtype": "float32",
        "crs": "EPSG:32644",
        "transform": from_origin(0, 20, 10, 10),
        "nodata": np.nan,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.zeros((2, 2), dtype=np.float32), 1)
        dst.write(np.zeros((2, 2), dtype=np.float32), 2)
        dst.write(np.full((2, 2), red, dtype=np.float32), 3)
        dst.write(np.full((2, 2), nir, dtype=np.float32), 4)
        dst.set_band_description(1, "B02_blue")
        dst.set_band_description(2, "B03_green")
        dst.set_band_description(3, "B04_red")
        dst.set_band_description(4, "B08_nir")


def _make_index(path, value):
    profile = {
        "driver": "GTiff",
        "height": 2,
        "width": 2,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:32644",
        "transform": from_origin(0, 20, 10, 10),
        "nodata": np.nan,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.full((2, 2), value, dtype=np.float32), 1)


def test_ndvi(tmp_path):
    s2 = tmp_path / "s2.tif"
    out = tmp_path / "ndvi.tif"
    _make_s2(s2, red=0.2, nir=0.6)
    result = calculate_indices(s2, out)
    assert result[0].index == "NDVI"
    with rasterio.open(out) as ds:
        arr = ds.read(1)
    assert np.allclose(arr, 0.5)


def test_change_detection(tmp_path):
    base = tmp_path / "base.tif"
    comp = tmp_path / "comp.tif"
    out = tmp_path / "change.tif"
    _make_index(base, 0.7)
    _make_index(comp, 0.4)
    result = detect_index_change(base, comp, out, threshold=0.2)
    assert result.changed_fraction == 1.0
    assert np.isclose(result.mean_delta, -0.3, atol=1e-6)
