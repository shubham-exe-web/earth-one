import pytest
import shutil
import json
from pathlib import Path
from earth_one.drought.data_staging import stage_us_corn_belt_2022_real_data_archive
from earth_one.drought.external_acquisition import (
    AssetOriginType,
    STACCatalogItemDeclaration,
    ExternalSatelliteAcquisitionSession,
    STACDiscoveryEngine,
    compute_bounding_box_coverage_fraction,
)


def test_coverage_fraction_metric():
    ref_box = (100.0, 100.0, 200.0, 200.0) # Area = 100 * 100 = 10000

    # Candidate covers half the reference box
    candidate_half = (150.0, 100.0, 250.0, 200.0) # Inter = 50 * 100 = 5000 -> 0.50
    assert compute_bounding_box_coverage_fraction(ref_box, candidate_half) == 0.50

    # Candidate covers only 10%
    candidate_tenth = (190.0, 100.0, 290.0, 200.0) # Inter = 10 * 100 = 1000 -> 0.10
    assert abs(compute_bounding_box_coverage_fraction(ref_box, candidate_tenth) - 0.10) < 1e-4


def test_insufficient_aoi_coverage_fraction_rejection(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(tmp_path / "cache"))

    def valid_downloader(url: str, dest_path: Path):
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    # Observed raster is around (400000, 4646800, 403200, 4650000)
    # Huge AOI box where this raster only covers ~5% of it:
    huge_aoi = (380000.0, 4600000.0, 4400000.0, 4700000.0)

    with pytest.raises(ValueError, match="Insufficient AOI coverage"):
        session.download_and_register_external_asset(
            product_name="s2_b02",
            asset_key="s2_b02",
            remote_source_url="https://planetarycomputer.microsoft.com/api/stac/v1/s2_b02.tif",
            remote_asset_id="S2B_B02_ITEM",
            destination_filename="s2_b02_partial.tif",
            target_aoi_bounds=huge_aoi,
            target_aoi_crs="EPSG:32615",
            min_aoi_coverage_fraction=0.50,  # Demands 50% coverage
            custom_downloader=valid_downloader,
        )


def test_stac_discovery_engine_query_and_item_parsing():
    discovery = STACDiscoveryEngine()

    def mock_stac_search(payload: dict):
        assert payload["collections"] == ["sentinel-2-l2a"]
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "id": "S2B_MSIL2A_20220717_HIGH_CLOUD",
                    "bbox": [-94.5, 41.5, -93.5, 42.5],
                    "geometry": {"type": "Polygon", "coordinates": [[[-94.5, 41.5], [-93.5, 41.5], [-93.5, 42.5], [-94.5, 42.5], [-94.5, 41.5]]]},
                    "properties": {"datetime": "2022-07-17T16:38:49Z", "eo:cloud_cover": 45.0},
                    "assets": {"B02": {"href": "https://planetarycomputer.microsoft.com/b02_cloudy.tif"}},
                },
                {
                    "id": "S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK",
                    "bbox": [-94.5, 41.5, -93.5, 42.5],
                    "geometry": {"type": "Polygon", "coordinates": [[[-94.5, 41.5], [-93.5, 41.5], [-93.5, 42.5], [-94.5, 42.5], [-94.5, 41.5]]]},
                    "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 2.1},
                    "assets": {
                        "B02": {"href": "https://planetarycomputer.microsoft.com/b02.tif"},
                        "B04": {"href": "https://planetarycomputer.microsoft.com/b04.tif"},
                        "B08": {"href": "https://planetarycomputer.microsoft.com/b08.tif"},
                    },
                },
            ],
        }

    decl = discovery.search_sentinel2_granule(
        bbox_wgs84=(-94.25, 41.95, -94.15, 42.05),
        start_datetime_utc="2022-07-01T00:00:00Z",
        end_datetime_utc="2022-07-31T23:59:59Z",
        max_cloud_cover_pct=20.0,
        custom_search_executor=mock_stac_search,
    )

    # Must select the 2.1% cloud cover scene
    assert decl.item_id == "S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK"
    assert decl.datetime_utc == "2022-07-22T16:38:49Z"
    assert "B02" in decl.asset_urls
    assert decl.raw_stac_json is not None


def test_stac_item_json_archival_in_cache(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    cache_dir = tmp_path / "cache_p13"
    session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(cache_dir))

    def valid_downloader(url: str, dest_path: Path):
        shutil.copyfile(staged["files"]["s2_b02"]["file_path"], dest_path)

    raw_item = {
        "id": "S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK",
        "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 1.5},
    }

    decl = STACCatalogItemDeclaration(
        item_id="S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK",
        collection_id="sentinel-2-l2a",
        datetime_utc="2022-07-22T16:38:49Z",
        bbox_latlon=(-94.25, 41.95, -94.15, 42.05),
        asset_urls={"s2_b02": "https://planetarycomputer.microsoft.com/b02.tif"},
        raw_stac_json=raw_item,
    )

    session.download_and_register_external_asset(
        product_name="s2_b02",
        asset_key="s2_b02",
        remote_source_url="https://planetarycomputer.microsoft.com/b02.tif",
        remote_asset_id="S2B_B02_ITEM",
        destination_filename="s2_b02.tif",
        catalog_declaration=decl,
        custom_downloader=valid_downloader,
    )

    # Verify that item.json was archived in the cache root
    expected_item_file = cache_dir / "S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK_stac_item.json"
    assert expected_item_file.exists()
    with open(expected_item_file) as f:
        loaded = json.load(f)
    assert loaded["id"] == "S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK"
