import pytest
import shutil
import json
from pathlib import Path
import numpy as np

from earth_one.drought.data_staging import stage_us_corn_belt_2022_real_data_archive
from earth_one.drought.data_manifest import ExecutionArchiveMode
from earth_one.drought.external_acquisition import (
    AssetOriginType,
    AssetAccessRecord,
    STACCatalogItemDeclaration,
    ExternalSatelliteAcquisitionSession,
    STACDiscoveryEngine,
    format_execution_provenance_summary,
)
from earth_one.drought.us_corn_belt_activation import run_drought_activation


def test_discovery_initializes_unprobed_status():
    discovery = STACDiscoveryEngine()
    aoi_bbox = (-94.25, 41.95, -94.15, 42.05)

    def mock_candidates(payload: dict):
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "id": "S2B_MSIL2A_20220722_SCENE",
                    "bbox": [-94.5, 41.5, -93.5, 42.5],
                    "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 1.0},
                    "assets": {b: {"href": f"https://example.com/{b}.tif"} for b in ("B02", "B04", "B05", "B08", "B11", "SCL")},
                },
            ],
        }

    decl = discovery.search_sentinel2_granule(
        bbox_wgs84=aoi_bbox,
        start_datetime_utc="2022-07-01T00:00:00Z",
        end_datetime_utc="2022-07-31T23:59:59Z",
        custom_search_executor=mock_candidates,
    )

    assert decl.asset_access_records is not None
    assert len(decl.asset_access_records) == 6
    for rec in decl.asset_access_records:
        assert rec.access_status == "NOT_YET_PROBED"
        assert rec.raster_status == "NOT_YET_VERIFIED"
        assert rec.probe_method == "NONE"


def test_provenance_summary_contains_probe_and_raster_status(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    cache_dir = tmp_path / "phase23_iowa_level4_test"
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
        asset_urls={b: f"https://planetarycomputer.microsoft.com/{b}.tif" for b in ("B02", "B04", "B05", "B08", "B11", "SCL")},
        cloud_cover_pct=1.2,
        selection_score=2.988,
        selection_rank=1,
        catalog_candidates_count=10,
        eligible_candidates_count=2,
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

    summary_text = format_execution_provenance_summary(session, result.manifest)

    assert "Probe Method:    CUSTOM" in summary_text
    assert "Access Status:   PROBE_SKIPPED_CUSTOM" in summary_text
    assert "Raster Status:   VALID" in summary_text
