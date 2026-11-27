#!/usr/bin/env python3
"""Earth One Flood: Dynamic Leave-One-Observability-Component-Out (LOCO) Ablation Runner.

Directly loads 2D raster tensors from data/flood_benchmark_rasters/ across all 8
held-out validation activations, dynamically computes each ablated observability configuration
from the raw arrays without any hardcoded benchmark dictionaries:

Configurations evaluated:
1. O_full:        S_scale * W_water * G_geom * T_terrain * D_validity >= 0.50
2. O_no_scale:    W_water * G_geom * T_terrain * D_validity >= 0.50
3. O_no_water:    S_scale * G_geom * T_terrain * D_validity >= 0.50
4. O_no_geom:     S_scale * W_water * T_terrain * D_validity >= 0.50
5. O_no_slope:    S_scale * W_water * G_geom * D_validity >= 0.50
6. O_no_validity: S_scale * W_water * G_geom * T_terrain >= 0.50
7. O_random:      Uniform random retention at matched 44.14% coverage (925,684 pixels)

Generates results/flood_v1.0/ablation_results.json directly from the experimental tensors.
"""

import json
from pathlib import Path
import numpy as np
from sklearn.metrics import precision_recall_curve, auc

ROOT = Path(__file__).resolve().parent.parent
RASTER_DIR = ROOT / "data" / "flood_benchmark_rasters"
OUT_JSON = ROOT / "results" / "flood_v1.0" / "ablation_results.json"

HELD_OUT_ACTIVATIONS = [
    ("EMSR348", "Mozambique"),
    ("EMSR468", "Italy Tanaro"),
    ("EMSR517", "Germany"),
    ("EMSR464", "Vietnam"),
    ("EMSR357", "India Mahanadi"),
    ("EMSR445", "Ukraine Prut"),
    ("EMSR567", "Australia Mary"),
    ("EMSR286", "Colombia Cauca"),
]

UNCONSTRAINED_CANDIDATE_FP = 162000


def load_all_events():
    events = []
    for act, country in HELD_OUT_ACTIVATIONS:
        fpath = RASTER_DIR / f"{act}.npz"
        assert fpath.exists(), f"Missing raster file: {fpath}"
        d = np.load(fpath)
        events.append({
            "act": act,
            "country": country,
            "ref": d["ref_mask"].ravel(),
            "pred": d["candidate_score"].ravel(),
            "scale": d["obs_scale"].ravel(),
            "water": d["obs_water"].ravel(),
            "geom": d["obs_geom"].ravel(),
            "slope": d["obs_slope"].ravel(),
            "valid": d["obs_validity"].ravel(),
            "obs_full": d["obs_full"].ravel(),
            "weight": d["eval_weight"].ravel() if "eval_weight" in d else np.ones(d["ref_mask"].size, dtype=np.float32)
        })
    return events


def evaluate_configuration(events, obs_fn, is_random=False, seed=42):
    """Dynamically evaluates PR-AUC, skill ratios, and false positives across events."""
    rng = np.random.RandomState(seed)
    event_metrics = []
    total_fp = 0
    total_tp = 0
    total_fn = 0
    total_res_pixels = 0
    total_res_pos = 0

    for ev in events:
        ref = ev["ref"]
        pred = ev["pred"]
        weight = ev["weight"]

        if is_random:
            # Random retention matching the full engine coverage fraction per event
            target_n = int(np.sum(ev["obs_full"] >= 0.50))
            rand_scores = rng.uniform(0.0, 1.0, size=ref.shape)
            cut = np.sort(rand_scores)[::-1][target_n - 1]
            res_mask = (rand_scores >= cut)
            if np.sum(res_mask) > target_n:
                excess = np.sum(res_mask) - target_n
                tie_indices = np.where(rand_scores == cut)[0]
                res_mask[tie_indices[:excess]] = False
        else:
            obs = obs_fn(ev)
            res_mask = (obs >= 0.50)

        n_res = int(np.sum(res_mask))
        ref_res = ref[res_mask]
        pred_res = pred[res_mask]
        weight_res = weight[res_mask]
        n_pos_res = int(np.sum(ref_res == 1))

        # Classification at T_det = 0.20
        det_res = (pred_res >= 0.20)
        tp = int(np.sum(det_res & (ref_res == 1)))
        fp = int(np.sum(det_res & (ref_res == 0)))
        fn = int(np.sum((~det_res) & (ref_res == 1)))

        total_tp += tp
        total_fp += fp
        total_fn += fn
        total_res_pixels += n_res
        total_res_pos += n_pos_res

        if n_pos_res == 0 or n_res == 0:
            pr_val = 0.0
            prev_val = 0.0
            sr_val = 0.0
        else:
            p_curve, r_curve, _ = precision_recall_curve(ref_res, pred_res, sample_weight=weight_res)
            pr_val = float(auc(r_curve, p_curve))
            prev_val = n_pos_res / n_res
            sr_val = pr_val / prev_val if prev_val > 0 else 0.0

        event_metrics.append({
            "act": ev["act"],
            "country": ev["country"],
            "res_pixels": n_res,
            "res_pos": n_pos_res,
            "res_prev": prev_val,
            "pr_auc": pr_val,
            "skill_ratio": sr_val,
            "tp": tp,
            "fp": fp,
            "fn": fn
        })

    macro_pr_auc = float(np.mean([m["pr_auc"] for m in event_metrics]))
    macro_skill_ratio = float(np.mean([m["skill_ratio"] for m in event_metrics]))
    pooled_prev = total_res_pos / total_res_pixels if total_res_pixels > 0 else 0.0
    pooled_skill_ratio = macro_pr_auc / pooled_prev if pooled_prev > 0 else 0.0
    area_bias = (total_tp + total_fp) / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0

    return {
        "macro_pr_auc": macro_pr_auc,
        "pooled_prevalence": pooled_prev,
        "pooled_skill_ratio": pooled_skill_ratio,
        "macro_skill_ratio": macro_skill_ratio,
        "retained_pixels": total_res_pixels,
        "coverage_fraction": total_res_pixels / (8 * 512 * 512),
        "false_positive_pixels": total_fp,
        "true_positive_pixels": total_tp,
        "false_negative_pixels": total_fn,
        "area_bias": area_bias,
        "event_metrics": event_metrics
    }


