from __future__ import annotations

"""Drought Module 3 Genuine Multi-Temporal Compositing & Rolling Climatology Builder (Phase 4).

Derives genuine 1M, 3M, and 6M rolling vegetation composites from chronological scene sequences:
- 1M: 30-day robust median / maximum value composite (MVC)
- 3M: 90-day rolling mean composite of valid observations
- 6M: 180-day rolling mean composite of valid observations
"""

import hashlib
from dataclasses import dataclass
from typing import Sequence
import numpy as np


@dataclass
class MultiTemporalCompositeResult:
    """True rolling multi-window vegetation composite container."""
    ndvi_1m_current: np.ndarray
    ndvi_3m_rolling: np.ndarray
    ndvi_6m_rolling: np.ndarray
    clear_observation_count_1m: np.ndarray
    clear_observation_count_3m: np.ndarray
    clear_observation_count_6m: np.ndarray
    valid_mask: np.ndarray
    provenance_hash: str


def compute_true_rolling_composites(
    chronological_ndvi_stack: np.ndarray,      # Shape: (T, H, W)
    chronological_valid_stack: np.ndarray,     # Shape: (T, H, W) boolean
    window_1m_slice: slice = slice(-2, None),  # Last 2 scenes (~30 days)
    window_3m_slice: slice = slice(-6, None),  # Last 6 scenes (~90 days)
    window_6m_slice: slice = slice(-12, None), # Last 12 scenes (~180 days)
) -> MultiTemporalCompositeResult:
    """Compute true rolling multi-window vegetation composites from a chronological scene stack."""
    T, H, W = chronological_ndvi_stack.shape

    # 1. 1-Month Composite (Robust Max-Value / Median Composite of clear observations)
    stack_1m = chronological_ndvi_stack[window_1m_slice]
    valid_1m = chronological_valid_stack[window_1m_slice]
    count_1m = np.sum(valid_1m, axis=0)

    # Use masked arrays to compute true clear-sky composite
    stack_1m_masked = np.where(valid_1m, stack_1m, np.nan)
    with np.errstate(all="ignore"):
        ndvi_1m = np.nanmedian(stack_1m_masked, axis=0)
        # Fallback to nanmax if median is NaN
        nan_locs = np.isnan(ndvi_1m)
        if np.any(nan_locs):
            ndvi_1m[nan_locs] = np.nanmax(stack_1m_masked, axis=0)[nan_locs]

    # 2. 3-Month Rolling Mean Composite
    stack_3m = chronological_ndvi_stack[window_3m_slice]
    valid_3m = chronological_valid_stack[window_3m_slice]
    count_3m = np.sum(valid_3m, axis=0)
    stack_3m_masked = np.where(valid_3m, stack_3m, np.nan)
    with np.errstate(all="ignore"):
        ndvi_3m = np.nanmean(stack_3m_masked, axis=0)

    # 3. 6-Month Rolling Mean Composite
    stack_6m = chronological_ndvi_stack[window_6m_slice]
    valid_6m = chronological_valid_stack[window_6m_slice]
    count_6m = np.sum(valid_6m, axis=0)
    stack_6m_masked = np.where(valid_6m, stack_6m, np.nan)
    with np.errstate(all="ignore"):
        ndvi_6m = np.nanmean(stack_6m_masked, axis=0)

    valid_overall = np.isfinite(ndvi_1m) & (count_1m >= 1)

    prov = hashlib.sha256(
        f"TRUE_COMPOSITE_{T}_{float(np.nanmean(ndvi_1m)):.4f}_{float(np.nanmean(ndvi_3m)):.4f}_{float(np.nanmean(ndvi_6m)):.4f}".encode()
    ).hexdigest()

    return MultiTemporalCompositeResult(
        ndvi_1m_current=np.nan_to_num(ndvi_1m, nan=0.0).astype(np.float32),
        ndvi_3m_rolling=np.nan_to_num(ndvi_3m, nan=0.0).astype(np.float32),
        ndvi_6m_rolling=np.nan_to_num(ndvi_6m, nan=0.0).astype(np.float32),
        clear_observation_count_1m=count_1m.astype(np.int32),
        clear_observation_count_3m=count_3m.astype(np.int32),
        clear_observation_count_6m=count_6m.astype(np.int32),
        valid_mask=valid_overall,
        provenance_hash=prov,
    )
