import json
import csv
from pathlib import Path
import pytest


def test_phase31_audit_pack_completeness_and_3tier_hierarchy():
    repo = Path(__file__).resolve().parents[2]
    audit_dir = repo / "audit"
    
    required_files = [
        "data_provenance.csv",
        "temporal_leakage_audit.json",
        "spatial_leakage_audit.json",
        "resolution_support_audit.json",
        "confusion_matrix.csv",
        "usdm_independent_reproduction.json",
        "ablation_reproduction.csv",
        "observability_distribution.csv",
        "failure_cases.csv",
        "parameter_manifest.json",
        "parameter_sensitivity_sweep.json",
        "observability_stress_experiment.json",
        "geographic_generalization_master.csv",
        "master_results_synthesis_table.csv",
        "tier_a_in_situ_physical_validation.json",
        "tier_c_agricultural_impact_corroboration.json",
        "master_3tier_validation_hierarchy.csv",
        "multi_event_severity_benchmark.csv",
        "audit_report.md",
        "checksums.sha256",
    ]
    
    for fname in required_files:
        assert (audit_dir / fname).exists(), f"Missing audit deliverable: {fname}"
        assert (audit_dir / fname).stat().st_size > 0, f"Empty audit deliverable: {fname}"

    # Verify Tier A in-situ physics
    with open(audit_dir / "tier_a_in_situ_physical_validation.json") as f:
        t_a = json.load(f)
        assert t_a["pearson_r"] > 0.95
        assert t_a["rmse"] < 0.10

    # Verify Multi-Event Severity Benchmark
    with open(audit_dir / "multi_event_severity_benchmark.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 3
        # Emerging stress event must have 14 days lead time
        emerging = next(r for r in rows if r["Severity_Regime"] == "EMERGING_STRESS")
        assert int(emerging["Multimodal_Lead_Days"]) == 14
        assert emerging["Multimodal_Detected"] == "True"
