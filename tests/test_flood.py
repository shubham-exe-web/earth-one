import pytest
import numpy as np
import rasterio
from affine import Affine

from earth_one.flood import (
    FloodEvidenceConfig,
    FloodDetectionResult,
    compute_sar_water_evidence,
    compute_optical_water_evidence,
    compute_water_novelty,
    compute_terrain_plausibility,
    compute_rainfall_context,
    fuse_flood_evidence,
    segment_flood_events,
    build_flood_alert_payload,
)
from earth_one.events import EventRecord


def test_flood_config_defaults():
    cfg = FloodEvidenceConfig()
    assert cfg.weight_sar == 0.35
    assert cfg.weight_optical == 0.25
    assert cfg.weight_novelty == 0.20
    assert cfg.weight_rain == 0.10
    assert cfg.weight_terrain == 0.10
    assert cfg.min_event_pixels == 4
    assert cfg.pixel_resolution_m == 20.0


def test_sar_water_evidence_computation():
    cfg = FloodEvidenceConfig()
    # Baseline dry land vs Event inundated water (significant backscatter drop)
    vv_before = np.array([[0.15, 0.12], [0.10, 0.14]], dtype=np.float32)
    vv_event = np.array([[0.005, 0.11], [0.002, 0.13]], dtype=np.float32)  # (0,0) and (1,0) flooded

    sar_score, valid = compute_sar_water_evidence(vv_before, vv_event, config=cfg)
    assert valid.all()
    assert sar_score.shape == (2, 2)
    assert sar_score[0, 0] > 0.70  # Flooded pixel has high SAR water evidence
    assert sar_score[1, 0] > 0.70  # Flooded pixel has high SAR water evidence
    assert sar_score[0, 1] < 0.30  # Unflooded pixel has low score


def test_sar_dual_pol_evidence():
    cfg = FloodEvidenceConfig()
    vv_b = np.full((4, 4), 0.15, dtype=np.float32)
    vv_e = np.full((4, 4), 0.008, dtype=np.float32)
    vh_b = np.full((4, 4), 0.03, dtype=np.float32)
    vh_e = np.full((4, 4), 0.001, dtype=np.float32)

    sar_score, valid = compute_sar_water_evidence(vv_b, vv_e, vh_b, vh_e, config=cfg)
    assert valid.all()
    assert np.all(sar_score > 0.75)


def test_optical_water_evidence_ndwi_mndwi():
    cfg = FloodEvidenceConfig()
    # Water has high green (B03) and low NIR (B08) & SWIR (B11)
    b03 = np.array([[0.20, 0.05], [0.18, 0.06]], dtype=np.float32)
    b08 = np.array([[0.04, 0.35], [0.03, 0.30]], dtype=np.float32)
    b11 = np.array([[0.02, 0.25], [0.02, 0.20]], dtype=np.float32)
    scl = np.array([[4, 4], [4, 9]], dtype=np.int32)  # (1,1) is cloud (SCL=9)

    opt_score, valid = compute_optical_water_evidence(b03, b08, b11, scl_mask=scl, config=cfg)
    assert valid[0, 0] == True
    assert valid[1, 1] == False  # Cloud pixel masked as invalid
    assert opt_score[0, 0] > 0.70  # High optical water evidence
    assert opt_score[0, 1] < 0.30  # Vegetation has low water evidence


def test_water_novelty():
    cfg = FloodEvidenceConfig()
    water_score = np.array([[0.85, 0.85], [0.10, 0.90]], dtype=np.float32)
    perm_freq = np.array([[0.95, 0.00], [0.00, 0.20]], dtype=np.float32)

    novelty, valid = compute_water_novelty(water_score, perm_freq, config=cfg)
    assert valid.all()
    assert novelty[0, 0] == 0.0  # Permanent lake is suppressed (0.0 novelty)
    assert novelty[0, 1] > 0.80  # Newly inundated dry land has high novelty score
    assert novelty[1, 1] > 0.60  # Low-frequency seasonal inundation retains novelty


def test_terrain_plausibility():
    cfg = FloodEvidenceConfig()
    slope = np.array([[1.5, 6.0], [12.0, 25.0]], dtype=np.float32)

    terrain_score, valid = compute_terrain_plausibility(slope, config=cfg)
    assert valid.all()
    assert terrain_score[0, 0] == 1.0  # Flat terrain (1.5 deg) fully plausible
    assert 0.0 < terrain_score[1, 0] < 1.0  # Moderate slope (12 deg) attenuated
    assert terrain_score[1, 1] == 0.0  # Steep mountain slope (25 deg) constrained to 0.0


