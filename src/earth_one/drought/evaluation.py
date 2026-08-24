from __future__ import annotations

"""Earth One Drought Module 3 Evaluation, Ablation & Observability Benchmark Engine."""

import hashlib
from dataclasses import dataclass
from typing import Literal
import numpy as np

from .config import DroughtConfig, ModalityWeights
from .anomalies import MultiWindowAnomalies
from .regime import RegimeClassificationResult
from .observability import DroughtObservabilityResult
from .fusion import fuse_drought_evidence, DroughtEvidenceBreakdown, z_to_evidence
from .classifier import classify_tristate_drought, TriStateDroughtDecision
from .pilots import DroughtPilotActivation


@dataclass
class DroughtBenchmarkMetrics:
    """Quantitative detection performance metrics against independent reference."""
    mode_name: str
    precision: float
    recall: float
    f1_score: float
    pr_auc: float
    iou: float
    area_bias: float
    resolvable_pr_auc: float
    unresolved_fraction: float
    total_pixels: int
    provenance_hash: str


@dataclass
class ObservabilityBinResult:
    bin_range: str
    pixel_count: int
    precision: float
    recall: float
    f1_score: float
    pr_auc: float


def compute_pr_auc(y_true: np.ndarray, y_score: np.ndarray, num_thresholds: int = 101) -> float:
    """Compute empirical Area Under the Precision-Recall Curve."""
    if not np.any(y_true):
        return 0.0
    
    thresholds = np.linspace(0.0, 1.0, num_thresholds)
    precisions = []
    recalls = []

    for t in thresholds:
        y_pred = (y_score >= t)
        tp = np.sum(y_pred & y_true)
        fp = np.sum(y_pred & (~y_true))
        fn = np.sum((~y_pred) & y_true)

        p = tp / max(1, tp + fp)
        r = tp / max(1, tp + fn)
        precisions.append(p)
        recalls.append(r)

    # Sort by recall ascending
    sorted_pairs = sorted(zip(recalls, precisions))
    r_sorted = np.array([r for r, p in sorted_pairs], dtype=np.float32)
    p_sorted = np.array([p for r, p in sorted_pairs], dtype=np.float32)

    # Standard monotonic precision envelope interpolation: p_interp(r) = max_{r' >= r} p(r')
    p_interp = np.maximum.accumulate(p_sorted[::-1])[::-1]

    # Trapezoidal integration across recall
    if hasattr(np, "trapezoid"):
        return float(np.trapezoid(p_interp, r_sorted))
    else:
        dx = np.diff(r_sorted)
        return float(np.sum(0.5 * (p_interp[:-1] + p_interp[1:]) * dx))


def evaluate_drought_mode(
    pilot: DroughtPilotActivation,
    mode: Literal["MODE_A_VEG_ONLY", "MODE_B_PRECIP_ONLY", "MODE_C_SM_ONLY", "MODE_D_VEG_PRECIP", "MODE_E_VEG_SM", "MODE_F_PRECIP_SM", "MODE_G_TRI_MODAL", "MODE_H_FULL_EARTH_ONE"],
    config: DroughtConfig = DroughtConfig(),
) -> DroughtBenchmarkMetrics:
    """Execute ablation mode on a pilot activation and compute quantitative metrics."""
    anom = pilot.current_anomalies
    regime = pilot.regime_context
    obs = pilot.observability
    y_true = pilot.reference_mask

    # Select weights based on ablation mode
    if mode == "MODE_A_VEG_ONLY":
        mw = ModalityWeights(vegetation=1.0, precipitation=0.0, soil_moisture=0.0, thermal=0.0)
    elif mode == "MODE_B_PRECIP_ONLY":
        mw = ModalityWeights(vegetation=0.0, precipitation=1.0, soil_moisture=0.0, thermal=0.0)
    elif mode == "MODE_C_SM_ONLY":
        mw = ModalityWeights(vegetation=0.0, precipitation=0.0, soil_moisture=1.0, thermal=0.0)
    elif mode == "MODE_D_VEG_PRECIP":
        mw = ModalityWeights(vegetation=0.50, precipitation=0.50, soil_moisture=0.0, thermal=0.0)
    elif mode == "MODE_E_VEG_SM":
        mw = ModalityWeights(vegetation=0.50, precipitation=0.0, soil_moisture=0.50, thermal=0.0)
    elif mode == "MODE_F_PRECIP_SM":
        mw = ModalityWeights(vegetation=0.0, precipitation=0.50, soil_moisture=0.50, thermal=0.0)
    elif mode == "MODE_G_TRI_MODAL":
        mw = ModalityWeights(vegetation=0.35, precipitation=0.35, soil_moisture=0.30, thermal=0.0)
    elif mode == "MODE_H_FULL_EARTH_ONE":
        mw = regime.recommended_modality_weights
    else:
        raise ValueError(f"Unknown mode: {mode}")

    # Compute custom fused score
    tw = config.temporal_weights
    e_veg = tw.window_1m * z_to_evidence(anom.veg_z_1m) + tw.window_3m * z_to_evidence(anom.veg_z_3m) + tw.window_6m * z_to_evidence(anom.veg_z_6m)
    e_pr = tw.window_1m * z_to_evidence(anom.precip_z_1m) + tw.window_3m * z_to_evidence(anom.precip_z_3m) + tw.window_6m * z_to_evidence(anom.precip_z_6m)
    e_sm = 0.35 * z_to_evidence(anom.sm_surf_z_1m) + 0.65 * z_to_evidence(anom.sm_rz_z_3m)
    e_th = np.clip(anom.thermal_z_1m / 2.0, 0.0, 1.0)

    s_score = mw.vegetation * e_veg + mw.precipitation * e_pr + mw.soil_moisture * e_sm + mw.thermal * e_th

    # Decision
    y_pred = (s_score >= config.drought_detection_threshold) & obs.resolvable_mask
    if obs.is_attribution_ambiguous is not None:
        y_pred = y_pred & (~(obs.attribution_ambiguity_index >= 0.80))

    # All-domain metrics
    tp = int(np.sum(y_pred & y_true))
    fp = int(np.sum(y_pred & (~y_true)))
    fn = int(np.sum((~y_pred) & y_true))

    prec = float(tp / max(1, tp + fp))
    rec = float(tp / max(1, tp + fn))
    f1 = float(2 * prec * rec / max(1e-6, prec + rec))
    iou = float(tp / max(1, tp + fp + fn))
    area_bias = float(np.sum(y_pred) / max(1, np.sum(y_true)))
    pr_auc_all = compute_pr_auc(y_true, s_score)

    # Resolvable-domain PR-AUC (O >= 0.50)
    res_mask = obs.resolvable_mask
    if np.any(res_mask):
        pr_auc_res = compute_pr_auc(y_true[res_mask], s_score[res_mask])
    else:
        pr_auc_res = 0.0

    prov = hashlib.sha256(f"EVAL_{pilot.pilot_id}_{mode}_{f1:.3f}_{pr_auc_all:.3f}".encode()).hexdigest()

    return DroughtBenchmarkMetrics(
        mode_name=mode,
        precision=round(prec, 4),
        recall=round(rec, 4),
        f1_score=round(f1, 4),
        pr_auc=round(pr_auc_all, 4),
        iou=round(iou, 4),
        area_bias=round(area_bias, 3),
        resolvable_pr_auc=round(pr_auc_res, 4),
        unresolved_fraction=round(obs.unresolved_fraction, 4),
        total_pixels=int(y_true.size),
        provenance_hash=prov,
    )
