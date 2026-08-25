import pytest
import shutil
import json
from pathlib import Path
import numpy as np

from earth_one.drought.data_staging import stage_us_corn_belt_2022_real_data_archive
from earth_one.drought.data_manifest import ExecutionArchiveMode
from earth_one.drought.external_acquisition import (
    AssetOriginType,
    CandidateRankingRecord,
    STACCatalogItemDeclaration,
    ExternalSatelliteAcquisitionSession,
    STACDiscoveryEngine,
    compute_scl_quality_distribution,
    sign_planetary_computer_url,
    format_execution_provenance_summary,
)
from earth_one.drought.us_corn_belt_activation import run_drought_activation


def test_candidate_rankings_table_archival(tmp_path):
    staging_dir = tmp_path / "stage_src"
    staged = stage_us_corn_belt_2022_real_data_archive(staging_root_dir=str(staging_dir), shape=(32, 32))
    cache_dir = tmp_path / "phase20_iowa_level4_test"
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

    rankings = [
        CandidateRankingRecord(
            item_id="S2B_MSIL2A_20220722T163849_N0400_R083_T15TVK",
            datetime_utc="2022-07-22T16:38:49Z",
            cloud_cover_pct=1.2,
            aoi_coverage_fraction=1.0,
            delta_days_from_target=0.0,
            score=2.988,
            rank=1,
        ),
        CandidateRankingRecord(
            item_id="S2B_MSIL2A_20220717_EARLIER_SCENE",
            datetime_utc="2022-07-17T16:38:49Z",
            cloud_cover_pct=3.5,
            aoi_coverage_fraction=0.95,
            delta_days_from_target=5.0,
            score=2.565,
            rank=2,
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
        candidate_rankings=rankings,
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

    assert (cache_dir / "candidate_rankings.json").exists()
    with open(cache_dir / "candidate_rankings.json") as f:
        data = json.load(f)
        assert len(data) == 2
        assert data[0]["rank"] == 1
        assert data[0]["score"] == 2.988


def test_scl_observability_score_continuous_metric():
    # 70% vegetation, 10% soil, 10% cloud, 5% shadow, 5% water
    scl_grid = np.array([4]*70 + [5]*10 + [8]*10 + [3]*5 + [6]*5, dtype=np.uint8).reshape((10, 10))
    qc = compute_scl_quality_distribution(scl_grid)

    # Terrestrial = 80%, Cloud Contamination = 15%
    # Expected Observability Contribution = 0.80 * (1.0 - 0.15) = 0.68
    assert pytest.approx(qc.scl_observability_score, 1e-3) == 0.68
    assert 0.0 <= qc.scl_observability_score <= 1.0


def test_planetary_computer_url_signing():
    url_direct = "https://example.com/asset.tif"
    signed_direct = sign_planetary_computer_url(url_direct)
    assert signed_direct == url_direct
