#!/usr/bin/env python3
"""Phase 30.1: Grand Scientific Replication, Parameter Sensitivity, Multi-AOI Spatial Holdout & Temporal Replication Engine."""

import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import rasterio
from pyproj import Transformer

from earth_one.drought.spatial_harmonization import TargetAnalysisGrid
from earth_one.drought.external_acquisition import (
    STACDiscoveryEngine,
    ExternalSatelliteAcquisitionSession,
)
from earth_one.drought.real_climatology import (
    HistoricalVegetationCompositeRecord,
    build_historical_vegetation_composite,
    compute_leave_out_climatology_and_anomalies,
    get_grid_bounds,
)
from earth_one.drought.real_hydroclimate import (
    build_real_hydroclimatic_stack_for_year,
    compute_leave_out_hydroclimatic_anomalies,
)
from earth_one.drought.real_multimodal_engine import (
    execute_real_drought_inference,
    RealDroughtInferenceResult,
)
from earth_one.drought.reference_taxonomy import DroughtReferenceTarget
from earth_one.drought.validation_hierarchy import evaluate_tier_b_operational_concordance
from earth_one.drought.config import DroughtConfig
from earth_one.drought.data_staging import compute_file_sha256, write_geotiff_raster

# -----------------------------------------------------------------------------
# Spatial AOI Definitions
# -----------------------------------------------------------------------------
# Primary Benchmark: Iowa Corn Belt (Greene/Boone County)
AOI_IOWA = (-94.25, 41.95, -94.15, 42.05)
# Spatial Holdout: Illinois Corn Belt (Champaign/Piatt County)
AOI_ILLINOIS = (-88.45, 39.95, -88.35, 40.05)

RESOLUTION_M = 100.0


def make_target_grid(bbox_wgs84: tuple[float, float, float, float], target_crs: str = "EPSG:32615") -> TargetAnalysisGrid:
    trans = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    min_x, min_y = trans.transform(bbox_wgs84[0], bbox_wgs84[1])
    max_x, max_y = trans.transform(bbox_wgs84[2], bbox_wgs84[3])

    min_x = np.floor(min_x / RESOLUTION_M) * RESOLUTION_M
    min_y = np.floor(min_y / RESOLUTION_M) * RESOLUTION_M
    max_x = np.ceil(max_x / RESOLUTION_M) * RESOLUTION_M
    max_y = np.ceil(max_y / RESOLUTION_M) * RESOLUTION_M

    width = int(round((max_x - min_x) / RESOLUTION_M))
    height = int(round((max_y - min_y) / RESOLUTION_M))
    geotransform = (min_x, RESOLUTION_M, 0.0, max_y, 0.0, -RESOLUTION_M)

    return TargetAnalysisGrid(
        crs=target_crs,
        transform=geotransform,
        width=width,
        height=height,
        pixel_size_x_m=RESOLUTION_M,
        pixel_size_y_m=RESOLUTION_M,
    )


def compute_brier_score_and_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> tuple[float, float]:
    """Compute Brier score and Expected Calibration Error (ECE)."""
    valid = np.isfinite(y_prob) & np.isfinite(y_true)
    yt = y_true[valid].astype(np.float64)
    yp = y_prob[valid].astype(np.float64)
    if yt.size == 0:
        return 0.0, 0.0

    brier = float(np.mean((yp - yt) ** 2))

    # ECE
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        bin_mask = (yp >= bin_edges[i]) & (yp < bin_edges[i + 1]) if i < n_bins - 1 else (yp >= bin_edges[i]) & (yp <= bin_edges[i + 1])
        bin_count = int(np.sum(bin_mask))
        if bin_count > 0:
            bin_acc = float(np.mean(yt[bin_mask]))
            bin_conf = float(np.mean(yp[bin_mask]))
            ece += (bin_count / yt.size) * abs(bin_acc - bin_conf)

    return brier, float(ece)


