# Earth One Flood Module 2: Aggregated Research Outputs (v1.0 Frozen Release)

This directory contains the machine-readable, lightweight aggregated validation ledgers, ablation studies, generalization benchmarks, and provenance manifests for Earth One Flood Module 2.

## Manifest Inventory

| File | Description | Cohort Size / Metrics |
|---|---|---|
| `flood_engine_frozen_v1.0_manifest.json` | Master frozen release manifest & architecture specification | Engine Version: `v1.0.0-frozen-publication` |
| `ablation_results.json` | 6-mode controlled evidence fusion ablation study | Modes A–F on EMSR439 (Bangladesh) |
| `multievent_results.json` | 3-event initial multi-regime cross-continent benchmark | Pakistan Indus, Italy Catania, Bangladesh Sandwip |
| `spatial_generalization_results.json` | 7-event large multi-continent spatial holdout benchmark | Asia, Europe, Africa (Development vs Unseen) |
| `temporal_generalization_results.json` | Multi-season interannual temporal domain shift benchmark | 2020–2022 Dev Era vs 2018–2019 Unseen Era |
| `observability_audit.json` | Physical & sensor failure-mechanism decomposition | Sub-pixel widths, relief, slope, SAR layover |
| `observability_validation.json` | Zero-shot independent validation of Observability Index $O$ | Australia Gympie, India Mahanadi, Ukraine Prut |
| `observability_calibration.json` | Empirical calibration & spatial-block bootstrap ($B=1000$) | 1.31M pixels, 5 bins, Pearson $r=0.9193$ |
| `operational_replay_results.json` | Multi-epoch autonomous historical replay & tracking | Pakistan Indus Disaster (Aug 27, Sep 8, Sep 15, 2022) |
| `alert_reliability_results.json` | 6-state alert state machine & idempotency benchmark | 0.0% duplicate rate, 100% blackout safety |
| `fault_injection_results.json` | 7-mode satellite & pipeline fault-tolerance audit | 7 / 7 safe non-crashing failure modes |
| `frozen_cohort_manifest.json` | Cryptographically signed cohort inclusion specifications | SHA-256 Provenance Digests |

All results correspond to the frozen repository state passing **119 / 119 automated regression tests**.
