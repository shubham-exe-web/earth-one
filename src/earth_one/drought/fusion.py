from __future__ import annotations

"""Drought Module 3 Deterministic Multi-Modal Evidence Fusion Engine."""

import hashlib
from dataclasses import dataclass
import numpy as np

from .config import DroughtConfig, ModalityWeights, TemporalWindowWeights
from .anomalies import MultiWindowAnomalies
from .regime import RegimeClassificationResult


@dataclass
class DroughtEvidenceBreakdown:
    """Component evidence scores for each analytical channel."""
    vegetation_stress_score: np.ndarray       # E_veg in [0, 1]
    precipitation_deficit_score: np.ndarray   # E_precip in [0, 1]
    soil_moisture_deficit_score: np.ndarray   # E_sm in [0, 1]
    thermal_stress_score: np.ndarray          # E_thermal in [0, 1]
    fused_drought_score: np.ndarray           # S_drought in [0, 1]
    modality_weights_applied: ModalityWeights
    provenance_hash: str


def z_to_evidence(z_deficit: np.ndarray, max_deficit_z: float = 2.0) -> np.ndarray:
    """Convert standardized anomaly deficit (-z) into normalized evidence in [0, 1]."""
    # Negative z indicates stress/deficit; clip between 0.0 and 1.0
    ev = -z_deficit / max_deficit_z
    return np.clip(ev, 0.0, 1.0).astype(np.float32)


def fuse_drought_evidence(
    anomalies: MultiWindowAnomalies,
    regime_context: RegimeClassificationResult,
    config: DroughtConfig = DroughtConfig(),
) -> DroughtEvidenceBreakdown:
    """Deterministically fuse multimodal hydroclimatic and vegetation anomalies."""
    tw = config.temporal_weights
    mw = regime_context.recommended_modality_weights

    # 1. Vegetation Stress Evidence (Multi-window weighted)
    e_veg_1m = z_to_evidence(anomalies.veg_z_1m)
    e_veg_3m = z_to_evidence(anomalies.veg_z_3m)
    e_veg_6m = z_to_evidence(anomalies.veg_z_6m)
    e_veg = tw.window_1m * e_veg_1m + tw.window_3m * e_veg_3m + tw.window_6m * e_veg_6m

    # 2. Precipitation Deficit Evidence (SPI-like multi-window weighted)
    e_pr_1m = z_to_evidence(anomalies.precip_z_1m)
    e_pr_3m = z_to_evidence(anomalies.precip_z_3m)
    e_pr_6m = z_to_evidence(anomalies.precip_z_6m)
    e_precip = tw.window_1m * e_pr_1m + tw.window_3m * e_pr_3m + tw.window_6m * e_pr_6m

    # 3. Soil Moisture Deficit Evidence (Surface + Root-Zone)
    e_sm_surf = z_to_evidence(anomalies.sm_surf_z_1m)
    e_sm_rz = z_to_evidence(anomalies.sm_rz_z_3m)
    e_sm = 0.35 * e_sm_surf + 0.65 * e_sm_rz

    # 4. Thermal Stress Evidence (Positive LST anomaly indicates heat stress)
    e_thermal = np.clip(anomalies.thermal_z_1m / 2.0, 0.0, 1.0).astype(np.float32)

    # Multi-Modal Weighted Fusion
    s_fused = (
        mw.vegetation * e_veg +
        mw.precipitation * e_precip +
        mw.soil_moisture * e_sm +
        mw.thermal * e_thermal
    )
    s_fused = np.clip(s_fused, 0.0, 1.0)
    s_fused = np.where(anomalies.valid_mask, s_fused, np.nan)

    prov_hash = hashlib.sha256(
        f"FUSION_{np.nanmean(s_fused):.4f}_{regime_context.regime}".encode()
    ).hexdigest()

    return DroughtEvidenceBreakdown(
        vegetation_stress_score=e_veg,
        precipitation_deficit_score=e_precip,
        soil_moisture_deficit_score=e_sm,
        thermal_stress_score=e_thermal,
        fused_drought_score=s_fused,
        modality_weights_applied=mw,
        provenance_hash=prov_hash,
    )
