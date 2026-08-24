from __future__ import annotations

"""Block 4D: Soft Biophysical Regime Routing, Confidence Blending, & Unseen-Event Validation.

Evaluates the Calibrated Autonomous Regime Router v0.2 across:
1. Development/Calibration Cohort (EMSR439, EMSR629, EMSR548)
2. Completely Unseen Holdout Cohort (EMSR348 Mozambique, EMSR468 Italy)

Features & Decision Architecture:
- Zero CEMS validation leakage: uses purely pre-event baseline rasters (GSW, DEM, slope)
- Soft Coastal Protection Layer with guaranteed multiplier floor (M_min = 0.35)
- Continuous Confidence-Weighted Blending: S_final = (1 - C) * S_global + C * S_regime
- Explicit abstention to MIXED_UNCERTAIN when confidence < 0.60
- Rigorous TP-Retention and FP-Reduction accounting
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
from .flood_multievent import FloodCohortEventSpec, get_stac_item, sign_planetary_url, compute_dem_slope


# 1. Calibration / Development Cohort (3 historical activations)
DEVELOPMENT_SPECS: list[FloodCohortEventSpec] = [
    FloodCohortEventSpec(
        activation="EMSR439",
        event_key="EMSR439_Sandwip",
        aoi_name="Sandwip_Channel_Bangladesh",
        country="Bangladesh",
        flood_regime="COASTAL_ESTUARINE_TIDAL",
        bbox=(91.3591, 22.3493, 91.4019, 22.3913),
        grid_shape=(512, 512),
        s1_before_item="S1A_IW_GRDH_1SDV_20200429T234818_20200429T234843_032349_03BE86",
        s1_event_item="S1A_IW_GRDH_1SDV_20200523T234819_20200523T234844_032699_03C99A",
        s2_before_item="S2B_MSIL2A_20200312T042659_R133_T46QCK_20201006T232116",
        s2_event_item="S2B_MSIL2A_20200531T042709_R133_T46QCK_20200911T155808",
        cop_dem_item="Copernicus_DSM_COG_10_N22_00_E091_00_DEM",
        jrc_gsw_item="90E_30Nv1_3_2020",
        reference_shapefile="data/results/flood_experiment1/emsr439_reference/extracted/EMSR439_AOI01_DEL_PRODUCT_r1_VECTORS_v1_vector/EMSR439_AOI01_DEL_PRODUCT_observedEventA_r1_v1.shp",
    ),
    FloodCohortEventSpec(
        activation="EMSR629",
        event_key="EMSR629_Indus_Sindh",
        aoi_name="Sindh_Indus_Basin_Pakistan",
        country="Pakistan",
        flood_regime="INLAND_RIVERINE_MEGA",
        bbox=(68.0727, 27.4560, 68.4402, 27.6986),
        grid_shape=(512, 512),
        s1_before_item="S1A_IW_GRDH_1SDV_20220827T133609_20220827T133634_044739_055782",
        s1_event_item="S1A_IW_GRDH_1SDV_20220908T133635_20220908T133700_044914_055D60",
        s2_before_item="S2B_MSIL2A_20220908T060639_R134_T42RVR_20220908T202920",
        s2_event_item="S2A_MSIL2A_20220910T055651_R091_T42RVR_20220911T193156",
        cop_dem_item="Copernicus_DSM_COG_10_N27_00_E068_00_DEM",
        jrc_gsw_item="60E_30Nv1_3_2020",
        reference_shapefile="data/results/flood_multievent/cems_reference/extracted/EMSR629_AOI01_DEL_PRODUCT_r1_RTP01_v2_vector/EMSR629_AOI01_DEL_PRODUCT_observedEventA_r1_v2.shp",
    ),
    FloodCohortEventSpec(
        activation="EMSR548",
        event_key="EMSR548_Catania",
        aoi_name="Catania_Plain_Sicily_Italy",
        country="Italy",
        flood_regime="INLAND_RIVERINE_PLUVIAL",
        bbox=(14.8242, 37.3195, 15.1298, 37.6442),
        grid_shape=(512, 512),
        s1_before_item="S1B_IW_GRDH_1SDV_20211013T165544_20211013T165609_029120_03798F",
        s1_event_item="S1A_IW_GRDH_1SDV_20211024T170445_20211024T170510_040264_04C54D",
        s2_before_item="S2B_MSIL2A_20210919T095029_R079_T33SWB_20210920T004521",
        s2_event_item="S2A_MSIL2A_20211004T095031_R079_T33SWB_20211004T200455",
        cop_dem_item="Copernicus_DSM_COG_10_N37_00_E014_00_DEM",
        jrc_gsw_item="10E_40Nv1_3_2020",
        reference_shapefile="data/results/flood_multievent/cems_reference/extracted/EMSR548_AOI01_DEL_MONIT03_r1_RTP01_v3_vector/EMSR548_AOI01_DEL_MONIT03_observedEventA_r1_v3.shp",
    ),
]

# 2. Completely Unseen Validation Holdout Cohort (2 historical activations)
UNSEEN_SPECS: list[FloodCohortEventSpec] = [
    FloodCohortEventSpec(
        activation="EMSR348",
        event_key="EMSR348_Quelimane",
        aoi_name="Quelimane_Zambezia_Mozambique",
        country="Mozambique",
        flood_regime="COASTAL_ESTUARINE_TIDAL",
        bbox=(36.7515, -17.9895, 37.0494, -17.7383),
        grid_shape=(512, 512),
        s1_before_item="S1B_IW_GRDH_1SDV_20190314T160711_20190314T160736_015352_01CBEE",
        s1_event_item="S1B_IW_GRDH_1SDV_20190320T030748_20190320T030813_015432_01CE6E",
        s2_before_item="S2A_MSIL2A_20190225T072901_R049_T37KBA_20201007T202348",
        s2_event_item="S2B_MSIL2A_20190401T072619_R049_T37KBA_20201006T210326",
        cop_dem_item="Copernicus_DSM_COG_10_S18_00_E036_00_DEM",
        jrc_gsw_item="30E_10Sv1_3_2020",
        reference_shapefile="data/results/flood_multievent/cems_reference/extracted/EMSR348_01QUELIMANE_01DELINEATION_MAP_v2_vector/VECTOR/EMSR348_01QUELIMANE_DEL_v2_observed_event_a.shp",
    ),
    FloodCohortEventSpec(
        activation="EMSR468",
        event_key="EMSR468_Piedmont",
        aoi_name="Tanaro_Piedmont_Italy",
        country="Italy",
        flood_regime="INLAND_RIVERINE_PLUVIAL",
        bbox=(7.7543, 44.1167, 8.0641, 44.5440),
        grid_shape=(512, 512),
        s1_before_item="S1B_IW_GRDH_1SDV_20200927T172230_20200927T172255_023564_02CC5D",
        s1_event_item="S1B_IW_GRDH_1SDV_20201008T053524_20201008T053549_023717_02D113",
        s2_before_item="S2A_MSIL2A_20200921T103031_R108_T32TLQ_20200921T181938",
        s2_event_item="S2B_MSIL2A_20201013T101909_R065_T32TLQ_20201028T180734",
        cop_dem_item="Copernicus_DSM_COG_10_N44_00_E007_00_DEM",
        jrc_gsw_item="0E_50Nv1_3_2020",
        reference_shapefile="data/results/flood_multievent/cems_reference/extracted/EMSR468_AOI02_DEL_PRODUCT_r1_RTP01_v1_vector/EMSR468_AOI02_DEL_PRODUCT_observedEventA_r1_v1.shp",
    ),
]


def evaluate_cohort_events(
    specs: list[FloodCohortEventSpec],
    cohort_tag: str = "unseen",
    output_dir: Path | str = "data/results/flood_regime_routing",
) -> dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 95)
    print(f"  EARTH ONE FLOOD MODULE: BLOCK 4D EVALUATION [{cohort_tag.upper()} COHORT]")
    print(f"  Cohort Size: {len(specs)} independent historical activations")
    print("  Engine: Soft Autonomous Regime Router v0.2 + Continuous Confidence Blending")
    print("=" * 95)

    cohort_results = {}
    classification_matches = []

    for spec in specs:
        print(f"\n>>> EVALUATING EVENT: {spec.activation} ({spec.country} — {spec.flood_regime}) <<<")
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

        # Stream Physical Pre-Event Baselines
        print("  [1/4] Streaming Pre-Event Baselines (GSW, DEM)...")
        jrc_item = get_stac_item("jrc-gsw", spec.jrc_gsw_item)
        dem_item = get_stac_item("cop-dem-glo-30", spec.cop_dem_item)

        jrc_raw = read_warped_band(jrc_item["assets"]["occurrence"]["href"])
        jrc_freq, jrc_valid = normalize_water_occurrence(jrc_raw, nodata=255)

        elevation_m = read_warped_band(dem_item["assets"]["data"]["href"])
        slope_deg = compute_dem_slope(elevation_m, cell_x_m, cell_y_m)

        # Autonomous Zero-Leakage Regime Classification v0.2
        print("  [2/4] Executing Autonomous Biophysical Regime Classification v0.2...")
        regime_result = classify_biophysical_regime(
            jrc_occurrence=jrc_freq,
            elevation_m=elevation_m,
            slope_deg=slope_deg,
            centroid_lat=mid_lat,
            centroid_lon=(w + e) / 2.0,
        )
        is_match = (regime_result.regime == spec.flood_regime)
        classification_matches.append(is_match)
        print(f"        -> Classified Regime: {regime_result.regime} (Confidence: {regime_result.confidence*100:.1f}%) | Ground Truth: {spec.flood_regime} -> Match: {is_match}")

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

        # Load Independent CEMS Reference Delineation
        ref_shp = Path(spec.reference_shapefile)
        cems_ref_mask, _ = load_vector_reference(ref_shp, target_profile)
        ref_y = cems_ref_mask.flatten().astype(int)
        cems_ref_px = int(np.sum(cems_ref_mask))
        cems_ref_ha = float(cems_ref_px * pixel_area_ha)

        # -------------------------------------------------------------
        # SYSTEM 1: FROZEN GLOBAL BASELINE v0.1
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
        # SYSTEM 2: CALIBRATED SOFT REGIME-ROUTED ENGINE v0.2
        # -------------------------------------------------------------
        cfg_routed = regime_result.recommended_config
        sar_sc_r, sar_v_r = compute_sar_water_evidence(vv_b, vv_e, vh_b, vh_e, config=cfg_routed)
        opt_sc_r, opt_v_r = compute_optical_water_evidence(b03_e, b08_e, b11_e, scl_mask=scl_e, config=cfg_routed)
        m_nov_r = np.where(jrc_valid, np.clip(1.0 - (jrc_freq / cfg_routed.permanent_water_max_freq), 0.0, 1.0), 1.0)
        terr_sc_r, terr_v_r = compute_terrain_plausibility(slope_deg, config=cfg_routed)
        rain_sc_r = compute_rainfall_context(rain_obs.accumulation_mm, rain_obs.anomaly_std, rain_obs.hours_since_peak, config=cfg_routed)

        # Soft Coastal Protection with floor M_min = 0.35
        m_intertidal, _ = compute_intertidal_suppression_mask(jrc_freq, elevation_m, slope_deg, min_multiplier_floor=0.35)
        if regime_result.regime == "COASTAL_ESTUARINE_TIDAL":
            m_nov_r = m_nov_r * m_intertidal

        det_regime_raw = fuse_flood_evidence(
            sar_evidence=sar_sc_r, sar_valid=sar_v_r,
            optical_evidence=opt_sc_r, optical_valid=opt_v_r,
            novelty_evidence=m_nov_r, novelty_valid=jrc_valid,
            terrain_plausibility=terr_sc_r, terrain_valid=terr_v_r,
            rainfall_score=rain_sc_r, config=cfg_routed,
        )

        # Continuous Confidence-Weighted Blending
        C = regime_result.confidence if regime_result.regime != "MIXED_UNCERTAIN" else 0.0
        fused_blended_score = (1.0 - C) * det_global.flood_score + C * det_regime_raw.flood_score

        score_routed = fused_blended_score.flatten()
        p_cr, r_cr, _ = precision_recall_curve(ref_y, score_routed)
        pr_auc_routed = float(auc(r_cr, p_cr))
        roc_auc_routed = float(roc_auc_score(ref_y, score_routed))

        # Operational metrics at T=0.20
        pred_r = det_global.valid_mask & (fused_blended_score >= 0.20)
        if cfg_routed.apply_morphological_opening and pred_r.any():
            pred_r = ndimage.binary_opening(pred_r, structure=np.ones((2, 2), dtype=bool))

        tp_r = int(np.sum(pred_r & cems_ref_mask))
        fp_r = int(np.sum(pred_r & (~cems_ref_mask)))
        prec_r = float(tp_r / (tp_r + fp_r)) if (tp_r + fp_r) > 0 else 0.0
        rec_r = float(tp_r / cems_ref_px) if cems_ref_px > 0 else 0.0
        f1_r = float(2 * prec_r * rec_r / (prec_r + rec_r)) if (prec_r + rec_r) > 0 else 0.0
        iou_r = float(tp_r / (tp_r + fp_r + (cems_ref_px - tp_r))) if cems_ref_px > 0 else 0.0
        bias_r = float((np.sum(pred_r) * pixel_area_ha) / cems_ref_ha) if cems_ref_ha > 0 else 0.0

        # Scientific Metrics
        delta_pr_auc = pr_auc_routed - pr_auc_global
        delta_f1 = f1_r - f1_g20
        delta_prec = prec_r - prec_g20
        tp_retention = float(tp_r / tp_g) if tp_g > 0 else 1.0
        fp_reduction_pct = float((fp_g - fp_r) / fp_g * 100.0) if fp_g > 0 else 0.0

        print(f"  [4/4] Comparative Performance:")
        print(f"        -> GLOBAL BASELINE: PR-AUC={pr_auc_global:.4f} | Prec={prec_g20*100:.1f}% | F1={f1_g20*100:.1f}% | Bias={bias_g20:.2f}x | FP={fp_g:,} | TP={tp_g:,}")
        print(f"        -> REGIME ROUTED:   PR-AUC={pr_auc_routed:.4f} | Prec={prec_r*100:.1f}% | F1={f1_r*100:.1f}% | Bias={bias_r:.2f}x | FP={fp_r:,} | TP={tp_r:,}")
        print(f"        -> SCIENTIFIC DELTA: ΔPR-AUC={delta_pr_auc:+.4f} | ΔPrec={delta_prec*100:+.1f}% | TP-Retention={tp_retention*100:.1f}% | FP-Cut={fp_reduction_pct:+.1f}%")

        cohort_results[spec.activation] = {
            "case_study": asdict(spec),
            "regime_classification": {
                "ground_truth_regime": spec.flood_regime,
                "classified_regime": regime_result.regime,
                "confidence": regime_result.confidence,
                "uncertainty": regime_result.uncertainty,
                "is_correct_classification": bool(is_match),
                "features": regime_result.features,
            },
            "global_baseline_v01": {
                "pr_auc": round(pr_auc_global, 5),
                "roc_auc": round(roc_auc_global, 5),
                "operational_metrics": {"threshold": 0.20, "precision": round(prec_g20, 4), "recall": round(rec_g20, 4), "f1_score": round(f1_g20, 4), "iou": round(iou_g20, 4), "area_bias": round(bias_g20, 3), "fp_pixels": fp_g, "tp_pixels": tp_g},
            },
            "regime_routed_engine": {
                "pr_auc": round(pr_auc_routed, 5),
                "roc_auc": round(roc_auc_routed, 5),
                "operational_metrics": {"threshold": 0.20, "precision": round(prec_r, 4), "recall": round(rec_r, 4), "f1_score": round(f1_r, 4), "iou": round(iou_r, 4), "area_bias": round(bias_r, 3), "fp_pixels": fp_r, "tp_pixels": tp_r},
            },
            "safety_and_delta_metrics": {
                "delta_pr_auc": round(delta_pr_auc, 5),
                "delta_precision": round(delta_prec, 4),
                "delta_f1_score": round(delta_f1, 4),
                "true_positive_retention_rate": round(tp_retention, 4),
                "false_positive_reduction_pct": round(fp_reduction_pct, 2),
            }
        }

    macro_pr_global = float(np.mean([e["global_baseline_v01"]["pr_auc"] for e in cohort_results.values()]))
    macro_pr_routed = float(np.mean([e["regime_routed_engine"]["pr_auc"] for e in cohort_results.values()]))
    classification_accuracy = float(np.mean(classification_matches))

    final_payload = {
        "schema": "earth_one_regime_routing_validation_v1.0",
        "cohort_tag": cohort_tag,
        "macro_summary": {
            "total_events": len(specs),
            "classification_accuracy": round(classification_accuracy, 4),
            "macro_pr_auc_global": round(macro_pr_global, 5),
            "macro_pr_auc_routed": round(macro_pr_routed, 5),
            "macro_delta_pr_auc": round(macro_pr_routed - macro_pr_global, 5),
        },
        "event_evaluations": cohort_results,
    }

    out_file = out_dir / f"{cohort_tag}_event_results.json"
    out_file.write_text(json.dumps(final_payload, indent=2), encoding="utf-8")
    print(f"\nSaved {cohort_tag.upper()} Cohort Ledger to {out_file}")
    return final_payload


def run_full_block4d_validation():
    # 1. Run Development Cohort
    dev_res = evaluate_cohort_events(DEVELOPMENT_SPECS, cohort_tag="development")
    # 2. Run Unseen Test Cohort
    unseen_res = evaluate_cohort_events(UNSEEN_SPECS, cohort_tag="unseen")

    manifest = {
        "block": "BLOCK_4D",
        "version": "regime_router_v0.2",
        "development_cohort": dev_res["macro_summary"],
        "unseen_cohort": unseen_res["macro_summary"],
    }
    Path("data/results/flood_regime_routing/regime_routing_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest
