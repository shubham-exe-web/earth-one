from __future__ import annotations

"""Block 4A: Multi-Event Flood Validation & Generalization Benchmark.

Evaluates the Frozen Gated Physics Decision Engine v0.1 across independent historical flood regimes:
1. Event 1: CEMS EMSR439 (Coastal Storm-Surge Inundation, Sandwip Channel, Bangladesh, May 2020)
2. Event 2: CEMS EMSR629 (Inland Mega-Riverine Inundation, Indus Basin / Sindh, Pakistan, Aug 2022)

Observational & Physical Evidence:
- Real Sentinel-1 dual-pol SAR specular attenuation (ΔVV, ΔVH)
- Real Sentinel-2 L2A optical water indices (NDWI, MNDWI) with cloud masking
- Real JRC Global Surface Water 1984-2024 occurrence novelty gating
- Real Copernicus DEM GLO-30 physical slope constraint
- Real precipitation time series & standardized anomaly (flood_rainfall.py)
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
from .flood_reference import load_vector_reference, normalize_water_occurrence
from .flood_rainfall import get_historical_event_rainfall, RainfallObservation


@dataclass(frozen=True)
class FloodCohortEventSpec:
    activation: str
    event_key: str
    aoi_name: str
    country: str
    flood_regime: str  # "Coastal Storm Surge", "Inland Riverine Flood", "Monsoon Valley Flood"
    bbox: tuple[float, float, float, float]  # W, S, E, N
    grid_shape: tuple[int, int]
    s1_before_item: str
    s1_event_item: str
    s2_before_item: str
    s2_event_item: str
    cop_dem_item: str
    jrc_gsw_item: str
    reference_shapefile: str


COHORT_SPECS: list[FloodCohortEventSpec] = [
    FloodCohortEventSpec(
        activation="EMSR548",
        event_key="EMSR548_Catania",
        aoi_name="Catania_Plain_Sicily_Italy",
        country="Italy",
        flood_regime="Inland Riverine Flood",
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
    FloodCohortEventSpec(
        activation="EMSR439",
        event_key="EMSR439_Sandwip",
        aoi_name="Sandwip_Channel_Bangladesh",
        country="Bangladesh",
        flood_regime="Coastal Storm Surge",
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
        flood_regime="Inland Mega-Riverine Flood",
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
]


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
    dz_dy, dz_dx = np.gradient(elevation_m, cell_size_y_m, cell_size_x_m)
    slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    return np.degrees(slope_rad).astype(np.float32)


def execute_multievent_flood_validation(
    specs: list[FloodCohortEventSpec] | None = None,
    output_dir: Path | str = "data/results/flood_multievent",
    config: FloodEvidenceConfig | None = None,
) -> dict[str, Any]:
    if specs is None:
        specs = COHORT_SPECS
    if config is None:
        config = FloodEvidenceConfig(fusion_strategy="gated_physics")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 90)
    print("  EARTH ONE FLOOD MODULE: MULTI-EVENT VALIDATION & GENERALIZATION BENCHMARK")
    print(f"  Cohort Size: {len(specs)} independent historical flood activations")
    print(f"  Engine: Frozen Gated Physics Decision Engine v0.1")
    print("=" * 90)

    cohort_results = {}

    for spec in specs:
        print(f"\n>>> PROCESSING EVENT: {spec.activation} ({spec.country} — {spec.flood_regime}) <<<")
        w, s, e, n = spec.bbox
        H, W = spec.grid_shape
        t_site = rasterio.transform.from_bounds(w, s, e, n, W, H)
        target_profile = {"width": W, "height": H, "crs": "EPSG:4326", "transform": t_site}

        mid_lat = (s + n) / 2.0
        cell_x_m = abs(t_site.a * 111319.5 * np.cos(np.radians(mid_lat)))
        cell_y_m = abs(t_site.e * 111319.5)
        pixel_area_m2 = cell_x_m * cell_y_m
        pixel_area_ha = pixel_area_m2 / 10000.0
        total_aoi_ha = (H * W) * pixel_area_ha

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

        # Fetch STAC items
        print("  -> Fetching STAC items...")
        s1_b_item = get_stac_item("sentinel-1-grd", spec.s1_before_item)
        s1_e_item = get_stac_item("sentinel-1-grd", spec.s1_event_item)
        s2_b_item = get_stac_item("sentinel-2-l2a", spec.s2_before_item)
        s2_e_item = get_stac_item("sentinel-2-l2a", spec.s2_event_item)
        dem_item = get_stac_item("cop-dem-glo-30", spec.cop_dem_item)
        jrc_item = get_stac_item("jrc-gsw", spec.jrc_gsw_item)

        # Stream Rasters
        print("  -> Streaming Sentinel-1 SAR GRD...")
        vv_raw_b = read_warped_band(s1_b_item["assets"]["vv"]["href"])
        vv_raw_e = read_warped_band(s1_e_item["assets"]["vv"]["href"])
        vv_b = (vv_raw_b / 475.0) ** 2
        vv_e = (vv_raw_e / 475.0) ** 2

        vh_b = (read_warped_band(s1_b_item["assets"]["vh"]["href"]) / 530.0) ** 2 if "vh" in s1_b_item.get("assets", {}) else None
        vh_e = (read_warped_band(s1_e_item["assets"]["vh"]["href"]) / 530.0) ** 2 if "vh" in s1_e_item.get("assets", {}) else None

        sar_score, sar_valid = compute_sar_water_evidence(vv_b, vv_e, vh_b, vh_e, config=config)

        print("  -> Streaming Sentinel-2 Optical L2A...")
        b03_e = read_warped_band(s2_e_item["assets"]["B03"]["href"]) / 10000.0
        b08_e = read_warped_band(s2_e_item["assets"]["B08"]["href"]) / 10000.0
        b11_e = read_warped_band(s2_e_item["assets"]["B11"]["href"]) / 10000.0
        scl_e = read_warped_band(s2_e_item["assets"]["SCL"]["href"], resampling=Resampling.nearest).astype(int)
        opt_score, opt_valid = compute_optical_water_evidence(b03_e, b08_e, b11_e, scl_mask=scl_e, config=config)

        print("  -> Streaming JRC GSW Occurrence Baseline...")
        jrc_raw = read_warped_band(jrc_item["assets"]["occurrence"]["href"])
        jrc_freq, jrc_valid = normalize_water_occurrence(jrc_raw, nodata=255)
        m_novelty = np.clip(1.0 - (jrc_freq / config.permanent_water_max_freq), 0.0, 1.0)
        m_novelty = np.where(jrc_valid, m_novelty, 1.0)

        print("  -> Streaming Copernicus DEM GLO-30...")
        elevation_m = read_warped_band(dem_item["assets"]["data"]["href"])
        slope_deg = compute_dem_slope(elevation_m, cell_x_m, cell_y_m)
        terrain_score, terr_valid = compute_terrain_plausibility(slope_deg, config=config)

        print("  -> Ingesting Verified Rainfall Observation...")
        rain_obs = get_historical_event_rainfall(spec.event_key)
        rain_score = compute_rainfall_context(
            accumulation_mm=rain_obs.accumulation_mm,
            anomaly_std=rain_obs.anomaly_std,
            hours_since_peak=rain_obs.hours_since_peak,
            config=config,
        )

        # Fuse Gated Decision Engine
        print("  -> Executing Frozen Gated Decision Engine v0.1...")
        det_res = fuse_flood_evidence(
            sar_evidence=sar_score, sar_valid=sar_valid,
            optical_evidence=opt_score, optical_valid=opt_valid,
            novelty_evidence=m_novelty, novelty_valid=jrc_valid,
            terrain_plausibility=terrain_score, terrain_valid=terr_valid,
            rainfall_score=rain_score, config=config,
            aoi_metadata={"activation": spec.activation, "country": spec.country}
        )

        # Load Independent CEMS Reference Delineation
        ref_shp = Path(spec.reference_shapefile)
        cems_ref_mask, _ = load_vector_reference(ref_shp, target_profile)
        cems_ref_px = int(np.sum(cems_ref_mask))
        cems_ref_ha = float(cems_ref_px * pixel_area_ha)
        ref_y = cems_ref_mask.flatten().astype(int)
        score_flat = det_res.flood_score.flatten()

        struct_8 = ndimage.generate_binary_structure(2, 2)
        ref_labeled, num_ref_objs = ndimage.label(cems_ref_mask, structure=struct_8)

        p_curve, r_curve, _ = precision_recall_curve(ref_y, score_flat)
        pr_auc = float(auc(r_curve, p_curve))
        roc_auc = float(roc_auc_score(ref_y, score_flat))
        brier = float(brier_score_loss(ref_y, score_flat))
        random_baseline = float(np.mean(ref_y))

        mean_ref_score = float(np.mean(score_flat[ref_y == 1])) if np.sum(ref_y) > 0 else 0.0
        mean_bg_score = float(np.mean(score_flat[ref_y == 0]))

        print(f"     Reference Inundation: {cems_ref_px:,} pixels ({cems_ref_ha:.1f} ha, {cems_ref_ha/total_aoi_ha*100:.2f}% of AOI)")
        print(f"     PR-AUC: {pr_auc:.4f} (Prevalence Baseline: {random_baseline:.4f}) | ROC-AUC: {roc_auc:.4f}")

        threshold_evals = {}
        for r_name, thresh in [("T=0.15 (High Sens)", 0.15), ("T=0.20 (Operational)", 0.20), ("T=0.30 (Balanced)", 0.30), ("T=0.50 (High Spec)", 0.50)]:
            pred_mask = det_res.valid_mask & (det_res.flood_score >= thresh)
            if config.apply_morphological_opening and pred_mask.any():
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

            threshold_evals[r_name] = {
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
            print(f"     [{r_name:20s}] Rec={recall*100:5.1f}% | Prec={precision*100:5.1f}% | F1={f1*100:5.1f}% | IoU={iou*100:5.1f}% | Bias={area_bias:5.2f}x | FP={fp:6d}")

        cohort_results[spec.activation] = {
            "case_study": asdict(spec),
            "precipitation_provenance": asdict(rain_obs),
            "distributional_metrics": {
                "pr_auc": round(pr_auc, 5),
                "roc_auc": round(roc_auc, 5),
                "brier_score": round(brier, 5),
                "prevalence_baseline": round(random_baseline, 5),
                "mean_reference_score": round(mean_ref_score, 4),
                "mean_background_score": round(mean_bg_score, 4),
                "signal_to_background_ratio": round(mean_ref_score / max(1e-5, mean_bg_score), 2),
            },
            "reference_summary": {
                "total_reference_pixels": cems_ref_px,
                "total_reference_ha": round(cems_ref_ha, 2),
                "reference_objects": num_ref_objs,
            },
            "threshold_evaluations": threshold_evals,
        }

    # Regime-Stratified Analytics Calculation
    inland_events = [res for res in cohort_results.values() if res["case_study"]["flood_regime"] == "Inland Riverine Flood" or res["case_study"]["flood_regime"] == "Inland Mega-Riverine Flood"]
    coastal_events = [res for res in cohort_results.values() if res["case_study"]["flood_regime"] == "Coastal Storm Surge"]

    pr_auc_inland = float(np.mean([res["distributional_metrics"]["pr_auc"] for res in inland_events])) if inland_events else 0.0
    roc_auc_inland = float(np.mean([res["distributional_metrics"]["roc_auc"] for res in inland_events])) if inland_events else 0.0
    pr_auc_coastal = float(np.mean([res["distributional_metrics"]["pr_auc"] for res in coastal_events])) if coastal_events else 0.0
    roc_auc_coastal = float(np.mean([res["distributional_metrics"]["roc_auc"] for res in coastal_events])) if coastal_events else 0.0

    macro_pr_auc = float(np.mean([res["distributional_metrics"]["pr_auc"] for res in cohort_results.values()]))
    macro_roc_auc = float(np.mean([res["distributional_metrics"]["roc_auc"] for res in cohort_results.values()]))

    # Operational metrics at T=0.20
    f1_inland_t20 = float(np.mean([res["threshold_evaluations"]["T=0.20 (Operational)"]["f1_score"] for res in inland_events])) if inland_events else 0.0
    prec_inland_t20 = float(np.mean([res["threshold_evaluations"]["T=0.20 (Operational)"]["precision"] for res in inland_events])) if inland_events else 0.0
    rec_inland_t20 = float(np.mean([res["threshold_evaluations"]["T=0.20 (Operational)"]["recall"] for res in inland_events])) if inland_events else 0.0
    bias_inland_t20 = float(np.mean([res["threshold_evaluations"]["T=0.20 (Operational)"]["area_bias_ratio"] for res in inland_events])) if inland_events else 0.0

    f1_coastal_t20 = float(np.mean([res["threshold_evaluations"]["T=0.20 (Operational)"]["f1_score"] for res in coastal_events])) if coastal_events else 0.0
    prec_coastal_t20 = float(np.mean([res["threshold_evaluations"]["T=0.20 (Operational)"]["precision"] for res in coastal_events])) if coastal_events else 0.0
    rec_coastal_t20 = float(np.mean([res["threshold_evaluations"]["T=0.20 (Operational)"]["recall"] for res in coastal_events])) if coastal_events else 0.0
    bias_coastal_t20 = float(np.mean([res["threshold_evaluations"]["T=0.20 (Operational)"]["area_bias_ratio"] for res in coastal_events])) if coastal_events else 0.0

    final_payload = {
        "schema": "earth_one_flood_multievent_validation_v1.0",
        "cohort_summary": {
            "total_events": len(specs),
            "macro_pr_auc": round(macro_pr_auc, 5),
            "macro_roc_auc": round(macro_roc_auc, 5),
            "events_evaluated": [spec.activation for spec in specs],
            "regime_stratification": {
                "inland_riverine": {
                    "event_count": len(inland_events),
                    "mean_pr_auc": round(pr_auc_inland, 5),
                    "mean_roc_auc": round(roc_auc_inland, 5),
                    "operational_t20": {
                        "precision": round(prec_inland_t20, 4),
                        "recall": round(rec_inland_t20, 4),
                        "f1_score": round(f1_inland_t20, 4),
                        "area_bias_ratio": round(bias_inland_t20, 3),
                    }
                },
                "coastal_storm_surge": {
                    "event_count": len(coastal_events),
                    "mean_pr_auc": round(pr_auc_coastal, 5),
                    "mean_roc_auc": round(roc_auc_coastal, 5),
                    "operational_t20": {
                        "precision": round(prec_coastal_t20, 4),
                        "recall": round(rec_coastal_t20, 4),
                        "f1_score": round(f1_coastal_t20, 4),
                        "area_bias_ratio": round(bias_coastal_t20, 3),
                    }
                }
            }
        },
        "event_evaluations": cohort_results,
    }

    out_file = out_dir / "multievent_flood_validation.json"
    out_file.write_text(json.dumps(final_payload, indent=2), encoding="utf-8")
    print(f"\nSaved Multi-Event Flood Validation Ledger to {out_file}")
    return final_payload
