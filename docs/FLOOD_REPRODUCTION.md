# Earth One Flood Module: Reproduction & Benchmark Execution Guide

This guide details how to reproduce all experimental benchmarks, validation ledgers, ablation studies, and operational replays for the Earth One Flood Monitoring Framework reported in *Pure and Applied Geophysics*.

## 1. Quick Reproduction

To run the automated regression suite and print all reconciled held-out validation tables:

```bash
# Clone the repository
git clone https://github.com/shubham-exe-web/earth-one.git
cd earth-one

# Install dependencies
pip install -r requirements.txt

# Run physics gate, observability, and raster mask unit tests
python -m pytest tests/test_physics_gates.py tests/test_abstention.py tests/test_raster_confusion_matrix.py

# Run direct raster mask tensor evaluation
python scripts/evaluate_raster_masks.py

# Evaluate the 8 held-out validation events and reproduce Tables 2a, 2b, 4, and 5
python scripts/evaluate_held_out_validation.py
```

Expected test output:
```text
tests/test_physics_gates.py .....          [ 55%]
tests/test_abstention.py ..                [ 77%]
tests/test_raster_confusion_matrix.py ..   [100%]
9 passed in ~3.7s
```

---

## 2. Experimental Cohort Structure

The evaluation architecture is strictly partitioned into:

### Development Cohort ($N = 3$)
Used exclusively for initial heuristic parameter bounds, threshold sensitivity, and diagnostic baseline verification:
1. **EMSR439** (Sandwip Channel, Bangladesh, May 2020) — Coastal Estuary / Tidal
2. **EMSR629** (Sindh Indus Basin, Pakistan, September 2022) — Inland Riverine Mega
3. **EMSR548** (Catania Plain, Sicily, Italy, October 2021) — Inland Riverine Pluvial

### Held-Out Validation Pool ($N = 8$)
Evaluated zero-shot without parameter tuning or threshold adjustments:
1. **EMSR348** (Quelimane, Mozambique, March 2019) — Coastal Estuary
2. **EMSR468** (Tanaro Valley, Piedmont, Italy, October 2020) — Alpine Pluvial
3. **EMSR517** (Rheinland-Pfalz, Germany, July 2021) — Fluvial Basin
4. **EMSR464** (Ha Tinh, Vietnam, October 2020) — Monsoon Pluvial
5. **EMSR357** (Mahanadi Delta, Odisha, India, May 2019) — Coastal Delta
6. **EMSR445** (Prut River, Chernivtsi, Ukraine, July 2020) — Fluvial Valley
7. **EMSR567** (Gympie Mary River, Queensland, Australia, March 2021) — Fluvial Basin
8. **EMSR286** (Ituango Cauca River, Colombia, May 2018) — Mountain Valley

---

## 3. Results Manifests & Output Data Paths

All frozen benchmark results reported in the manuscript are archived under `results/flood_v1.0/`:
- `results/flood_v1.0/frozen_cohort_manifest.json`: Master metadata and satellite scene IDs.
- `results/flood_v1.0/spatial_generalization_results.json`: Spatial zero-shot evaluations across EMSR348, EMSR468, EMSR517, EMSR464.
- `results/flood_v1.0/observability_validation.json`: Independent validation metrics for EMSR357, EMSR445, EMSR567.
- `results/flood_v1.0/temporal_generalization_results.json`: Chronological evaluation across modern ($2020\text{--}2021$) and historical ($2018\text{--}2019$) holdouts.
- `results/flood_v1.0/observability_calibration.json`: Reliability audit across $1,310,720$ held-out pixels across 5 observability bins.
- `results/flood_v1.0/ablation_results.json`: Component ablation data across evidence channels and quality gates.

Executing `python scripts/evaluate_held_out_validation.py` parses these ledgers and displays the full-domain operational tri-state confusion matrix, resolvable domain decomposition ($O \ge 0.50$), risk-coverage operating point ($44.14\%$ coverage), and temporal generalization benchmark.
