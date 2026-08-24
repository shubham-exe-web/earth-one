from __future__ import annotations

"""Block 4C: Autonomous Biophysical Regime Router Benchmark & Delta Audit.

Compares:
1. Autonomous Regime-Routed Flood Engine (Regime Router + Coastal Protection M_intertidal)
2. Frozen Global Baseline Engine v0.1 (Single fixed policy)

Evaluates on the 3-event multi-continent cohort without ground-truth label leakage.
Computes Delta PR-AUC, Delta F1, Delta Precision, and Delta Area Bias.
"""

import hashlib
import json
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
from scipy import ndimage
from sklearn.metrics import precision_recall_curve, auc, roc_auc_score, brier_score_loss

from .flood import (
    FloodEvidenceConfig,
    FloodDetectionResult,
    compute_sar_water_evidence,
    compute_optical_water_evidence,
    compute_water_novelty,
    compute_terrain_plausibility,
    compute_rainfall_context,
    fuse_flood_evidence,
)
from .flood_reference import load_vector_reference, normalize_water_occurrence
from .flood_rainfall import get_historical_event_rainfall
from .coastal_context import compute_intertidal_suppression_mask
from .regime_router import classify_biophysical_regime, RegimeRoutingResult
from .flood_multievent import COHORT_SPECS, FloodCohortEventSpec, get_stac_item, sign_planetary_url, compute_dem_slope


