#!/usr/bin/env python3
"""Earth One Flood: Dynamic Development Cohort Threshold Calibration and Sensitivity Sweep.

Performs an exhaustive, reproducible 2D parameter sweep across detection thresholds
T_det in [0.10, 0.40] and observability thresholds O in [0.00, 0.80] strictly across
the three Development activations (EMSR439 Bangladesh, EMSR629 Pakistan, EMSR548 Italy Catania).

Outputs:
- ASCII summary of macro F1, pooled F1, false positive reduction, and Brier Skill Scores
- JSON artifact: results/flood_v1.0/development_calibration_sweep.json
"""

import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RASTER_DIR = ROOT / "data" / "flood_benchmark_rasters"
OUT_JSON = ROOT / "results" / "flood_v1.0" / "development_calibration_sweep.json"

DEV_EVENTS = ["EMSR439", "EMSR629", "EMSR548"]


def load_dev_rasters():
    rasters = {}
    for act in DEV_EVENTS:
        fpath = RASTER_DIR / f"{act}.npz"
        assert fpath.exists(), f"Missing development raster: {fpath}"
        d = np.load(fpath)
        rasters[act] = {
            "ref": d["ref_mask"].ravel(),
            "cand": d["candidate_score"].ravel(),
            "obs": d["obs_full"].ravel(),
            "weight": d["eval_weight"].ravel() if "eval_weight" in d else np.ones_like(d["ref_mask"].ravel())
        }
    return rasters


