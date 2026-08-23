import sys
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from earth_one.events import segment_events
from earth_one.reference import match_events_to_reference


def _raster(path, arr, dtype="float32", nodata=np.nan):
    profile = {
        "driver": "GTiff",
        "height": arr.shape[0],
        "width": arr.shape[1],
        "count": 1,
        "dtype": dtype,
        "crs": "EPSG:32644",
        "transform": from_origin(0, arr.shape[0] * 10, 10, 10),
        "nodata": nodata,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr.astype(dtype), 1)


def test_event_segmentation_and_reference(tmp_path):
    change = tmp_path / "change.tif"
    score = tmp_path / "score.tif"
    event_raster = tmp_path / "events.tif"
    table = tmp_path / "events.csv"
    event_json = tmp_path / "events.json"
    reference = tmp_path / "reference.tif"
    match = tmp_path / "match.csv"

    change_arr = np.zeros((6, 6), dtype=np.float32)
    score_arr = np.zeros((6, 6), dtype=np.float32)

    change_arr[1:4, 1:4] = -0.35
    score_arr[1:4, 1:4] = 0.9
    change_arr[5, 5] = -0.8
    score_arr[5, 5] = 0.9

    _raster(change, change_arr)
    _raster(score, score_arr)

    events = segment_events(
        change, score, event_raster,
        min_pixels=4,
        score_threshold=0.5,
        geojson_path=tmp_path / "events.geojson",
    )

    assert len(events) == 1
    assert events[0].area_pixels == 9

    ref_arr = np.zeros((6, 6), dtype=np.int16)
    ref_arr[1:4, 1:4] = 2
    _raster(reference, ref_arr, dtype="int16", nodata=0)

    result = match_events_to_reference(event_raster, reference, match)
    assert result["events_with_reference"] == 1
    assert result["mean_agreement"] == 1.0
