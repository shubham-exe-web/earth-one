# Earth One Flood Module 2: Reproduction & Benchmark Execution Guide

This guide details how to reproduce all experimental benchmarks, validation ledgers, ablation studies, and operational replays for Earth One Flood Module 2.

## 1. Quick Reproduction (Full Automated Test Suite)

To run the complete repository regression and verification suite:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all 119 verification and regression tests
pytest -q
```
Expected output:
```text
119 passed in ~210s (100% green)
```

---

## 2. Executing Individual Experimental Blocks

All experiment runners are self-contained and execute against live / cached Copernicus STAC endpoints:

### Block 6A: Large Multi-Continent Spatial Generalization Benchmark ($N=7$)
```bash
python -c "from earth_one.flood_spatial_generalization import run_large_spatial_generalization_benchmark; run_large_spatial_generalization_benchmark()"
```
*Output manifest*: `data/results/flood_regime_routing/spatial_generalization_results.json`

### Block 6B: Observability & Failure-Mechanism Audit
```bash
python -c "from earth_one.flood_observability_audit import run_full_observability_audit; run_full_observability_audit()"
```
*Output manifest*: `data/results/flood_regime_routing/observability_audit_results.json`

### Block 6C: Temporal & Interannual Generalization Benchmark (2018–2022)
```bash
python -c "from earth_one.flood_temporal_generalization import run_temporal_generalization_benchmark; run_temporal_generalization_benchmark()"
```
*Output manifest*: `data/results/flood_regime_routing/temporal_generalization_results.json`

### Block 6D: Zero-Shot Independent Validation of Observability Index ($O$)
```bash
python -c "from earth_one.flood_observability_validation import run_independent_observability_validation; run_independent_observability_validation()"
```
*Output manifest*: `data/results/flood_regime_routing/observability_validation_results.json`

### Block 6E: Empirical Observability Calibration & Spatial-Block Bootstrap ($B=1000$)
```bash
python -c "from earth_one.flood_observability_calibration import run_observability_calibration_benchmark; run_observability_calibration_benchmark(n_bootstrap=1000)"
```
*Output manifest*: `data/results/flood_regime_routing/observability_calibration_results.json`

### Block 6F: Confidence Calibration, Event Uncertainty & Engine Freeze
```bash
python -c "from earth_one.flood_calibration import run_full_calibration_and_freezing_pipeline; run_full_calibration_and_freezing_pipeline()"
```
*Output manifest*: `data/results/flood_engine_frozen_v1.0_manifest.json`

### Block 5A: Multi-Epoch Autonomous Historical Replay & Tracking
```bash
python -c "from earth_one.flood_replay import run_full_historical_replay; run_full_historical_replay()"
```
*Output manifest*: `data/results/flood_replay/operational_replay_manifest.json`

### Block 5B: 7-Mode Satellite & Pipeline Fault-Injection Harness
```bash
python -c "from earth_one.flood_fault_injection import run_flood_fault_injection_suite; run_flood_fault_injection_suite()"
```
*Output manifest*: `data/results/flood_replay/fault_injection_results.json`

### Block 5C: Alert State Machine Reliability & Idempotency Benchmark
```bash
python -c "from earth_one.flood_alerts import run_alert_reliability_benchmark; run_alert_reliability_benchmark()"
```
*Output manifest*: `data/results/flood_replay/alert_reliability_results.json`

---

## 3. Reviewing Aggregated Research Outputs

Pre-computed lightweight JSON summaries for peer review are archived in [`results/flood_v1.0/`](../results/flood_v1.0/).
