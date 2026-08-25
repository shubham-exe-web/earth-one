import pytest
import shutil
from pathlib import Path
from earth_one.drought.data_staging import stage_us_corn_belt_2022_real_data_archive
from earth_one.drought.data_manifest import ExecutionArchiveMode
from earth_one.drought.external_acquisition import (
    AssetOriginType,
    STACCatalogItemDeclaration,
    ExternalSatelliteAcquisitionSession,
    STACDiscoveryEngine,
    format_execution_provenance_summary,
)
from earth_one.drought.us_corn_belt_activation import run_drought_activation


def test_stac_multi_criteria_ranking():
    discovery = STACDiscoveryEngine()
    aoi_bbox = (-94.25, 41.95, -94.15, 42.05)

    def mock_stac_multi_criteria(payload: dict):
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    # 1% cloud, but barely grazes the AOI (5% coverage)
                    "id": "S2B_SCENE_A_TINY_OVERLAP",
                    "bbox": [-94.16, 42.04, -94.00, 42.20],
                    "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 1.0},
                    "assets": {b: {"href": f"https://eo/{b}.tif"} for b in ("B02", "B04", "B05", "B08", "B11", "SCL")},
                },
                {
                    # 5% cloud, but covers 100% of the target AOI
                    "id": "S2B_SCENE_B_FULL_COVERAGE",
                    "bbox": [-94.50, 41.50, -93.50, 42.50],
                    "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 5.0},
                    "assets": {b: {"href": f"https://eo/{b}.tif"} for b in ("B02", "B04", "B05", "B08", "B11", "SCL")},
                },
            ],
        }

    decl = discovery.search_sentinel2_granule(
        bbox_wgs84=aoi_bbox,
        start_datetime_utc="2022-07-01T00:00:00Z",
        end_datetime_utc="2022-07-31T23:59:59Z",
        max_cloud_cover_pct=20.0,
        custom_search_executor=mock_stac_multi_criteria,
    )

    # Multi-criteria ranking MUST pick Scene B (full AOI coverage) over Scene A (tiny 5% overlap)
    assert decl.item_id == "S2B_SCENE_B_FULL_COVERAGE"


def test_checksum_source_local_only_classification(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    def valid_downloader(url: str, dest_path: Path):
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    decl_no_checksum = STACCatalogItemDeclaration(
        item_id="S2B_ITEM",
        collection_id="sentinel-2-l2a",
        datetime_utc="2022-07-22T16:38:49Z",
        bbox_latlon=(-94.25, 41.95, -94.15, 42.05),
        asset_urls={"s2_b02": "https://planetarycomputer.microsoft.com/b02.tif"},
        catalog_checksum_sha256=None,  # No provider checksum
    )

    rec = session.download_and_register_external_asset(
        product_name="s2_b02",
        asset_key="s2_b02",
        remote_source_url="https://planetarycomputer.microsoft.com/b02.tif",
        remote_asset_id="S2B_B02_ITEM",
        destination_filename="s2_b02.tif",
        catalog_declaration=decl_no_checksum,
        custom_downloader=valid_downloader,
    )

    assert rec.checksum_source == "LOCAL_ONLY_HASH"


def test_format_execution_provenance_summary(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    def valid_downloader(url: str, dest_path: Path):
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
            remote_source_url=f"https://planetarycomputer.microsoft.com/api/stac/v1/{key}",
            remote_asset_id=f"S2B_MSIL2A_ACTUAL_{key}_20220722",
            destination_filename=f"{key}_downloaded.tif",
            custom_downloader=valid_downloader,
        )

    result = run_drought_activation(
        archive_mode=ExecutionArchiveMode.REAL_OBSERVATION,
        grid_shape=(32, 32),
        pixel_size_m=100.0,
        real_eo_session=session,
    )

    summary = format_execution_provenance_summary(session, result.manifest)
    assert "LEVEL 4 REAL_OBSERVATION PROVENANCE LEDGER" in summary
    assert "US_CORN_BELT_IOWA_2022" in summary
    assert "VERIFIED SATELLITE ASSETS:" in summary
    assert "[s2_b02]" in summary