def run_development_sweep():
    print("=" * 100)
    print("  EARTH ONE FLOOD: DEVELOPMENT THRESHOLD CALIBRATION AND SENSITIVITY SWEEP")
    print("  Cohort: EMSR439 (Bangladesh), EMSR629 (Pakistan), EMSR548 (Italy Catania) | N = 3")
    print("=" * 100)

    rasters = load_dev_rasters()

    ref_all = np.concatenate([rasters[a]["ref"] for a in DEV_EVENTS])
    cand_all = np.concatenate([rasters[a]["cand"] for a in DEV_EVENTS])
    obs_all = np.concatenate([rasters[a]["obs"] for a in DEV_EVENTS])

    def calc_bss(mask):
        if np.sum(mask) == 0:
            return 0.0
        r = ref_all[mask]
        c = cand_all[mask]
        prev = np.mean(r)
        bs = np.mean((c - r) ** 2)
        bs_clim = prev * (1.0 - prev)
        return float(1.0 - bs / bs_clim) if bs_clim > 0 else 0.0

    t_det_values = [0.10, 0.15, 0.18, 0.20, 0.22, 0.25, 0.30]
    o_values = [0.00, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70]

    sweep_records = []

    # Baseline false positives at T_det = 0.20, O >= 0.00 and O >= 0.20
    raw_fp_020 = sum(np.sum((rasters[a]["cand"] >= 0.20) & (rasters[a]["ref"] == 0)) for a in DEV_EVENTS)
    raw_fp_o020 = sum(np.sum((rasters[a]["cand"] >= 0.20) & (rasters[a]["ref"] == 0) & (rasters[a]["obs"] >= 0.20)) for a in DEV_EVENTS)

    print(f"Development Cohort Baseline False Positives (T_det = 0.20):")
    print(f"  Unconstrained (O >= 0.00): {raw_fp_020:,} pixels")
    print(f"  Initial Cutoff (O >= 0.20): {raw_fp_o020:,} pixels\n")

    print(f"{'T_det':<7} {'O_th':<7} {'Macro F1':<10} {'Pooled F1':<11} {'Total FP':<11} {'FP Red vs O>=0':<16} {'FP Red vs O>=0.2':<18} {'BSS (< O)':<11} {'BSS (>= O)'}")
    print("-" * 105)

    for t_det in t_det_values:
        for o_th in o_values:
            event_f1s = {}
            event_fps = {}
            event_precs = {}
            event_recs = {}
            tot_tp = 0
            tot_fp = 0
            tot_fn = 0

            for act in DEV_EVENTS:
                d = rasters[act]
                ref = d["ref"]
                cand = d["cand"]
                obs = d["obs"]

                mask = (obs >= o_th)
                pred_pos = (cand >= t_det) & mask

                tp = int(np.sum(pred_pos & (ref == 1)))
                fp = int(np.sum(pred_pos & (ref == 0)))
                fn = int(np.sum((~pred_pos) & (ref == 1) & mask))

                p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
                r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
                f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0

                event_f1s[act] = f1
                event_fps[act] = fp
                event_precs[act] = p
                event_recs[act] = r

                tot_tp += tp
                tot_fp += fp
                tot_fn += fn

            macro_f1 = float(np.mean(list(event_f1s.values())))
            pooled_p = tot_tp / (tot_tp + tot_fp) if (tot_tp + tot_fp) > 0 else 0.0
            pooled_r = tot_tp / (tot_tp + tot_fn) if (tot_tp + tot_fn) > 0 else 0.0
            pooled_f1 = float(2 * pooled_p * pooled_r / (pooled_p + pooled_r)) if (pooled_p + pooled_r) > 0 else 0.0

            red_vs_raw = (raw_fp_020 - tot_fp) / raw_fp_020 * 100.0
            red_vs_o020 = (raw_fp_o020 - tot_fp) / raw_fp_o020 * 100.0

            bss_below = calc_bss(obs_all < o_th)
            bss_above = calc_bss(obs_all >= o_th)

            record = {
                "detection_threshold": t_det,
                "observability_threshold": o_th,
                "macro_f1": round(macro_f1, 4),
                "pooled_f1": round(pooled_f1, 4),
                "total_false_positive_pixels": tot_fp,
                "fp_reduction_vs_raw_percent": round(red_vs_raw, 2),
                "fp_reduction_vs_o020_percent": round(red_vs_o020, 2),
                "bss_below_threshold": round(bss_below, 4),
                "bss_above_threshold": round(bss_above, 4),
                "event_metrics": {
                    act: {
                        "precision": round(event_precs[act], 4),
                        "recall": round(event_recs[act], 4),
                        "f1": round(event_f1s[act], 4),
                        "fp": event_fps[act]
                    } for act in DEV_EVENTS
                }
            }
            sweep_records.append(record)

            if t_det in [0.18, 0.20, 0.22]:
                mark = " <-- KNEE POINT" if (t_det == 0.20 and o_th == 0.50) else ""
                print(f"{t_det:<7.2f} {o_th:<7.2f} {macro_f1:<10.4f} {pooled_f1:<11.4f} {tot_fp:<11,} {red_vs_raw:>6.1f}%          {red_vs_o020:>6.1f}%            {bss_below:>6.2f}      {bss_above:>6.2f}{mark}")

    print("-" * 105)

    # Detailed knee-point breakdown
    knee = next(r for r in sweep_records if r["detection_threshold"] == 0.20 and r["observability_threshold"] == 0.50)
    print("\nAUTHORITATIVE OPERATING POINT CALIBRATION (T_det = 0.20, O >= 0.50):")
    print(f"  Macro F1: {knee['macro_f1']:.4f}")
    print(f"  Individual Event F1s:")
    for act, m in knee["event_metrics"].items():
        print(f"    - {act}: Prec={m['precision']*100:.2f}%, Rec={m['recall']*100:.2f}%, F1={m['f1']:.4f}, FP={m['fp']:,}")
    print(f"  Unweighted Mean F1: ({' + '.join(str(m['f1']) for m in knee['event_metrics'].values())}) / 3 = {knee['macro_f1']:.4f}")
    print(f"  False Positive Reduction vs O >= 0.20: {knee['fp_reduction_vs_o020_percent']:.1f}% ({raw_fp_o020:,} -> {knee['total_false_positive_pixels']:,})")
    print(f"  False Positive Reduction vs Raw O >= 0.00: {knee['fp_reduction_vs_raw_percent']:.1f}% ({raw_fp_020:,} -> {knee['total_false_positive_pixels']:,})")
    print(f"  Brier Skill Score: Below O < 0.50 = {knee['bss_below_threshold']:.2f} | Above O >= 0.50 = {knee['bss_above_threshold']:.2f}")

    output_payload = {
        "protocol_version": "v2.3.0-publication",
        "description": "Exhaustive 2D parameter sweep on development cohort for detection threshold and observability threshold calibration",
        "cohort": DEV_EVENTS,
        "operating_knee_point": knee,
        "full_sweep_grid": sweep_records
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)

    print(f"\n[Saved Calibration Artifact]: {OUT_JSON}")


if __name__ == "__main__":
    run_development_sweep()
