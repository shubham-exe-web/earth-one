from __future__ import annotations

"""Drought Module 3 End-to-End Real EO Ingestion & Evaluation Pipeline (Phase 2.5)."""

import hashlib
from dataclasses import dataclass
from typing import Sequence
import numpy as np

from .config import DroughtConfig
from .data_sources import RealEODroughtSceneStack
from .reference_taxonomy import DroughtReferenceTarget
from .reference_governance import ValidationGovernanceAudit, audit_reference_governance
from .climatology import BaselineClimatology, HistoricalClimatologyStore, compute_standardized_anomaly
from .anomalies import MultiWindowAnomalies
from .regime import classify_drought_regime, RegimeClassificationResult
from .observability import compute_drought_observability, DroughtObservabilityResult
from .fusion import fuse_drought_evidence, DroughtEvidenceBreakdown
from .classifier import classify_tristate_drought, TriStateDroughtDecision
from .events import extract_drought_events, DroughtSegmentationResult
from .tracking import MultiEpochDroughtTracker, DroughtTrack
from .evaluation import DroughtBenchmarkMetrics, compute_pr_auc
from .spatial_harmonization import TargetAnalysisGrid


@dataclass
class RealEODroughtPipelineResult:
    """Complete provenance-tracked inference and evaluation result from real EO scene stack."""
    aoi_id: str
    epoch_timestamp: str
    target_grid: TargetAnalysisGrid
    anomalies: MultiWindowAnomalies
    regime_context: RegimeClassificationResult
    observability: DroughtObservabilityResult
    evidence: DroughtEvidenceBreakdown
    decision: TriStateDroughtDecision
    segmentation: DroughtSegmentationResult
    active_tracks: list[DroughtTrack]
    validation_metrics: DroughtBenchmarkMetrics | None
    governance_audit: ValidationGovernanceAudit | None
    provenance_hash: str


