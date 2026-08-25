import pytest
import shutil
import json
import inspect
from pathlib import Path
import numpy as np

from earth_one.drought.data_staging import stage_us_corn_belt_2022_real_data_archive
from earth_one.drought.data_manifest import ExecutionArchiveMode
from earth_one.drought.external_acquisition import (
    AssetOriginType,
    STACCatalogItemDeclaration,
    ExternalSatelliteAcquisitionSession,
    STACDiscoveryEngine,
    compute_scl_quality_distribution,
    execute_live_sentinel2_acquisition,
    format_execution_provenance_summary,
)
from earth_one.drought.us_corn_belt_activation import run_drought_activation


def test_catalog_and_eligible_candidates_tracking():
    discovery = STACDiscoveryEngine()
    aoi_bbox = (-94.25, 41.95, -94.15, 42.05)

    def mock_candidates(payload: dict):
        return {
            "type": "FeatureCollection",
            "features": [
                # 3 incomplete items
                {"id": f"S2B_INCOMP_{i}", "bbox": [-94.5, 41.5, -93.5, 42.5], "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 0.0}, "assets": {"B02": {"href": "h"}}}
                for i in range(3)
            ] + [
                # 2 complete items
                {
                    "id": "S2B_COMP_1",
                    "bbox": [-94.5, 41.5, -93.5, 42.5],
                    "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 5.0},
                    "assets": {b: {"href": f"https://eo/{b}.tif"} for b in ("B02", "B04", "B05", "B08", "B11", "SCL")},
                },
                {
                    "id": "S2B_COMP_2",
                    "bbox": [-94.5, 41.5, -93.5, 42.5],
                    "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 1.0},
                    "assets": {b: {"href": f"https://eo/{b}.tif"} for b in ("B02", "B04", "B05", "B08", "B11", "SCL")},
                },
            ],
        }

    decl = discovery.search_sentinel2_granule(
        bbox_wgs84=aoi_bbox,
        start_datetime_utc="2022-07-01T00:00:00Z",
        end_datetime_utc="2022-07-31T23:59:59Z",
        spectral_required_bands=("B02", "B04", "B05", "B08", "B11"),
        qa_required_assets=("SCL",),
        custom_search_executor=mock_candidates,
    )

    assert decl.catalog_candidates_count == 5
    assert decl.eligible_candidates_count == 2
    assert decl.selection_rank == 1
    assert decl.item_id == "S2B_COMP_2"


def test_item_level_selection_provenance_ledger_formatting(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    cache_dir = tmp_path / "phase19_iowa_level4_test"
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
        eligible_candidates_count=3,
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

    assert "SELECTED STAC ITEM PROVENANCE:" in summary_text
    assert "Catalog Candidates:  10" in summary_text
    assert "Eligible Candidates: 3" in summary_text
    assert "Selection Rank:      1 / 3" in summary_text
    assert "VERIFIED SATELLITE ASSETS:" in summary_text


def test_context_aware_scl_quality_distribution():
    # 100 pixels: 20% Veg (4), 10% Soil (5), 60% Water (6), 10% Cloud (8)
    scl_water = np.array([4]*20 + [5]*10 + [6]*60 + [8]*10, dtype=np.uint8).reshape((10, 10))

    qc_ag = compute_scl_quality_distribution(scl_water, target_landcover_context="TERRESTRIAL_AGRICULTURE")
    assert qc_ag.is_usable_observation is False  # Fails agriculture context (veg+soil < 40%)

    qc_water = compute_scl_quality_distribution(scl_water, target_landcover_context="WATER_BODY")
    assert qc_water.is_usable_observation is True  # Passes water context (water >= 40% and cloud < 30%)


def test_execute_live_sentinel2_acquisition_signature():
    sig = inspect.signature(execute_live_sentinel2_acquisition)
    # Ensure no mock bypass parameters exist
    assert "custom_search_executor" not in sig.parameters
    assert "custom_downloader" not in sig.parameters
