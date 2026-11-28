# Earth One: Master Reproduction Guide

This guide provides end-to-end instructions for reproducing all results, tables, benchmarks, and regression suites reported in the Earth One publications (*Pure and Applied Geophysics*).

---

## 1. Environment Setup

```bash
git clone https://github.com/shubham-exe-web/earth-one.git
cd earth-one

python -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## 2. Automated Regression Test Suite (10 / 10 Passing)

To verify complete repository and scientific integrity:

```bash
python -m pytest tests/test_physics_gates.py tests/test_abstention.py tests/test_raster_confusion_matrix.py
```
Expected output:
```text
tests/test_physics_gates.py .....          [ 50%]
tests/test_abstention.py ...               [ 80%]
tests/test_raster_confusion_matrix.py ..   [100%]
============================== 10 passed in ~2.1s ===============================
```

---

## 3. Flood Module Benchmark Execution & Table Reproduction

All experimental benchmarks and tables can be reproduced directly from the frozen benchmark tensors in `data/flood_benchmark_rasters/` and bundled CEMS vectors in `data/cems_reference_vectors/`:

```bash
# 1. Extract real Planetary Computer STAC EO stacks (local UTM 10.0 m Sentinel-1 RTC, COP-30 DEM, JRC GSW, bundled CEMS polygons)
python scripts/extract_real_eo_validation_stacks.py

# 2. Evaluate Table 4A auxiliary real-EO baselines (Otsu, Change Detection, Mode A, Mode B) on local UTM 10 m stacks
python scripts/evaluate_panel_a_baselines.py
python -m earth_one.flood_ablation

# 3. Evaluate Held-Out Multi-Regime Validation (Tables 2a, 2b, 4B, 4C, 5)
# Dynamically loads 2D benchmark raster tensors and derives macro & concatenated pooled PR-AUC and dual skill ratios
python scripts/evaluate_held_out_validation.py

# 4. Leave-One-Observability-Component-Out (LOCO) Ablation (Table 4C)
# Evaluates 5 component ablations and random retention control under matched coverage (44.14%)
python scripts/run_loco_ablation.py

# 5. Complete 8-Event Statistical Reliability Audit, Empirical UTM Semivariogram, Correlation & Bootstrap (Tables 3, S4)
# Computes 8-event (2,097,152 px, 512 blocks) pooled reliability audit, empirical semivariogram range, and 95% bootstrap CIs
python scripts/run_statistical_tests.py

# 6. Regenerate Publication Figures 3, 4, 5, 6 and Supplementary Figures S2, S3
python scripts/generate_reconciled_figures.py
```

---

## 4. Cohort Partitioning & Experimental Architecture

The evaluation architecture is strictly partitioned into:
- **Development Cohort ($N = 3$ activations; reference only):**
  - EMSR439 (Bangladesh, Cyclone Amphan)
  - EMSR629 (Pakistan, Indus Mega-Flood)
  - EMSR548 (Italy, Catania Pluvial Flood)
- **Held-Out Validation Pool ($N = 8$ activations; zero-shot evaluated):**
  - EMSR348 (Mozambique, Cyclone Idai)
  - EMSR468 (Italy, Tanaro Alpine Flood)
  - EMSR517 (Germany, Ahr Valley Flash Flood)
  - EMSR464 (Vietnam, Ha Tinh Monsoon Flood)
  - EMSR357 (India, Mahanadi Delta Flood)
  - EMSR445 (Ukraine, Prut River Flood)
  - EMSR567 (Australia, Mary River Flood)
  - EMSR286 (Colombia, Cauca River Flood)

### Summary Metrics across 8 Held-Out Activations ($2,097,152$ pixels):
- **Full-Domain PR-AUC:** Macro $= 0.06973$ | Pooled $= 0.05085$ | Class Prevalence $= 4.43\%$
  - Dual Skill Ratios: **Macro Event SR $= 2.59\times$** | **Pooled SR $= 1.15\times$**
- **Resolvable Domain PR-AUC ($O \ge 0.50$, $44.14\%$ operating coverage):** Macro $= 0.09016$ ($\bar{\pi}_{\text{res}} = 13.72\%$) | Pooled $= 0.05618$ ($\pi_{\text{pool, res}} = 5.79\%$)
  - Dual Skill Ratios: **Macro Event SR $= 1.97\times$** | **Pooled SR $= 0.97\times$**
  - Relative PR-AUC Gain: **$+29.3\%$** (macro) / **$+10.5\%$** (pooled)
- **False Alarm Footprint Reduction:** **$-35.8\%$** ($162,000 \rightarrow 104,016$ false-positive pixels).