def test_rainfall_context():
    cfg = FloodEvidenceConfig()
    # High rainfall (150 mm)
    r_high = compute_rainfall_context(accumulation_mm=150.0, anomaly_std=2.5, hours_since_peak=6.0, config=cfg)
    # Low rainfall (5 mm)
    r_low = compute_rainfall_context(accumulation_mm=5.0, anomaly_std=0.0, hours_since_peak=48.0, config=cfg)

    assert r_high > 0.70
    assert r_low <= 0.10


def test_evidence_fusion_full_and_missing():
    cfg = FloodEvidenceConfig()
    shape = (10, 10)
    sar = np.full(shape, 0.85, dtype=np.float32)
    opt = np.full(shape, 0.75, dtype=np.float32)
    novelty = np.full(shape, 0.90, dtype=np.float32)
    terrain = np.full(shape, 1.0, dtype=np.float32)
    rain = 0.80

    # 1. Full 5-channel fusion (gated physics strategy)
    res_full = fuse_flood_evidence(
        sar_evidence=sar, optical_evidence=opt, novelty_evidence=novelty,
        terrain_plausibility=terrain, rainfall_score=rain, config=cfg
    )
    assert res_full.status == "accepted"
    assert len(res_full.available_channels) == 5
    assert res_full.score_statistics["mean"] > 0.65
    assert res_full.candidate_pixels == 100

    # 2. Linear blend strategy test
    cfg_linear = FloodEvidenceConfig(fusion_strategy="linear_blend")
    res_linear = fuse_flood_evidence(
        sar_evidence=sar, optical_evidence=opt, novelty_evidence=novelty,
        terrain_plausibility=terrain, rainfall_score=rain, config=cfg_linear
    )
    assert res_linear.score_statistics["mean"] > 0.80

    # 2. SAR-only fusion (cloudy flood scene, missing optical)
    res_sar = fuse_flood_evidence(
        sar_evidence=sar, optical_evidence=None, novelty_evidence=novelty,
        terrain_plausibility=terrain, rainfall_score=None, config=cfg
    )
    assert res_sar.status == "accepted"
    assert "optical" not in res_sar.available_channels
    assert "sar" in res_sar.available_channels
    assert res_sar.score_statistics["mean"] > 0.70


def test_flood_event_segmentation():
    # Create synthetic grid with two flood patches (one 6 px, one 2 px)
    grid = np.zeros((10, 10), dtype=np.float32)
    grid[1:4, 1:3] = 0.75  # 6 pixels >= 0.5 (above min 4 px)
    grid[7:9, 7] = 0.80    # 2 pixels >= 0.5 (below min 4 px -> filtered out)
    valid = np.ones((10, 10), dtype=bool)

    t = Affine.translation(78.0, 22.0) * Affine.scale(0.0002, -0.0002)

    events = segment_flood_events(
        grid, valid_mask=valid, transform=t, threshold=0.50, min_pixels=4
    )

    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, EventRecord)
    assert ev.event_id == 1
    assert ev.area_pixels == 6
    assert ev.mean_score == pytest.approx(0.75)
    assert ev.geometry is not None
    assert ev.event_version == "2.0.0-flood"


def test_build_flood_alert_payload():
    cfg = FloodEvidenceConfig()
    sar = np.full((10, 10), 0.85, dtype=np.float32)
    res = fuse_flood_evidence(sar_evidence=sar, config=cfg)

    events = [
        EventRecord(
            event_id=1, area_pixels=50, area_m2=20000.0, area_ha=2.0,
            mean_change=0.85, mean_score=0.85,
            min_row=0, min_col=0, max_row=5, max_col=10,
            geometry=None, event_version="2.0.0-flood"
        )
    ]

    alert = build_flood_alert_payload(
        events=events, aoi_name="Assam_Valley", target_date="2026-07-15",
        detection_result=res, config=cfg
    )

    assert alert["hazard_type"] == "FLOOD_INUNDATION"
    assert alert["aoi_name"] == "Assam_Valley"
    assert alert["total_event_count"] == 1
    assert alert["total_flooded_area_ha"] == 2.0
    assert alert["severity"] in ["ADVISORY", "WARNING", "CRITICAL"]
    assert "sar" in alert["available_evidence_channels"]
    assert len(alert["provenance_hash"]) == 64
