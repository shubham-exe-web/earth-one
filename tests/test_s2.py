import sys
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from earth_one.s2 import DEFAULT_MASK_CLASSES


def test_default_s2_mask_classes():
    assert 8 in DEFAULT_MASK_CLASSES
    assert 9 in DEFAULT_MASK_CLASSES
    assert 10 in DEFAULT_MASK_CLASSES
    assert 4 not in DEFAULT_MASK_CLASSES
    assert 5 not in DEFAULT_MASK_CLASSES


def test_small_raster_can_be_read(tmp_path):
    path = tmp_path / "x.tif"
    data = np.ones((5, 5), dtype=np.float32)
    with rasterio.open(
        path, "w", driver="GTiff",
        height=5, width=5, count=1,
        dtype="float32", crs="EPSG:32644",
        transform=from_origin(0, 50, 10, 10),
    ) as dst:
        dst.write(data, 1)

    with rasterio.open(path) as ds:
        assert ds.crs.to_string() == "EPSG:32644"
        assert ds.read(1).shape == (5, 5)
