import pytest
import shutil
import json
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


def test_stac_hard_completeness_filter():
    discovery = STACDiscoveryEngine()
    aoi_bbox = (-94.25, 41.95, -94.15, 42.05)

    def mock_missing_bands(payload: dict):
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    # 0% cloud, but MISSING B08!
                    "id": "S2B_INCOMPLETE_SCENE",
                    "bbox": [-94.50, 41.50, -93.50, 42.50],
                    "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 0.0},
                    "assets": {"B02": {"href": "https://eo/b02.tif"}, "B04": {"href": "https://eo/b04.tif"}},
                },
                {
                    # 3% cloud, but HAS ALL REQUIRED BANDS (B02, B04, B05, B08, B11)
                    "id": "S2B_COMPLETE_SCENE",
                    "bbox": [-94.50, 41.50, -93.50, 42.50],
                    "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 3.0},
                    "assets": {b: {"href": f"https://eo/{b}.tif"} for b in ("B02", "B04", "B05", "B08", "B11")},
                },
            ],
        }

    decl = discovery.search_sentinel2_granule(
        bbox_wgs84=aoi_bbox,
        start_datetime_utc="2022-07-01T00:00:00Z",
        end_datetime_utc="2022-07-31T23:59:59Z",
        max_cloud_cover_pct=20.0,
        required_bands=("B02", "B04", "B05", "B08", "B11"),
        custom_search_executor=mock_missing_bands,
    )

    # Hard filter must completely reject the incomplete scene and select the complete one
    assert decl.item_id == "S2B_COMPLETE_SCENE"


def test_stac_temporal_proximity_ranking():
    discovery = STACDiscoveryEngine()
    aoi_bbox = (-94.25, 41.95, -94.15, 42.05)

    def mock_temporal_scenes(payload: dict):
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    # July 2, 2022 (20 days away from July 22)
                    "id": "S2B_EARLY_JULY",
                    "bbox": [-94.50, 41.50, -93.50, 42.50],
                    "properties": {"datetime": "2022-07-02T16:38:49Z", "eo:cloud_cover": 2.0},
                    "assets": {b: {"href": f"https://eo/{b}.tif"} for b in ("B02", "B04", "B05", "B08", "B11")},
                },
                {
                    # July 22, 2022 (Exact target date)
                    "id": "S2B_EXACT_TARGET_DATE",
                    "bbox": [-94.50, 41.50, -93.50, 42.50],
                    "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 2.0},
                    "assets": {b: {"href": f"https://eo/{b}.tif"} for b in ("B02", "B04", "B05", "B08", "B11")},
                },
            ],
        }

    decl = discovery.search_sentinel2_granule(
        bbox_wgs84=aoi_bbox,
        start_datetime_utc="2022-07-01T00:00:00Z",
        end_datetime_utc="2022-07-31T23:59:59Z",
        target_datetime_utc="2022-07-22T16:38:49Z",
        max_cloud_cover_pct=20.0,
        custom_search_executor=mock_temporal_scenes,
    )

    # Temporal proximity ranking MUST select the scene on the exact target date
    assert decl.item_id == "S2B_EXACT_TARGET_DATE"


def test_phase15_live_pipeline_ledger_archival(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    cache_dir = tmp_path / "phase15_real_iowa"
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(cache_dir))

    def valid_downloader(url: str, dest_path: Path):
        key = dest_path.stem.split("_")[0]
        for staged_k, f_meta in staged["files"].items():
            if key in staged_k:
                shutil.copyfile(f_meta["file_path"], dest_path)
                return
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    raw_item = {
        "id": "S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK",
        "collection": "sentinel-2-l2a",
        "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 1.2},
    }

    decl = STACCatalogItemDeclaration(
        item_id="S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK",
        collection_id="sentinel-2-l2a",
        datetime_utc="2022-07-22T16:38:49Z",
        bbox_latlon=(-94.25, 41.95, -94.15, 42.05),
        asset_urls={"s2_b02": "https://planetarycomputer.microsoft.com/b02.tif"},
        raw_stac_json=raw_item,
    )

    for key, f_meta in staged["files"].items():
        session.download_and_register_external_asset(
            product_name=key,
            asset_key=key,
            remote_source_url=f"https://planetarycomputer.microsoft.com/api/stac/v1/{key}",
            remote_asset_id=f"S2B_MSIL2A_ACTUAL_{key}_20220722",
            destination_filename=f"{key}_downloaded.tif",
            catalog_declaration=decl if "s2" in key else None,
            custom_downloader=valid_downloader,
        )

    result = run_drought_activation(
        archive_mode=ExecutionArchiveMode.REAL_OBSERVATION,
        grid_shape=(32, 32),
        pixel_size_m=100.0,
        real_eo_session=session,
    )

    # Save provenance summary into cache directory
    summary_text = format_execution_provenance_summary(session, result.manifest)
    summary_path = cache_dir / "provenance_summary.txt"
    summary_path.write_text(summary_text)

    # Save manifest json into cache directory
    manifest_path = cache_dir / "acquisition_manifest.json"
    manifest_path.write_text(json.dumps(result.manifest.to_dict(), indent=2))

    assert (cache_dir / "S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK_stac_item.json").exists()
    assert summary_path.exists()
    assert manifest_path.exists()
    assert "LEVEL 4 REAL_OBSERVATION PROVENANCE LEDGER" in summary_text
