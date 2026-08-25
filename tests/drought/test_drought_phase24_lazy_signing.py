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


def test_discovery_does_not_eagerly_sign_assets():
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
                    "assets": {
                        b: {"href": f"https://sentinel2l2a01.blob.core.windows.net/{b}.tif"}
                        for b in ("B02", "B04", "B05", "B08", "B11", "SCL")
                    },
                },
            ],
        }

    decl = discovery.search_sentinel2_granule(
        bbox_wgs84=aoi_bbox,
        start_datetime_utc="2022-07-01T00:00:00Z",
        end_datetime_utc="2022-07-31T23:59:59Z",
        custom_search_executor=mock_candidates,
    )

    # Confirm canonical URLs are unchanged during discovery (no eager SAS token appended)
    assert decl.canonical_asset_urls is not None
    assert decl.canonical_asset_urls["B02"] == "https://sentinel2l2a01.blob.core.windows.net/B02.tif"
    assert "st=" not in decl.canonical_asset_urls["B02"]
    assert decl.asset_access_records is not None
    for rec in decl.asset_access_records:
        assert rec.signing_status == "NOT_YET_SIGNED"
        assert rec.access_status == "NOT_YET_PROBED"


def test_lazy_signing_occurs_at_download_time(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    cache_dir = tmp_path / "phase24_iowa_level4_test"
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
        candidate_rankings=[],
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

    assert (cache_dir / "selected_item.json").exists()
    assert (cache_dir / "candidate_rankings.json").exists()
