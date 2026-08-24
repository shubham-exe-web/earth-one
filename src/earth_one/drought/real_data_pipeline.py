from __future__ import annotations

"""Drought Module 3 End-to-End Real EO Ingestion & Evaluation Pipeline (Phase 2)."""

import hashlib
from dataclasses import dataclass
from typing import Sequence
import numpy as np

from .config import DroughtConfig
from .data_sources import RealEODroughtSceneStack
from .reference_taxonomy import DroughtReferenceTarget
from .climatology import BaselineClimatology, HistoricalClimatologyStore, compute_standardized_anomaly
from .anomalies import MultiWindowAnomalies
from .regime import classify_drought_regime, RegimeClassificationResult
from .observability import compute_drought_observability, DroughtObservabilityResult
from .fusion import fuse_drought_evidence, DroughtEvidenceBreakdown
from .classifier import classify_tristate_drought, TriStateDroughtDecision
from .events import extract_drought_events, DroughtSegmentationResult
from .tracking import MultiEpochDroughtTracker, DroughtTrack
from .evaluation import DroughtBenchmarkMetrics, compute_pr_auc


@dataclass
class RealEODroughtPipelineResult:
    """Complete provenance-tracked inference and evaluation result from real EO scene stack."""
    aoi_id: str
    epoch_timestamp: str
    anomalies: MultiWindowAnomalies
    regime_context: RegimeClassificationResult
    observability: DroughtObservabilityResult
    evidence: DroughtEvidenceBreakdown
    decision: TriStateDroughtDecision
    segmentation: DroughtSegmentationResult
    active_tracks: list[DroughtTrack]
    validation_metrics: DroughtBenchmarkMetrics | None
    provenance_hash: str


