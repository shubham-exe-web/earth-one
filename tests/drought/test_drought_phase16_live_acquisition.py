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
    format_execution_provenance_summary,
)
from earth_one.drought.us_corn_belt_activation import run_drought_activation


def test_stac_requires_spectral_and_qa_bands():
    discovery = STACDiscoveryEngine()
    aoi_bbox = (-94.25, 41.95, -94.15, 42.05)

    def mock_missing_scl(payload: dict):
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    # Has B02, B04, B05, B08, B11, but MISSING SCL!
                    "id": "S2B_NO_SCL",
                    "bbox": [-94.50, 41.50, -93.50, 42.50],
                    "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 0.5},
                    "assets": {b: {"href": f"https://eo/{b}.tif"} for b in ("B02", "B04", "B05", "B08", "B11")},
                },
            ],
        }

    with pytest.raises(RuntimeError, match="No Sentinel-2 STAC items have all required spectral & QA assets"):
        discovery.search_sentinel2_granule(
            bbox_wgs84=aoi_bbox,
            start_datetime_utc="2022-07-01T00:00:00Z",
            end_datetime_utc="2022-07-31T23:59:59Z",
            spectral_required_bands=("B02", "B04", "B05", "B08", "B11"),
            qa_required_assets=("SCL",),
            custom_search_executor=mock_missing_scl,
        )


def test_stac_accepts_when_spectral_and_scl_present():
    discovery = STACDiscoveryEngine()
    aoi_bbox = (-94.25, 41.95, -94.15, 42.05)

    def mock_with_scl(payload: dict):
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    # Has ALL spectral bands + SCL!
                    "id": "S2B_WITH_SCL",
                    "bbox": [-94.50, 41.50, -93.50, 42.50],
                    "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 1.2},
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
        custom_search_executor=mock_with_scl,
    )

    assert decl.item_id == "S2B_WITH_SCL"
    assert "SCL" in decl.asset_urls


def test_phase16_quicklook_and_artifact_generation(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    cache_dir = tmp_path / "phase16_iowa_real"
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

    # 1. Output Quicklooks
    quicklook_dir = cache_dir / "quicklook"
    quicklook_dir.mkdir(parents=True, exist_ok=True)

    transform = (400000.0, 100.0, 0.0, 4650000.0, 0.0, -100.0)
    write_geotiff_raster(quicklook_dir / "NDVI_Anomaly.tif", result.anomalies.veg_z_1m, "EPSG:32615", transform)
    write_geotiff_raster(quicklook_dir / "Drought_Decision.tif", result.decision.drought_mask.astype(np.float32), "EPSG:32615", transform)

    # 2. Output Provenance Summary & Manifest JSON
    summary_text = format_execution_provenance_summary(session, result.manifest)
    (cache_dir / "provenance_summary.txt").write_text(summary_text)
    (cache_dir / "acquisition_manifest.json").write_text(json.dumps(result.manifest.to_dict(), indent=2))

    assert (quicklook_dir / "NDVI_Anomaly.tif").exists()
    assert (quicklook_dir / "Drought_Decision.tif").exists()
    assert (cache_dir / "acquisition_manifest.json").exists()
    assert (cache_dir / "provenance_summary.txt").exists()
