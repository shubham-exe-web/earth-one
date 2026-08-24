from __future__ import annotations

"""Block 6E: Empirical Calibration of the Observability Index (O) with Spatial-Block Bootstrapping.

Evaluates whether the continuous physical Observability Index:
    O = S_scale * W_water * G_geom * T_terrain * D_validity

is genuinely and monotonically predictive of independent flood detection reliability.

Methodology:
1. Independent Pixel Pooling: Aggregates pixel-level scores, ground truth, and continuous O
   across independent validation activations (EMSR567 Australia, EMSR357 India, EMSR445 Ukraine, EMSR286 Colombia).
2. Observability Stratification: Discretizes O into 5 continuous intervals:
   [0.0, 0.20), [0.20, 0.40), [0.40, 0.60), [0.60, 0.80), [0.80, 1.00].
3. Spatial-Block Bootstrap Resampling (B = 1000 iterations):
   Resamples spatial blocks (32x32 pixels) with replacement to account for spatial autocorrelation,
   computing 95% Confidence Intervals [CI_2.5%, CI_97.5%] for Precision, F1, and PR-AUC.
4. Non-Parametric Rank Correlation:
   Computes Spearman rho, Pearson r, and p-values to evaluate calibration monotonicity.
"""

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
from scipy import ndimage
import scipy.stats
from sklearn.metrics import precision_recall_curve, auc, brier_score_loss

