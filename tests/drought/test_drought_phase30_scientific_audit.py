import json
import csv
from pathlib import Path
import pytest


def test_phase30_1_audit_pack_completeness_and_generalization():
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
        "spatial_holdout_illinois.json",
        "temporal_holdout_iowa_2020.json",
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

    # Verify spatial holdout results
    with open(audit_dir / "spatial_holdout_illinois.json") as f:
        sp_audit = json.load(f)
        assert sp_audit["usdm_f1_score"] > 0.95
        assert 2022 not in sp_audit["baseline_years"]

    # Verify temporal holdout results
    with open(audit_dir / "temporal_holdout_iowa_2020.json") as f:
        tp_audit = json.load(f)
        assert tp_audit["target_year"] == 2020
        assert 2020 not in tp_audit["baseline_years"]

    # Verify confusion matrix consistency
    with open(audit_dir / "confusion_matrix.csv") as f:
        reader = csv.DictReader(f)
        rows = {r["Metric"]: r["Value"] for r in reader}
        assert int(rows["True_Positives_TP"]) == 9539
        assert int(rows["False_Positives_FP"]) == 0
        assert int(rows["False_Negatives_FN"]) == 7
        assert float(rows["Spatial_Concordance_F1"]) == pytest.approx(0.9996, abs=1e-4)
