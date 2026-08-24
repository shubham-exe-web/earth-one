from __future__ import annotations

"""Block 3D: Flood Decision-Engine Redesign, Ablation, and PR-AUC Benchmark.

Evaluates both:
1. Redesigned Gated Physics Engine (JRC multiplicative novelty gate + DEM slope constraint)
2. Baseline Linear Blend Engine (Prototypical additive blend)

Metrics Computed across Modes A-F and Operating Regimes:
- Continuous PR-AUC (Precision-Recall Area Under Curve)
- Continuous ROC-AUC
- Brier Calibration Score
- Precision, Recall, F1 Score, IoU, MCC
- Object-level Bipartite Recall (tau_IoU >= 0.10)
- Area Bias Ratio (Predicted Area / Reference Inundation Area)
- Score Distributions (Mean score over Ground Truth vs Background)
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
    segment_flood_events,
    build_flood_alert_payload,
)
from .flood_reference import load_vector_reference, normalize_water_occurrence, permanent_water_mask


def robust_urlopen(req: urllib.request.Request, timeout: int = 25, retries: int = 3):
    for attempt in range(retries):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except Exception as e:
            if attempt == retries - 1:
                raise e
            time.sleep(1.5 * (attempt + 1))


def sign_planetary_url(href: str) -> str:
    encoded = urllib.parse.quote(href, safe="")
    sign_url = f"https://planetarycomputer.microsoft.com/api/sas/v1/sign?href={encoded}"
    req = urllib.request.Request(sign_url, headers={"User-Agent": "EarthOne-Flood-Research"})
    with robust_urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8")).get("href")


def get_stac_item(collection: str, item_id: str) -> dict[str, Any]:
    url = f"https://planetarycomputer.microsoft.com/api/stac/v1/collections/{collection}/items/{item_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "EarthOne-Flood-Research"})
    with robust_urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def compute_dem_slope(elevation_m: np.ndarray, cell_size_x_m: float, cell_size_y_m: float) -> np.ndarray:
    """Compute physical slope in degrees from 2D elevation matrix."""
    dz_dy, dz_dx = np.gradient(elevation_m, cell_size_y_m, cell_size_x_m)
    slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    return np.degrees(slope_rad).astype(np.float32)


def run_flood_evidence_ablation(
    output_dir: Path | str = "data/results/flood_experiment1/ablation",
    config: FloodEvidenceConfig | None = None,
) -> dict[str, Any]:
    if config is None:
        config = FloodEvidenceConfig(fusion_strategy="gated_physics")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Exact Analysis Grid Definition (512 x 512)
    bbox = (91.3591, 22.3493, 91.4019, 22.3913)
    w, s, e, n = bbox
    H, W = 512, 512
    t_site = rasterio.transform.from_bounds(w, s, e, n, W, H)
    target_profile = {"width": W, "height": H, "crs": "EPSG:4326", "transform": t_site}

    cell_x_m = abs(t_site.a * 111319.5 * np.cos(np.radians(22.37)))
    cell_y_m = abs(t_site.e * 111319.5)
    pixel_area_m2 = cell_x_m * cell_y_m
    pixel_area_ha = pixel_area_m2 / 10000.0
    total_aoi_ha = (H * W) * pixel_area_ha

    print("=" * 88)
    print("  EARTH ONE FLOOD MODULE: BLOCK 3D DECISION-ENGINE REDESIGN & ABLATION BENCHMARK")
    print(f"  AOI: EMSR439 Sandwip Channel | BBox: {bbox}")
    print(f"  Grid: {W}x{H} | Cell: {cell_x_m:.2f}m x {cell_y_m:.2f}m | Pixel Area: {pixel_area_m2:.2f} m² ({pixel_area_ha:.6f} ha)")
    print(f"  Total Footprint: {total_aoi_ha:.1f} ha")
    print("=" * 88)

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
            except Exception as e:
                if attempt == retries - 1:
                    print(f"Warning: failed band read {href.split('/')[-1]} after {retries} attempts: {e}")
                    return dest
                time.sleep(1.5 * (attempt + 1))
        return dest

    # 2. Fetch STAC items
    print("  [1/5] Fetching Satellite & Reference STAC Items...")
    s1_b_item = get_stac_item("sentinel-1-grd", "S1A_IW_GRDH_1SDV_20200429T234818_20200429T234843_032349_03BE86")
    s1_e_item = get_stac_item("sentinel-1-grd", "S1A_IW_GRDH_1SDV_20200523T234819_20200523T234844_032699_03C99A")
    s2_b_item = get_stac_item("sentinel-2-l2a", "S2B_MSIL2A_20200312T042659_R133_T46QCK_20201006T232116")
    s2_e_item = get_stac_item("sentinel-2-l2a", "S2B_MSIL2A_20200531T042709_R133_T46QCK_20200911T155808")
    dem_item = get_stac_item("cop-dem-glo-30", "Copernicus_DSM_COG_10_N22_00_E091_00_DEM")
    jrc_item = get_stac_item("jrc-gsw", "90E_30Nv1_3_2020")

    # 3. Stream Satellite & Baseline Rasters
    print("  [2/5] Streaming Real Earth Observation Layers...")
    vv_raw_b = read_warped_band(s1_b_item["assets"]["vv"]["href"])
    vh_raw_b = read_warped_band(s1_b_item["assets"]["vh"]["href"])
    vv_raw_e = read_warped_band(s1_e_item["assets"]["vv"]["href"])
    vh_raw_e = read_warped_band(s1_e_item["assets"]["vh"]["href"])

    vv_b = (vv_raw_b / 475.0) ** 2
    vh_b = (vh_raw_b / 530.0) ** 2
    vv_e = (vv_raw_e / 475.0) ** 2
    vh_e = (vh_raw_e / 530.0) ** 2
    sar_score, sar_valid = compute_sar_water_evidence(vv_b, vv_e, vh_b, vh_e, config=config)

    b03_e = read_warped_band(s2_e_item["assets"]["B03"]["href"]) / 10000.0
    b08_e = read_warped_band(s2_e_item["assets"]["B08"]["href"]) / 10000.0
    b11_e = read_warped_band(s2_e_item["assets"]["B11"]["href"]) / 10000.0
    scl_e = read_warped_band(s2_e_item["assets"]["SCL"]["href"], resampling=Resampling.nearest).astype(int)
    opt_score, opt_valid = compute_optical_water_evidence(b03_e, b08_e, b11_e, scl_mask=scl_e, config=config)

    jrc_raw = read_warped_band(jrc_item["assets"]["occurrence"]["href"])
    jrc_freq, jrc_valid = normalize_water_occurrence(jrc_raw, nodata=255)
    # JRC Novelty Multiplier: 1.0 on dry land (0% occ), decaying to 0.0 on permanent water (>= 80% occ)
    m_novelty = np.clip(1.0 - (jrc_freq / config.permanent_water_max_freq), 0.0, 1.0)
    m_novelty = np.where(jrc_valid, m_novelty, 1.0)

    elevation_m = read_warped_band(dem_item["assets"]["data"]["href"])
    slope_deg = compute_dem_slope(elevation_m, cell_x_m, cell_y_m)
    terrain_score, terr_valid = compute_terrain_plausibility(slope_deg, config=config)

    rain_score = compute_rainfall_context(accumulation_mm=220.0, anomaly_std=3.2, hours_since_peak=12.0, config=config)

    # 4. Rasterize Independent CEMS Reference
    ref_shp = Path("data/results/flood_experiment1/emsr439_reference/extracted/EMSR439_AOI01_DEL_PRODUCT_r1_VECTORS_v1_vector/EMSR439_AOI01_DEL_PRODUCT_observedEventA_r1_v1.shp")
    print(f"  [3/5] Rasterizing Independent CEMS Reference from {ref_shp.name}...")
    cems_ref_mask, _ = load_vector_reference(ref_shp, target_profile)
    cems_ref_px = int(np.sum(cems_ref_mask))
    cems_ref_ha = float(cems_ref_px * pixel_area_ha)
    ref_y = cems_ref_mask.flatten().astype(int)
    print(f"        CEMS Reference Inundation: {cems_ref_px:,} pixels ({cems_ref_ha:.2f} ha, {cems_ref_ha/total_aoi_ha*100:.2f}% of AOI)")

    # 5. Define 6 Ablation Modes
    ablation_modes = {
        "A_SAR_Only": {
            "name": "Mode A: SAR Backscatter Only",
            "channels": {"sar_evidence": sar_score, "sar_valid": sar_valid},
        },
        "B_Optical_Only": {
            "name": "Mode B: Optical MNDWI/NDWI Only",
            "channels": {"optical_evidence": opt_score, "optical_valid": opt_valid},
        },
        "C_SAR_Optical": {
            "name": "Mode C: SAR + Optical Multimodal",
            "channels": {"sar_evidence": sar_score, "sar_valid": sar_valid, "optical_evidence": opt_score, "optical_valid": opt_valid},
        },
        "D_SAR_JRC_Novelty": {
            "name": "Mode D: SAR + JRC GSW Water Novelty",
            "channels": {"sar_evidence": sar_score, "sar_valid": sar_valid, "novelty_evidence": m_novelty, "novelty_valid": jrc_valid},
        },
        "E_SAR_DEM_Terrain": {
            "name": "Mode E: SAR + Real COP-DEM Slope Constraint",
            "channels": {"sar_evidence": sar_score, "sar_valid": sar_valid, "terrain_plausibility": terrain_score, "terrain_valid": terr_valid},
        },
        "F_Full_5_Channel": {
            "name": "Mode F: Full 5-Channel Evidence Fusion",
            "channels": {
                "sar_evidence": sar_score, "sar_valid": sar_valid,
                "optical_evidence": opt_score, "optical_valid": opt_valid,
                "novelty_evidence": m_novelty, "novelty_valid": jrc_valid,
                "terrain_plausibility": terrain_score, "terrain_valid": terr_valid,
                "rainfall_score": rain_score,
            },
        },
    }

    # 6. Execute Quantitative Ablation Matrix with Gated Physics vs Linear Blend
    print("\n  [4/5] Executing Decision-Engine Comparison & Ablation Matrix...")
    struct_8 = ndimage.generate_binary_structure(2, 2)
    ref_labeled, num_ref_objs = ndimage.label(cems_ref_mask, structure=struct_8)

    ablation_results = {}

    for strat in ["gated_physics", "linear_blend"]:
        print(f"\n  ==================== STRATEGY: {strat.upper()} ====================")
        strat_cfg = FloodEvidenceConfig(fusion_strategy=strat)
        strat_results = {}

        for mode_id, m_spec in ablation_modes.items():
            print(f"\n  ---> EVALUATING {m_spec["name"]} [{strat}] <---")
            det_res = fuse_flood_evidence(**m_spec["channels"], config=strat_cfg)
            score_flat = det_res.flood_score.flatten()

            # Continuous PR-AUC & ROC-AUC
            p_curve, r_curve, _ = precision_recall_curve(ref_y, score_flat)
            pr_auc = float(auc(r_curve, p_curve))
            roc_auc = float(roc_auc_score(ref_y, score_flat))
            brier = float(brier_score_loss(ref_y, score_flat))

            mean_ref_score = float(np.mean(score_flat[ref_y == 1])) if np.sum(ref_y) > 0 else 0.0
            mean_bg_score = float(np.mean(score_flat[ref_y == 0]))

            mode_thresholds = {}
            for r_name, thresh in [("T=0.15 (High Sens)", 0.15), ("T=0.20 (Operational)", 0.20), ("T=0.30 (Balanced)", 0.30), ("T=0.50 (High Spec)", 0.50)]:
                pred_mask = det_res.valid_mask & (det_res.flood_score >= thresh)
                if strat_cfg.apply_morphological_opening and pred_mask.any():
                    pred_mask = ndimage.binary_opening(pred_mask, structure=np.ones((2, 2), dtype=bool))

                pred_px = int(np.sum(pred_mask))
                pred_ha = float(pred_px * pixel_area_ha)

                tp = int(np.sum(pred_mask & cems_ref_mask))
                fp = int(np.sum(pred_mask & (~cems_ref_mask) & det_res.valid_mask))
                fn = int(np.sum((~pred_mask) & cems_ref_mask & det_res.valid_mask))
                tn = int(np.sum((~pred_mask) & (~cems_ref_mask) & det_res.valid_mask))

                precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
                recall = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0
                f1 = float(2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
                iou = float(tp / (tp + fp + fn)) if (tp + fp + fn) > 0 else 0.0
                mcc_den = np.sqrt(float(tp + fp) * float(tp + fn) * float(tn + fp) * float(tn + fn))
                mcc = float((tp * tn - fp * fn) / mcc_den) if mcc_den > 0 else 0.0

                # Object matching
                pred_labeled, num_pred_objs = ndimage.label(pred_mask, structure=struct_8)
                matched_objs = 0
                obj_ious = []
                if num_ref_objs > 0 and num_pred_objs > 0:
                    for ref_idx in range(1, num_ref_objs + 1):
                        r_mask = (ref_labeled == ref_idx)
                        inter_preds = np.unique(pred_labeled[r_mask])
                        inter_preds = inter_preds[inter_preds > 0]
                        if len(inter_preds) > 0:
                            p_mask = np.isin(pred_labeled, inter_preds)
                            o_iou = float(np.sum(r_mask & p_mask) / np.sum(r_mask | p_mask))
                            obj_ious.append(o_iou)
                            if o_iou >= 0.10:
                                matched_objs += 1

                obj_recall = float(matched_objs / num_ref_objs) if num_ref_objs > 0 else 0.0
                area_bias = float(pred_ha / cems_ref_ha) if cems_ref_ha > 0 else 0.0

                mode_thresholds[r_name] = {
                    "threshold": thresh,
                    "predicted_ha": round(pred_ha, 2),
                    "area_bias_ratio": round(area_bias, 3),
                    "precision": round(precision, 4),
                    "recall": round(recall, 4),
                    "f1_score": round(f1, 4),
                    "iou": round(iou, 4),
                    "mcc": round(mcc, 4),
                    "object_recall_tau10": round(obj_recall, 4),
                    "false_positive_pixels": fp,
                    "false_negative_pixels": fn,
                }
                print(f"       [{r_name:20s}] Rec={recall*100:5.1f}% | Prec={precision*100:5.1f}% | F1={f1*100:5.1f}% | IoU={iou*100:5.1f}% | Bias={area_bias:5.2f}x | FP={fp:6d}")

            strat_results[mode_id] = {
                "mode_name": m_spec["name"],
                "channels_used": det_res.available_channels,
                "distributional_metrics": {
                    "pr_auc": round(pr_auc, 5),
                    "roc_auc": round(roc_auc, 5),
                    "brier_score": round(brier, 5),
                    "mean_reference_score": round(mean_ref_score, 4),
                    "mean_background_score": round(mean_bg_score, 4),
                    "signal_to_background_ratio": round(mean_ref_score / max(1e-5, mean_bg_score), 2),
                },
                "threshold_metrics": mode_thresholds,
            }
            print(f"       >> PR-AUC: {pr_auc:.4f} | ROC-AUC: {roc_auc:.4f} | Sig/BG Ratio: {mean_ref_score/max(1e-5, mean_bg_score):.2f}x <<")

        ablation_results[strat] = strat_results

    # 7. Serialize Output Manifest & Results Ledger
    print("\n  [5/5] Serializing Block 3D Results Ledger...")
    final_payload = {
        "schema": "earth_one_flood_decision_engine_benchmark_v1.0",
        "case_study": {
            "activation": "EMSR439",
            "aoi": "Sandwip_Channel_Bangladesh",
            "bbox_epsg4326": list(bbox),
            "grid_dimensions": {"width": W, "height": H, "pixel_area_m2": round(pixel_area_m2, 2), "pixel_area_ha": round(pixel_area_ha, 6), "total_aoi_ha": round(total_aoi_ha, 2)},
        },
        "provenance": {
            "sentinel1_grd_baseline": s1_b_item["id"],
            "sentinel1_grd_event": s1_e_item["id"],
            "sentinel2_l2a_baseline": s2_b_item["id"],
            "sentinel2_l2a_event": s2_e_item["id"],
            "copernicus_dem_glo30": dem_item["id"],
            "jrc_gsw_occurrence_tile": jrc_item["id"],
            "cems_reference_vector": str(ref_shp.resolve()),
        },
        "reference_summary": {
            "total_reference_pixels": cems_ref_px,
            "total_reference_ha": round(cems_ref_ha, 2),
            "reference_polygons": num_ref_objs,
        },
        "decision_engine_benchmark": ablation_results,
    }

    manifest_file = out_dir / "flood_ablation_results.json"
    manifest_file.write_text(json.dumps(final_payload, indent=2), encoding="utf-8")
    print(f"        Saved to {manifest_file}")
    return final_payload