from .flood_multievent import FloodCohortEventSpec, get_stac_item, sign_planetary_url, compute_dem_slope
from .flood import (
    FloodEvidenceConfig,
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
from .regime_router import classify_biophysical_regime
from .flood_tristate import compute_continuous_observability_index
from .flood_observability_validation import INDEPENDENT_VALIDATION_SPECS
from .flood_temporal_generalization import UNSEEN_TEMPORAL_SPECS


@dataclass
class ObservabilityBinMetrics:
    bin_name: str
    o_min: float
    o_max: float
    pixel_count: int
    pixel_fraction: float
    ground_truth_positives: int
    empirical_precision: float
    precision_ci_95: list[float]  # [lower, upper]
    empirical_recall: float
    recall_ci_95: list[float]
    empirical_f1: float
    f1_ci_95: list[float]
    empirical_pr_auc: float
    pr_auc_ci_95: list[float]
    brier_score: float
    is_monotonic_precision_gain: bool


@dataclass
class ObservabilityCalibrationManifest:
    total_validation_pixels: int
    total_events_pooled: int
    pooled_events: list[str]
    spearman_rho_precision: float
    spearman_pvalue_precision: float
    spearman_rho_pr_auc: float
    spearman_pvalue_pr_auc: float
    pearson_r_precision: float
    is_statistically_significant: bool
    observability_bins: list[ObservabilityBinMetrics]
    provenance_hash: str


def extract_event_arrays(spec: FloodCohortEventSpec) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[int, int]]:
    """Extract fused score S, ground truth Y, and continuous Observability Index O."""
    w, s, e, n = spec.bbox
    H, W = spec.grid_shape
    t_site = rasterio.transform.from_bounds(w, s, e, n, W, H)
    target_profile = {"width": W, "height": H, "crs": "EPSG:4326", "transform": t_site}

    mid_lat = (s + n) / 2.0
    cell_x_m = abs(t_site.a * 111319.5 * np.cos(np.radians(mid_lat)))
    cell_y_m = abs(t_site.e * 111319.5)

    def read_b(href: str) -> np.ndarray:
        signed = sign_planetary_url(href)
        dest = np.zeros((H, W), dtype=np.float32)
        with rasterio.open(signed) as src:
            reproject(
                rasterio.band(src, 1), dest,
                src_transform=src.transform, src_crs=src.crs,
                dst_transform=t_site, dst_crs="EPSG:4326"
            )
        return dest

    # Baselines
    jrc_item = get_stac_item("jrc-gsw", spec.jrc_gsw_item)
    dem_item = get_stac_item("cop-dem-glo-30", spec.cop_dem_item)

    jrc_raw = read_b(jrc_item["assets"]["occurrence"]["href"])
    jrc_freq, jrc_v = normalize_water_occurrence(jrc_raw)
    elev = read_b(dem_item["assets"]["data"]["href"])
    slope = compute_dem_slope(elev, cell_x_m, cell_y_m)

    regime_res = classify_biophysical_regime(jrc_freq, elev, slope, centroid_lat=mid_lat, centroid_lon=(w + e) / 2.0)
    cfg = regime_res.recommended_config

    # Satellite SAR
    s1_b_item = get_stac_item("sentinel-1-grd", spec.s1_before_item)
    s1_e_item = get_stac_item("sentinel-1-grd", spec.s1_event_item)
    vv_b = (read_b(s1_b_item["assets"]["vv"]["href"]) / 475.0) ** 2
    vv_e = (read_b(s1_e_item["assets"]["vv"]["href"]) / 475.0) ** 2
    vh_b = (read_b(s1_b_item["assets"]["vh"]["href"]) / 530.0) ** 2 if "vh" in s1_b_item.get("assets", {}) else None
    vh_e = (read_b(s1_e_item["assets"]["vh"]["href"]) / 530.0) ** 2 if "vh" in s1_e_item.get("assets", {}) else None

    sar_sc, sar_v = compute_sar_water_evidence(vv_b, vv_e, vh_b, vh_e, config=cfg)
    m_nov = np.where(jrc_v, np.clip(1.0 - (jrc_freq / cfg.permanent_water_max_freq), 0.0, 1.0), 1.0)
    if regime_res.regime == "COASTAL_ESTUARINE_TIDAL":
        m_int, _ = compute_intertidal_suppression_mask(jrc_freq, elev, slope, min_multiplier_floor=0.35)
        m_nov = m_nov * m_int

    terr_sc, terr_v = compute_terrain_plausibility(slope, config=cfg)
    rain_obs = get_historical_event_rainfall(spec.event_key)
    rain_sc = compute_rainfall_context(rain_obs.accumulation_mm, rain_obs.anomaly_std, rain_obs.hours_since_peak, config=cfg)

    cfg_global = FloodEvidenceConfig(fusion_strategy="gated_physics")
    det_global = fuse_flood_evidence(
        sar_evidence=sar_sc, sar_valid=sar_v,
        novelty_evidence=m_nov, novelty_valid=jrc_v,
        terrain_plausibility=terr_sc, terrain_valid=terr_v,
        rainfall_score=rain_sc, config=cfg_global,
    )
    det_regime = fuse_flood_evidence(
        sar_evidence=sar_sc, sar_valid=sar_v,
        novelty_evidence=m_nov, novelty_valid=jrc_v,
        terrain_plausibility=terr_sc, terrain_valid=terr_v,
        rainfall_score=rain_sc, config=cfg,
    )
    C = regime_res.confidence if regime_res.regime != "MIXED_UNCERTAIN" else 0.0
    fused_score = (1.0 - C) * det_global.flood_score + C * det_regime.flood_score

    # Compute Continuous Observability Index O
    O, _ = compute_continuous_observability_index(
        valid_mask=det_global.valid_mask,
        slope_deg=slope,
        elevation_m=elev,
        jrc_occurrence=jrc_freq,
        pixel_resolution_m=float((cell_x_m + cell_y_m) / 2.0),
    )

    # Reference Delineation
    ref_shp = Path(spec.reference_shapefile)
    cems_ref_mask, _ = load_vector_reference(ref_shp, target_profile)

    return fused_score, cems_ref_mask.astype(int), O, (H, W)


