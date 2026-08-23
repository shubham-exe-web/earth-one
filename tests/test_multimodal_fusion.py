
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin

from earth_one.multimodal_fusion import FeatureSpec, build_multimodal_stack, inspect_feature


def _write(path: Path, arr: np.ndarray, crs="EPSG:4326"):
    transform = from_origin(0, 1, 1, 1)
    profile = {
        "driver": "GTiff",
        "height": arr.shape[0],
        "width": arr.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": crs,
        "transform": transform,
        "nodata": np.nan,
    }
    with rasterio.open(path, "w", **profile) as ds:
        ds.write(arr.astype("float32"), 1)


def test_fusion_builds_valid_stack(tmp_path):
    ndvi = tmp_path / "ndvi.tif"
    vv = tmp_path / "vv.tif"
    vh = tmp_path / "vh.tif"
    _write(ndvi, np.array([[0.2, 0.3], [0.4, 0.5]], dtype=np.float32))
    _write(vv, np.array([[0.1, 0.2], [0.2, 0.4]], dtype=np.float32))
    _write(vh, np.array([[0.05, 0.1], [0.1, 0.2]], dtype=np.float32))

    out = tmp_path / "stack.tif"
    result = build_multimodal_stack(
        [
            FeatureSpec("NDVI", ndvi, "sentinel-2"),
            FeatureSpec("VV", vv, "sentinel-1"),
            FeatureSpec("VH", vh, "sentinel-1"),
        ],
        out,
        target_feature="NDVI",
    )
    assert result["status"] == "accepted"
    with rasterio.open(out) as ds:
        assert ds.count == 3
        assert ds.descriptions == ("NDVI", "VV", "VH")


def test_fusion_rejects_constant_input(tmp_path):
    ndvi = tmp_path / "ndvi.tif"
    vv = tmp_path / "vv.tif"
    vh = tmp_path / "vh.tif"
    _write(ndvi, np.ones((2, 2), dtype=np.float32))
    _write(vv, np.array([[0.1, 0.2], [0.2, 0.3]], dtype=np.float32))
    _write(vh, np.array([[0.05, 0.1], [0.1, 0.2]], dtype=np.float32))

    try:
        inspect = inspect_feature(ndvi)
        assert inspect["valid"] is False
    finally:
        pass


def test_fusion_rejects_zero_input(tmp_path):
    bad = tmp_path / "bad.tif"
    _write(bad, np.zeros((2, 2), dtype=np.float32))
    assert inspect_feature(bad)["valid"] is False