def run_regime_routed_benchmark(
    specs: list[FloodCohortEventSpec] | None = None,
    output_dir: Path | str = "data/results/flood_regime_routing",
) -> dict[str, Any]:
    if specs is None:
        specs = COHORT_SPECS

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 95)
    print("  EARTH ONE FLOOD MODULE: BLOCK 4C AUTONOMOUS REGIME-ROUTED BENCHMARK")
    print(f"  Cohort Size: {len(specs)} independent historical activations")
    print("  Comparison: Regime-Adapted Policy + Intertidal Mask vs Frozen Global Policy v0.1")
    print("=" * 95)

    benchmark_events = {}

    for spec in specs:
        print(f"\n>>> EVALUATING EVENT: {spec.activation} ({spec.aoi_name}) <<<")
        w, s, e, n = spec.bbox
        H, W = spec.grid_shape
        t_site = rasterio.transform.from_bounds(w, s, e, n, W, H)
        target_profile = {"width": W, "height": H, "crs": "EPSG:4326", "transform": t_site}

        mid_lat = (s + n) / 2.0
        cell_x_m = abs(t_site.a * 111319.5 * np.cos(np.radians(mid_lat)))
        cell_y_m = abs(t_site.e * 111319.5)
        pixel_area_m2 = cell_x_m * cell_y_m
        pixel_area_ha = pixel_area_m2 / 10000.0

        def read_warped_band(href: str, resampling: Resampling = Resampling.bilinear, retries: int = 4) -> np.ndarray:
            dest = np.zeros((H, W), dtype=np.float32)
            for attempt in range(retries):
                try:
                    signed = sign_planetary_url(href)
                    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF,.tiff,.TIFF", VSI_CACHE=True):
                        with rasterio.open(signed) as src:
                            reproject(
                                source=rasterio.band(src, 1), destination=dest,
                                src_transform=src.transform, src_crs=src.crs,
                                dst_transform=t_site, dst_crs="EPSG:4326", resampling=resampling
                            )
                    return dest
                except Exception as exc:
                    if attempt == retries - 1:
                        fname = href.split("/")[-1]
                        print(f"Warning: failed band read {fname}: {exc}")
                        return dest
                    time.sleep(1.5 * (attempt + 1))
            return dest

        # Stream Base Physical Rasters for Classification
        print("  [1/4] Streaming Pre-Event Baselines (GSW, DEM, Rainfall)...")
        jrc_item = get_stac_item("jrc-gsw", spec.jrc_gsw_item)
        dem_item = get_stac_item("cop-dem-glo-30", spec.cop_dem_item)

        jrc_raw = read_warped_band(jrc_item["assets"]["occurrence"]["href"])
        jrc_freq, jrc_valid = normalize_water_occurrence(jrc_raw, nodata=255)

        elevation_m = read_warped_band(dem_item["assets"]["data"]["href"])
        slope_deg = compute_dem_slope(elevation_m, cell_x_m, cell_y_m)

        # Autonomous Zero-Leakage Regime Classification
        print("  [2/4] Executing Autonomous Biophysical Regime Classification...")
        regime_result = classify_biophysical_regime(
            jrc_occurrence=jrc_freq,
            elevation_m=elevation_m,
            slope_deg=slope_deg,
            centroid_lat=mid_lat,
            centroid_lon=(w + e) / 2.0,
        )
        print(f"        -> Classified Regime: {regime_result.regime} (Confidence: {regime_result.confidence*100:.1f}%)")

        # Stream Satellite Observations
        print("  [3/4] Streaming Sentinel-1 SAR & Sentinel-2 Optical Layers...")
        s1_b_item = get_stac_item("sentinel-1-grd", spec.s1_before_item)
        s1_e_item = get_stac_item("sentinel-1-grd", spec.s1_event_item)
        s2_e_item = get_stac_item("sentinel-2-l2a", spec.s2_event_item)

        vv_raw_b = read_warped_band(s1_b_item["assets"]["vv"]["href"])
        vv_raw_e = read_warped_band(s1_e_item["assets"]["vv"]["href"])
        vv_b = (vv_raw_b / 475.0) ** 2
        vv_e = (vv_raw_e / 475.0) ** 2
        vh_b = (read_warped_band(s1_b_item["assets"]["vh"]["href"]) / 530.0) ** 2 if "vh" in s1_b_item.get("assets", {}) else None
        vh_e = (read_warped_band(s1_e_item["assets"]["vh"]["href"]) / 530.0) ** 2 if "vh" in s1_e_item.get("assets", {}) else None

        b03_e = read_warped_band(s2_e_item["assets"]["B03"]["href"]) / 10000.0
        b08_e = read_warped_band(s2_e_item["assets"]["B08"]["href"]) / 10000.0
        b11_e = read_warped_band(s2_e_item["assets"]["B11"]["href"]) / 10000.0
        scl_e = read_warped_band(s2_e_item["assets"]["SCL"]["href"], resampling=Resampling.nearest).astype(int)

        rain_obs = get_historical_event_rainfall(spec.event_key)

        # Load Independent Reference
        ref_shp = Path(spec.reference_shapefile)
        cems_ref_mask, _ = load_vector_reference(ref_shp, target_profile)
        ref_y = cems_ref_mask.flatten().astype(int)
        cems_ref_px = int(np.sum(cems_ref_mask))
        cems_ref_ha = float(cems_ref_px * pixel_area_ha)

        # -------------------------------------------------------------
        # SYSTEM A: FROZEN GLOBAL BASELINE v0.1
        # -------------------------------------------------------------
        cfg_global = FloodEvidenceConfig(fusion_strategy="gated_physics")
        sar_sc_g, sar_v_g = compute_sar_water_evidence(vv_b, vv_e, vh_b, vh_e, config=cfg_global)
        opt_sc_g, opt_v_g = compute_optical_water_evidence(b03_e, b08_e, b11_e, scl_mask=scl_e, config=cfg_global)
        m_nov_g = np.where(jrc_valid, np.clip(1.0 - (jrc_freq / cfg_global.permanent_water_max_freq), 0.0, 1.0), 1.0)
        terr_sc_g, terr_v_g = compute_terrain_plausibility(slope_deg, config=cfg_global)
        rain_sc_g = compute_rainfall_context(rain_obs.accumulation_mm, rain_obs.anomaly_std, rain_obs.hours_since_peak, config=cfg_global)

        det_global = fuse_flood_evidence(
            sar_evidence=sar_sc_g, sar_valid=sar_v_g,
            optical_evidence=opt_sc_g, optical_valid=opt_v_g,
            novelty_evidence=m_nov_g, novelty_valid=jrc_valid,
            terrain_plausibility=terr_sc_g, terrain_valid=terr_v_g,
            rainfall_score=rain_sc_g, config=cfg_global,
        )
        score_global = det_global.flood_score.flatten()
        p_cg, r_cg, _ = precision_recall_curve(ref_y, score_global)
        pr_auc_global = float(auc(r_cg, p_cg))
        roc_auc_global = float(roc_auc_score(ref_y, score_global))

        # Operational metrics at T=0.20
        pred_g20 = det_global.valid_mask & (det_global.flood_score >= 0.20)
        pred_g20 = ndimage.binary_opening(pred_g20, structure=np.ones((2, 2), dtype=bool)) if pred_g20.any() else pred_g20
        tp_g = int(np.sum(pred_g20 & cems_ref_mask))
        fp_g = int(np.sum(pred_g20 & (~cems_ref_mask)))
        prec_g20 = float(tp_g / (tp_g + fp_g)) if (tp_g + fp_g) > 0 else 0.0
        rec_g20 = float(tp_g / cems_ref_px) if cems_ref_px > 0 else 0.0
        f1_g20 = float(2 * prec_g20 * rec_g20 / (prec_g20 + rec_g20)) if (prec_g20 + rec_g20) > 0 else 0.0
        iou_g20 = float(tp_g / (tp_g + fp_g + (cems_ref_px - tp_g))) if cems_ref_px > 0 else 0.0
        bias_g20 = float((np.sum(pred_g20) * pixel_area_ha) / cems_ref_ha) if cems_ref_ha > 0 else 0.0

        # -------------------------------------------------------------
        # SYSTEM B: AUTONOMOUS REGIME-ROUTED ENGINE
        # -------------------------------------------------------------
        cfg_routed = regime_result.recommended_config
        sar_sc_r, sar_v_r = compute_sar_water_evidence(vv_b, vv_e, vh_b, vh_e, config=cfg_routed)
        opt_sc_r, opt_v_r = compute_optical_water_evidence(b03_e, b08_e, b11_e, scl_mask=scl_e, config=cfg_routed)
        m_nov_r = np.where(jrc_valid, np.clip(1.0 - (jrc_freq / cfg_routed.permanent_water_max_freq), 0.0, 1.0), 1.0)
        terr_sc_r, terr_v_r = compute_terrain_plausibility(slope_deg, config=cfg_routed)
        rain_sc_r = compute_rainfall_context(rain_obs.accumulation_mm, rain_obs.anomaly_std, rain_obs.hours_since_peak, config=cfg_routed)

        # Apply Intertidal Protection Mask if Coastal
        m_intertidal, _ = compute_intertidal_suppression_mask(jrc_freq, elevation_m, slope_deg)
        if regime_result.regime == "COASTAL_ESTUARINE_TIDAL":
            m_nov_r = m_nov_r * m_intertidal

        det_routed = fuse_flood_evidence(
            sar_evidence=sar_sc_r, sar_valid=sar_v_r,
            optical_evidence=opt_sc_r, optical_valid=opt_v_r,
            novelty_evidence=m_nov_r, novelty_valid=jrc_valid,
            terrain_plausibility=terr_sc_r, terrain_valid=terr_v_r,
            rainfall_score=rain_sc_r, config=cfg_routed,
        )
        score_routed = det_routed.flood_score.flatten()
        p_cr, r_cr, _ = precision_recall_curve(ref_y, score_routed)
        pr_auc_routed = float(auc(r_cr, p_cr))
        roc_auc_routed = float(roc_auc_score(ref_y, score_routed))

        # Operational metrics at recommended detection threshold
        t_op = cfg_routed.default_detection_threshold
        pred_r = det_routed.valid_mask & (det_routed.flood_score >= t_op)
        if cfg_routed.apply_morphological_opening and pred_r.any():
            k = cfg_routed.morphology_kernel_size
            pred_r = ndimage.binary_opening(pred_r, structure=np.ones((k, k), dtype=bool))

        tp_r = int(np.sum(pred_r & cems_ref_mask))
        fp_r = int(np.sum(pred_r & (~cems_ref_mask)))
        prec_r = float(tp_r / (tp_r + fp_r)) if (tp_r + fp_r) > 0 else 0.0
        rec_r = float(tp_r / cems_ref_px) if cems_ref_px > 0 else 0.0
        f1_r = float(2 * prec_r * rec_r / (prec_r + rec_r)) if (prec_r + rec_r) > 0 else 0.0
        iou_r = float(tp_r / (tp_r + fp_r + (cems_ref_px - tp_r))) if cems_ref_px > 0 else 0.0
        bias_r = float((np.sum(pred_r) * pixel_area_ha) / cems_ref_ha) if cems_ref_ha > 0 else 0.0

        # Compute Scientific Deltas
        delta_pr_auc = pr_auc_routed - pr_auc_global
        delta_f1 = f1_r - f1_g20
        delta_prec = prec_r - prec_g20
        delta_bias = bias_r - bias_g20
        fp_reduction_pct = float((fp_g - fp_r) / fp_g * 100.0) if fp_g > 0 else 0.0

        print(f"  [4/4] Comparative Results:")
        print(f"        -> GLOBAL BASELINE: PR-AUC={pr_auc_global:.4f} | Prec={prec_g20*100:.1f}% | F1={f1_g20*100:.1f}% | Bias={bias_g20:.2f}x | FP={fp_g:,}")
        print(f"        -> REGIME ROUTED:   PR-AUC={pr_auc_routed:.4f} | Prec={prec_r*100:.1f}% | F1={f1_r*100:.1f}% | Bias={bias_r:.2f}x | FP={fp_r:,}")
        print(f"        -> SCIENTIFIC DELTA: ΔPR-AUC={delta_pr_auc:+.4f} | ΔPrec={delta_prec*100:+.1f}% | FP Reduction={fp_reduction_pct:+.1f}%")

        benchmark_events[spec.activation] = {
            "case_study": asdict(spec),
            "regime_classification": {
                "classified_regime": regime_result.regime,
                "confidence": regime_result.confidence,
                "uncertainty": regime_result.uncertainty,
                "features": regime_result.features,
                "coastal_profile": asdict(regime_result.coastal_profile),
            },
            "global_baseline_v01": {
                "pr_auc": round(pr_auc_global, 5),
                "roc_auc": round(roc_auc_global, 5),
                "operational_metrics": {"threshold": 0.20, "precision": round(prec_g20, 4), "recall": round(rec_g20, 4), "f1_score": round(f1_g20, 4), "iou": round(iou_g20, 4), "area_bias": round(bias_g20, 3), "fp_pixels": fp_g},
            },
            "regime_routed_engine": {
                "pr_auc": round(pr_auc_routed, 5),
                "roc_auc": round(roc_auc_routed, 5),
                "operational_metrics": {"threshold": t_op, "precision": round(prec_r, 4), "recall": round(rec_r, 4), "f1_score": round(f1_r, 4), "iou": round(iou_r, 4), "area_bias": round(bias_r, 3), "fp_pixels": fp_r},
            },
            "scientific_deltas": {
                "delta_pr_auc": round(delta_pr_auc, 5),
                "delta_precision": round(delta_prec, 4),
                "delta_f1_score": round(delta_f1, 4),
                "delta_area_bias": round(delta_bias, 3),
                "false_positive_reduction_pct": round(fp_reduction_pct, 2),
            }
        }

    # Macro-Averaged Summary
    macro_pr_global = float(np.mean([e["global_baseline_v01"]["pr_auc"] for e in benchmark_events.values()]))
    macro_pr_routed = float(np.mean([e["regime_routed_engine"]["pr_auc"] for e in benchmark_events.values()]))

    final_payload = {
        "schema": "earth_one_regime_routing_benchmark_v1.0",
        "macro_summary": {
            "total_events": len(specs),
            "macro_pr_auc_global": round(macro_pr_global, 5),
            "macro_pr_auc_routed": round(macro_pr_routed, 5),
            "macro_delta_pr_auc": round(macro_pr_routed - macro_pr_global, 5),
        },
        "event_evaluations": benchmark_events,
    }

    out_file = out_dir / "regime_routing_benchmark.json"
    out_file.write_text(json.dumps(final_payload, indent=2), encoding="utf-8")
    print(f"\nSaved Block 4C Regime-Routing Benchmark Ledger to {out_file}")
    return final_payload