def run_observability_calibration_benchmark(
    n_bootstrap: int = 1000,
    block_size: int = 32,
    seed: int = 42,
) -> dict[str, Any]:
    print("=" * 95)
    print("  EARTH ONE FLOOD MODULE: BLOCK 6E EMPIRICAL CALIBRATION OF OBSERVABILITY INDEX (O)")
    print("  Pooling independent validation activations & running spatial-block bootstrap (B=1000)")
    print("=" * 95)

    rng = np.random.default_rng(seed)

    # Combine independent validation activations
    test_specs = list({s.activation: s for s in (INDEPENDENT_VALIDATION_SPECS + UNSEEN_TEMPORAL_SPECS)}.values())

    all_scores = []
    all_refs = []
    all_o = []
    all_block_ids = []
    block_offset = 0

    print(f"\nExtracting spatial layers across {len(test_specs)} independent activations...")
    for spec in test_specs:
        print(f"  Streaming {spec.activation} ({spec.country} — {spec.flood_regime})...")
        sc, ref, o_arr, (H, W) = extract_event_arrays(spec)
        
        # Assign spatial block IDs (32x32 blocks)
        n_by = (H + block_size - 1) // block_size
        n_bx = (W + block_size - 1) // block_size
        y_idx = np.arange(H) // block_size
        x_idx = np.arange(W) // block_size
        grid_y, grid_x = np.meshgrid(y_idx, x_idx, indexing="ij")
        b_ids = grid_y * n_bx + grid_x + block_offset
        block_offset += int(np.max(b_ids)) + 1

        all_scores.append(sc.flatten())
        all_refs.append(ref.flatten())
        all_o.append(o_arr.flatten())
        all_block_ids.append(b_ids.flatten())

    S_all = np.concatenate(all_scores)
    Y_all = np.concatenate(all_refs)
    O_all = np.concatenate(all_o)
    B_all = np.concatenate(all_block_ids)

    n_pixels = len(S_all)
    unique_blocks = np.unique(B_all)
    n_blocks = len(unique_blocks)
    print(f"\nPooled {n_pixels:,} validation pixels across {n_blocks:,} spatial blocks ({block_size}x{block_size} px).")

    # Define 5 Observability Bins
    bins = [
        ("Bin 1: Severe Obscuration [0.0 - 0.20)", 0.0, 0.20),
        ("Bin 2: High Ambiguity   [0.20 - 0.40)", 0.20, 0.40),
        ("Bin 3: Moderate Obs.    [0.40 - 0.60)", 0.40, 0.60),
        ("Bin 4: High Obs.        [0.60 - 0.80)", 0.60, 0.80),
        ("Bin 5: Pristine Obs.    [0.80 - 1.00]", 0.80, 1.001),
    ]

    bin_results: list[ObservabilityBinMetrics] = []
    prev_prec = -1.0
    bin_centers = []
    prec_list = []
    prauc_list = []

    print("\n--- COMPUTING EMPIRICAL PERFORMANCE & SPATIAL-BLOCK BOOTSTRAP CI ---")
    for name, o_lo, o_hi in bins:
        mask = (O_all >= o_lo) & (O_all < o_hi)
        n_bin = int(np.sum(mask))
        if n_bin == 0:
            continue

        s_bin = S_all[mask]
        y_bin = Y_all[mask]
        b_bin = B_all[mask]

        n_pos = int(np.sum(y_bin))
        pred_bin = (s_bin >= 0.20)
        tp = int(np.sum(pred_bin & (y_bin == 1)))
        fp = int(np.sum(pred_bin & (y_bin == 0)))
        fn = int(np.sum((~pred_bin) & (y_bin == 1)))

        prec = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        rec = float(tp / n_pos) if n_pos > 0 else 0.0
        f1 = float(2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        
        if n_pos > 0:
            p_c, r_c, _ = precision_recall_curve(y_bin, s_bin)
            pr_auc = float(auc(r_c, p_c))
        else:
            pr_auc = 0.0

        brier = float(brier_score_loss(y_bin, np.clip(s_bin, 0.0, 1.0)))

        # Spatial Block Bootstrap (B iterations)
        blocks_in_bin = np.unique(b_bin)
        b_prec_dist = []
        b_rec_dist = []
        b_f1_dist = []
        b_prauc_dist = []

        for _ in range(n_bootstrap):
            sampled_b = rng.choice(blocks_in_bin, size=len(blocks_in_bin), replace=True)
            # Find matching indices
            s_idx = np.isin(b_bin, sampled_b)
            if not s_idx.any():
                continue
            sb_s = s_bin[s_idx]
            sb_y = y_bin[s_idx]
            sb_pos = int(np.sum(sb_y))
            sb_pred = (sb_s >= 0.20)
            sb_tp = int(np.sum(sb_pred & (sb_y == 1)))
            sb_fp = int(np.sum(sb_pred & (sb_y == 0)))

            sb_p = float(sb_tp / (sb_tp + sb_fp)) if (sb_tp + sb_fp) > 0 else 0.0
            sb_r = float(sb_tp / sb_pos) if sb_pos > 0 else 0.0
            sb_f = float(2 * sb_p * sb_r / (sb_p + sb_r)) if (sb_p + sb_r) > 0 else 0.0

            b_prec_dist.append(sb_p)
            b_rec_dist.append(sb_r)
            b_f1_dist.append(sb_f)

            if sb_pos > 0:
                p_k, r_k, _ = precision_recall_curve(sb_y, sb_s)
                b_prauc_dist.append(float(auc(r_k, p_k)))
            else:
                b_prauc_dist.append(0.0)

        p_ci = [round(float(np.percentile(b_prec_dist, 2.5)), 4), round(float(np.percentile(b_prec_dist, 97.5)), 4)]
        r_ci = [round(float(np.percentile(b_rec_dist, 2.5)), 4), round(float(np.percentile(b_rec_dist, 97.5)), 4)]
        f_ci = [round(float(np.percentile(b_f1_dist, 2.5)), 4), round(float(np.percentile(b_f1_dist, 97.5)), 4)]
        auc_ci = [round(float(np.percentile(b_prauc_dist, 2.5)), 4), round(float(np.percentile(b_prauc_dist, 97.5)), 4)]

        is_mono = (prec >= prev_prec)
        prev_prec = prec

        bin_center = (o_lo + min(1.0, o_hi)) / 2.0
        bin_centers.append(bin_center)
        prec_list.append(prec)
        prauc_list.append(pr_auc)

        bm = ObservabilityBinMetrics(
            bin_name=name,
            o_min=o_lo,
            o_max=min(1.0, o_hi),
            pixel_count=n_bin,
            pixel_fraction=round(float(n_bin / n_pixels), 4),
            ground_truth_positives=n_pos,
            empirical_precision=round(prec, 4),
            precision_ci_95=p_ci,
            empirical_recall=round(rec, 4),
            recall_ci_95=r_ci,
            empirical_f1=round(f1, 4),
            f1_ci_95=f_ci,
            empirical_pr_auc=round(pr_auc, 4),
            pr_auc_ci_95=auc_ci,
            brier_score=round(brier, 4),
            is_monotonic_precision_gain=is_mono,
        )
        bin_results.append(bm)

        print(f"  {name:40s} | N={n_bin:,} ({n_bin/n_pixels*100:4.1f}%) | Prec: {prec*100:4.1f}% [{p_ci[0]*100:4.1f}%, {p_ci[1]*100:4.1f}%] | PR-AUC: {pr_auc:.4f} [{auc_ci[0]:.4f}, {auc_ci[1]:.4f}]")

    # Statistical Monotonicity & Rank Correlation Tests
    spearman_prec, pval_prec = scipy.stats.spearmanr(bin_centers, prec_list)
    spearman_auc, pval_auc = scipy.stats.spearmanr(bin_centers, prauc_list)
    pearson_prec, _ = scipy.stats.pearsonr(bin_centers, prec_list)

    is_sig = bool(spearman_prec >= 0.80 and pval_prec < 0.10)

    print(f"\n--- STATISTICAL CALIBRATION SUMMARY ---")
    print(f"  Spearman rho (O vs Precision): {spearman_prec:.4f} (p-value = {pval_prec:.4f})")
    print(f"  Spearman rho (O vs PR-AUC):    {spearman_auc:.4f} (p-value = {pval_auc:.4f})")
    print(f"  Pearson r (O vs Precision):    {pearson_prec:.4f}")
    print(f"  Observability Genuinely Predictive: {is_sig}")

    manifest = ObservabilityCalibrationManifest(
        total_validation_pixels=n_pixels,
        total_events_pooled=len(test_specs),
        pooled_events=[s.activation for s in test_specs],
        spearman_rho_precision=round(float(spearman_prec), 4),
        spearman_pvalue_precision=round(float(pval_prec), 4),
        spearman_rho_pr_auc=round(float(spearman_auc), 4),
        spearman_pvalue_pr_auc=round(float(pval_auc), 4),
        pearson_r_precision=round(float(pearson_prec), 4),
        is_statistically_significant=is_sig,
        observability_bins=bin_results,
        provenance_hash=hashlib.sha256(f"CALIBRATION_O_{n_pixels}_{spearman_prec:.4f}".encode()).hexdigest(),
    )

    out_file = Path("data/results/flood_regime_routing/observability_calibration_results.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(asdict(manifest), indent=2), encoding="utf-8")
    print(f"\nSaved Observability Calibration Results to {out_file}")
    return asdict(manifest)
