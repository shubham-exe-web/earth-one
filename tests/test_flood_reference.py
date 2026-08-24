import json
import numpy as np
from affine import Affine

from earth_one.flood_reference import (
    WaterBaselineSpec,
    build_novelty_multiplier,
    load_geojson_reference,
    normalize_water_occurrence,
    permanent_water_mask,
    write_water_baseline_manifest,
)


def test_normalize_water_occurrence():
    arr = np.array([[0, 50, 80, 100], [np.nan, 25, 120, -1]], dtype=np.float32)
    freq, valid = normalize_water_occurrence(arr)
    assert valid[0, 0]
    assert freq[0, 1] == 0.5
    assert freq[0, 2] == 0.8
    assert freq[0, 3] == 1.0
    assert not valid[1, 0]
    assert not valid[1, 2]
    assert not valid[1, 3]


def test_permanent_water_mask():
    freq = np.array([[0.79, 0.80], [0.95, 0.0]], dtype=np.float32)
    valid = np.ones((2, 2), dtype=bool)
    out = permanent_water_mask(freq, valid, threshold=0.80)
    assert not out[0, 0]
    assert out[0, 1]
    assert out[1, 0]
    assert not out[1, 1]


def test_novelty_multiplier():
    freq = np.array([[0.0, 0.4, 0.8], [1.0, 0.2, 0.7]], dtype=np.float32)
    valid = np.ones_like(freq, dtype=bool)
    out = build_novelty_multiplier(freq, valid, permanent_threshold=0.80)
    assert out[0, 0] == 1.0
    assert out[0, 1] == 0.5
    assert out[0, 2] == 0.0
    assert out[1, 0] == 0.0


def test_write_baseline_manifest(tmp_path):
    profile = {
        'width': 4,
        'height': 3,
        'crs': 'EPSG:32644',
        'transform': Affine.translation(500000, 2500000) * Affine.scale(10, -10),
    }
    manifest_path = tmp_path / 'baseline_manifest.json'
    manifest = write_water_baseline_manifest(
        manifest_path,
        '/tmp/jrc_occurrence.tif',
        profile,
        WaterBaselineSpec(),
    )
    assert manifest.schema == 'earth_one_flood_water_baseline_v1.0'
    payload = json.loads(manifest_path.read_text())
    assert payload['dataset'] == 'GSW_1984_2024'
    assert manifest.integrity_hash


def test_load_geojson_reference(tmp_path):
    geojson = {
        'type': 'FeatureCollection',
        'features': [{
            'type': 'Feature',
            'properties': {'event': 'flood'},
            'geometry': {
                'type': 'Polygon',
                'coordinates': [[
                    [0.0, 0.0], [0.0, 1.0], [1.0, 1.0],
                    [1.0, 0.0], [0.0, 0.0]
                ]],
            },
        }],
    }
    path = tmp_path / 'reference.geojson'
    path.write_text(json.dumps(geojson), encoding='utf-8')
    profile = {
        'width': 10,
        'height': 10,
        'transform': Affine.translation(0, 1) * Affine.scale(0.1, -0.1),
        'crs': 'EPSG:4326',
    }
    mask, meta = load_geojson_reference(path, profile)
    assert mask.shape == (10, 10)
    assert mask.any()
    assert meta['source'] == 'Copernicus_EMS'
    assert meta['feature_count'] == 1

def test_load_shapefile_reference(tmp_path):
    import shapefile
    from affine import Affine
    from earth_one.flood_reference import load_vector_reference

    shp_path = tmp_path / "test_ref.shp"
    w = shapefile.Writer(str(shp_path))
    w.field("name", "C")
    w.poly([[[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]])
    w.record("flood_poly_1")
    w.close()

    profile = {
        "width": 10,
        "height": 10,
        "transform": Affine.translation(0, 1) * Affine.scale(0.1, -0.1),
        "crs": "EPSG:4326",
    }
    mask, meta = load_vector_reference(shp_path, profile)
    assert mask.shape == (10, 10)
    assert mask.any()
    assert meta["source"] == "Copernicus_EMS"
    assert meta["feature_count"] == 1
