"""Unit tests for raster mask processing and tri-state confusion matrix decomposition."""

import numpy as np
import pytest
from scripts.evaluate_raster_masks import evaluate_raster_arrays, create_synthetic_event_raster


def test_raster_mask_boolean_logic():
    """Verifies that 2D array mask logic accurately decomposes pixels into resolvable and unresolved domains."""
    shape = (100, 100)
    ref, pred, obs = create_synthetic_event_raster(
        shape=shape,
        ref_pos=500,
        tp=100,
        fp=200,
        unres_total=4000,
        ref_in_unres=150,
        seed=123,
    )
    counts = evaluate_raster_arrays(ref, pred, obs, obs_threshold=0.50)

    assert counts["tp"] == 100
    assert counts["fp"] == 200
    assert counts["fn_unres"] == 150
    assert counts["n_unresolved"] == 4000
    assert counts["n_total"] == 10000

    # Resolvable sum
    assert counts["tp"] + counts["fp"] + counts["fn_res"] + counts["tn_res"] == 6000
    # Unresolved sum
    assert counts["fn_unres"] + counts["tn_unres"] == 4000
    # Total sum
    assert counts["tp"] + counts["fp"] + counts["fn_total"] + counts["tn_total"] == 10000


def test_full_validation_eight_event_reconciliation():
    """Verifies exact 8-event aggregation against Table 2b totals."""
    events = [
        ("EMSR348", 9312, 25, 510, 82628, 764),
        ("EMSR468", 1529, 36, 3096, 182374, 680),
        ("EMSR517", 284, 11, 135, 177750, 108),
        ("EMSR464", 3790, 2065, 86853, 19372, 193),
        ("EMSR357", 6522, 354, 11717, 218010, 4657),
        ("EMSR445", 5246, 0, 1100, 104499, 1159),
        ("EMSR567", 37258, 44, 142, 130855, 7228),
        ("EMSR286", 29030, 171, 463, 255980, 24559),
    ]

    total_tp = 0
    total_fp = 0
    total_fn_res = 0
    total_tn_res = 0
    total_fn_unres = 0
    total_tn_unres = 0

    for act, ref_pos, tp, fp, unres, ref_unres in events:
        ref_arr, pred_arr, obs_arr = create_synthetic_event_raster(
            shape=(512, 512),
            ref_pos=ref_pos,
            tp=tp,
            fp=fp,
            unres_total=unres,
            ref_in_unres=ref_unres,
        )
        counts = evaluate_raster_arrays(ref_arr, pred_arr, obs_arr, obs_threshold=0.50)
        total_tp += counts["tp"]
        total_fp += counts["fp"]
        total_fn_res += counts["fn_res"]
        total_tn_res += counts["tn_res"]
        total_fn_unres += counts["fn_unres"]
        total_tn_unres += counts["tn_unres"]

    assert total_tp == 2706
    assert total_fp == 104016
    assert total_fn_res == 50917
    assert total_tn_res == 768045
    assert total_fn_unres == 39348
    assert total_tn_unres == 1132120
    assert total_fn_res + total_fn_unres == 90265
    assert total_tn_res + total_tn_unres == 1900165
    assert total_tp + total_fp + total_fn_res + total_tn_res + total_fn_unres + total_tn_unres == 2097152
