#!/usr/bin/env python3
"""Executable Table 4 Panel A Baseline Evaluator across the 8 Held-Out Validation Events.

Reproduces full-domain unconstrained baseline comparisons (Single-Channel SAR Otsu,
SAR Amplitude Change Detection, Additive Linear Blending Mode A, Unconstrained Mode B)
and compares them against Gated Physics + Observability Filtering (O >= 0.50) directly
from real Planetary Computer Sentinel-1 RTC, Copernicus GLO-30 DEM, JRC GSW, and
authoritative Copernicus EMS reference masks (data/real_eo_stacks/{act}_real_eo.npz).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

import numpy as np
from sklearn.metrics import auc, precision_recall_curve

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from earth_one.flood import FloodEvidenceConfig, compute_sar_water_evidence

REAL_EO_DIR = ROOT / "data" / "real_eo_stacks"
OUT_JSON = ROOT / "results" / "flood_v1.0" / "panel_a_baselines.json"

HELD_OUT_EVENTS = [
    ("EMSR348", "Mozambique"),
    ("EMSR468", "Italy Tanaro"),
    ("EMSR517", "Germany"),
    ("EMSR464", "Vietnam"),
    ("EMSR357", "India Mahanadi"),
    ("EMSR445", "Ukraine Prut"),
    ("EMSR567", "Australia Mary"),
    ("EMSR286", "Colombia Cauca"),
]


def otsu_threshold(values: np.ndarray, nbins: int = 256) -> float:
    """Deterministic NumPy Otsu threshold maximization for scalar arrays."""
    v = values[np.isfinite(values)]
    if v.size == 0:
        return 0.0
    hist, bin_edges = np.histogram(v, bins=nbins)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    weight1 = np.cumsum(hist).astype(np.float64)
    weight2 = np.cumsum(hist[::-1])[::-1].astype(np.float64)
    mean1 = np.cumsum(hist * bin_centers) / np.maximum(weight1, 1e-9)
    mean2 = (np.cumsum((hist * bin_centers)[::-1]) / np.maximum(weight2[::-1], 1e-9))[::-1]
    var_between = weight1[:-1] * weight2[1:] * (mean1[:-1] - mean2[1:]) ** 2
    idx = int(np.argmax(var_between))
    return float(bin_centers[idx])


def compute_otsu_score_and_mask(d: np.lib.npyio.NpzFile) -> tuple[np.ndarray, np.ndarray]:
    """Single-channel Sentinel-1 VV post-event dark-water Otsu score & binary mask."""
    vv_e = d["vv_after"].astype(np.float32)
    valid = (d["valid_mask"] > 0) & np.isfinite(vv_e) & (vv_e > 0)
    vv_db = np.where(valid, 10.0 * np.log10(np.clip(vv_e, 1e-7, 10.0)), 0.0)
    thresh_db = otsu_threshold(vv_db[valid]) if valid.any() else -14.0
    # Lower backscatter than Otsu threshold indicates smoother/darker surface (candidate water)
    score = np.where(valid, np.clip((thresh_db - vv_db) / 8.0 + 0.5, 0.0, 1.0), 0.0).astype(np.float32)
    mask = valid & (vv_db <= thresh_db)
    return score, mask


def compute_sar_change_score_and_mask(d: np.lib.npyio.NpzFile) -> tuple[np.ndarray, np.ndarray]:
    """Unconstrained SAR amplitude backscatter drop (Sentinel-1 VV+VH), ignoring DEM & JRC."""
    cfg = FloodEvidenceConfig(sar_input_units="linear")
    vh_b = d["vh_before"] if "vh_before" in d and np.isfinite(d["vh_before"]).any() else None
    vh_e = d["vh_after"] if "vh_after" in d and np.isfinite(d["vh_after"]).any() else None
    sar_ev, sar_valid = compute_sar_water_evidence(
        vv_before=d["vv_before"],
        vv_event=d["vv_after"],
        vh_before=vh_b,
        vh_event=vh_e,
        config=cfg,
    )
    return sar_ev.astype(np.float32), sar_valid & (sar_ev >= 0.20)


def evaluate_method(
    stacks: dict[str, dict],
    name: str,
    extractor: Callable[[dict], tuple[np.ndarray, np.ndarray, np.ndarray]],
    note: str,
) -> dict:
    """Evaluate macro PR-AUC, true concatenated pixel-pooled PR-AUC, dual SRs, and FP area."""
    event_rows = []
    pool_refs, pool_scores, pool_pos_preds = [], [], []
    tot_tp = tot_fp = tot_fn = tot_n = tot_ref_pos = 0

    for act, country in HELD_OUT_EVENTS:
        d = stacks[act]
        ref, score, pred_mask = extractor(d)
        ref_flat = ref.ravel().astype(np.uint8)
        sc_flat = score.ravel().astype(np.float32)
        pred_flat = pred_mask.ravel().astype(bool)

        n_px = ref_flat.size
        pos_px = int(np.sum(ref_flat == 1))
        prev = pos_px / n_px if n_px > 0 else 0.0

        tp = int(np.sum(pred_flat & (ref_flat == 1)))
        fp = int(np.sum(pred_flat & (ref_flat == 0)))
        fn = int(np.sum((~pred_flat) & (ref_flat == 1)))

        if pos_px > 0 and pos_px < n_px:
            p, r, _ = precision_recall_curve(ref_flat, sc_flat)
            pr_val = float(auc(r, p))
        else:
            pr_val = 0.0
        sr_val = pr_val / prev if prev > 0 else 0.0

        pool_refs.append(ref_flat)
        pool_scores.append(sc_flat)
        pool_pos_preds.append(pred_flat)

        tot_tp += tp
        tot_fp += fp
        tot_fn += fn
        tot_n += n_px
        tot_ref_pos += pos_px

        event_rows.append({
            "act": act,
            "country": country,
            "n_pixels": n_px,
            "ref_pos": pos_px,
            "prevalence": round(prev, 5),
            "pr_auc": round(pr_val, 5),
            "skill_ratio": round(sr_val, 2),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        })

    cat_ref = np.concatenate(pool_refs)
    cat_sc = np.concatenate(pool_scores)
    pooled_prev = tot_ref_pos / tot_n if tot_n > 0 else 0.0
    if tot_ref_pos > 0:
        p_pool, r_pool, _ = precision_recall_curve(cat_ref, cat_sc)
        pooled_pr = float(auc(r_pool, p_pool))
    else:
        pooled_pr = 0.0

    macro_pr = float(np.mean([e["pr_auc"] for e in event_rows]))
    macro_sr = float(np.mean([e["skill_ratio"] for e in event_rows]))
    pooled_sr = pooled_pr / pooled_prev if pooled_prev > 0 else 0.0
    area_bias = (tot_tp + tot_fp) / tot_ref_pos if tot_ref_pos > 0 else 0.0

    return {
        "name": name,
        "macro_pr_auc": round(macro_pr, 5),
        "pooled_pr_auc": round(pooled_pr, 5),
        "pooled_prevalence": round(pooled_prev, 5),
        "sr_pool": round(pooled_sr, 2),
        "sr_macro": round(macro_sr, 2),
        "tp_pixels": tot_tp,
        "fp_pixels": tot_fp,
        "fn_pixels": tot_fn,
        "evaluated_pixels": tot_n,
        "area_bias": round(area_bias, 2),
        "note": note,
        "events": event_rows,
    }


def main() -> None:
    stacks: dict[str, dict] = {}
    for act, _ in HELD_OUT_EVENTS:
        p = REAL_EO_DIR / f"{act}_real_eo.npz"
        if not p.exists():
            raise FileNotFoundError(
                f"Missing real EO stack {p}. Run `python scripts/extract_real_eo_validation_stacks.py` first."
            )
        stacks[act] = dict(np.load(p))

    def ext_otsu(d: dict):
        sc, mk = compute_otsu_score_and_mask(d)
        return d["ref_mask"], sc, mk

    def ext_sar_chg(d: dict):
        sc, mk = compute_sar_change_score_and_mask(d)
        return d["ref_mask"], sc, mk

    def ext_mode_a(d: dict):
        sc = d["mode_a_score"].astype(np.float32)
        mk = (d["valid_mask"] > 0) & (sc >= 0.20)
        return d["ref_mask"], sc, mk

    def ext_mode_b_full(d: dict):
        sc = d["fused_score"].astype(np.float32)
        mk = (d["valid_mask"] > 0) & (sc >= 0.20)
        return d["ref_mask"], sc, mk

    def ext_mode_b_obs(d: dict):
        is_res = d["obs_full"] >= 0.50
        sc = d["fused_score"][is_res].astype(np.float32)
        mk = (d["tri_state"][is_res] == 1)
        return d["ref_mask"][is_res], sc, mk

    rows = [
        evaluate_method(stacks, "Single-Channel SAR Otsu (S1)", ext_otsu, "Unconstrained S1 VV post-event Otsu threshold"),
        evaluate_method(stacks, "SAR Amplitude Change Detection", ext_sar_chg, "Unconstrained dual-pol delta-sigma0 change score"),
        evaluate_method(stacks, "Additive Linear Blending (Mode A)", ext_mode_a, "Weighted additive linear combination (slope penalty bypassed)"),
        evaluate_method(stacks, "Unconstrained Multi-Modal Fusion (Mode B)", ext_mode_b_full, "Gated physics fusion without observability filtering (O >= 0.00)"),
        evaluate_method(stacks, "Mode B + Observability Filter (O >= 0.50)", ext_mode_b_obs, "Gated physics fusion evaluated strictly in resolvable domain"),
    ]

    print("=" * 124)
    print("  EARTH ONE FLOOD: REAL EO TABLE 4 PANEL A BASELINE BENCHMARK (N = 8 HELD-OUT EVENTS)")
    print("=" * 124)
    print(f"{'Method':<43} {'Macro PR':<10} {'Pool PR':<10} {'SR_pool':<9} {'SR_macro':<9} {'FP Pixels':<11} {'Area Bias':<10} {'Coverage'}")
    print("-" * 124)
    for r in rows:
        cov = r["evaluated_pixels"] / (8 * 512 * 512) * 100.0
        print(
            f"{r['name']:<43} {r['macro_pr_auc']:<10.5f} {r['pooled_pr_auc']:<10.5f} "
            f"{r['sr_pool']:>5.2f}x   {r['sr_macro']:>5.2f}x   {r['fp_pixels']:<11,} "
            f"{r['area_bias']:>5.2f}x     {cov:>5.1f}%"
        )

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "schema": "earth_one_panel_a_real_eo_baselines_v2.3",
                "source_stacks": str(REAL_EO_DIR.relative_to(ROOT)),
                "methods": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n[Saved] {OUT_JSON}")


if __name__ == "__main__":
    main()
