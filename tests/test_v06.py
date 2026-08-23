import sys
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from earth_one.s1_process import build_s1_request
from earth_one.composite import temporal_median
from earth_one.feature_stack import build_optical_sar_stack
from earth_one.event_score import score_disturbance_candidates


def _raster(path, value, count=1):
    profile = {
        "driver": "GTiff", "height": 2, "width": 2, "count": count,
        "dtype": "float32", "crs": "EPSG:32644",
        "transform": from_origin(0, 20, 10, 10), "nodata": np.nan,
    }
    with rasterio.open(path, "w", **profile) as dst:
        for i in range(1, count + 1):
            dst.write(np.full((2, 2), value + i * 0.01, dtype=np.float32), i)


def test_s1_request():
    req = build_s1_request([80, 20, 80.1, 20.1], "2026-01-01", "2026-01-02", 256, 256)
    assert req["input"]["data"][0]["type"] == "sentinel-1-grd"
    assert req["input"]["data"][0]["processing"]["backCoeff"] == "GAMMA0_TERRAIN"
    assert req["input"]["data"][0]["processing"]["orthorectify"] == "TRUE"


def test_composite(tmp_path):
    a, b, out = tmp_path / "a.tif", tmp_path / "b.tif", tmp_path / "out.tif"
    _raster(a, 0.2)
    _raster(b, 0.6)
    result = temporal_median([a, b], out)
    assert result["valid_fraction"] == 1.0
    with rasterio.open(out) as ds:
        assert np.allclose(ds.read(1), 0.41)


def test_stack_and_score(tmp_path):
    ndvi = tmp_path / "ndvi.tif"
    vv = tmp_path / "vv.tif"
    vh = tmp_path / "vh.tif"
    stack = tmp_path / "stack.tif"
    score = tmp_path / "score.tif"
    _raster(ndvi, 0.5)
    _raster(vv, -0.2)
    _raster(vh, -0.3)
    result = build_optical_sar_stack(ndvi, vv, vh, stack)
    assert result["bands"] == ["NDVI", "VV", "VH"]
    # A synthetic change raster for scoring.
    _raster(stack, 0.3)
    score_result = score_disturbance_candidates(stack, score, threshold=0.2)
    assert score_result["valid_fraction"] == 1.0
