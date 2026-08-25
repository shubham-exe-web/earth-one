import pytest
import shutil
from pathlib import Path
import numpy as np
from earth_one.drought.data_manifest import ExecutionArchiveMode
from earth_one.drought.data_staging import stage_us_corn_belt_2022_real_data_archive
from earth_one.drought.external_acquisition import (
    AssetOriginType,
    ExternalSatelliteAcquisitionSession,
)
from earth_one.drought.us_corn_belt_activation import (
    run_drought_activation,
    run_us_corn_belt_2022_real_observation_activation,
)


def test_download_and_register_external_asset_authenticity(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))

    cache_dir = tmp_path / "immutable_real_cache"
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(cache_dir))

    # Custom downloader simulating streaming from remote STAC API to local immutable cache
    def mock_stac_downloader(url: str, dest_path: Path):
        # Locate corresponding staged raster to stream bytes
        key = dest_path.stem.split("_")[0]
        for staged_k, f_meta in staged["files"].items():
            if key in staged_k:
                shutil.copyfile(f_meta["file_path"], dest_path)
                return
        # fallback
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    # Download and register all required modalities
    for key, f_meta in staged["files"].items():
        session.download_and_register_external_asset(
            product_name=key,
            asset_key=key,
            remote_source_url=f"https://planetarycomputer.microsoft.com/api/stac/v1/collections/{key}/items/20220722",
            remote_asset_id=f"S2B_MSIL2A_ACTUAL_{key}_20220722",
            destination_filename=f"{key}_downloaded.tif",
            expected_crs=f_meta["crs"],
            expected_resolution_m=20.0 if "s2" in key else None,
            effective_spatial_support_m=20.0 if "s2" in key else 10000.0,
            custom_downloader=mock_stac_downloader,
        )

    # Verify that records have EXTERNAL_DOWNLOAD origin
    assert session.verified_records["s2_b02"].asset_origin == AssetOriginType.EXTERNAL_DOWNLOAD
    assert Path(session.verified_records["s2_b02"].local_cached_path).exists()
    assert len(session.verified_records["s2_b02"].sha256_checksum) == 64

    # Build genuine REAL_OBSERVATION manifest
    manifest = session.build_real_observation_manifest(
        aoi_id="US_CORN_BELT_IOWA_2022",
        target_crs="EPSG:32615",
        target_resolution_m=100.0,
        target_transform=(400000.0, 100.0, 0.0, 4650000.0, 0.0, -100.0),
        target_shape=(32, 32),
        eval_year=2022,
        eval_month=7,
        climatology_baseline_years=[2015, 2016, 2017, 2018, 2019, 2020, 2021, 2023],
        excluded_years=[2022],
        operational_comparator_id="USDM_20220726",
        in_situ_station_ids=["USCRN_IA_AMES"],
        impact_dataset_id="USDA_RMA_2022",
        available_validation_tiers=["TIER_A_PHYSICAL"],
        independence_matrix=[],
    )
    assert manifest.archive_mode == ExecutionArchiveMode.REAL_OBSERVATION


def test_register_synthetic_fixture_strictly_synthetic(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))

    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    # Register using register_synthetic_fixture
    for key, f_meta in staged["files"].items():
        session.register_synthetic_fixture(
            product_name=key,
            asset_key=key,
            local_file_path=f_meta["file_path"],
            native_crs=f_meta["crs"],
            native_resolution_m=20.0 if "s2" in key else 10000.0,
            effective_spatial_support_m=20.0 if "s2" in key else 10000.0,
        )

    # Must have SYNTHETIC_FIXTURE origin
    assert session.verified_records["s2_b02"].asset_origin == AssetOriginType.SYNTHETIC_FIXTURE

    # Attempting to build REAL_OBSERVATION manifest must fail!
    with pytest.raises(ValueError, match="REAL_OBSERVATION mode strictly requires AssetOriginType.EXTERNAL_DOWNLOAD"):
        session.build_real_observation_manifest(
            aoi_id="TEST_AOI",
            target_crs="EPSG:32615",
            target_resolution_m=100.0,
            target_transform=(400000.0, 100.0, 0.0, 4650000.0, 0.0, -100.0),
            target_shape=(32, 32),
            eval_year=2022,
            eval_month=7,
            climatology_baseline_years=[2015, 2016],
            excluded_years=[2022],
            operational_comparator_id="USDM",
            in_situ_station_ids=[],
            impact_dataset_id="",
            available_validation_tiers=[],
            independence_matrix=[],
        )


def test_real_observation_activation_with_historical_stacks(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))

    cache_dir = tmp_path / "cache_p9"
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(cache_dir))

    def mock_downloader(url: str, dest_path: Path):
        key = dest_path.stem.split("_")[0]
        for staged_k, f_meta in staged["files"].items():
            if key in staged_k:
                shutil.copyfile(f_meta["file_path"], dest_path)
                return
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    for key, f_meta in staged["files"].items():
        session.download_and_register_external_asset(
            product_name=key,
            asset_key=key,
            remote_source_url=f"https://catalog.eo/{key}",
            remote_asset_id=f"ACTUAL_ID_{key}",
            destination_filename=f"{key}_downloaded.tif",
            expected_crs=f_meta["crs"],
            expected_resolution_m=20.0 if "s2" in key else None,
            effective_spatial_support_m=20.0 if "s2" in key else 10000.0,
            custom_downloader=mock_downloader,
        )

    # Provide explicit multi-year historical stacks
    baseline_years = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2023]
    n_years = len(baseline_years)
    hist_stacks = {
        "ndvi_1m": np.full((n_years, 32, 32), 0.74, dtype=np.float32),
        "ndvi_3m": np.full((n_years, 32, 32), 0.70, dtype=np.float32),
        "ndvi_6m": np.full((n_years, 32, 32), 0.58, dtype=np.float32),
        "precip_1m": np.full((n_years, 32, 32), 105.0, dtype=np.float32),
        "precip_3m": np.full((n_years, 32, 32), 310.0, dtype=np.float32),
        "precip_6m": np.full((n_years, 32, 32), 560.0, dtype=np.float32),
        "sm_surf": np.full((n_years, 32, 32), 0.32, dtype=np.float32),
        "sm_rz": np.full((n_years, 32, 32), 0.34, dtype=np.float32),
        "lst": np.full((n_years, 32, 32), 299.0, dtype=np.float32),
    }

    result = run_us_corn_belt_2022_real_observation_activation(
        session=session,
        grid_shape=(32, 32),
        pixel_size_m=100.0,
        baseline_years=baseline_years,
        historical_climatology_stacks=hist_stacks,
    )

    assert result.manifest.archive_mode == ExecutionArchiveMode.REAL_OBSERVATION
    assert result.decision.drought_pixels > 0
    assert result.segmentation.event_count >= 1