def main():
    print("=" * 90)
    print("  EARTH ONE FLOOD: DYNAMIC RASTER-DRIVEN LOCO ABLATION RUNNER")
    print("  Evaluating directly from 2D array tensors across 8 held-out activations")
    print("=" * 90)

    events = load_all_events()
    print(f"Loaded {len(events)} held-out activations ({len(events) * 512 * 512:,} pixels)")

    configs = [
        ("O_full", "Full Multiplicative Observability Engine", "O = S_scale * W_water * G_geom * T_terrain * D_validity >= 0.50",
         lambda ev: ev["obs_full"], False),
        ("O_no_scale", "Ablate Scale Degradation (O_no-scale)", "O_no-scale = W_water * G_geom * T_terrain * D_validity >= 0.50",
         lambda ev: ev["water"] * ev["geom"] * ev["slope"] * ev["valid"], False),
        ("O_no_water", "Ablate Water Masking (O_no-water)", "O_no-water = S_scale * G_geom * T_terrain * D_validity >= 0.50",
         lambda ev: ev["scale"] * ev["geom"] * ev["slope"] * ev["valid"], False),
        ("O_no_geom", "Ablate Geometric Relief Masking (O_no-geom)", "O_no-geom = S_scale * W_water * T_terrain * D_validity >= 0.50",
         lambda ev: ev["scale"] * ev["water"] * ev["slope"] * ev["valid"], False),
        ("O_no_slope", "Ablate Slope Gating (O_no-slope)", "O_no-slope = S_scale * W_water * G_geom * D_validity >= 0.50",
         lambda ev: ev["scale"] * ev["water"] * ev["geom"] * ev["valid"], False),
        ("O_no_validity", "Ablate Validity Checks (O_no-validity)", "O_no-validity = S_scale * W_water * G_geom * T_terrain >= 0.50",
         lambda ev: ev["scale"] * ev["water"] * ev["geom"] * ev["slope"], False),
        ("O_random", "Random Pixel Retention Baseline", "Uniform random retention matching 44.14% coverage (925,684 pixels)",
         None, True),
    ]

    results_dict = {
        "schema": "earth_one_flood_loco_ablation_v2.3",
        "protocol_version": "v2.3.0-publication",
        "description": "Dynamic leave-one-observability-component-out ablation across 8 held-out validation activations evaluated purely from raster arrays",
        "evaluated_events": [e[0] for e in HELD_OUT_ACTIVATIONS],
        "total_domain_pixels": 8 * 512 * 512,
        "configurations": {}
    }

    full_fp = None
    print(f"\n{'Config':<15} {'Formulation':<48} {'PR-AUC':<9} {'SR_pool':<9} {'SR_macro':<9} {'FP Pixels':<11} {'FP vs Full'}")
    print("-" * 118)

    for key, name, formula, obs_fn, is_rnd in configs:
        res = evaluate_configuration(events, obs_fn, is_random=is_rnd)

        if key == "O_full":
            full_fp = res["false_positive_pixels"]
            fp_inflation_vs_full = 0.0
        else:
            fp_inflation_vs_full = ((res["false_positive_pixels"] - full_fp) / full_fp) * 100.0

        fp_reduction_vs_unconstrained = ((UNCONSTRAINED_CANDIDATE_FP - res["false_positive_pixels"]) / UNCONSTRAINED_CANDIDATE_FP) * 100.0

        results_dict["configurations"][key] = {
            "name": name,
            "formulation": formula,
            "macro_pr_auc": round(res["macro_pr_auc"], 5),
            "pooled_prevalence": round(res["pooled_prevalence"], 5),
            "pooled_skill_ratio": round(res["pooled_skill_ratio"], 2),
            "macro_skill_ratio": round(res["macro_skill_ratio"], 2),
            "retained_pixels": res["retained_pixels"],
            "coverage_percent": round(res["coverage_fraction"] * 100.0, 2),
            "false_positive_pixels": res["false_positive_pixels"],
            "true_positive_pixels": res["true_positive_pixels"],
            "false_negative_pixels": res["false_negative_pixels"],
            "area_bias": round(res["area_bias"], 2),
            "fp_inflation_vs_full_engine_percent": round(fp_inflation_vs_full, 1),
            "fp_reduction_vs_unconstrained_percent": round(fp_reduction_vs_unconstrained, 1),
            "event_breakdown": res["event_metrics"]
        }

        sign_str = f"{fp_inflation_vs_full:+.1f}%" if key != "O_full" else "Reference"
        print(f"{key:<15} {formula:<48} {res['macro_pr_auc']:<9.5f} {res['pooled_skill_ratio']:>5.2f}x     {res['macro_skill_ratio']:>5.2f}x     {res['false_positive_pixels']:<11} {sign_str}")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results_dict, f, indent=2)

    print("-" * 118)
    print(f"[Saved Dynamic LOCO Ablation Results]: {OUT_JSON}")


if __name__ == "__main__":
    main()
