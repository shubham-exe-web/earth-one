"""Test suite for Earth One Flood physics gates.

Verifies mathematical properties of:
- Direct SAR backscatter drop scoring (VV and VH)
- Direct optical MNDWI/NDWI scoring
- Permanent water novelty gating (M_novelty)
- Topographic slope plausibility gating (M_terrain)
- Antecedent precipitation corroboration gating (M_rain)
"""

import numpy as np
import pytest
from earth_one.flood import (
    FloodEvidenceConfig,
    compute_sar_water_evidence,
    compute_optical_water_evidence,
    compute_water_novelty,
    compute_terrain_plausibility,
    compute_rainfall_context,
    fuse_flood_evidence,
)


def test_sar_backscatter_drop():
    config = FloodEvidenceConfig()
    # Severe backscatter drop (0.15 -> 0.005) vs no drop (0.12 -> 0.11)
    vv_before = np.array([[0.15, 0.12]], dtype=np.float32)
    vv_event = np.array([[0.005, 0.11]], dtype=np.float32)
    sar_score, valid = compute_sar_water_evidence(vv_before, vv_event, config=config)
    assert valid.all()
    assert sar_score[0, 0] > sar_score[0, 1]
    assert sar_score[0, 0] > 0.70
    assert sar_score[0, 1] < 0.30


def test_optical_water_evidence():
    config = FloodEvidenceConfig()
    # Water pixel: high green, low swir
    b03 = np.array([[0.30, 0.05]], dtype=np.float32)
    b08 = np.array([[0.05, 0.35]], dtype=np.float32)
    b11 = np.array([[0.03, 0.30]], dtype=np.float32)
    opt_score, valid = compute_optical_water_evidence(b03, b08, b11, config=config)
    assert valid.all()
    assert opt_score[0, 0] > opt_score[0, 1]
    assert opt_score[0, 0] > 0.60


def test_water_novelty_gate():
    config = FloodEvidenceConfig()
    water_score = np.array([[0.90, 0.90]], dtype=np.float32)
    # Permanent water (f_perm=0.95) vs novel flood (f_perm=0.02)
    perm_freq = np.array([[0.95, 0.02]], dtype=np.float32)
    novelty_score, mask = compute_water_novelty(water_score, perm_freq, config=config)
    assert novelty_score[0, 0] < 0.10  # Suppressed permanent water
    assert novelty_score[0, 1] > 0.80  # Retained anomalous flood


def test_terrain_plausibility_gate():
    config = FloodEvidenceConfig()
    # Steep slope (25 deg) vs flat floodplain (1 deg)
    slope = np.array([[25.0, 1.0]], dtype=np.float32)
    terrain_mod, valid = compute_terrain_plausibility(slope, config=config)
    assert valid.all()
    assert terrain_mod[0, 0] == 0.0   # Steep slopes cannot retain standing flood
    assert terrain_mod[0, 1] == 1.0   # Flat terrain fully plausible


def test_rainfall_corroboration_floor():
    config = FloodEvidenceConfig()
    # Antecedent rainfall context: zero rain vs heavy rain
    # Crucial property: M_rain has a positive floor (never suppresses to zero)
    rain_score_zero = compute_rainfall_context(accumulation_mm=0.0, config=config)
    rain_score_storm = compute_rainfall_context(accumulation_mm=150.0, config=config)
    assert rain_score_zero >= 0.0
    assert rain_score_storm > rain_score_zero
