import pytest
from pathlib import Path
from earth_one.drought.data_staging import (
    stage_us_corn_belt_2022_real_data_archive,
    compute_file_sha256,
)
from earth_one.drought.data_acquisition import (
    RealEODataAcquisitionManager,
    read_geotiff_with_metadata,
)
from earth_one.drought.spatial_harmonization import TargetAnalysisGrid
from earth_one.drought.us_corn_belt_activation import run_us_corn_belt_2022_actual_eo_activation


def test_geotiff_data_staging_and_checksums(tmp_path):
    staging_dir = tmp_path / "drought_stage_test"
    manifest = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))

    assert manifest["staging_status"] == "ACQUIRED_ON_DISK"
    assert "files" in manifest
    assert "s2_b02" in manifest["files"]
    
    b02_path = Path(manifest["files"]["s2_b02"]["file_path"])
    assert b02_path.exists()
    assert manifest["files"]["s2_b02"]["file_size_bytes"] > 0
    assert len(manifest["files"]["s2_b02"]["sha256"]) == 64

    # Verify rasterio read of native 20m Sentinel-2 raster (32x5 = 160x160)
    data, crs_str, transform, nodata = read_geotiff_with_metadata(b02_path)
    assert data.shape == (160, 160)
    assert "32615" in crs_str


def test_actual_eo_mode_guardrail_fail_loudly():
    acq_mgr = RealEODataAcquisitionManager()
    target_grid = TargetAnalysisGrid("EPSG:32615", (400000.0, 100.0, 0.0, 4650000.0, 0.0, -100.0), 32, 32, 100.0, -100.0)

    # When require_actual_assets is True, passing None for Sentinel-2 must raise RuntimeError!
    with pytest.raises(RuntimeError, match="Actual EO activation cannot execute with synthetic placeholders"):
        acq_mgr.build_harmonized_scene_stack_from_geotiff(
            aoi_id="TEST_AOI",
            epoch_timestamp="2022-07-22T00:00:00Z",
            target_grid=target_grid,
            s2_b02_path=None,
            s2_b04_path=None,
            s2_b05_path=None,
            s2_b08_path=None,
            s2_b11_path=None,
            s2_scl_path=None,
            require_actual_assets=True,
        )


def test_actual_eo_pipeline_end_to_end_from_geotiff(tmp_path):
    staging_dir = str(tmp_path / "iowa_actual_stage")
    result = run_us_corn_belt_2022_actual_eo_activation(grid_shape=(32, 32), pixel_size_m=100.0, staging_dir=staging_dir)

    # 1. Verification of real GeoTIFF ingestion
    assert result.manifest.aoi_id == "US_CORN_BELT_IOWA_2022"
    assert result.decision.drought_pixels > 0
    assert result.segmentation.event_count >= 1

    # 2. Tier A Physical Validation against in-situ station readings
    assert result.tier_a_metrics is not None
    assert result.tier_a_metrics.rmse < 0.05
    assert result.tier_a_metrics.station_count > 0

    # 3. Tier B USDM Operational Concordance
    assert result.tier_b_metrics is not None
    assert result.tier_b_metrics.spatial_concordance_f1 >= 0.85
    assert result.tier_b_metrics.comparator_name == "USDM_IOWA_JULY_2022_GEOTIFF"
    assert "operational agreement" in result.tier_b_metrics.scientific_disclaimer.lower()

    # 4. Tier C Impact Corroboration
    assert result.tier_c_metrics is not None
    assert result.tier_c_metrics.is_pixel_truth_prohibited is True
