import pytest
import numpy as np
from earth_one.drought.data_manifest import (
    ExecutionArchiveMode,
    DroughtActivationManifest,
    SensorSupportMetadata,
)
from earth_one.drought.data_staging import stage_us_corn_belt_2022_real_data_archive, read_geotiff_with_metadata
from earth_one.drought.us_corn_belt_activation import run_us_corn_belt_2022_disk_backed_synthetic_activation


def test_execution_archive_mode_validation():
    # 1. DISK_BACKED_SYNTHETIC does not raise
    manifest_synth = DroughtActivationManifest(
        aoi_id="TEST_AOI",
        archive_mode=ExecutionArchiveMode.DISK_BACKED_SYNTHETIC,
        target_crs="EPSG:32615",
        target_resolution_m=100.0,
        target_transform=(400000.0, 100.0, 0.0, 4650000.0, 0.0, -100.0),
        target_shape=(64, 64),
        eval_year=2022,
        eval_month=7,
        climatology_baseline_years=[2015, 2016],
        excluded_years=[2022],
        optical_scene_ids=["SYNTHETIC_SCENE_1"],
        precipitation_product="GPM",
        soil_moisture_product="SMAP",
        thermal_lst_product="MODIS",
        operational_comparator_id="USDM",
        in_situ_station_ids=[],
        impact_dataset_id="",
        sensor_supports={},
        independence_matrix=[],
        software_commit="v0.6",
    )
    manifest_synth.validate_real_observation_requirements()  # Should not raise

    # 2. REAL_OBSERVATION with synthetic placeholders MUST raise ValueError!
    manifest_real_fake = DroughtActivationManifest(
        aoi_id="TEST_AOI",
        archive_mode=ExecutionArchiveMode.REAL_OBSERVATION,
        target_crs="EPSG:32615",
        target_resolution_m=100.0,
        target_transform=(400000.0, 100.0, 0.0, 4650000.0, 0.0, -100.0),
        target_shape=(64, 64),
        eval_year=2022,
        eval_month=7,
        climatology_baseline_years=[2015, 2016],
        excluded_years=[2022],
        optical_scene_ids=["SYNTHETIC_SCENE_1"],
        precipitation_product="GPM",
        soil_moisture_product="SMAP",
        thermal_lst_product="MODIS",
        operational_comparator_id="USDM",
        in_situ_station_ids=[],
        impact_dataset_id="",
        sensor_supports={},
        independence_matrix=[],
        software_commit="v0.6",
    )
    with pytest.raises(ValueError, match="REAL_OBSERVATION mode requires actual verified Sentinel-2 scene IDs"):
        manifest_real_fake.validate_real_observation_requirements()


def test_native_20m_to_100m_area_average_reprojection(tmp_path):
    staging_dir = tmp_path / "stage_20m_test"
    manifest = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))

    # Verify native 20m Sentinel-2 GeoTIFF shape (32x5 = 160x160)
    b02_path = manifest["files"]["s2_b02"]["file_path"]
    data_20m, crs_str, trans, _ = read_geotiff_with_metadata(b02_path)
    assert data_20m.shape == (160, 160)
    assert trans.a == 20.0  # Native 20m pixel width!
    assert trans.e == -20.0 # Native 20m pixel height!


def test_disk_backed_synthetic_activation_execution(tmp_path):
    staging_dir = str(tmp_path / "iowa_disk_test")
    res = run_us_corn_belt_2022_disk_backed_synthetic_activation(grid_shape=(32, 32), pixel_size_m=100.0, staging_dir=staging_dir)

    assert res.manifest.archive_mode == ExecutionArchiveMode.DISK_BACKED_SYNTHETIC
    assert res.decision.drought_pixels > 0
    assert res.segmentation.event_count >= 1
    assert res.tier_b_metrics is not None