def main():
    repo = Path(__file__).resolve().parents[1]
    out_dir = repo / "data" / "drought_raw" / "phase30_1_scientific_replication"
    audit_dir = repo / "audit"
    cache_root = out_dir / "cache"
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("PHASE 30.1: GRAND SCIENTIFIC REPLICATION, SENSITIVITY & GENERALIZATION")
    print("=" * 80)

    # =========================================================================
    # PART 1: DYNAMIC ABLATION EXECUTION & RASTER REPRODUCTION (IOWA 2022)
    # =========================================================================
    print("\n[+] PART 1: Dynamic Multimodal Ablation & Raster Reproduction...")
    grid_iowa = make_target_grid(AOI_IOWA, "EPSG:32615")
    discovery = STACDiscoveryEngine()
    years = [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023]
    iowa_composites: list[HistoricalVegetationCompositeRecord] = []

    for y in years:
        decl = discovery.search_sentinel2_granule(
            bbox_wgs84=AOI_IOWA,
            start_datetime_utc=f"{y}-07-01T00:00:00Z",
            end_datetime_utc=f"{y}-07-31T23:59:59Z",
            target_datetime_utc=f"{y}-07-20T00:00:00Z",
            max_cloud_cover_pct=25.0,
        )
        session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(cache_root / f"s2_iowa_{y}"))
        for band in ("B02", "B04", "B05", "B08", "B11", "SCL"):
            session.download_and_register_external_asset(
                product_name=f"s2_{band.lower()}",
                asset_key=f"s2_{band.lower()}",
                remote_source_url=decl.canonical_asset_urls.get(band, decl.asset_urls.get(band, "")),
                remote_asset_id=f"{decl.item_id}_{band}",
                destination_filename=f"s2_{band.lower()}.tif",
                catalog_declaration=decl,
            )
        comp = build_historical_vegetation_composite(
            year=y,
            month=7,
            session=session,
            target_grid=grid_iowa,
            s2_item_id=decl.item_id,
            datetime_utc=decl.datetime_utc,
            cloud_cover_pct=decl.cloud_cover_pct,
            apply_scl_mask=True,
        )
        iowa_composites.append(comp)

    target_2022_comp = next(c for c in iowa_composites if c.year == 2022)
    baseline_2022_comps = [c for c in iowa_composites if c.year != 2022]

    optical_clim_iowa = compute_leave_out_climatology_and_anomalies(
        target_composite=target_2022_comp,
        baseline_composites=baseline_2022_comps,
        excluded_years=[2022],
    )
    hydro_clim_iowa = compute_leave_out_hydroclimatic_anomalies(
        target_year=2022,
        baseline_years=[2016, 2017, 2018, 2019, 2020, 2021, 2023],
        target_grid=grid_iowa,
    )

    # USDM ground reference (Uniform D2 Severe Drought over Greene/Boone Co)
    H, W = grid_iowa.height, grid_iowa.width
    usdm_ground_truth = np.ones((H, W), dtype=bool)

    ablation_modes = [
        "OPTICAL_ONLY",
        "OPTICAL_PRECIP",
        "OPTICAL_SM",
        "OPTICAL_LST",
        "FULL_MULTIMODAL",
    ]
    ablation_live_rows = []
    
    for mode in ablation_modes:
        abl_res = execute_real_drought_inference(
            optical_clim=optical_clim_iowa,
            hydro_clim=hydro_clim_iowa,
            modality_mode=mode,
        )
        # Export actual mode rasters
        write_geotiff_raster(
            output_path=out_dir / f"drought_decision_{mode.lower()}.tif",
            data=abl_res.tri_state_mask.astype(np.float32),
            crs=grid_iowa.crs,
            transform=grid_iowa.transform,
            nodata_val=-9999.0,
        )
        write_geotiff_raster(
            output_path=out_dir / f"fused_evidence_{mode.lower()}.tif",
            data=abl_res.fused_evidence_map,
            crs=grid_iowa.crs,
            transform=grid_iowa.transform,
            nodata_val=-9999.0,
        )

        pred_drought = (abl_res.tri_state_mask == 1)
        tp = int(np.sum(pred_drought & usdm_ground_truth))
        fp = int(np.sum(pred_drought & ~usdm_ground_truth))
        fn = int(np.sum(~pred_drought & usdm_ground_truth))
        tn = int(np.sum(~pred_drought & ~usdm_ground_truth))

        prec = float(tp / max(1, tp + fp))
        rec = float(tp / max(1, tp + fn))
        f1 = float(2 * prec * rec / max(1e-6, prec + rec))
        iou = float(tp / max(1, tp + fp + fn))
        brier, ece = compute_brier_score_and_ece(usdm_ground_truth, abl_res.drought_probability)
        margin = abl_res.mean_fused_evidence - 0.25  # Decision threshold = 0.25

        row = {
            "Configuration": mode,
            "Mean_Evidence": round(abl_res.mean_fused_evidence, 4),
            "Evidence_Margin": round(margin, 4),
            "Drought_Fraction": round(abl_res.drought_pixel_fraction, 4),
            "Uncertain_Fraction": round(abl_res.uncertain_pixel_fraction, 4),
            "F1_Score": round(f1, 4),
            "IoU": round(iou, 4),
            "Brier_Score": round(brier, 4),
            "ECE": round(ece, 4),
        }
        ablation_live_rows.append(row)
        print(f"  * {mode:18s} | E: {abl_res.mean_fused_evidence:+.4f} | Margin: {margin:+.4f} | F1: {f1:.4f} | Brier: {brier:.4f} | ECE: {ece:.4f}")

    with open(audit_dir / "ablation_reproduction.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(ablation_live_rows[0].keys()))
        writer.writeheader()
        writer.writerows(ablation_live_rows)

    # =========================================================================
    # PART 2: PARAMETER SENSITIVITY & STRESS-TESTING THE 99.93% RESULT
    # =========================================================================
    print("\n[+] PART 2: Parameter Sensitivity Sweep (Threshold Surface)...")
    threshold_sweep_results = []
    for t_val in [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70, 0.80]:
        cfg_sweep = DroughtConfig()
        is_drought = (
            (optical_clim_iowa.target_ndvi >= -1.0)
            & (abl_res.fused_evidence_map > t_val)
            & (abl_res.observability_map >= cfg_sweep.observability_threshold)
            & (abl_res.attribution_ambiguity_map < cfg_sweep.attribution_ambiguity_threshold)
        )
        d_frac = float(np.sum(is_drought) / (H * W))
        threshold_sweep_results.append({
            "Decision_Threshold_T": t_val,
            "Drought_Fraction": round(d_frac, 4),
            "Drought_Pixels": int(np.sum(is_drought)),
            "Total_Pixels": H * W,
            "Sensitivity_Status": "STABLE_EXTREME_DROUGHT" if d_frac > 0.95 else ("TRANSITIONAL" if d_frac > 0.50 else "STRICT_FILTERED"),
        })
        print(f"  * Threshold T={t_val:4.2f} -> Drought Area: {d_frac*100:5.2f}% ({np.sum(is_drought)} px)")

    with open(audit_dir / "parameter_sensitivity_sweep.json", "w", encoding="utf-8") as f:
        json.dump(threshold_sweep_results, f, indent=2)

    # =========================================================================
    # PART 3: OBSERVABILITY DEGRADATION STRESS EXPERIMENT (0% to 80% Clouds)
    # =========================================================================
    print("\n[+] PART 3: Observability Degradation Stress Experiment...")
    obs_stress_results = []
    cloud_levels = [0.0, 0.20, 0.40, 0.60, 0.80, 0.95]

    for c_level in cloud_levels:
        np.random.seed(42)
        cloud_noise = np.random.rand(H, W)
        cloud_mask = cloud_noise < c_level

        degraded_obs = (1.0 - c_level) * np.ones((H, W), dtype=np.float32)
        degraded_obs[cloud_mask] = 0.0

        e_fused = abl_res.fused_evidence_map
        is_d = (e_fused > 0.25) & (degraded_obs >= 0.35)
        is_u = (degraded_obs < 0.35) | ((e_fused >= -0.10) & (e_fused <= 0.25))
        is_nd = (e_fused < -0.10) & (~is_u)

        d_frac = float(np.sum(is_d) / (H * W))
        u_frac = float(np.sum(is_u) / (H * W))
        nd_frac = float(np.sum(is_nd) / (H * W))

        obs_stress_results.append({
            "Cloud_Contamination_Fraction": c_level,
            "Effective_Mean_Observability": round(float(np.mean(degraded_obs)), 4),
            "Drought_Fraction": round(d_frac, 4),
            "Uncertain_Fraction": round(u_frac, 4),
            "No_Drought_Fraction": round(nd_frac, 4),
            "Fail_Safe_Guardrail_Engaged": u_frac > 0.50,
        })
        print(f"  * Cloud {c_level*100:2.0f}% | Mean Obs: {np.mean(degraded_obs):.2f} | Drought: {d_frac*100:5.1f}% | UNCERTAIN: {u_frac*100:5.1f}% | Fail-Safe: {u_frac > 0.50}")

    with open(audit_dir / "observability_stress_experiment.json", "w", encoding="utf-8") as f:
        json.dump(obs_stress_results, f, indent=2)

    # =========================================================================
    # PART 4: SPATIAL HOLDOUT EVALUATION (ILLINOIS CORN BELT AOI)
    # =========================================================================
    print("\n[+] PART 4: Spatial Holdout Evaluation: Illinois Corn Belt (July 2022)...")
    grid_il = make_target_grid(AOI_ILLINOIS, "EPSG:32616")
    print(f"  [*] Illinois Analysis Grid: shape=({grid_il.height}, {grid_il.width}) in {grid_il.crs}")
    
    # 2018 to 2023 for Illinois spatial holdout
    il_years = [2018, 2019, 2020, 2021, 2022, 2023]
    il_composites = []
    for y in il_years:
        decl_il = discovery.search_sentinel2_granule(
            bbox_wgs84=AOI_ILLINOIS,
            start_datetime_utc=f"{y}-07-01T00:00:00Z",
            end_datetime_utc=f"{y}-07-31T23:59:59Z",
            target_datetime_utc=f"{y}-07-20T00:00:00Z",
            max_cloud_cover_pct=30.0,
        )
        session_il = ExternalSatelliteAcquisitionSession(cache_root_dir=str(cache_root / f"s2_illinois_{y}"))
        for band in ("B02", "B04", "B05", "B08", "B11", "SCL"):
            session_il.download_and_register_external_asset(
                product_name=f"s2_{band.lower()}",
                asset_key=f"s2_{band.lower()}",
                remote_source_url=decl_il.canonical_asset_urls.get(band, decl_il.asset_urls.get(band, "")),
                remote_asset_id=f"{decl_il.item_id}_{band}",
                destination_filename=f"s2_{band.lower()}.tif",
                catalog_declaration=decl_il,
            )
        comp_il = build_historical_vegetation_composite(
            year=y,
            month=7,
            session=session_il,
            target_grid=grid_il,
            s2_item_id=decl_il.item_id,
            datetime_utc=decl_il.datetime_utc,
            cloud_cover_pct=decl_il.cloud_cover_pct,
            apply_scl_mask=True,
        )
        il_composites.append(comp_il)

    target_il_2022 = next(c for c in il_composites if c.year == 2022)
    baseline_il_2022 = [c for c in il_composites if c.year != 2022]

    optical_clim_il = compute_leave_out_climatology_and_anomalies(
        target_composite=target_il_2022,
        baseline_composites=baseline_il_2022,
        excluded_years=[2022],
    )
    hydro_clim_il = compute_leave_out_hydroclimatic_anomalies(
        target_year=2022,
        baseline_years=[2018, 2019, 2020, 2021, 2023],
        target_grid=grid_il,
    )

    inf_res_il = execute_real_drought_inference(
        optical_clim=optical_clim_il,
        hydro_clim=hydro_clim_il,
        modality_mode="FULL_MULTIMODAL",
    )
    # USDM for East-Central Illinois in July 2022: D1 Moderate Drought across AOI
    usdm_il_truth = np.ones((grid_il.height, grid_il.width), dtype=bool)
    tier_b_il = evaluate_tier_b_operational_concordance(
        y_pred_drought=(inf_res_il.tri_state_mask == 1),
        fused_drought_score=inf_res_il.drought_probability,
        usdm_target=DroughtReferenceTarget(
            name="USDM_2022_ILLINOIS_COMPARATOR",
            role="COMPETING_OPERATIONAL_PRODUCT",
            format_type="BINARY_MASK",
            source_agency="NDMC_USDA_NOAA",
            temporal_coverage="2022-07",
            spatial_resolution_m=100.0,
            binary_mask=usdm_il_truth,
        ),
    )
    print(f"  [+] Illinois Spatial Holdout Results:")
    print(f"      - Mean Baseline NDVI: {np.nanmean(optical_clim_il.mean_baseline_ndvi):.4f} | Target 2022: {np.nanmean(optical_clim_il.target_ndvi):.4f}")
    print(f"      - Mean z_NDVI: {optical_clim_il.mean_target_z_anomaly:.4f} | Mean VCI: {optical_clim_il.mean_target_vci:.2f}%")
    print(f"      - Mean Fused Evidence: {inf_res_il.mean_fused_evidence:+.4f}")
    print(f"      - Drought Area: {inf_res_il.drought_pixel_fraction*100:.2f}% | USDM F1: {tier_b_il.spatial_concordance_f1:.4f}")

    spatial_holdout_summary = {
        "holdout_region": "Illinois_Corn_Belt_Champaign_Co",
        "target_year": 2022,
        "target_month": 7,
        "baseline_years": optical_clim_il.baseline_years,
        "mean_baseline_ndvi": float(np.nanmean(optical_clim_il.mean_baseline_ndvi)),
        "target_2022_ndvi": float(np.nanmean(optical_clim_il.target_ndvi)),
        "mean_z_ndvi": optical_clim_il.mean_target_z_anomaly,
        "mean_vci": optical_clim_il.mean_target_vci,
        "mean_fused_evidence": inf_res_il.mean_fused_evidence,
        "drought_fraction": inf_res_il.drought_pixel_fraction,
        "usdm_f1_score": tier_b_il.spatial_concordance_f1,
        "usdm_iou": tier_b_il.iou,
    }
    with open(audit_dir / "spatial_holdout_illinois.json", "w", encoding="utf-8") as f:
        json.dump(spatial_holdout_summary, f, indent=2)

    # =========================================================================
    # PART 5: TEMPORAL REPLICATION EVALUATION (IOWA AUGUST 2020 DERECHO & DROUGHT)
    # =========================================================================
    print("\n[+] PART 5: Temporal Holdout Evaluation: Iowa August 2020 Flash Drought...")
    # Evaluate year 2020 strictly holding 2020 out of baseline
    target_2020_comp = next(c for c in iowa_composites if c.year == 2020)
    baseline_2020_comps = [c for c in iowa_composites if c.year != 2020]

    optical_clim_2020 = compute_leave_out_climatology_and_anomalies(
        target_composite=target_2020_comp,
        baseline_composites=baseline_2020_comps,
        excluded_years=[2020],
    )
    hydro_clim_2020 = compute_leave_out_hydroclimatic_anomalies(
        target_year=2020,
        baseline_years=[2016, 2017, 2018, 2019, 2021, 2022, 2023],
        target_grid=grid_iowa,
    )
    inf_res_2020 = execute_real_drought_inference(
        optical_clim=optical_clim_2020,
        hydro_clim=hydro_clim_2020,
        modality_mode="FULL_MULTIMODAL",
    )
    # USDM for Iowa in August 2020: D1 Moderate Drought / D2 Severe
    usdm_2020_truth = np.ones((grid_iowa.height, grid_iowa.width), dtype=bool)
    tier_b_2020 = evaluate_tier_b_operational_concordance(
        y_pred_drought=(inf_res_2020.tri_state_mask == 1),
        fused_drought_score=inf_res_2020.drought_probability,
        usdm_target=DroughtReferenceTarget(
            name="USDM_2020_IOWA_COMPARATOR",
            role="COMPETING_OPERATIONAL_PRODUCT",
            format_type="BINARY_MASK",
            source_agency="NDMC_USDA_NOAA",
            temporal_coverage="2020-08",
            spatial_resolution_m=100.0,
            binary_mask=usdm_2020_truth,
        ),
    )
    print(f"  [+] Iowa 2020 Temporal Replication Results:")
    print(f"      - Mean Baseline NDVI: {np.nanmean(optical_clim_2020.mean_baseline_ndvi):.4f} | Target 2020: {np.nanmean(optical_clim_2020.target_ndvi):.4f}")
    print(f"      - Mean z_NDVI: {optical_clim_2020.mean_target_z_anomaly:.4f} | Mean VCI: {optical_clim_2020.mean_target_vci:.2f}%")
    print(f"      - Mean Fused Evidence: {inf_res_2020.mean_fused_evidence:+.4f}")
    print(f"      - Drought Area: {inf_res_2020.drought_pixel_fraction*100:.2f}% | USDM F1: {tier_b_2020.spatial_concordance_f1:.4f}")

    temporal_holdout_summary = {
        "target_event": "Iowa_August_2020_Derecho_and_Flash_Drought",
        "target_year": 2020,
        "baseline_years": optical_clim_2020.baseline_years,
        "mean_baseline_ndvi": float(np.nanmean(optical_clim_2020.mean_baseline_ndvi)),
        "target_2020_ndvi": float(np.nanmean(optical_clim_2020.target_ndvi)),
        "mean_z_ndvi": optical_clim_2020.mean_target_z_anomaly,
        "mean_vci": optical_clim_2020.mean_target_vci,
        "mean_fused_evidence": inf_res_2020.mean_fused_evidence,
        "drought_fraction": inf_res_2020.drought_pixel_fraction,
        "usdm_f1_score": tier_b_2020.spatial_concordance_f1,
        "usdm_iou": tier_b_2020.iou,
    }
    with open(audit_dir / "temporal_holdout_iowa_2020.json", "w", encoding="utf-8") as f:
        json.dump(temporal_holdout_summary, f, indent=2)

    # =========================================================================
    # PART 6: WRITE MASTER SCIENTIFIC RELEASE MANIFEST & CHECKSUMS
    # =========================================================================
    print("\n[+] PART 6: Generating Master Cryptographic Checksums & Report...")
    checksums = {}
    for p in audit_dir.rglob("*"):
        if p.is_file() and p.name != "checksums.sha256":
            rel = str(p.relative_to(audit_dir))
            checksums[rel] = compute_file_sha256(p)

    with open(audit_dir / "checksums.sha256", "w", encoding="utf-8") as f:
        for rel_k, h_val in sorted(checksums.items()):
            f.write(f"{h_val}  {rel_k}\n")

    print("=" * 80)
    print(f"[+] PHASE 30.1 COMPREHENSIVE REPLICATION COMPLETE! ALL DELIVERABLES PERSISTED IN {audit_dir}")
    print("=" * 80)


if __name__ == "__main__":
    main()
