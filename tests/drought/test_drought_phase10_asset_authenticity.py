import pytest
import shutil
from pathlib import Path
import rasterio
from earth_one.drought.data_staging import stage_us_corn_belt_2022_real_data_archive
from earth_one.drought.external_acquisition import (
    AssetOriginType,
    ExternalSatelliteAcquisitionSession,
)


def test_download_asset_fails_on_corrupt_or_non_raster(tmp_path):
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    # Custom downloader that writes a fake HTML error page
    def html_error_downloader(url: str, dest_path: Path):
        with open(dest_path, "w") as f:
            f.write("<html><body>404 Not Found</body></html>")

    with pytest.raises(ValueError, match="is not a valid readable raster"):
        session.download_and_register_external_asset(
            product_name="s2_b02",
            asset_key="s2_b02",
            remote_source_url="https://planetarycomputer.microsoft.com/api/stac/v1/collections/s2_b02",
            remote_asset_id="S2B_B02_ITEM",
            destination_filename="s2_b02_bad.tif",
            custom_downloader=html_error_downloader,
        )


def test_download_asset_fails_on_crs_mismatch(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    def valid_downloader(url: str, dest_path: Path):
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    # Sentinel-2 raster is EPSG:32615. Expecting EPSG:4326 must trigger fail-closed ValueError!
    with pytest.raises(ValueError, match="Asset integrity mismatch.*observed CRS.*does not match expected"):
        session.download_and_register_external_asset(
            product_name="s2_b02",
            asset_key="s2_b02",
            remote_source_url="https://planetarycomputer.microsoft.com/api/stac/v1/collections/s2_b02",
            remote_asset_id="S2B_B02_ITEM",
            destination_filename="s2_b02_mismatch.tif",
            expected_crs="EPSG:4326",  # Intentionally mismatched!
            custom_downloader=valid_downloader,
        )


def test_download_asset_fails_on_resolution_mismatch(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    def valid_downloader(url: str, dest_path: Path):
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    # Sentinel-2 raster is 20m. Expecting 10.0m must trigger fail-closed ValueError!
    with pytest.raises(ValueError, match="Asset integrity mismatch.*observed resolution.*does not match expected"):
        session.download_and_register_external_asset(
            product_name="s2_b02",
            asset_key="s2_b02",
            remote_source_url="https://planetarycomputer.microsoft.com/api/stac/v1/collections/s2_b02",
            remote_asset_id="S2B_B02_ITEM",
            destination_filename="s2_b02_res_mismatch.tif",
            expected_resolution_m=10.0,  # Intentionally mismatched!
            custom_downloader=valid_downloader,
        )


def test_automated_raster_metadata_extraction(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    def valid_downloader(url: str, dest_path: Path):
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    rec = session.download_and_register_external_asset(
        product_name="s2_b02",
        asset_key="s2_b02",
        remote_source_url="https://planetarycomputer.microsoft.com/api/stac/v1/collections/s2_b02",
        remote_asset_id="S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK_B02",
        destination_filename="s2_b02_extracted.tif",
        expected_crs="EPSG:32615",
        expected_resolution_m=20.0,
        expected_shape=(160, 160),
        custom_downloader=valid_downloader,
    )

    # Verify extracted properties
    assert rec.asset_origin == AssetOriginType.EXTERNAL_DOWNLOAD
    assert "32615" in rec.observed_crs
    assert rec.observed_resolution_m == 20.0
    assert rec.observed_shape == (160, 160)
    assert rec.observed_dtype == "float32"
    assert rec.file_size_bytes > 0
    assert len(rec.sha256_checksum) == 64
