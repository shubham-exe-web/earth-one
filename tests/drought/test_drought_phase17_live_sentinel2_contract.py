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


def test_phase17_live_acquisition_contract_no_synthetic_fallback(tmp_path):
    cache_dir = tmp_path / "phase17_live_test"
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(cache_dir))

    # Real observation mode must hard fail if any required asset is missing from remote
    def failing_downloader(url: str, dest_path: Path):
        raise ConnectionError(f"Simulated live upstream network timeout for {url}")

    with pytest.raises(ConnectionError, match="Simulated live upstream network timeout"):
        session.download_and_register_external_asset(
            product_name="s2_b02",
            asset_key="s2_b02",
            remote_source_url="https://planetarycomputer.microsoft.com/api/stac/v1/s2_b02",
            remote_asset_id="S2B_MSIL2A_ACTUAL_s2_b02_20220722",
            destination_filename="s2_b02.tif",
            custom_downloader=failing_downloader,
        )


def test_phase17_provenance_ledger_directory_structure(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    cache_dir = tmp_path / "phase17_iowa_level4_test"
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

    assert (cache_dir / "S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK_stac_item.json").exists()
    assert (quicklook_dir / "NDVI_Anomaly.tif").exists()
    assert (quicklook_dir / "Drought_Decision.tif").exists()
    assert (cache_dir / "acquisition_manifest.json").exists()
    assert (cache_dir / "provenance_summary.txt").exists()
