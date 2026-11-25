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

## 2. Automated Regression Test Suite (9 / 9 Passing)

To verify complete repository and scientific integrity:

```bash
python -m pytest tests/test_physics_gates.py tests/test_abstention.py tests/test_raster_confusion_matrix.py
```
Expected output:
```text
tests/test_physics_gates.py .....          [ 55%]
tests/test_abstention.py ..                [ 77%]
tests/test_raster_confusion_matrix.py ..   [100%]
============================== 9 passed in ~1.9s ===============================
```

---

## 3. Flood Module Benchmark Execution & Table Reproduction

All experimental benchmarks and tables can be reproduced directly from the frozen benchmark tensors in `data/flood_benchmark_rasters/`:

```bash
# 1. Evaluate Held-Out Multi-Regime Validation (Tables 2a, 2b, 4, 5)
# Dynamically loads 2D benchmark raster tensors and derives PR-AUC and dual skill ratios
python scripts/evaluate_held_out_validation.py

# 2. Leave-One-Observability-Component-Out (LOCO) Ablation (Table 4 Panel C)
# Evaluates 5 component ablations and random retention control under matched coverage (44.14%)
python scripts/run_loco_ablation.py

# 3. Statistical Reliability Audit, Correlation & Bootstrap (Tables 3, S4)
# Computes 5-event pooled reliability audit, Kendall tau, Spearman rho, and 95% bootstrap CIs
python scripts/run_statistical_tests.py
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
- **Full-Domain PR-AUC:** Macro $= 0.06970$ | Class Prevalence $= 4.43\%$
  - Dual Skill Ratios: **Macro Event SR $= 2.59\times$** | **Pooled SR $= 1.57\times$**
- **Resolvable Domain PR-AUC ($O \ge 0.50$, $44.14\%$ operating coverage):** Macro $= 0.09016$ | Class Prevalence $= 13.72\%$
  - Dual Skill Ratios: **Macro Event SR $= 1.97\times$** | **Pooled SR $= 0.66\times$**
  - Relative PR-AUC Gain: **$+29.4\%$**
- **False Alarm Footprint Reduction:** **$-35.8\%$** ($162,000 \rightarrow 104,016$ false-positive pixels).
