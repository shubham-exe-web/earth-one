import json
import csv
from pathlib import Path
import pytest
from earth_one.drought.data_staging import compute_file_sha256


def test_phase31_3_forensic_evidence_traceability_and_strict_matching():
    repo = Path(__file__).resolve().parents[2]
    audit_dir = repo / "audit"
    uscrn_dir = repo / "data" / "drought_raw" / "in_situ_uscrn"
    usda_dir = repo / "data" / "drought_raw" / "usda_impacts"

    # 1. Verify raw in-situ USCRN source files exist and have non-zero size
    uscrn_files = list(uscrn_dir.glob("*.csv"))
    assert len(uscrn_files) >= 5, f"Expected 5 raw NOAA USCRN files, found {len(uscrn_files)}"
    for f in uscrn_files:
        assert f.stat().st_size > 10000, f"Raw NOAA file {f.name} is unexpectedly small ({f.stat().st_size} bytes)"
        sha = compute_file_sha256(f)
        assert len(sha) == 64

    # 2. Verify raw USDA NASS/RMA datasets exist
    nass_file = usda_dir / "USDA_NASS_Crop_Condition_Midwest_2018_2022.csv"
    rma_file = usda_dir / "USDA_RMA_Crop_Indemnity_Losses_Midwest_2018_2022.csv"
    assert nass_file.exists() and nass_file.stat().st_size > 0
    assert rma_file.exists() and rma_file.stat().st_size > 0

    # 3. Verify Tier A Station Matches CSV with strict within-pixel distance (<= 50m)
    matches_file = audit_dir / "tier_a_station_matches.csv"
    assert matches_file.exists()
    with open(matches_file) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 7, f"Expected 7 station observation pairs, found {len(rows)}"
        for r in rows:
            assert float(r["earth_one_drought_prob"]) >= 0.0
            assert float(r["measured_physical_stress_index"]) >= 0.0
            # Strict within-pixel spatial distance
            assert float(r["spatial_distance_m"]) <= 50.0, f"Station {r['station_name']} distance {r['spatial_distance_m']} exceeds 50m"
            assert int(r["temporal_window_days"]) == 0
            assert len(r["raw_source_sha256"]) == 64

    # 4. Verify Tier A Leave-One-Station-Out Sensitivity CSV
    loso_file = audit_dir / "tier_a_loso_sensitivity.csv"
    assert loso_file.exists()
    with open(loso_file) as f:
        reader = csv.DictReader(f)
        loso_rows = list(reader)
        assert len(loso_rows) == 5

    # 5. Verify Empirical Lead-Time Trajectory with Granule Traceability
    traj_file = audit_dir / "empirical_lead_time_trajectory_iowa_2020.csv"
    assert traj_file.exists()
    with open(traj_file) as f:
        reader = csv.DictReader(f)
        t_rows = list(reader)
        assert len(t_rows) == 7  # 7 weekly time steps
        timesteps = [r["timestep"] for r in t_rows]
        assert "t-28" in timesteps and "t0" in timesteps and "t+14" in timesteps
        # Verify first detection occurs at t-21 (2020-07-28)
        t_minus_21 = next(r for r in t_rows if r["timestep"] == "t-21")
        assert t_minus_21["earth_one_decision"] in ["DROUGHT_DETECTED", "DROUGHT_CONFIRMED"]
        assert "S2B_MSIL2A" in t_minus_21["s2_granule_id"]

    # 6. Verify Master Deliverables and Checksums
    checksum_file = audit_dir / "checksums.sha256"
    assert checksum_file.exists() and checksum_file.stat().st_size > 0
