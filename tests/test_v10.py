import sys
from pathlib import Path
import json
import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from earth_one.tracking import track_event_observations


def _geojson(path, date, event_id, x0=0, y0=0, size=1, area=1.0):
    # Simple lon/lat polygon. Tracking projects it internally.
    geom = {
        "type": "Polygon",
        "coordinates": [[
            [x0, y0], [x0 + size, y0],
            [x0 + size, y0 + size], [x0, y0 + size],
            [x0, y0],
        ]],
    }
    payload = {
        "type": "FeatureCollection",
        "observation_date": date,
        "features": [{
            "type": "Feature",
            "properties": {
                "event_id": event_id,
                "area_ha": area,
                "mean_change": -0.3,
                "mean_score": 0.8,
            },
            "geometry": geom,
        }],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_event_tracking(tmp_path):
    a = tmp_path / "2026-01-01.geojson"
    b = tmp_path / "2026-02-01.geojson"
    out = tmp_path / "tracks.json"

    _geojson(a, "2026-01-01", 1, x0=80, y0=20)
    _geojson(b, "2026-02-01", 7, x0=80.001, y0=20.001)

    result = track_event_observations([a, b], out, max_centroid_distance_km=2.0)
    assert result["track_count"] == 1
    assert result["tracks"][0]["observation_count"] == 2
