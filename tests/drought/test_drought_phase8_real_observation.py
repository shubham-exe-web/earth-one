import pytest
from pathlib import Path
from earth_one.drought.data_manifest import (
    ExecutionArchiveMode,
    ReferenceIndependenceRecord,
)
from earth_one.drought.data_staging import stage_us_corn_belt_2022_real_data_archive
from earth_one.drought.external_acquisition import (
    AssetOriginType,
    ExternalSatelliteAcquisitionSession,
)
from earth_one.drought.us_corn_belt_activation import (
    run_drought_activation,
    run_us_corn_belt_2022_real_observation_activation,
)


def test_real_observation_rejects_synthetic_fixture_origin(tmp_path):
    staging_dir = tmp_path / "stage_test"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))

    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    # Register with register_synthetic_fixture
    for key, f_meta in staged["files"].items():
        session.register_synthetic_fixture(
            product_name=key,
            asset_key=key,
            local_file_path=f_meta["file_path"],
            native_crs=f_meta["crs"],
            native_resolution_m=20.0 if "s2" in key else 10000.0,
            effective_spatial_support_m=20.0 if "s2" in key else 10000.0,
        )

    # Attempting to build REAL_OBSERVATION manifest from SYNTHETIC_FIXTURE must raise ValueError!
    with pytest.raises(ValueError, match="REAL_OBSERVATION mode strictly requires AssetOriginType.EXTERNAL_DOWNLOAD"):
        session.build_real_observation_manifest(
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
            independence_matrix=[],
        )


def test_real_observation_execution_with_external_download_session(tmp_path):
    import shutil
    staging_dir = tmp_path / "stage_test"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))

    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    def mock_downloader(url: str, dest_path: Path):
        key = dest_path.stem.split("_")[0]
        for staged_k, f_meta in staged["files"].items():
            if key in staged_k:
                shutil.copyfile(f_meta["file_path"], dest_path)
                return
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    # Register genuine EXTERNAL_DOWNLOAD assets
    for key, f_meta in staged["files"].items():
        session.download_and_register_external_asset(
            product_name=key,
            asset_key=key,
            remote_source_url=f"https://planetarycomputer.microsoft.com/api/stac/v1/collections/{key}",
            remote_asset_id=f"S2B_MSIL2A_ACTUAL_{key}_20220722",
            destination_filename=f"{key}_downloaded.tif",
            expected_crs=f_meta["crs"],
            expected_resolution_m=20.0 if "s2" in key else None,
            effective_spatial_support_m=20.0 if "s2" in key else 10000.0,
            custom_downloader=mock_downloader,
        )

    # Execute genuine Level 4 pipeline via unified dispatcher
    result = run_drought_activation(
        archive_mode=ExecutionArchiveMode.REAL_OBSERVATION,
        grid_shape=(32, 32),
        pixel_size_m=100.0,
        real_eo_session=session,
    )

    assert result.manifest.archive_mode == ExecutionArchiveMode.REAL_OBSERVATION
    assert result.decision.drought_pixels > 0
    assert result.segmentation.event_count >= 1
