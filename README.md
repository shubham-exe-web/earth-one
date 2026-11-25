# Earth One (v2.1.0) — Autonomous Multimodal Environmental Disturbance Monitoring Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22065695.svg)](https://doi.org/zenodo.22065695)
[![Tests: 119/119 Passed](https://img.shields.io/badge/Tests-119%2F119%20Passing-brightgreen.svg)](tests/)

Earth One is a unified, autonomous, multimodal Earth-observation disturbance monitoring engine designed for zero-touch detection, biophysical regime routing, spatial observability decomposition, multi-epoch event tracking, and blackout-safe alerting across global ecosystems.

The repository integrates five core planetary disturbance monitoring modules:
- **Wildfire Module 1**: Active fire thermal anomaly detection (VIIRS/MODIS), biomass consumption, and perimeter tracking.
- **Flood Module 2**: Gated physics multimodal evidence fusion (SAR specular + Optical MNDWI) across 11 global activations.
- **Drought Module 3**: Multi-satellite hydroclimate stress and vegetative drought monitoring.
- **Forest Disturbance Module 4 (Paper 4.1)**: Autonomous multimodal forest disturbance and deforestation intelligence, decoupled systems verification (Layer A) vs. operational concordance (Layer B), and a complete 2023 planetary computational assessment.
- **Land Degradation Module 5 (Paper 5.1)**: Autonomous multimodal architecture for terrestrial degradation detection, persistence assessment, and reference-governed benchmarking across 10 canonical global biomes (3,240 ha) spanning six continents.

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   Earth One Platform Overview                                    │
│                                                                                                  │
│ 1. Upstream Constellation Harvesters:                                                            │
│    • Dynamic Sentinel-1 (C-band SAR GRD) & Sentinel-2 (MSI L2A BOA) discovery via STAC.         │
│    • JRC Global Surface Water (GSW v1.3), Copernicus DEM GLO-30 & GPM IMERG / ERA5-Land.         │
│                                                                                                  │
│ 2. Penta-Hazard Disturbance Architecture:                                                        │
│    • Wildfire Module 1: Biomass & burned-area estimation with operational tracking.              │
│    • Flood Module 2: Gated physics multi-modal evidence fusion (SAR specular + Optical MNDWI).   │
│    • Drought Module 3: Multi-sensor hydroclimatic anomaly and vegetative drought tracking.        │
│    • Forest Module 4: Multimodal canopy loss, degradation, radar cloud dividend, & carbon ledger.│
│    • Land Degradation Module 5: RESTREND climate decoupling, SMA unmixing, RVI, & SOC accounting.│
│                                                                                                  │
│ 3. Biophysical Regime Routing & Observability Index:                                             │
│    • Autonomous classifier routing across biophysical biomes and ecozones.                      │
│    • Continuous Observability Index O resolving observational validity vs true absence.          │
│    • Resolution-Aware Tri-State Contracts: EVENT (O ≥ O_gate), NO_EVENT, UNRESOLVED.             │
│                                                                                                  │
│ 4. Operational Telemetry & Alert State Machine:                                                  │
│    • Multi-epoch tracking with 0.0% duplicate alert rate and temporal persistence confirmation. │
│    • Guaranteed blackout safety: Sensor outages hold state; NEVER emits false "ALL-CLEAR".       │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Quickstart & Verification

```bash
# Clone the repository
git clone https://github.com/shubham-exe-web/earth-one.git
cd earth-one

# Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run full test suite
pytest -q
```

---

## 3. Directory Layout

```text
earth-one/
├── audit/                     # Publication audit ledgers & reproducibility verification tables
├── dist/zenodo/               # Zenodo-ready packages (Earth_One_Land_v1.0.0.zip, Earth_One_Forest_v1.0.0.zip, etc.)
├── docs/                      # Technical architecture, specifications, and paper manuscripts
│   ├── PAPER_5_1_MANUSCRIPT.md              # Land Degradation Paper 5.1 scientific manuscript
│   ├── PAPER_5_1_SUPPLEMENTARY_INFORMATION.md # Land Paper 5.1 extended mathematical derivations
│   ├── LAND_DEGRADATION_SPECIFICATION_v1.0.md # Land degradation architectural specification
│   ├── LAND_DEGRADATION_REPRODUCTION.md     # Step-by-step reproduction guide for Paper 5.1
│   ├── LAND_DEGRADATION_DATA_SOURCES.md     # Upstream satellite & reference data provenance
│   ├── PAPER_4_1_MANUSCRIPT.md              # Forest Paper 4.1 complete scientific manuscript
│   ├── FOREST_DISTURBANCE_SPECIFICATION_v1.0.md # Forest architectural & mathematical spec
│   ├── FOREST_REPRODUCTION.md               # Step-by-step reproduction guide for Paper 4.1
│   ├── FOREST_DATA_SOURCES.md               # Upstream satellite & reference data provenance
│   ├── FLOOD_MODULE_v1.0.md                 # Flood mathematical formulations & architecture
│   ├── FLOOD_REPRODUCTION.md                # Detailed reproduction instructions for Flood
│   └── FLOOD_VALIDATION.md                  # Master validation ledger across 11 flood activations
├── src/earth_one/             # Core Python source modules
│   ├── land_degradation/      # Module 5: Autonomous Land Degradation engine (24 modules)
│   ├── forest/                # Module 4: Autonomous Forest Disturbance engine (24 modules)
│   ├── flood.py               # Module 2: Multimodal flood segmentation & routing
└── tests/                     # Automated regression test suites
    ├── test_land_degradation.py           # Module 5 core algorithmic tests (14 tests)
    ├── test_land_degradation_real_eval.py # Module 5 benchmarks & governance tests (7 tests)
    └── forest/                            # Module 4 test suites (54 tests)
```

For benchmark reproduction instructions:
- **Land Degradation Module 5**: See [`docs/LAND_DEGRADATION_REPRODUCTION.md`](docs/LAND_DEGRADATION_REPRODUCTION.md)
- **Forest Module 4**: See [`docs/FOREST_REPRODUCTION.md`](docs/FOREST_REPRODUCTION.md)
- **Flood Module 2**: See [`docs/FLOOD_REPRODUCTION.md`](docs/FLOOD_REPRODUCTION.md) or [`REPRODUCE.md`](REPRODUCE.md)

---

## 4. Citation

If you use Earth One in your research or operational workflows, please cite the corresponding module:

### Land Degradation (Module 5, Paper 5.1)
```bibtex
@article{sharma2026earthoneland,
  title={Autonomous Multimodal Satellite Remote Sensing of Global Land Degradation: Climate-Decoupled RESTREND Tracking, Observability Gating, and Three-Tier Reference Governance},
  author={Sharma, Shubham and Earth One Collaboration},
  journal={Earth One Technical Reports},
  volume={5},
  number={1},
  pages={1--42},
  year={2026}
}
```

### Forest Disturbance (Module 4, Paper 4.1)
```bibtex
@article{sharma2026earthoneforest,
  title={Autonomous Multimodal Satellite Remote Sensing of Global Forest Disturbance: Physics-Guided Radar-Optical Fusion, Structural Degradation Tracking, and Planetary Carbon Accounting},
  author={Sharma, Shubham and Earth One Collaboration},
  journal={Earth One Technical Reports},
  volume={4},
  number={1},
  pages={1--48},
  year={2026}
}
```

### Flood Inundation (Module 2)
```bibtex
@software{earth_one_flood_2026,
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