def run_real_eo_drought_pipeline(
    scene_stack: RealEODroughtSceneStack,
    climatology_store_ndvi: HistoricalClimatologyStore,
    climatology_store_precip: HistoricalClimatologyStore,
    climatology_store_sm: HistoricalClimatologyStore,
    climatology_store_lst: HistoricalClimatologyStore,
    eval_month: int,
    eval_year: int,
    tracker: MultiEpochDroughtTracker | None = None,
    epoch_index: int = 1,
    reference_target: DroughtReferenceTarget | None = None,
    config: DroughtConfig = DroughtConfig(),
) -> RealEODroughtPipelineResult:
    """Execute end-to-end inference over real EO satellite observations with out-of-sample climatology."""
    opt = scene_stack.optical
    pr = scene_stack.precipitation
    sm = scene_stack.soil_moisture
    th = scene_stack.thermal

    # 1. Optical BOA Index Extraction & Cloud Masking
    opt_indices = opt.compute_indices()
    ndvi = opt_indices["ndvi"]
    valid_mask = opt_indices["valid_mask"]
    cloud_mask = opt_indices["cloud_mask"]
    cloud_frac = float(np.mean(cloud_mask))

    # 2. Retrieve Leave-One-Year-Out Historical Climatological Baselines
    clim_v = climatology_store_ndvi.monthly_baselines.get(eval_month)
    clim_p = climatology_store_precip.monthly_baselines.get(eval_month)
    clim_s = climatology_store_sm.monthly_baselines.get(eval_month)
    clim_t = climatology_store_lst.monthly_baselines.get(eval_month)

    assert clim_v is not None and clim_p is not None and clim_s is not None and clim_t is not None, \
        f"Missing fitted climatology for month {eval_month}"

    # 3. Standardized Multi-Window Anomaly Computation
    # Use real 1M, 3M, and 6M precipitation and soil moisture observations
    z_v1 = compute_standardized_anomaly(ndvi, clim_v.mean, clim_v.std)
    z_v3 = z_v1.copy()  # In full temporal pipeline, rolling composite replaces instantaneous
    z_v6 = z_v1.copy()

    z_p1 = compute_standardized_anomaly(pr.precip_1m_mm, clim_p.mean, clim_p.std, min_std=5.0)
    z_p3 = compute_standardized_anomaly(pr.precip_3m_mm, clim_p.mean * 3.0, clim_p.std * 1.7, min_std=10.0)
    z_p6 = compute_standardized_anomaly(pr.precip_6m_mm, clim_p.mean * 6.0, clim_p.std * 2.4, min_std=15.0)

    z_sms = compute_standardized_anomaly(sm.surface_sm_m3m3, clim_s.mean, clim_s.std, min_std=0.01)
    z_smrz = compute_standardized_anomaly(sm.rootzone_sm_m3m3, clim_s.mean * 1.05, clim_s.std * 0.9, min_std=0.01)

    z_lst = compute_standardized_anomaly(th.lst_kelvin, clim_t.mean, clim_t.std, min_std=1.0)

    anomalies = MultiWindowAnomalies(
        veg_z_1m=z_v1,
        veg_z_3m=z_v3,
        veg_z_6m=z_v6,
        precip_z_1m=z_p1,
        precip_z_3m=z_p3,
        precip_z_6m=z_p6,
        sm_surf_z_1m=z_sms,
        sm_rz_z_3m=z_smrz,
        thermal_z_1m=z_lst,
        valid_mask=valid_mask,
        provenance_hash=hashlib.sha256(f"REAL_ANOM_{scene_stack.aoi_id}_{eval_year}_{eval_month}".encode()).hexdigest(),
    )

    # 4. Contextual Biophysical Regime Routing
    regime = classify_drought_regime(
        baseline_mean_ndvi=clim_v.mean,
        baseline_min_ndvi=clim_v.min_observed,
        baseline_max_ndvi=clim_v.max_observed,
    )

    # 5. Decoupled Observability & Attribution Ambiguity
    obs = compute_drought_observability(
        valid_mask=valid_mask,
        cloud_fraction=cloud_frac,
        baseline_ndvi=clim_v.mean,
        config=config,
    )

    # 6. Gated Multi-Modal Fusion
    evidence = fuse_drought_evidence(anomalies, regime, config=config)

    # 7. Tri-State Decision Contract
    decision = classify_tristate_drought(evidence, obs, config=config)

    # 8. Spatial Event Segmentation & Sensitivity Bounding
    segmentation = extract_drought_events(
        decision, evidence.fused_drought_score, obs, resolution_m=opt.resolution_m, config=config
    )

    # 9. Multi-Epoch Persistent Tracking
    if tracker is not None:
        active_tracks = tracker.update_epoch(segmentation, epoch_index=epoch_index)
    else:
        active_tracks = []

    # 10. Validation against Independent Reference Target (if provided)
    val_metrics = None
    if reference_target is not None:
        ref_mask = reference_target.get_eval_binary_mask()
        y_pred = decision.drought_mask
        y_true = ref_mask

        tp = int(np.sum(y_pred & y_true))
        fp = int(np.sum(y_pred & (~y_true)))
        fn = int(np.sum((~y_pred) & y_true))

        prec = float(tp / max(1, tp + fp))
        rec = float(tp / max(1, tp + fn))
        f1 = float(2 * prec * rec / max(1e-6, prec + rec))
        iou = float(tp / max(1, tp + fp + fn))
        area_bias = float(np.sum(y_pred) / max(1, np.sum(y_true)))
        pr_auc = compute_pr_auc(y_true, evidence.fused_drought_score)
        
        res_mask = obs.resolvable_mask
        pr_auc_res = compute_pr_auc(y_true[res_mask], evidence.fused_drought_score[res_mask]) if np.any(res_mask) else 0.0

        val_metrics = DroughtBenchmarkMetrics(
            mode_name="REAL_EO_INFERENCE",
            precision=round(prec, 4),
            recall=round(rec, 4),
            f1_score=round(f1, 4),
            pr_auc=round(pr_auc, 4),
            iou=round(iou, 4),
            area_bias=round(area_bias, 3),
            resolvable_pr_auc=round(pr_auc_res, 4),
            unresolved_fraction=round(obs.unresolved_fraction, 4),
            total_pixels=int(y_true.size),
            provenance_hash=hashlib.sha256(f"VAL_{reference_target.name}_{f1:.3f}".encode()).hexdigest(),
        )

    prov = hashlib.sha256(
        f"REAL_PIPELINE_{scene_stack.aoi_id}_{eval_year}_{eval_month}_{decision.drought_pixels}".encode()
    ).hexdigest()

    return RealEODroughtPipelineResult(
        aoi_id=scene_stack.aoi_id,
        epoch_timestamp=scene_stack.epoch_timestamp,
        anomalies=anomalies,
        regime_context=regime,
        observability=obs,
        evidence=evidence,
        decision=decision,
        segmentation=segmentation,
        active_tracks=active_tracks,
        validation_metrics=val_metrics,
        provenance_hash=prov,
    )
