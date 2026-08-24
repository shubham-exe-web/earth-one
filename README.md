# Earth One (v2.0.0) — Autonomous Multimodal Environmental Disturbance Monitoring Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22065695.svg)](https://doi.org/10.5281/zenodo.22065695)
[![Tests: 119/119 Passed](https://img.shields.io/badge/Tests-119%2F119%20Passing-brightgreen.svg)](tests/)

Earth One is a unified, autonomous, multimodal Earth-observation disturbance monitoring engine designed for zero-touch detection, biophysical regime routing, spatial observability decomposition, multi-epoch event tracking, and blackout-safe alerting across global ecosystems.

The **v2.0.0 Frozen Release** integrates **Wildfire Module 1** (Experiments 1–3) and **Flood Module 2** (Blocks 1–6F), validated across 11 global flood activations spanning 5 continents.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             EARTH ONE UNIFIED SYSTEM CAPABILITIES                                │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 1. Autonomous Multimodal Ingestion:                                                              │
│    • Dynamic Sentinel-1 (C-band SAR GRD) & Sentinel-2 (MSI L2A BOA) discovery via STAC.         │
│    • JRC Global Surface Water (GSW v1.3), Copernicus DEM GLO-30 & GPM IMERG / ERA5-Land.         │
│                                                                                                  │
│ 2. Dual-Hazard Disturbance Modules:                                                              │
│    • Wildfire Module 1: Biomass & burned-area estimation with operational tracking (Exps 1–3).  │
│    • Flood Module 2: Gated physics multi-modal evidence fusion (SAR specular + Optical MNDWI).   │
│                                                                                                  │
│ 3. Biophysical Regime Routing & Observability Index:                                             │
│    • Autonomous classifier routing Alluvial Mega-River, Pluvial Gorge, and Coastal Estuaries.    │
│    • Continuous Observability Index O = S_scale · W_water · G_geom · T_terrain · D_validity.     │
│    • Resolution-Aware Tri-State Contract: FLOOD (O ≥ 0.50), NO_FLOOD (O ≥ 0.50), UNRESOLVED.    │
│                                                                                                  │
│ 4. Operational Telemetry & Alert State Machine:                                                  │
│    • Multi-epoch tracking with 0.0% duplicate alert rate.                                       │
│    • Guaranteed blackout safety: Sensor outages hold state; NEVER emits false "ALL-CLEAR".       │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Quick Start & Installation

```bash
# Clone the repository
git clone https://github.com/shubham-exe-web/earth-one.git
cd earth-one

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Run full automated regression suite (119 tests)
pytest -q
```

---

## 2. Key Empirical Findings (Flood Module 2)

| Dimension | Key Measured Metric | Scientific Takeaway |
|---|---|---|
| **Alluvial Mega-River Floods** | **PR-AUC: 0.8337, F1: 80.1%, Precision: 73.8%** | High observability ($O \ge 0.80$) produces exceptional detection fidelity in alluvial sheet flooding (Pakistan Indus). |
| **Multi-Continent Spatial Holdouts** | **+25.8% Relative PR-AUC Gain on Resolvable Domain** | Restricting evaluation to $O \ge 0.50$ systematically boosts PR-AUC ($0.0896 \rightarrow 0.1127$) across 7 global holdout events. |
| **Interannual Temporal Shift** | **$\Delta_{\text{temporal, resolvable}} = -0.00312$** | Zero interannual performance degradation between 2020–2022 and 2018–2019 pre-development seasons. |
| **Statistical Calibration of $O$** | **Pearson $r = 0.9193$, Spearman $\rho = 0.8000$** | Observability Index $O$ linearly and monotonically predicts empirical detector precision ($B=1000$ bootstrap). |
| **Operational Alerting Reliability** | **0.0% Duplicate Rate, 100% Blackout Safety** | Hysteresis suppression prevents alert spam; sensor loss safely holds state without false clearance. |

---

## 3. Repository & Documentation Structure

```text
earth-one/
├── configs/flood/frozen_v1.0/  # Frozen threshold, regime, and observability parameter files
├── data/results/              # Raw experimental cache & provenance manifests
├── docs/                      # Comprehensive technical architecture & validation docs
│   ├── FLOOD_MODULE_v1.0.md   # Mathematical formulations & component architectures
│   ├── FLOOD_REPRODUCTION.md  # Detailed reproduction instructions for all benchmarks
│   ├── FLOOD_DATA_SOURCES.md  # Satellite constellations, DEM, and ground-truth specs
│   └── FLOOD_VALIDATION.md    # Master validation ledger across 11 global activations
├── results/flood_v1.0/        # Lightweight, review-friendly aggregated JSON results
├── src/earth_one/             # Core Python source modules
└── tests/                     # 119 automated unit & regression tests
```

For detailed benchmark reproduction instructions, see [`docs/FLOOD_REPRODUCTION.md`](docs/FLOOD_REPRODUCTION.md) or [`REPRODUCE.md`](REPRODUCE.md).

---

## 4. Citation

If you use Earth One in your research or operational workflows, please cite:

```bibtex
@software{earth_one_2026,
  author = {Sharma, Shubham},
  title = {Earth One: Autonomous Multimodal Environmental Disturbance Monitoring & Flood Module 2},
  version = {2.0.0},
  year = {2026},
  doi = {10.5281/zenodo.22065695},
  url = {https://github.com/shubham-exe-web/earth-one}
}
```

---

## 5. License

This project is licensed under the Apache 2.0 License. See the [LICENSE](LICENSE) file for details.