def run_real_eo_drought_pipeline(
    scene_stack: RealEODroughtSceneStack,
    climatology_store_veg_1m: HistoricalClimatologyStore,
    climatology_store_veg_3m: HistoricalClimatologyStore,
    climatology_store_veg_6m: HistoricalClimatologyStore,
    climatology_store_precip_1m: HistoricalClimatologyStore,
    climatology_store_precip_3m: HistoricalClimatologyStore,
    climatology_store_precip_6m: HistoricalClimatologyStore,
    climatology_store_sm_surf: HistoricalClimatologyStore,
    climatology_store_sm_rz: HistoricalClimatologyStore,
    climatology_store_lst: HistoricalClimatologyStore,
    eval_month: int,
    eval_year: int,
    tracker: MultiEpochDroughtTracker | None = None,
    epoch_index: int = 1,
    reference_target: DroughtReferenceTarget | None = None,
    candidate_overlapping_inputs: Sequence[str] | None = None,
    config: DroughtConfig = DroughtConfig(),
) -> RealEODroughtPipelineResult:
    """Execute end-to-end inference over real EO satellite observations with out-of-sample climatology."""
    grid = scene_stack.target_grid
    opt = scene_stack.optical
    pr = scene_stack.precipitation
    sm = scene_stack.soil_moisture
    th = scene_stack.thermal

    # 1. Optical BOA Index Extraction & Cloud Masking
    opt_indices = opt.compute_indices()
    ndvi_1m = opt_indices["ndvi_1m"]
    ndvi_3m = opt_indices["ndvi_3m"]
    ndvi_6m = opt_indices["ndvi_6m"]
    valid_mask = opt_indices["valid_mask"]
    cloud_mask = opt_indices["cloud_mask"]
    cloud_frac = float(np.mean(cloud_mask))

    # 2. Retrieve Leave-One-Year-Out Multi-Window Climatologies (Task D-15)
    clim_v1 = climatology_store_veg_1m.monthly_baselines.get(eval_month)
    clim_v3 = climatology_store_veg_3m.monthly_baselines.get(eval_month)
    clim_v6 = climatology_store_veg_6m.monthly_baselines.get(eval_month)

    clim_p1 = climatology_store_precip_1m.monthly_baselines.get(eval_month)
    clim_p3 = climatology_store_precip_3m.monthly_baselines.get(eval_month)
    clim_p6 = climatology_store_precip_6m.monthly_baselines.get(eval_month)

    clim_ss = climatology_store_sm_surf.monthly_baselines.get(eval_month)
    clim_srz = climatology_store_sm_rz.monthly_baselines.get(eval_month)
    clim_t = climatology_store_lst.monthly_baselines.get(eval_month)

    assert clim_v1 is not None and clim_v3 is not None and clim_v6 is not None, f"Missing veg climatologies for month {eval_month}"
    assert clim_p1 is not None and clim_p3 is not None and clim_p6 is not None, f"Missing precip climatologies for month {eval_month}"
    assert clim_ss is not None and clim_srz is not None and clim_t is not None, f"Missing SM/LST climatologies for month {eval_month}"

    # 3. Standardized Multi-Window Anomaly Computation (Task D-14 & D-15)
    z_v1 = compute_standardized_anomaly(ndvi_1m, clim_v1.mean, clim_v1.std)
    z_v3 = compute_standardized_anomaly(ndvi_3m, clim_v3.mean, clim_v3.std)
    z_v6 = compute_standardized_anomaly(ndvi_6m, clim_v6.mean, clim_v6.std)

    z_p1 = compute_standardized_anomaly(pr.precip_1m_mm, clim_p1.mean, clim_p1.std, min_std=5.0)
    z_p3 = compute_standardized_anomaly(pr.precip_3m_mm, clim_p3.mean, clim_p3.std, min_std=10.0)
    z_p6 = compute_standardized_anomaly(pr.precip_6m_mm, clim_p6.mean, clim_p6.std, min_std=15.0)

    z_sms = compute_standardized_anomaly(sm.surface_sm_m3m3, clim_ss.mean, clim_ss.std, min_std=0.01)
    z_smrz = compute_standardized_anomaly(sm.rootzone_sm_m3m3, clim_srz.mean, clim_srz.std, min_std=0.01)

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
        provenance_hash=hashlib.sha256(f"REAL_ANOM_V2_{scene_stack.aoi_id}_{eval_year}_{eval_month}".encode()).hexdigest(),
    )

    # 4. Contextual Biophysical Regime Routing
    regime = classify_drought_regime(
        baseline_mean_ndvi=clim_v1.mean,
        baseline_min_ndvi=clim_v1.min_observed,
        baseline_max_ndvi=clim_v1.max_observed,
    )

    # 5. Decoupled Observability & Attribution Ambiguity
    obs = compute_drought_observability(
        valid_mask=valid_mask,
        cloud_fraction=cloud_frac,
        baseline_ndvi=clim_v1.mean,
        config=config,
    )

    # 6. Gated Multi-Modal Fusion
    evidence = fuse_drought_evidence(anomalies, regime, config=config)

    # 7. Tri-State Decision Contract
    decision = classify_tristate_drought(evidence, obs, config=config)

    # 8. Spatial Event Segmentation & Exact Analysis Grid Pixel Area (Task D-16)
    pixel_area_ha = grid.pixel_area_ha
    segmentation = extract_drought_events(
        decision, evidence.fused_drought_score, obs, resolution_m=np.sqrt(pixel_area_ha * 10000.0), config=config
    )

    # 9. Multi-Epoch Persistent Tracking
    if tracker is not None:
        active_tracks = tracker.update_epoch(segmentation, epoch_index=epoch_index)
    else:
        active_tracks = []

    # 10. Validation & Reference Governance (Task D-16)
    val_metrics = None
    gov_audit = None
    if reference_target is not None:
        gov_audit = audit_reference_governance(reference_target, candidate_overlapping_inputs)
        
        if gov_audit.is_pixel_truth_allowed:
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
                mode_name=f"EVAL_{reference_target.name}",
                precision=round(prec, 4),
                recall=round(rec, 4),
                f1_score=round(f1, 4),
                pr_auc=round(pr_auc, 4),
                iou=round(iou, 4),
                area_bias=round(area_bias, 3),
                resolvable_pr_auc=round(pr_auc_res, 4),
                unresolved_fraction=round(obs.unresolved_fraction, 4),
                total_pixels=int(y_true.size),
                provenance_hash=hashlib.sha256(f"VAL_REAL_{reference_target.name}_{f1:.3f}".encode()).hexdigest(),
            )

    prov = hashlib.sha256(
        f"REAL_PIPELINE_V2_{scene_stack.aoi_id}_{eval_year}_{eval_month}_{decision.drought_pixels}".encode()
    ).hexdigest()

    return RealEODroughtPipelineResult(
        aoi_id=scene_stack.aoi_id,
        epoch_timestamp=scene_stack.epoch_timestamp,
        target_grid=grid,
        anomalies=anomalies,
        regime_context=regime,
        observability=obs,
        evidence=evidence,
        decision=decision,
        segmentation=segmentation,
        active_tracks=active_tracks,
        validation_metrics=val_metrics,
        governance_audit=gov_audit,
        provenance_hash=prov,
    )
