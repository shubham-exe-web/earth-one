# Earth One: Master Reproduction Guide

This guide provides end-to-end instructions for reproducing all results, tables, benchmarks, and regression suites reported in the Earth One papers (Wildfire Module 1 & Flood Module 2).

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

## 2. Automated Regression Test Suite (119 / 119 Passing)

To verify complete repository and scientific integrity:

```bash
pytest -q
```
Expected output:
```text
119 passed in ~210s (100% green)
```

---

## 3. Flood Module 2 Benchmark Execution

All experimental benchmarks can be executed independently:

```bash
# 1. Multi-Continent Spatial Generalization Benchmark (N=7 events)
python -c "from earth_one.flood_spatial_generalization import run_large_spatial_generalization_benchmark; run_large_spatial_generalization_benchmark()"

# 2. Observability & Failure-Mechanism Decomposition Audit
python -c "from earth_one.flood_observability_audit import run_full_observability_audit; run_full_observability_audit()"

# 3. Interannual Temporal Generalization (2020-2022 vs 2018-2019)
python -c "from earth_one.flood_temporal_generalization import run_temporal_generalization_benchmark; run_temporal_generalization_benchmark()"

# 4. Zero-Shot Independent Validation of Observability Index (O)
python -c "from earth_one.flood_observability_validation import run_independent_observability_validation; run_independent_observability_validation()"

# 5. Empirical Calibration & Spatial-Block Bootstrap (B=1000)
python -c "from earth_one.flood_observability_calibration import run_observability_calibration_benchmark; run_observability_calibration_benchmark(n_bootstrap=1000)"

# 6. Confidence Calibration, Event Uncertainty & Engine Freeze
python -c "from earth_one.flood_calibration import run_full_calibration_and_freezing_pipeline; run_full_calibration_and_freezing_pipeline()"

# 7. Multi-Epoch Operational Replay (Pakistan Indus Flood)
python -c "from earth_one.flood_replay import run_full_historical_replay; run_full_historical_replay()"

# 8. Alert State Machine Reliability & Idempotency Audit
python -c "from earth_one.flood_alerts import run_alert_reliability_benchmark; run_alert_reliability_benchmark()"

# 9. Satellite Fault-Tolerance & Blackout Safety Audit
python -c "from earth_one.flood_fault_injection import run_flood_fault_injection_suite; run_flood_fault_injection_suite()"
```

---

## 4. Aggregated Machine-Readable Results

Reviewers can directly inspect aggregated JSON ledgers in [`results/flood_v1.0/`](results/flood_v1.0/):
- `flood_engine_frozen_v1.0_manifest.json`
- `spatial_generalization_results.json`
- `temporal_generalization_results.json`
- `observability_validation.json`
- `observability_calibration.json`
- `operational_replay_results.json`
- `alert_reliability_results.json`
- `fault_injection_results.json`
- `frozen_cohort_manifest.json`
