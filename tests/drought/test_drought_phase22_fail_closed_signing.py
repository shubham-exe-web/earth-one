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
    sign_planetary_computer_url,
    format_execution_provenance_summary,
)
from earth_one.drought.us_corn_belt_activation import run_drought_activation


def test_sas_signing_fails_closed_on_unauthorized_blob():
    # If a blob url cannot be signed by the endpoint in a restricted environment, it MUST raise RuntimeError
    fake_blob_url = "https://nonexistentstorageaccount.blob.core.windows.net/container/file.tif"
    with pytest.raises(RuntimeError, match="Fail-Closed Authorization Error"):
        sign_planetary_computer_url(fake_blob_url)


def test_asset_access_ledger_records_probe_and_raster_status(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    cache_dir = tmp_path / "phase22_iowa_level4_test"
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

    access_records = [
        AssetAccessRecord(
            asset_key="B02",
            catalog_href="https://planetarycomputer.microsoft.com/b02.tif",
            signed_href_used="https://planetarycomputer.microsoft.com/b02.tif",
            signing_required=False,
            signing_status="UNSIGNED_DIRECT",
            access_status="HTTP_200",
            raster_status="VALID",
        ),
    ]

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
        asset_access_records=access_records,
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

    assert (cache_dir / "asset_access.json").exists()
    with open(cache_dir / "asset_access.json") as f:
        data = json.load(f)
        assert len(data) == 1
        assert data[0]["access_status"] == "HTTP_200"
        assert data[0]["raster_status"] == "VALID"
