import numpy as np
from earth_one.drought.events import DroughtEventRecord, DroughtSegmentationResult
from earth_one.drought.tracking import MultiEpochDroughtTracker, compute_mask_iou


def test_mask_iou_computation():
    mask1 = np.zeros((20, 20), dtype=bool)
    mask2 = np.zeros((20, 20), dtype=bool)

    mask1[0:10, 0:10] = True  # 100 px
    mask2[5:15, 0:10] = True  # 100 px, intersection = 50 px, union = 150 px

    iou = compute_mask_iou(mask1, mask2)
    assert np.isclose(iou, 50.0 / 150.0)  # ~0.333


def test_multi_epoch_spatial_tracking():
    tracker = MultiEpochDroughtTracker(iou_overlap_threshold=0.15)
    shape = (50, 50)

    # Epoch 1: Drought event at (10..30, 10..30)
    raster_e1 = np.zeros(shape, dtype=np.uint8)
    raster_e1[10:30, 10:30] = 1
    ev1 = DroughtEventRecord(
        event_id=1, area_expected_ha=16.0, area_sensitivity_low_ha=12.0, area_sensitivity_high_ha=20.0,
        area_sensitivity_margin_ha=4.0, area_sensitivity_pct=25.0, pixel_count=400,
        mean_severity=0.65, peak_severity=0.75, mean_observability=0.90, is_well_observed=True,
        centroid_row=20.0, centroid_col=20.0, bounding_box=(10, 10, 30, 30), provenance_hash="E1",
    )
    seg1 = DroughtSegmentationResult(1, 16.0, [ev1], raster_e1, 0.04, "SEG1")
    tracks_e1 = tracker.update_epoch(seg1, epoch_index=1)
    assert len(tracks_e1) == 1
    assert tracks_e1[0].track_id == 1
    assert tracks_e1[0].duration_epochs == 1

    # Epoch 2: Expanding drought event overlapping at (12..35, 10..35)
    raster_e2 = np.zeros(shape, dtype=np.uint8)
    raster_e2[12:35, 10:35] = 1
    ev2 = DroughtEventRecord(
        event_id=1, area_expected_ha=23.0, area_sensitivity_low_ha=18.0, area_sensitivity_high_ha=28.0,
        area_sensitivity_margin_ha=5.0, area_sensitivity_pct=21.7, pixel_count=575,
        mean_severity=0.78, peak_severity=0.85, mean_observability=0.90, is_well_observed=True,
        centroid_row=23.5, centroid_col=22.5, bounding_box=(12, 10, 35, 35), provenance_hash="E2",
    )
    seg2 = DroughtSegmentationResult(1, 23.0, [ev2], raster_e2, 0.04, "SEG2")
    tracks_e2 = tracker.update_epoch(seg2, epoch_index=2)
    assert len(tracks_e2) == 1
    assert tracks_e2[0].track_id == 1
    assert tracks_e2[0].duration_epochs == 2
    assert tracks_e2[0].area_trajectory_ha == [16.0, 23.0]
    assert tracks_e2[0].peak_severity == 0.85
