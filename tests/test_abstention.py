"""Test suite for Earth One Flood continuous observability and resolution-aware abstention.

Verifies:
- Continuous Observability Index formulation (O in [0.0, 1.0])
- Tri-state contract (FLOOD, NO_FLOOD, UNRESOLVED)
- Sensor blackout fail-safe (D_validity = 0 -> O = 0 -> UNRESOLVED)
"""

import numpy as np
import pytest
from earth_one.flood_tristate import (
    compute_continuous_observability_index,
    compute_tristate_flood_decision,
)


def test_tristate_classification_rules():
    shape = (16, 16)
    slope = np.full(shape, 1.0, dtype=np.float32)
    # Set right half to steep mountains
    slope[:, 8:] = 25.0
    elevation = np.full(shape, 50.0, dtype=np.float32)
    occurrence = np.zeros(shape, dtype=np.float32)
    valid_mask = np.ones(shape, dtype=bool)

    O, stats = compute_continuous_observability_index(
        valid_mask=valid_mask,
        slope_deg=slope,
        elevation_m=elevation,
        jrc_occurrence=occurrence,
    )

    # Flat floodplain in left center is highly observable
    assert O[8, 4] >= 0.70
    # Steep mountains in right center are completely unobservable
    assert O[8, 12] == 0.0

    # Decision testing
    scores = np.full(shape, 0.65, dtype=np.float32)  # High candidate score everywhere
    res = compute_tristate_flood_decision(
        flood_score=scores,
        valid_mask=valid_mask,
        slope_deg=slope,
        elevation_m=elevation,
        jrc_occurrence=occurrence,
        detection_threshold=0.20,
        observability_threshold=0.50,
    )

    # Left side (flat, O >= 0.50) -> FLOOD
    assert res.flood_mask[8, 4] == True
    assert res.unresolved_mask[8, 4] == False

    # Right side (steep, O < 0.50) -> UNRESOLVED (abstained despite high score!)
    assert res.flood_mask[8, 12] == False
    assert res.unresolved_mask[8, 12] == True


def test_sensor_blackout_abstention():
    shape = (16, 16)
    slope = np.full(shape, 1.0, dtype=np.float32)
    elevation = np.full(shape, 50.0, dtype=np.float32)
    occurrence = np.zeros(shape, dtype=np.float32)
    # Complete telemetry loss: valid_mask = False
    valid_mask = np.zeros(shape, dtype=bool)

    O, _ = compute_continuous_observability_index(
        valid_mask=valid_mask,
        slope_deg=slope,
        elevation_m=elevation,
        jrc_occurrence=occurrence,
    )
    assert np.all(O == 0.0)  # Complete blackout enforces O=0 everywhere

    res = compute_tristate_flood_decision(
        flood_score=np.full(shape, 0.95, dtype=np.float32),
        valid_mask=valid_mask,
        slope_deg=slope,
        elevation_m=elevation,
        jrc_occurrence=occurrence,
    )
    assert np.all(res.unresolved_mask == True)
    assert np.all(res.flood_mask == False)
    assert np.all(res.no_flood_mask == False)


def test_tristate_partition_after_morphological_opening():
    shape = (16, 16)
    slope = np.full(shape, 1.0, dtype=np.float32)
    elevation = np.full(shape, 50.0, dtype=np.float32)
    occurrence = np.zeros(shape, dtype=np.float32)
    valid_mask = np.ones(shape, dtype=bool)
    # Right edge unobservable
    slope[:, 12:] = 25.0

    scores = np.full(shape, 0.05, dtype=np.float32)
    # Contiguous 3x3 flood patch that survives 2x2 binary opening
    scores[4:7, 4:7] = 0.85
    # Isolated 1x1 speckle pixel in resolvable zone that will be removed by 2x2 opening
    scores[2, 2] = 0.85

    res = compute_tristate_flood_decision(
        flood_score=scores,
        valid_mask=valid_mask,
        slope_deg=slope,
        elevation_m=elevation,
        jrc_occurrence=occurrence,
        detection_threshold=0.20,
        observability_threshold=0.50,
    )

    # Isolated pixel (2, 2) must become NO_FLOOD, never UNRESOLVED or unclassified
    assert res.resolvable_mask[2, 2] == True
    assert res.flood_mask[2, 2] == False
    assert res.no_flood_mask[2, 2] == True
    assert res.unresolved_mask[2, 2] == False

    # Mutually exclusive and exhaustive tri-state partition over all pixels
    assert not np.any(res.flood_mask & res.no_flood_mask)
    assert not np.any(res.flood_mask & res.unresolved_mask)
    assert not np.any(res.no_flood_mask & res.unresolved_mask)
    assert np.all(res.flood_mask | res.no_flood_mask | res.unresolved_mask)
    assert res.flood_pixels + res.no_flood_pixels + res.unresolved_pixels == res.total_pixels
