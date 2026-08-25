import pytest
import shutil
from pathlib import Path
from earth_one.drought.data_staging import stage_us_corn_belt_2022_real_data_archive
from earth_one.drought.external_acquisition import (
    AssetOriginType,
    STACCatalogItemDeclaration,
    ExternalSatelliteAcquisitionSession,
    reproject_bounding_box,
    compute_bounding_box_overlap_fraction,
)


def test_reproject_bounding_box_wgs84_to_utm():
    # Iowa lon/lat in EPSG:4326 -> EPSG:32615
    wgs84_bbox = (-94.0, 42.0, -93.0, 43.0)
    utm_bbox = reproject_bounding_box(wgs84_bbox, "EPSG:4326", "EPSG:32615")
    min_x, min_y, max_x, max_y = utm_bbox

    # Should be around 400000m - 500000m X, and 4650000m - 4760000m Y
    assert 400000.0 < min_x < 450000.0
    assert 4600000.0 < min_y < 4700000.0
    assert max_x > min_x
    assert max_y > min_y


def test_wgs84_stac_bbox_reprojection_and_geometric_intersection(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    def valid_downloader(url: str, dest_path: Path):
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    # Genuine Central Iowa bounding box in WGS84 lon/lat
    iowa_wgs84_bbox = (-94.25, 41.95, -94.15, 42.05)

    catalog_decl = STACCatalogItemDeclaration(
        item_id="S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK",
        collection_id="sentinel-2-l2a",
        datetime_utc="2022-07-22T16:38:49Z",
        bbox_latlon=iowa_wgs84_bbox,
        asset_urls={"s2_b02": "https://planetarycomputer.microsoft.com/api/stac/v1/s2_b02.tif"},
        catalog_content_length_bytes={"s2_b02": staged["files"]["s2_b02"]["file_size_bytes"]},
    )

    rec = session.download_and_register_external_asset(
        product_name="s2_b02",
        asset_key="s2_b02",
        remote_source_url="https://planetarycomputer.microsoft.com/api/stac/v1/s2_b02.tif",
        remote_asset_id="S2B_B02_ITEM",
        destination_filename="s2_b02_geom_align.tif",
        expected_crs="EPSG:32615",
        catalog_declaration=catalog_decl,
        custom_downloader=valid_downloader,
    )

    assert rec.asset_origin == AssetOriginType.EXTERNAL_DOWNLOAD
    assert rec.catalog_content_length == staged["files"]["s2_b02"]["file_size_bytes"]
    assert rec.checksum_source == "LOCAL_STREAM_COMPUTATION"


def test_download_fails_on_disjoint_wgs84_catalog_bbox(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    def valid_downloader(url: str, dest_path: Path):
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    # Disjoint California bounding box in WGS84 lon/lat
    california_wgs84_bbox = (-120.5, 35.5, -119.5, 36.5)

    catalog_decl = STACCatalogItemDeclaration(
        item_id="S2B_CALIFORNIA_SCENE",
        collection_id="sentinel-2-l2a",
        datetime_utc="2022-07-22T16:38:49Z",
        bbox_latlon=california_wgs84_bbox,
        asset_urls={"s2_b02": "https://planetarycomputer.microsoft.com/api/stac/v1/s2_b02.tif"},
    )

    with pytest.raises(ValueError, match="Catalog geometry mismatch.*does not intersect observed raster bounds"):
        session.download_and_register_external_asset(
            product_name="s2_b02",
            asset_key="s2_b02",
            remote_source_url="https://planetarycomputer.microsoft.com/api/stac/v1/s2_b02.tif",
            remote_asset_id="S2B_B02_ITEM",
            destination_filename="s2_b02_california.tif",
            catalog_declaration=catalog_decl,
            custom_downloader=valid_downloader,
        )


def test_download_fails_on_catalog_content_length_mismatch(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    def valid_downloader(url: str, dest_path: Path):
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    iowa_wgs84_bbox = (-94.25, 41.95, -94.15, 42.05)

    catalog_decl = STACCatalogItemDeclaration(
        item_id="S2B_ITEM",
        collection_id="sentinel-2-l2a",
        datetime_utc="2022-07-22T16:38:49Z",
        bbox_latlon=iowa_wgs84_bbox,
        asset_urls={"s2_b02": "https://planetarycomputer.microsoft.com/api/stac/v1/s2_b02.tif"},
        catalog_content_length_bytes={"s2_b02": 999999999},  # Intentionally mismatched!
    )

    with pytest.raises(ValueError, match="Catalog content-length mismatch for s2_b02"):
        session.download_and_register_external_asset(
            product_name="s2_b02",
            asset_key="s2_b02",
            remote_source_url="https://planetarycomputer.microsoft.com/api/stac/v1/s2_b02.tif",
            remote_asset_id="S2B_B02_ITEM",
            destination_filename="s2_b02_bad_len.tif",
            catalog_declaration=catalog_decl,
            custom_downloader=valid_downloader,
        )


def test_target_aoi_reprojection_from_wgs84(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    def valid_downloader(url: str, dest_path: Path):
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    # Pass target AOI in EPSG:4326 lon/lat degrees
    target_aoi_wgs84 = (-94.25, 41.95, -94.15, 42.05)

    rec = session.download_and_register_external_asset(
        product_name="s2_b02",
        asset_key="s2_b02",
        remote_source_url="https://planetarycomputer.microsoft.com/api/stac/v1/s2_b02.tif",
        remote_asset_id="S2B_B02_ITEM",
        destination_filename="s2_b02_aoi_wgs84.tif",
        expected_crs="EPSG:32615",
        target_aoi_bounds=target_aoi_wgs84,
        target_aoi_crs="EPSG:4326",  # Reprojection to EPSG:32615 tested!
        custom_downloader=valid_downloader,
    )

    assert rec.asset_origin == AssetOriginType.EXTERNAL_DOWNLOAD
