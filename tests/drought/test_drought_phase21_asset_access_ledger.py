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
    compute_scl_quality_distribution,
    format_execution_provenance_summary,
)
from earth_one.drought.us_corn_belt_activation import run_drought_activation


def test_asset_access_ledger_archival(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    cache_dir = tmp_path / "phase21_iowa_level4_test"
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
            signed_href_used="https://planetarycomputer.microsoft.com/b02.tif?token=abc",
            signing_required=True,
            signing_status="SUCCESS",
        ),
        AssetAccessRecord(
            asset_key="B04",
            catalog_href="https://planetarycomputer.microsoft.com/b04.tif",
            signed_href_used="https://planetarycomputer.microsoft.com/b04.tif?token=abc",
            signing_required=True,
            signing_status="SUCCESS",
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
        assert len(data) == 2
        assert data[0]["asset_key"] == "B02"
        assert data[0]["signing_status"] == "SUCCESS"


def test_scl_terrestrial_observability_contribution_named_attribute():
    scl_grid = np.array([4]*60 + [5]*20 + [8]*10 + [3]*10, dtype=np.uint8).reshape((10, 10))
    qc = compute_scl_quality_distribution(scl_grid)

    # Terrestrial = 80%, Cloud Contamination = 20%
    # Expected contribution = 0.80 * 0.80 = 0.64
    assert hasattr(qc, "scl_terrestrial_observability_contribution")
    assert pytest.approx(qc.scl_terrestrial_observability_contribution, 1e-3) == 0.64
    assert qc.scl_observability_score == qc.scl_terrestrial_observability_contribution
