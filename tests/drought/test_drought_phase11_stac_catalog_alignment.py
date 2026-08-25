import pytest
import shutil
from pathlib import Path
from earth_one.drought.data_staging import stage_us_corn_belt_2022_real_data_archive
from earth_one.drought.external_acquisition import (
    AssetOriginType,
    STACCatalogItemDeclaration,
    ExternalSatelliteAcquisitionSession,
    compute_bounding_box_overlap_fraction,
)


def test_bounding_box_overlap_fraction():
    # Identical boxes -> 1.0
    b1 = (100.0, 100.0, 200.0, 200.0)
    assert compute_bounding_box_overlap_fraction(b1, b1) == 1.0

    # Half overlap
    b2 = (150.0, 100.0, 250.0, 200.0)
    assert compute_bounding_box_overlap_fraction(b1, b2) == 0.5

    # Completely disjoint -> 0.0
    b3 = (300.0, 300.0, 400.0, 400.0)
    assert compute_bounding_box_overlap_fraction(b1, b3) == 0.0


def test_download_asset_fails_on_aoi_footprint_disjoint(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    def valid_downloader(url: str, dest_path: Path):
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    # Disjoint AOI bounds far away from Central Iowa (UTM 400000, 4650000)
    disjoint_aoi_bounds = (800000.0, 5000000.0, 803200.0, 5003200.0)

    with pytest.raises(ValueError, match="Insufficient AOI coverage"):
        session.download_and_register_external_asset(
            product_name="s2_b02",
            asset_key="s2_b02",
            remote_source_url="https://planetarycomputer.microsoft.com/api/stac/v1/collections/s2_b02",
            remote_asset_id="S2B_B02_ITEM",
            destination_filename="s2_b02_disjoint.tif",
            target_aoi_bounds=disjoint_aoi_bounds,
            custom_downloader=valid_downloader,
        )


def test_download_asset_fails_on_catalog_checksum_mismatch(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    def valid_downloader(url: str, dest_path: Path):
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    # Catalog declaration with a mismatched expected checksum
    catalog_decl = STACCatalogItemDeclaration(
        item_id="S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK",
        collection_id="sentinel-2-l2a",
        datetime_utc="2022-07-22T16:38:49Z",
        bbox_latlon=(-94.5, 41.5, -93.5, 42.5),
        asset_urls={"s2_b02": "https://planetarycomputer.microsoft.com/api/stac/v1/s2_b02.tif"},
        catalog_checksum_sha256={"s2_b02": "0000000000000000000000000000000000000000000000000000000000000000"}, # Mismatched!
    )

    with pytest.raises(ValueError, match="Catalog checksum mismatch for s2_b02"):
        session.download_and_register_external_asset(
            product_name="s2_b02",
            asset_key="s2_b02",
            remote_source_url="https://planetarycomputer.microsoft.com/api/stac/v1/s2_b02.tif",
            remote_asset_id="S2B_B02_ITEM",
            destination_filename="s2_b02_chk_mismatch.tif",
            catalog_declaration=catalog_decl,
            custom_downloader=valid_downloader,
        )


def test_stac_catalog_item_declaration_and_registration(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    def valid_downloader(url: str, dest_path: Path):
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    # Calculate actual sha256 to provide authentic catalog declaration
    b02_sha256 = staged["files"]["s2_b02"]["sha256"]
    target_aoi_bounds = (400000.0, 4646800.0, 403200.0, 4650000.0)

    catalog_decl = STACCatalogItemDeclaration(
        item_id="S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK",
        collection_id="sentinel-2-l2a",
        datetime_utc="2022-07-22T16:38:49Z",
        bbox_latlon=(-94.5, 41.5, -93.5, 42.5),
        asset_urls={"s2_b02": "https://planetarycomputer.microsoft.com/api/stac/v1/s2_b02.tif"},
        catalog_checksum_sha256={"s2_b02": b02_sha256},
        catalog_content_length_bytes={"s2_b02": staged["files"]["s2_b02"]["file_size_bytes"]},
    )

    rec = session.download_and_register_external_asset(
        product_name="s2_b02",
        asset_key="s2_b02",
        remote_source_url="https://planetarycomputer.microsoft.com/api/stac/v1/s2_b02.tif",
        remote_asset_id="S2B_MSIL2A_20220722T163849_B02",
        destination_filename="s2_b02_stac_verified.tif",
        expected_crs="EPSG:32615",
        target_aoi_bounds=target_aoi_bounds,
        catalog_declaration=catalog_decl,
        custom_downloader=valid_downloader,
    )

    assert rec.asset_origin == AssetOriginType.EXTERNAL_DOWNLOAD
    assert rec.catalog_checksum == b02_sha256
    assert rec.catalog_datetime_utc == "2022-07-22T16:38:49Z"
    assert rec.observed_bounds is not None
