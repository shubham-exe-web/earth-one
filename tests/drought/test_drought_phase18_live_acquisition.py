import pytest
import shutil
import json
from pathlib import Path
import numpy as np

from earth_one.drought.data_staging import (
    stage_us_corn_belt_2022_real_data_archive,
    write_geotiff_raster,
)
from earth_one.drought.data_manifest import ExecutionArchiveMode
from earth_one.drought.external_acquisition import (
    AssetOriginType,
    STACCatalogItemDeclaration,
    ExternalSatelliteAcquisitionSession,
    STACDiscoveryEngine,
    compute_scl_quality_distribution,
    format_execution_provenance_summary,
)
from earth_one.drought.us_corn_belt_activation import run_drought_activation


def test_scl_quality_distribution_calculation():
    # 100 pixel test SCL raster:
    # 70 pixels Vegetation (4), 10 pixels Soil (5), 15 pixels Cloud (8), 5 pixels Shadow (3)
    scl_mock = np.array([4]*70 + [5]*10 + [8]*15 + [3]*5, dtype=np.uint8).reshape((10, 10))
    qc = compute_scl_quality_distribution(scl_mock)

    assert qc.valid_vegetation_pct == 70.0
    assert qc.bare_soil_pct == 10.0
    assert qc.cloud_pct == 15.0
    assert qc.cloud_shadow_pct == 5.0
    assert qc.is_usable_observation is True


def test_stac_raw_query_and_response_archival(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    cache_dir = tmp_path / "phase18_iowa_live_test"
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(cache_dir))

    def valid_downloader(url: str, dest_path: Path):
        key = dest_path.stem.split("_")[0]
        for staged_k, f_meta in staged["files"].items():
            if key in staged_k:
                shutil.copyfile(f_meta["file_path"], dest_path)
                return
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    raw_req = {"collections": ["sentinel-2-l2a"], "bbox": [-94.25, 41.95, -94.15, 42.05]}
    raw_resp = {
        "type": "FeatureCollection",
        "features": [
            {
                "id": "S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK",
                "collection": "sentinel-2-l2a",
                "bbox": [-94.5, 41.5, -93.5, 42.5],
                "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 1.2},
                "assets": {b: {"href": f"https://eo/{b}.tif"} for b in ("B02", "B04", "B05", "B08", "B11", "SCL")},
            }
        ],
    }

    decl = STACCatalogItemDeclaration(
        item_id="S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK",
        collection_id="sentinel-2-l2a",
        datetime_utc="2022-07-22T16:38:49Z",
        bbox_latlon=(-94.25, 41.95, -94.15, 42.05),
        asset_urls={b: f"https://planetarycomputer.microsoft.com/{b}.tif" for b in ("B02", "B04", "B05", "B08", "B11", "SCL")},
        selection_score=2.988,
        selection_rank=1,
        candidate_count=1,
        raw_stac_json=raw_resp["features"][0],
        raw_search_request=raw_req,
        raw_search_response=raw_resp,
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

    assert (cache_dir / "search_request.json").exists()
    assert (cache_dir / "search_response.json").exists()
    assert (cache_dir / "selected_item.json").exists()
    assert "selection_score=2.9880 (from 1 candidates)" in summary_text
