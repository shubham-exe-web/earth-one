import pytest
from pathlib import Path
from earth_one.drought.data_manifest import ExecutionArchiveMode, ReferenceIndependenceRecord
from earth_one.drought.data_staging import stage_us_corn_belt_2022_real_data_archive
from earth_one.drought.external_acquisition import ExternalSatelliteAcquisitionSession
from earth_one.drought.us_corn_belt_activation import run_drought_activation


def test_external_satellite_acquisition_session(tmp_path):
    staging_dir = tmp_path / "stage_test"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))

    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    from earth_one.drought.external_acquisition import AssetOriginType
    # Register staged files into external session
    for key, f_meta in staged["files"].items():
        session.register_and_verify_downloaded_asset(
            product_name=key,
            asset_key=key,
            asset_origin=AssetOriginType.EXTERNAL_DOWNLOAD,
            remote_source_url=f"https://planetarycomputer.microsoft.com/api/stac/v1/collections/{key}",
            remote_asset_id=f"S2B_ACTUAL_{key}_20220722",
            local_file_path=f_meta["file_path"],
            native_crs=f_meta["crs"],
            native_resolution_m=20.0 if "s2" in key else 10000.0,
            effective_spatial_support_m=20.0 if "s2" in key else 10000.0,
            qa_summary="QC_PASSED",
        )

    independence = [
        ReferenceIndependenceRecord("NOAA_USCRN", "NOAA", False, True, "TIER_A_PHYSICAL", True, []),
    ]

    manifest = session.build_real_observation_manifest(
        aoi_id="IOWA_CORN_BELT_2022",
        target_crs="EPSG:32615",
        target_resolution_m=100.0,
        target_transform=(400000.0, 100.0, 0.0, 4650000.0, 0.0, -100.0),
        target_shape=(32, 32),
        eval_year=2022,
        eval_month=7,
        climatology_baseline_years=[2015, 2016],
        excluded_years=[2022],
        operational_comparator_id="USDM_20220726",
        in_situ_station_ids=["USCRN_IA_AMES"],
        impact_dataset_id="USDA_RMA_2022",
        available_validation_tiers=["TIER_A_PHYSICAL"],
        independence_matrix=independence,
    )

    assert manifest.archive_mode == ExecutionArchiveMode.REAL_OBSERVATION
    assert len(manifest.manifest_sha256) == 64
    assert manifest.available_validation_tiers == ["TIER_A_PHYSICAL"]


def test_unified_run_drought_activation_dispatcher(tmp_path):
    # Level 1: Synthetic
    res_l1 = run_drought_activation(archive_mode=ExecutionArchiveMode.SYNTHETIC, grid_shape=(32, 32))
    assert res_l1.aoi_id == "US_CORN_BELT_2022_SYNTHETIC_SCENARIO"

    # Level 2: Geospatial Synthetic
    res_l2 = run_drought_activation(archive_mode=ExecutionArchiveMode.GEOSPATIAL_SYNTHETIC, grid_shape=(32, 32))
    assert res_l2.aoi_id == "US_CORN_BELT_2022_IOWA_GEOSPATIAL_TEST"

    # Level 3: Disk-Backed Synthetic
    staging_dir = str(tmp_path / "stage_l3")
    res_l3 = run_drought_activation(
        archive_mode=ExecutionArchiveMode.DISK_BACKED_SYNTHETIC,
        grid_shape=(32, 32),
        staging_dir=staging_dir,
    )
    assert res_l3.manifest.archive_mode == ExecutionArchiveMode.DISK_BACKED_SYNTHETIC


def test_real_observation_mode_requires_session_guardrail():
    # Calling REAL_OBSERVATION without a verified session must raise RuntimeError!
    with pytest.raises(RuntimeError, match="REAL_OBSERVATION mode requires a verified ExternalSatelliteAcquisitionSession"):
        run_drought_activation(archive_mode=ExecutionArchiveMode.REAL_OBSERVATION)
