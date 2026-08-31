import json
import csv
from pathlib import Path
import pytest


def test_phase30_2_audit_pack_completeness_and_generalization():
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
        "audit_report.md",
        "checksums.sha256",
    ]
    
    for fname in required_files:
        assert (audit_dir / fname).exists(), f"Missing audit deliverable: {fname}"
        assert (audit_dir / fname).stat().st_size > 0, f"Empty audit deliverable: {fname}"

    # Verify temporal holdout partition
    with open(audit_dir / "temporal_leakage_audit.json") as f:
        t_audit = json.load(f)
        assert t_audit["optical_climatology_partition"]["target_year_included_in_baseline"] is False
        assert 2022 not in t_audit["optical_climatology_partition"]["declared_baseline_years"]

    # Verify master results synthesis
    with open(audit_dir / "master_results_synthesis_table.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) >= 4
        # Verify Iowa, Illinois, Nebraska, and Iowa August 2020 all exist
        experiments = [r["Evaluation_Experiment"] for r in rows]
        assert any("Iowa Corn Belt" in exp for exp in experiments)
        assert any("Illinois Corn Belt" in exp for exp in experiments)
        assert any("Nebraska Platte" in exp for exp in experiments)
        assert any("August 2020" in exp for exp in experiments)
