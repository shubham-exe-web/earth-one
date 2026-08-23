from __future__ import annotations

"""NASA MCD64A1 Native-Scale (500m) Burned-Area Validation & QA Engine.

Evaluates high-resolution Earth One predictions against NASA MCD64A1 Collection 6.1
at the native reference spatial scale (500m MODIS Sinusoidal projection grid).

NASA MCD64A1 QA Bit Semantics (Collection 6.1):
- Bit 0: Land / Water mask (1 = Land, 0 = Water)
- Bit 1: Valid data flag (1 = Sufficient valid reflectance data, 0 = Insufficient)
- Bit 2: Shortened mapping period (0 = Unshortened / full month, 1 = Shortened)
- Bit 3: Contextual relabeling (0 = Not contextually relabeled, 1 = Relabeled)
- Bits 5-7: Special condition codes for unburned cells

Features:
- Exact native Sinusoidal georegistered window extraction
- Area-weighted fractional aggregation: F_EarthOne = N_alarm_px / N_cell_px
- Rigorous NASA QA bitmask decoding & high-confidence filtering
- Area accounting: Reference Burned Area, Predicted Burned Area, Commissioned/Omitted Area, Bias (ha)
- Standardized statistical metrics: Precision, Recall, F1, MCC, Area Estimation Ratio
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling, transform_bounds
from rasterio.windows import from_bounds


@dataclass(frozen=True)
class NativeMCDConfig:
    """Configuration for Native-Scale MCD64A1 validation."""
    fractional_alarm_thresholds: tuple[float, ...] = (0.10, 0.20, 0.33, 0.50)
    modis_cell_nominal_ha: float = 21.466  # (463.31m)^2 in hectares
    output_dir: str = "data/results/experiment1"


def decode_mcd64a1_qa_bits(qa_array: np.ndarray) -> dict[str, np.ndarray]:
    """
    Decode NASA MCD64A1 Collection 6.1 8-bit QA layer.
    """
    qa = qa_array.astype(np.uint8)
    is_land = (qa & 1) == 1
    is_valid_data = ((qa >> 1) & 1) == 1
    is_unshortened = ((qa >> 2) & 1) == 0
    is_not_contextually_relabeled = ((qa >> 3) & 1) == 0

    # High-confidence: Land + Valid reflectance time series + Full month + Not contextually relabeled
    high_confidence = is_land & is_valid_data & is_unshortened & is_not_contextually_relabeled

    return {
        "is_land": is_land,
        "is_valid_data": is_valid_data,
        "is_unshortened": is_unshortened,
        "is_not_contextually_relabeled": is_not_contextually_relabeled,
        "high_confidence_burn": high_confidence,
    }


def evaluate_native_mcd64a1_agreement(
    fine_prediction_grid: np.ndarray,
    fine_valid_mask: np.ndarray,
    fine_profile: dict[str, Any],
    native_burn_date: np.ndarray,
    native_qa: np.ndarray,
    native_profile: dict[str, Any],
    fraction_threshold: float = 0.20,
    filter_qa_high_confidence: bool = True,
    modis_cell_ha: float = 21.466,
) -> dict[str, Any]:
    """
    Compute native-scale burned-area agreement metrics in MODIS native Sinusoidal space.
    """
    qa_decoded = decode_mcd64a1_qa_bits(native_qa)
    
    # Base valid mask: Land & Sufficient valid data
    native_valid_mask = qa_decoded["is_land"] & qa_decoded["is_valid_data"]

    # Reference Burned Mask
    if filter_qa_high_confidence:
        ref_burned = (native_burn_date > 0) & qa_decoded["high_confidence_burn"] & native_valid_mask
    else:
        ref_burned = (native_burn_date > 0) & native_valid_mask

    # Project fine-scale predictions into native Sinusoidal space via area-weighted averaging
    fine_float = (fine_prediction_grid & fine_valid_mask).astype(np.float32)
    native_fraction = np.zeros(native_burn_date.shape, dtype=np.float32)

    reproject(
        source=fine_float,
        destination=native_fraction,
        src_transform=fine_profile["transform"],
        src_crs=fine_profile["crs"],
        dst_transform=native_profile["transform"],
        dst_crs=native_profile["crs"],
        resampling=Resampling.average,
    )

    coarse_pred_binary = (native_fraction >= fraction_threshold) & native_valid_mask

    tp = int(np.sum(coarse_pred_binary & ref_burned))
    fp = int(np.sum(coarse_pred_binary & (~ref_burned) & native_valid_mask))
    fn = int(np.sum((~coarse_pred_binary) & ref_burned))
    tn = int(np.sum((~coarse_pred_binary) & (~ref_burned) & native_valid_mask))

    precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1 = float(2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    denom = np.sqrt(float((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)))
    mcc = float((tp * tn - fp * fn) / denom) if denom > 0 else 0.0

    # Area metrics
    ref_ha = float(np.sum(ref_burned) * modis_cell_ha)
    pred_ha = float(np.sum(coarse_pred_binary) * modis_cell_ha)
    tp_ha = float(tp * modis_cell_ha)
    comm_ha = float(fp * modis_cell_ha)
    om_ha = float(fn * modis_cell_ha)
    bias_ha = float(pred_ha - ref_ha)
    bias_ratio = float(pred_ha / ref_ha) if ref_ha > 0 else 0.0

    return {
        "fraction_threshold": fraction_threshold,
        "qa_filtered_high_confidence": filter_qa_high_confidence,
        "total_native_cells": int(native_burn_date.size),
        "valid_land_cells": int(np.sum(native_valid_mask)),
        "reference_burned_cells": int(np.sum(ref_burned)),
        "predicted_burned_cells": int(np.sum(coarse_pred_binary)),
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "metrics": {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "mcc": mcc,
        },
        "area_accounting_ha": {
            "reference_burned_area_ha": ref_ha,
            "predicted_burned_area_ha": pred_ha,
            "correctly_mapped_burned_area_ha": tp_ha,
            "commissioned_area_ha": comm_ha,
            "omitted_area_ha": om_ha,
            "area_bias_ha": bias_ha,
            "area_bias_ratio": bias_ratio,
        },
    }
