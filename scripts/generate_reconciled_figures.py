#!/usr/bin/env python3
"""Generate publication Figures 3, 4, 5, 6 and Supplementary Figures S2 and S3.

Every figure is derived strictly from real Earth Observation STAC stacks
(fig3_real_eo_rasters.npz / data/real_eo_stacks/*.npz), frozen 8-event benchmark
raster arrays (data/flood_benchmark_rasters/*.npz), and authoritative JSON ledgers
(results/flood_v1.0/*.json), with zero synthetic noise and zero hardcoded series.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
import numpy as np
import shapefile
from sklearn.metrics import auc, precision_recall_curve

ROOT = Path("/Users/shubhamsharma/Earth-One")
BRAIN_FIGS = Path("/Users/shubhamsharma/.gemini/antigravity/brain/e2a61b8e-ff9e-4a79-a6a7-b00c9c265b4f/figures")
OUT_DIRS = [ROOT / "docs" / "figures", BRAIN_FIGS]
for d in OUT_DIRS:
    d.mkdir(parents=True, exist_ok=True)

REAL_EO_DIR = ROOT / "data" / "real_eo_stacks"
BENCHMARK_DIR = ROOT / "data" / "flood_benchmark_rasters"
RESULTS_DIR = ROOT / "results" / "flood_v1.0"
MANIFEST_PATH = RESULTS_DIR / "frozen_cohort_manifest.json"


def find_shapefile_path(ev_entry: dict) -> Path:
    shp = ROOT / ev_entry["reference_shapefile"]
    if shp.exists():
        return shp
    act = ev_entry["activation"]
    matches = list((ROOT / "data").rglob(shp.name)) or list((ROOT / "data").rglob(f"*{act}*observed*event*.shp"))
    if not matches:
        raise FileNotFoundError(f"Shapefile missing for {act}")
    return matches[0]


def save_all(fig: plt.Figure, filename: str) -> None:
    for d in OUT_DIRS:
        fig.savefig(d / filename, dpi=300, bbox_inches="tight")


def render_spatial_comparison_figure(
    rows_spec: list[tuple[str, str, Path, dict[str, np.ndarray]]],
    suptitle: str,
    out_filenames: list[str],
) -> None:
    """Shared 4-panel spatial comparison plotter for Figure 3, Figure S2, and Figure S3."""
    n_rows = len(rows_spec)
    fig, axes = plt.subplots(n_rows, 4, figsize=(15.2, 3.85 * n_rows), dpi=300)
    if n_rows == 1:
        axes = np.expand_dims(axes, axis=0)

    cmap_tri = ListedColormap(["#94a3b8", "#06b6d4", "#f97316"])
    cmap_delta = plt.get_cmap("RdBu_r").copy()
    cmap_delta.set_bad("#e2e8f0")

    for r_idx, (act, title, shp_path, rasters) in enumerate(rows_spec):
        delta_vv = rasters["delta_vv_db"]
        obs = rasters["obs"]
        tri = rasters["tri_state"]
        ref_mask = rasters["ref_mask"]
        bbox = rasters["bbox"]
        x0, y0, x1, y1 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])

        # (a) Real Sentinel-1 SAR Delta-VV backscatter change (dB)
        ax = axes[r_idx, 0]
        im0 = ax.imshow(
            np.ma.masked_invalid(delta_vv),
            cmap=cmap_delta,
            vmin=-8.0,
            vmax=8.0,
            extent=[x0, x1, y0, y1],
            interpolation="nearest",
        )
        ax.set_ylabel(title, fontsize=9.0, fontweight="bold")
        if r_idx == 0:
            ax.set_title("(a) Sentinel-1 SAR $\\Delta\\sigma^0_{\\mathrm{VV}}$ (dB)", fontsize=9.8, fontweight="bold")
        cb0 = fig.colorbar(im0, ax=ax, fraction=0.046, pad=0.03)
        cb0.ax.tick_params(labelsize=7)

        # (b) Real Continuous Observability Index (O)
        ax = axes[r_idx, 1]
        im1 = ax.imshow(
            obs,
            cmap="magma",
            vmin=0.0,
            vmax=1.0,
            extent=[x0, x1, y0, y1],
            interpolation="nearest",
        )
        if r_idx == 0:
            ax.set_title("(b) Observability Index ($O$)", fontsize=9.8, fontweight="bold")
        cb1 = fig.colorbar(im1, ax=ax, fraction=0.046, pad=0.03)
        cb1.ax.tick_params(labelsize=7)

        # (c) Tri-State Classification (FLOOD, NO_FLOOD, UNRESOLVED)
        ax = axes[r_idx, 2]
        ax.imshow(
            tri,
            cmap=cmap_tri,
            vmin=0,
            vmax=2,
            extent=[x0, x1, y0, y1],
            interpolation="nearest",
        )
        if r_idx == 0:
            ax.set_title("(c) Tri-State Classification", fontsize=9.8, fontweight="bold")
            patches = [
                Patch(facecolor="#06b6d4", label="FLOOD"),
                Patch(facecolor="#94a3b8", label="NO_FLOOD"),
                Patch(facecolor="#f97316", label="UNRESOLVED"),
            ]
            ax.legend(handles=patches, loc="lower right", fontsize=6.5, framealpha=0.92)

        # (d) Real CEMS Vector Reference Polygons overlaid on Observability backdrop
        ax = axes[r_idx, 3]
        ax.imshow(obs, cmap="Greys", vmin=0.0, vmax=1.4, extent=[x0, x1, y0, y1], alpha=0.35, interpolation="nearest")
        ax.imshow(
            np.ma.masked_where(ref_mask == 0, ref_mask),
            cmap=ListedColormap(["#fca5a5"]),
            alpha=0.55,
            extent=[x0, x1, y0, y1],
            interpolation="nearest",
        )
        sf = shapefile.Reader(str(shp_path))
        for shp_geom in sf.shapes():
            pts = np.asarray(shp_geom.points)
            if pts.size == 0:
                continue
            parts = list(shp_geom.parts) + [len(pts)]
            for i in range(len(parts) - 1):
                seg = pts[parts[i]:parts[i + 1]]
                ax.plot(seg[:, 0], seg[:, 1], color="#dc2626", linewidth=0.55, alpha=0.9)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        if r_idx == 0:
            ax.set_title("(d) CEMS Vector Reference", fontsize=9.8, fontweight="bold")

        for c_idx in range(4):
            axes[r_idx, c_idx].set_xticks([])
            axes[r_idx, c_idx].set_yticks([])

    fig.suptitle(suptitle, fontsize=11.5, fontweight="bold", y=0.995)
    plt.tight_layout(rect=[0, 0, 1, 0.985])
    for fname in out_filenames:
        save_all(fig, fname)
    plt.close(fig)
    print(f"Generated {out_filenames[0]}")


def generate_spatial_figures() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ev_lookup = {ev["activation"]: ev for ev in manifest["development_cohort"] + manifest["unseen_spatial_holdout_cohort"]}

    # Figure 3: Primary 3 archetypes from real Sentinel-1 RTC / DEM / JRC stacks
    fig3_npz = np.load(BENCHMARK_DIR / "fig3_real_eo_rasters.npz")
    fig3_specs = [
        ("EMSR629", "EMSR629: Pakistan Indus\n(Alluvial Mega-Flood)"),
        ("EMSR468", "EMSR468: Italy Tanaro\n(Alpine Gorge / Steep)"),
        ("EMSR567", "EMSR567: Australia Mary\n(Fluvial Riverine)"),
    ]
    fig3_rows = []
    for act, label in fig3_specs:
        fig3_rows.append((
            act,
            label,
            find_shapefile_path(ev_lookup[act]),
            {
                "delta_vv_db": fig3_npz[f"{act}_delta_vv_db"],
                "obs": fig3_npz[f"{act}_obs"],
                "tri_state": fig3_npz[f"{act}_tristate"],
                "ref_mask": fig3_npz[f"{act}_ref"],
                "bbox": fig3_npz[f"{act}_bbox"],
            },
        ))
    render_spatial_comparison_figure(
        fig3_rows,
        "Figure 3. Real Sentinel-1 RTC Backscatter, Observability Index, Tri-State Output, and CEMS Reference",
        ["figure_3_spatial_prediction_vs_reference.png"],
    )

    # Supplementary Figure S2 & S3: Remaining 8 activations from real EO stacks when available
    s2_specs = [
        ("EMSR348", "EMSR348: Mozambique\n(Coastal Estuary)"),
        ("EMSR517", "EMSR517: Germany\n(Temperate Fluvial)"),
        ("EMSR464", "EMSR464: Vietnam\n(Monsoon Pluvial)"),
        ("EMSR357", "EMSR357: India Mahanadi\n(Coastal Delta)"),
    ]
    s3_specs = [
        ("EMSR445", "EMSR445: Ukraine Prut\n(Fluvial Valley)"),
        ("EMSR286", "EMSR286: Colombia Cauca\n(Steep Canyon)"),
        ("EMSR439", "EMSR439: Bangladesh (Dev)\n(Estuarine Tidal)"),
        ("EMSR548", "EMSR548: Italy Catania (Dev)\n(Pluvial Plain)"),
    ]

    def build_real_rows(spec_list):
        rows = []
        for act, label in spec_list:
            p = REAL_EO_DIR / f"{act}_real_eo.npz"
            if not p.exists():
                return None
            d = np.load(p)
            rows.append((
                act,
                label,
                find_shapefile_path(ev_lookup[act]),
                {
                    "delta_vv_db": d["delta_vv_db"],
                    "obs": d["obs_full"],
                    "tri_state": d["tri_state"],
                    "ref_mask": d["ref_mask"],
                    "bbox": d["bbox_wgs84"],
                },
            ))
        return rows

    s2_rows = build_real_rows(s2_specs)
    if s2_rows:
        render_spatial_comparison_figure(
            s2_rows,
            "Figure S2. Real Sentinel-1 RTC Diagnostic Comparisons across Held-Out Activations (Part 1)",
            ["figure_s2_validation_maps_part1.png"],
        )
    s3_rows = build_real_rows(s3_specs)
    if s3_rows:
        render_spatial_comparison_figure(
            s3_rows,
            "Figure S3. Real Sentinel-1 RTC Diagnostic Comparisons across Remaining Held-Out & Dev Activations (Part 2)",
            ["figure_s3_validation_maps_part2.png"],
        )


def generate_figure_4() -> None:
    calib_json = json.loads((RESULTS_DIR / "observability_calibration.json").read_text(encoding="utf-8"))
    t3_bins = calib_json["reliability_audit_table3"]["bins"]

    fig, ax1 = plt.subplots(figsize=(8.2, 5.2), dpi=300)
    ax2 = ax1.twinx()

    bins = ["Bin 1\n[0.0, 0.20)", "Bin 2\n[0.20, 0.40)", "Bin 3\n[0.40, 0.60)", "Bin 4\n[0.60, 0.80)", "Bin 5\n[0.80, 1.00]"]
    x = np.arange(len(bins))

    prevs = [b["empirical_prevalence"] for b in t3_bins]
    ax1.plot(x, [p * 100 for p in prevs], "k:o", lw=1.6, markersize=5, label="Positive Class Prevalence (Chance Baseline)", zorder=3)

    defined_x = [i for i, b in enumerate(t3_bins) if b["empirical_precision"] is not None]
    precs = [t3_bins[i]["empirical_precision"] * 100 for i in defined_x]
    prec_err_lo = [t3_bins[i]["empirical_precision"] * 100 - t3_bins[i]["precision_ci_95"][0] * 100 for i in defined_x]
    prec_err_hi = [t3_bins[i]["precision_ci_95"][1] * 100 - t3_bins[i]["empirical_precision"] * 100 for i in defined_x]
    ax1.errorbar(
        defined_x, precs, yerr=[prec_err_lo, prec_err_hi],
        fmt="s-", color="#2563eb", ecolor="#2563eb", elinewidth=1.5, capsize=4, capthick=1.5,
        lw=2.0, markersize=7, label="Empirical Precision (95% Block Bootstrap CI)", zorder=4,
    )
    ax1.text(
        0, 1.8, "Undefined\n(0 / 0)", ha="center", va="center", fontsize=8.5, fontweight="bold",
        color="#dc2626", bbox=dict(boxstyle="round,pad=0.3", fc="#fef2f2", ec="#dc2626", lw=1.0),
    )

    praucs = [b["empirical_pr_auc"] for b in t3_bins]
    pr_err_lo = [b["empirical_pr_auc"] - b["pr_auc_ci_95"][0] for b in t3_bins]
    pr_err_hi = [b["pr_auc_ci_95"][1] - b["empirical_pr_auc"] for b in t3_bins]
    ax2.errorbar(
        x, praucs, yerr=[pr_err_lo, pr_err_hi],
        fmt="o--", color="#ea580c", ecolor="#ea580c", elinewidth=1.5, capsize=4, capthick=1.5,
        lw=2.0, markersize=7, label="Empirical PR-AUC (95% Block Bootstrap CI)", zorder=5,
    )

    ax1.set_xlabel("Observability Tier ($O$)", fontsize=10.5, fontweight="bold")
    ax1.set_ylabel("Empirical Precision & Prevalence (%)", fontsize=10.5, fontweight="bold", color="#1e3a8a")
    ax2.set_ylabel("Empirical PR-AUC", fontsize=10.5, fontweight="bold", color="#c2410c")
    ax1.set_xticks(x)
    ax1.set_xticklabels(bins, fontsize=9.0, fontweight="bold")
    ax1.set_ylim(0, 14.0)
    ax2.set_ylim(0, 0.14)
    ax1.tick_params(axis="y", labelcolor="#1e3a8a")
    ax2.tick_params(axis="y", labelcolor="#c2410c")
    ax1.set_title("Figure 4. Observability-Bin Reliability Audit across 1,310,720 Pixels", fontsize=11.0, fontweight="bold")
    ax1.grid(True, linestyle="--", alpha=0.4)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8.5)

    plt.tight_layout()
    save_all(fig, "figure_4_observability_calibration.png")
    plt.close(fig)
    print("Generated Figure 4: figure_4_observability_calibration.png")


def generate_figure_5() -> None:
    """Dynamically compute Risk-Coverage curves across held-out raster tensors."""
    acts = ["EMSR348", "EMSR468", "EMSR517", "EMSR464", "EMSR357", "EMSR445", "EMSR567", "EMSR286"]
    rasters = {a: np.load(BENCHMARK_DIR / f"{a}.npz") for a in acts}
    total_px = len(acts) * 512 * 512
    unconstrained_fp = sum(int(((rasters[a]["candidate_score"] >= 0.20) & (rasters[a]["ref_mask"] == 0)).sum()) for a in acts)

    taus = [0.90, 0.85, 0.82, 0.80, 0.75, 0.50, 0.42, 0.35, 0.25, 0.15, 0.00]
    covs, macro_prs, pooled_prs, fp_reds, fp_counts = [], [], [], [], []

    for tau in taus:
        retained = 0
        fp_sum = 0
        ev_prs = []
        p_refs, p_preds, p_ws = [], [], []
        for a in acts:
            d = rasters[a]
            m = d["obs_full"].ravel() >= tau
            ref = d["ref_mask"].ravel()[m]
            pred = d["candidate_score"].ravel()[m]
            w = d["eval_weight"].ravel()[m]
            retained += int(m.sum())
            fp_sum += int(((pred >= 0.20) & (ref == 0)).sum())
            if ref.sum() > 0:
                p_c, r_c, _ = precision_recall_curve(ref, pred, sample_weight=w)
                ev_prs.append(float(auc(r_c, p_c)))
            else:
                ev_prs.append(0.0)
            p_refs.append(ref)
            p_preds.append(pred)
            p_ws.append(w)

        pp, pr, _ = precision_recall_curve(np.concatenate(p_refs), np.concatenate(p_preds), sample_weight=np.concatenate(p_ws))
        covs.append(retained / total_px * 100.0)
        macro_prs.append(float(np.mean(ev_prs)))
        pooled_prs.append(float(auc(pr, pp)))
        fp_counts.append(fp_sum)
        fp_reds.append((unconstrained_fp - fp_sum) / unconstrained_fp * 100.0)

    op_idx = taus.index(0.50)
    op_cov = covs[op_idx]
    op_mpr = macro_prs[op_idx]
    op_ppr = pooled_prs[op_idx]
    op_fp = fp_counts[op_idx]
    op_fpr = fp_reds[op_idx]
    gain_pct = (op_mpr - macro_prs[-1]) / macro_prs[-1] * 100.0

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.8, 5.0), dpi=300)

    ax1.plot(covs, macro_prs, "o-", color="#1e3a8a", lw=2.2, markersize=5, label="Macro PR-AUC (8 Held-Out Events)")
    ax1.plot(covs, pooled_prs, "s--", color="#0284c7", lw=1.8, markersize=4.5, label="Pooled PR-AUC (Concatenated Pixels)")
    ax1.axvline(op_cov, color="#dc2626", linestyle="--", lw=1.5, label=f"Operating Point ($O \\geq 0.50$, Cov = {op_cov:.2f}%)")
    ax1.scatter([op_cov], [op_mpr], color="#dc2626", s=90, zorder=5)
    ax1.annotate(
        f"Operating Point:\nCoverage = {op_cov:.2f}%\nMacro PR-AUC = {op_mpr:.5f} (+{gain_pct:.1f}%)\nPooled PR-AUC = {op_ppr:.5f}",
        xy=(op_cov, op_mpr), xytext=(56, 0.083),
        arrowprops=dict(facecolor="#dc2626", shrink=0.06, width=1.2, headwidth=6),
        fontsize=8.2, fontweight="bold", bbox=dict(boxstyle="round,pad=0.35", fc="#fef2f2", ec="#dc2626", lw=1.1),
    )
    ax1.set_xlabel("Domain Coverage Fraction (%)", fontsize=10, fontweight="bold")
    ax1.set_ylabel("PR-AUC", fontsize=10, fontweight="bold")
    ax1.set_ylim(0.045, 0.098)
    ax1.set_title("(a) Macro & Pooled PR-AUC vs Domain Coverage", fontsize=10.5, fontweight="bold")
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(loc="lower left", fontsize=8.0)

    ax2.plot(covs, fp_reds, "s-", color="#16a34a", lw=2.2, markersize=5, label="Empirical FP Area Reduction (%)")
    ax2.axvline(op_cov, color="#dc2626", linestyle="--", lw=1.5, label=f"Operating Point ($O \\geq 0.50$, Cov = {op_cov:.2f}%)")
    ax2.scatter([op_cov], [op_fpr], color="#dc2626", s=90, zorder=5)
    ax2.annotate(
        f"Operating Point:\nFP Reduction = {op_fpr:.1f}%\n({unconstrained_fp:,} to {op_fp:,} px)",
        xy=(op_cov, op_fpr), xytext=(56, 52),
        arrowprops=dict(facecolor="#dc2626", shrink=0.06, width=1.2, headwidth=6),
        fontsize=8.2, fontweight="bold", bbox=dict(boxstyle="round,pad=0.35", fc="#f0fdf4", ec="#16a34a", lw=1.1),
    )
    ax2.set_xlabel("Domain Coverage Fraction (%)", fontsize=10, fontweight="bold")
    ax2.set_ylabel("False Positive Area Reduction (%)", fontsize=10, fontweight="bold")
    ax2.set_title("(b) Empirical False Positive Suppression vs Coverage", fontsize=10.5, fontweight="bold")
    ax2.grid(True, linestyle="--", alpha=0.5)
    ax2.legend(loc="upper right", fontsize=8.2)

    plt.tight_layout()
    save_all(fig, "figure_5_risk_coverage_curves.png")
    save_all(fig, "figure_4_risk_coverage_curves.png")
    plt.close(fig)
    print("Generated Figure 5: figure_5_risk_coverage_curves.png")


def generate_figure_6() -> None:
    """Dynamically plot Table 5 Temporal Generalization & Table 4 Panel C LOCO Ablation from JSON."""
    summary_json = json.loads((RESULTS_DIR / "held_out_evaluation_summary.json").read_text(encoding="utf-8"))
    ablation_json = json.loads((RESULTS_DIR / "ablation_results.json").read_text(encoding="utf-8"))["configurations"]

    t5 = summary_json["table_5_temporal_generalization"]
    mod = t5["modern_era_2020_2022"]
    hist = t5["historical_era_2018_2019"]
    macro_base = summary_json["macro_metrics"]["full_domain_macro_pr_auc"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.2, 5.4), dpi=300)

    eras = ["Modern Era (2020–2022)\n(N = 5 Held-Out Events)", "Historical Era (2018–2019)\n(N = 3 Held-Out Events)"]
    full_domain = [mod["full_pr_auc"], hist["full_pr_auc"]]
    resolvable = [mod["res_pr_auc"], hist["res_pr_auc"]]
    full_pool_prev = [mod["full_pool_prev"], hist["full_pool_prev"]]
    sr_mac_full = [mod["full_macro_sr"], hist["full_macro_sr"]]
    sr_mac_res = [mod["res_macro_sr"], hist["res_macro_sr"]]
    sr_pool_full = [mod["full_pool_sr"], hist["full_pool_sr"]]
    sr_pool_res = [mod["res_pool_sr"], hist["res_pool_sr"]]

    x = np.arange(len(eras))
    width = 0.30
    ax1.bar(x - width / 2, full_domain, width, label="Full Domain (Unconstrained)", color="#94a3b8", edgecolor="black", lw=1.1)
    ax1.bar(x + width / 2, resolvable, width, label="Resolvable Domain ($O \\geq 0.50$)", color="#2563eb", edgecolor="black", lw=1.1)

    ax1.set_ylabel("Macro PR-AUC", fontsize=10, fontweight="bold")
    ax1.set_title("(a) Primary Independent Temporal Generalization (Table 5)", fontsize=10.5, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(eras, fontsize=9.0, fontweight="bold")
    ax1.set_ylim(0, 0.168)
    ax1.grid(True, linestyle="--", alpha=0.4, axis="y")

    for idx, p_base in enumerate(full_pool_prev):
        ax1.plot([x[idx] - width * 1.1, x[idx] - width * 0.1], [p_base, p_base], color="#dc2626", linestyle=":", lw=1.4)
        ax1.text(x[idx] - width * 0.6, p_base + 0.002, f"$\\pi_{{pool}}={p_base*100:.2f}\\%$", color="#b91c1c", fontsize=7.2, ha="center", fontweight="bold")

        ax1.text(
            x[idx] - width / 2, full_domain[idx] + 0.0025,
            f"{full_domain[idx]:.4f}\n$SR_m$={sr_mac_full[idx]:.2f}x\n$SR_p$={sr_pool_full[idx]:.2f}x",
            ha="center", va="bottom", fontsize=7.2,
        )
        gain = ((resolvable[idx] - full_domain[idx]) / full_domain[idx]) * 100.0
        ax1.text(
            x[idx] + width / 2, resolvable[idx] + 0.0025,
            f"{resolvable[idx]:.4f} (+{gain:.1f}%)\n$SR_m$={sr_mac_res[idx]:.2f}x\n$SR_p$={sr_pool_res[idx]:.2f}x",
            ha="center", va="bottom", fontsize=7.2, fontweight="bold", color="#1d4ed8",
        )

    ax1.legend(loc="upper left", fontsize=8.5)

    loco_order = [
        ("O_random", "Random\nRetention"),
        ("O_no_slope", "Ablate Slope\n($O_{\\mathrm{no-slope}}$)"),
        ("O_no_geom", "Ablate Geom.\n($O_{\\mathrm{no-geom}}$)"),
        ("O_no_validity", "Ablate Valid.\n($O_{\\mathrm{no-validity}}$)"),
        ("O_no_water", "Ablate Water\n($O_{\\mathrm{no-water}}$)"),
        ("O_no_scale", "Ablate Scale\n($O_{\\mathrm{no-scale}}$)"),
        ("O_full", "Full Engine\n($O_{\\mathrm{full}} \\geq 0.50$)"),
    ]
    modes = [label for _, label in loco_order]
    scores = [ablation_json[key]["macro_pr_auc"] for key, _ in loco_order]
    bar_cols = ["#94a3b8", "#7dd3fc", "#38bdf8", "#0ea5e9", "#0284c7", "#0369a1", "#1e3a8a"]

    bars = ax2.bar(range(len(modes)), scores, color=bar_cols, width=0.58, edgecolor="black", linewidth=1.1)
    ax2.axhline(macro_base, color="#dc2626", linestyle="--", lw=1.3, label=f"Unconstrained Candidate Baseline ({macro_base:.4f})")
    ax2.set_ylabel("Macro PR-AUC at Matched Coverage (44.14%)", fontsize=9.5, fontweight="bold")
    ax2.set_title("(b) LOCO Observability Ablation at 44.14% Coverage (Table 4 Panel C)", fontsize=9.8, fontweight="bold")
    ax2.set_xticks(range(len(modes)))
    ax2.set_xticklabels(modes, rotation=28, ha="right", fontsize=8.0)
    ax2.set_ylim(0, 0.112)
    ax2.grid(True, linestyle="--", alpha=0.4, axis="y")
    ax2.legend(loc="upper left", fontsize=8.0)

    for bar in bars:
        yval = bar.get_height()
        delta = yval - macro_base
        sign = "+" if delta >= 0 else ""
        ax2.text(
            bar.get_x() + bar.get_width() / 2.0, yval + 0.0015,
            f"{yval:.4f}\n({sign}{delta:.4f})", ha="center", va="bottom", fontsize=7.5, fontweight="bold",
        )

    plt.tight_layout()
    save_all(fig, "figure_6_temporal_shift_and_ablation.png")
    plt.close(fig)
    print("Generated Figure 6: figure_6_temporal_shift_and_ablation.png")


if __name__ == "__main__":
    generate_spatial_figures()
    generate_figure_4()
    generate_figure_5()
    generate_figure_6()
