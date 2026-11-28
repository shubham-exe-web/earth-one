# Earth One Flood Module: Reproduction & Benchmark Execution Guide

This guide details how to reproduce all experimental benchmarks, validation ledgers, ablation studies, and operational replays for the Earth One Flood Monitoring Framework reported in *Pure and Applied Geophysics*.

## 1. Quick Reproduction

To run the automated regression suite and print all reconciled held-out validation tables:

```bash
# Clone the repository
git clone https://github.com/shubham-exe-web/earth-one.git
cd earth-one

# Install dependencies
pip install -e .

# Run physics gate, observability, and raster mask unit tests
python -m pytest tests/test_physics_gates.py tests/test_abstention.py tests/test_raster_confusion_matrix.py

# Run physical EO STAC stack extraction (local UTM 10.0 m Sentinel-1 RTC, COP-30 DEM, JRC GSW, bundled CEMS polygons)
python scripts/extract_real_eo_validation_stacks.py

# Run executable Table 4A unconstrained baselines (Otsu, Change Detection, Mode A, Mode B) on local UTM 10 m real EO stacks
python scripts/evaluate_panel_a_baselines.py

# Also see EMSR439 multi-mode ablation benchmark:
python -m earth_one.flood_ablation

# Run development threshold calibration (discrete 2D grid sweep)
python scripts/calibrate_development_thresholds.py

# Run matched-coverage leave-one-component-out (LOCO) ablation (Table 4C)
python scripts/run_loco_ablation.py

# Run complete 8-event (2,097,152 px) 5-bin reliability audit, deterministic isotonic calibration (seed=42), UTM semivariogram, and bootstrap tests
python scripts/run_statistical_tests.py

# Run direct raster mask tensor evaluation
python scripts/evaluate_raster_masks.py

# Evaluate the 8 held-out validation events and reproduce Tables 2a, 2b, 4B, 4C, and 5
python scripts/evaluate_held_out_validation.py

# Regenerate Figures 3, 4, 5, 6 and Supplementary Figures S2 and S3 directly from real EO stacks & dynamic JSON ledgers
python scripts/generate_reconciled_figures.py
```

Expected test output:
```text
tests/test_physics_gates.py .....          [ 50%]
tests/test_abstention.py ...               [ 80%]
tests/test_raster_confusion_matrix.py ..   [100%]
============================== 10 passed in ~2.1s ===============================
```

---

## 2. Experimental Cohort Structure

The evaluation architecture is strictly partitioned into:

### Development Cohort ($N = 3$)
Used exclusively for initial heuristic parameter bounds, threshold sensitivity, and diagnostic baseline verification:
1. **EMSR439** (Bhasan Char, Meghna Estuary, Bangladesh, May 2020) — Coastal Estuary / Tidal
2. **EMSR629** (Sindh Indus Basin, Pakistan, August 2022) — Inland Riverine Mega
3. **EMSR548** (Catania Plain, Sicily, Italy, October 2021) — Inland Riverine Pluvial

### Held-Out Validation Pool ($N = 8$)
Evaluated zero-shot without parameter tuning or threshold adjustments:
1. **EMSR348** (Quelimane, Mozambique, March 2019) — Coastal Estuary
2. **EMSR468** (Tanaro Valley, Piedmont, Italy, October 2020) — Alpine Pluvial
3. **EMSR517** (Rheinland-Pfalz, Germany, July 2021) — Fluvial Basin
4. **EMSR464** (Ha Tinh, Vietnam, October 2020) — Monsoon Pluvial
5. **EMSR357** (Mahanadi Delta, Odisha, India, May 2019) — Coastal Delta
6. **EMSR445** (Prut River, Chernivtsi, Ukraine, June 2020) — Fluvial Valley
7. **EMSR567** (Gympie Mary River, Queensland, Australia, February 2022) — Fluvial Basin
8. **EMSR286** (Ituango Cauca River, Colombia, May 2018) — Mountain Valley

---

## 3. Results Manifests & Output Data Paths

All frozen benchmark results reported in the manuscript are archived under `results/flood_v1.0/`:
- `results/flood_v1.0/frozen_cohort_manifest.json`: Master metadata and satellite scene IDs.
- `results/flood_v1.0/spatial_generalization_results.json`: Spatial zero-shot evaluations across EMSR348, EMSR468, EMSR517, EMSR464.
- `results/flood_v1.0/observability_validation.json`: Independent validation metrics for EMSR357, EMSR445, EMSR567.
- `results/flood_v1.0/temporal_generalization_results.json`: Chronological evaluation across modern ($2020\text{--}2022$) and historical ($2018\text{--}2019$) holdouts.
- `results/flood_v1.0/observability_calibration.json`: Reliability audit across all $2,097,152$ held-out pixels (all 8 test events, 512 blocks) across 5 observability bins plus UTM $10.0\text{ m}$ empirical semivariograms.
- `results/flood_v1.0/ablation_results.json`: Component ablation data across evidence channels and quality gates.

Executing `python scripts/evaluate_held_out_validation.py` parses these ledgers and displays the full-domain operational tri-state confusion matrix, resolvable domain decomposition ($O \ge 0.50$), risk-coverage operating point ($44.14\%$ coverage), and temporal generalization benchmark.
