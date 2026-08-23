import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import numpy as np
import rasterio
from rasterio.transform import from_origin

from earth_one.s1_autonomous import S1AutonomousEngine, S1Scene, validate_raster


def scene(product, dt, rel=19, direction="DESCENDING", mode="IW", pol="DV", platform="S1A", slice_no=11):
    return S1Scene(product, product, dt, platform, direction, rel, 57316, mode, pol, slice_no, [82,22,83,23], None, {})


def test_pair_matching_prefers_same_relative_orbit_and_slice():
    a = [scene("S1A_IW_GRDH_1SDV_20250106T002052_20250106T002117_057316_070D73_D497", "2025-01-06T00:20:52Z")]
    b = [scene("S1A_IW_GRDH_1SDV_20260113T002052_20260113T002117_062741_07B123_1234", "2026-01-13T00:20:52Z")]
    x, y = S1AutonomousEngine.match_pair(a, b)
    assert x.relative_orbit == y.relative_orbit == 19
    assert x.slice_number == y.slice_number == 11


def test_pair_matching_rejects_different_relative_orbit():
    a = [scene("a", "2025-01-06T00:20:52Z", rel=19)]
    b = [scene("b", "2026-01-13T00:20:52Z", rel=20)]
    try:
        S1AutonomousEngine.match_pair(a, b)
    except RuntimeError:
        return
    assert False, "different relative orbit must not match"


def test_validate_raster_rejects_all_zero(tmp_path):
    p = tmp_path / "zero.tif"
    with rasterio.open(p, "w", driver="GTiff", width=10, height=10, count=1, dtype="float32", crs="EPSG:4326", transform=from_origin(82,23,.01,.01)) as ds:
        ds.write(np.zeros((1,10,10), dtype="float32"))
    assert validate_raster(p)["valid"] is False


def test_validate_raster_accepts_real_values(tmp_path):
    p = tmp_path / "real.tif"
    a = np.linspace(0.01, 0.4, 100, dtype="float32").reshape(1,10,10)
    with rasterio.open(p, "w", driver="GTiff", width=10, height=10, count=1, dtype="float32", crs="EPSG:4326", transform=from_origin(82,23,.01,.01)) as ds:
        ds.write(a)
    qc = validate_raster(p)
    assert qc["valid"] is True
    assert qc["max"] > qc["min"]

def test_validate_multiband_rejects_zero_data_band(tmp_path):
    from earth_one.s1_autonomous import validate_multiband_raster
    p = tmp_path / "two_band.tif"
    with rasterio.open(p, "w", driver="GTiff", width=16, height=16, count=2, dtype="float32", crs="EPSG:4326", transform=from_origin(82,23,.01,.01)) as ds:
        ds.write(np.linspace(0.01, 0.4, 256, dtype="float32").reshape(16,16), 1)
        ds.write(np.zeros((16,16), dtype="float32"), 2)
    qc = validate_multiband_raster(p, expected_bands=2)
    assert qc["valid"] is False
    assert qc["bands"][1]["valid"] is False
