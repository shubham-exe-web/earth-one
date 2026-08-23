from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin

from earth_one.event_validation import (
    EventValidationConfig,
    ingest_reference_mask,
    evaluate_event_detection,
    evaluate_point_event_corroboration,
    _calculate_geodetic_pixel_area,
)


def _create_synthetic_profile(width=64, height=64):
    return {
        "driver": "GTiff",
        "dtype": "uint8",
        "nodata": 255,
        "width": width,
        "height": height,
        "count": 1,
        "crs": "EPSG:4326",
        "transform": from_origin(82.60, 22.45, 0.001, 0.001),
    }


def test_calculate_geodetic_pixel_area():
    profile = _create_synthetic_profile(1024, 1024)
    total_km2, pixel_ha = _calculate_geodetic_pixel_area(profile)
    assert total_km2 > 0
    assert pixel_ha > 0


def test_ingest_reference_mask_numpy():
    profile = _create_synthetic_profile(32, 32)
    arr = np.zeros((32, 32), dtype=bool)
    arr[5:10, 5:10] = True
    mask = ingest_reference_mask(arr, profile)
    assert mask.shape == (32, 32)
    assert bool(mask[7, 7]) is True
    assert bool(mask[0, 0]) is False


def test_ingest_reference_mask_geojson():
    profile = _create_synthetic_profile(32, 32)
    geojson_data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [82.605, 22.445],
                        [82.615, 22.445],
                        [82.615, 22.435],
                        [82.605, 22.435],
                        [82.605, 22.445],
                    ]]
                },
                "properties": {"event_id": 1}
            }
        ]
    }
    mask = ingest_reference_mask(geojson_data, profile)
    assert mask.shape == (32, 32)
    assert np.count_nonzero(mask) > 0


def test_evaluate_event_detection_perfect_match():
    profile = _create_synthetic_profile(32, 32)
    ref = np.zeros((32, 32), dtype=bool)
    ref[5:9, 5:9] = True
    ref[15:18, 15:18] = True

    pred = np.zeros((32, 32), dtype=bool)
    pred[5:9, 5:9] = True
    pred[15:18, 15:18] = True

    cfg = EventValidationConfig(min_alarm_pixels=4)
    res = evaluate_event_detection(pred, ref, profile, config=cfg)

    assert res["event_summary"]["total_reference_objects"] == 2
    assert res["event_summary"]["total_predicted_alarms"] == 2
    tau_05 = res["object_metrics_by_iou"]["tau_0.50"]
    assert tau_05["matched_events"] == 2
    assert tau_05["object_recall"] == 1.0
    assert tau_05["object_precision"] == 1.0
    assert tau_05["object_f1"] == 1.0
    assert tau_05["mean_matched_iou"] == 1.0


def test_evaluate_event_detection_alarm_filter_and_bipartite():
    profile = _create_synthetic_profile(32, 32)
    ref = np.zeros((32, 32), dtype=bool)
    ref[5:9, 5:9] = True

    pred = np.zeros((32, 32), dtype=bool)
    pred[5:8, 5:8] = True
    pred[25, 25:27] = True
    pred[20:24, 20:24] = True

    cfg = EventValidationConfig(min_alarm_pixels=4, iou_thresholds=(0.10, 0.50))
    res = evaluate_event_detection(pred, ref, profile, config=cfg)

    assert res["event_summary"]["total_predicted_alarms"] == 2
    assert res["event_summary"]["filtered_alarms_count"] == 1

    tau_05 = res["object_metrics_by_iou"]["tau_0.50"]
    assert tau_05["matched_events"] == 1
    assert tau_05["object_recall"] == 1.0
    assert tau_05["object_precision"] == 0.5
    assert np.isclose(tau_05["object_f1"], 2 * (1.0 * 0.5) / 1.5)


def test_evaluate_event_detection_empty_cases():
    profile = _create_synthetic_profile(16, 16)
    empty = np.zeros((16, 16), dtype=bool)
    res = evaluate_event_detection(empty, empty, profile)
    assert res["event_summary"]["total_reference_objects"] == 0
    assert res["event_summary"]["total_predicted_alarms"] == 0
    assert res["pixel_metrics"]["true_positives"] == 0


def test_evaluate_point_event_corroboration():
    profile = _create_synthetic_profile(64, 64)
    pred = np.zeros((64, 64), dtype=bool)
    pred[10:15, 10:15] = True

    points = [
        {"longitude": 82.6125, "latitude": 22.4375, "acq_date": "2025-03-01", "frp": 10.0},
        {"longitude": 82.6500, "latitude": 22.4000, "acq_date": "2025-06-05", "frp": 1.5},
    ]

    res = evaluate_point_event_corroboration(
        pred,
        points,
        profile,
        spatial_tolerance_meters=[100.0, 500.0, 5000.0],
        start_date="2025-01-01",
        end_date="2025-12-31"
    )

    assert res["total_predicted_alarms"] == 1
    assert res["temporal_window"]["total_points_in_window"] == 2
    r500 = res["corroboration_by_radius"]["radius_500m"]
    assert r500["corroborated_alarm_objects"] == 1
    assert r500["alarm_corroboration_rate"] == 1.0
    assert r500["recovered_active_fire_points"] == 1
    assert r500["hotspot_recovery_rate"] == 0.5
    assert r500["high_frp_ge_5mw_recovery_rate"] == 1.0
    assert "temporal_lag_breakdown" in res
