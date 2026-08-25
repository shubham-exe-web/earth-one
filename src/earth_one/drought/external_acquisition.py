from __future__ import annotations

"""Drought Module 3 External Satellite Catalog Acquisition & Discovery Engine (Phase 19).

Provides cryptographically authenticated acquisition APIs with:
- Task D-19: Explicit spectral & QA asset completeness filtering (B02, B04, B05, B08, B11, SCL).
- Catalog vs eligible candidate counts tracking (catalog_candidates_count vs eligible_candidates_count).
- Item-level STAC selection summary ledger formatting.
- Context-aware SCL Scene Classification Layer QA distribution breakdown.
- Zero-mock scientific live acquisition runner: execute_live_sentinel2_acquisition().
"""

import hashlib
import json
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Sequence
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine
from pyproj import Transformer

from .data_manifest import (
    ExecutionArchiveMode,
    SensorSupportMetadata,
    ReferenceIndependenceRecord,
    DroughtActivationManifest,
)
from .data_staging import compute_file_sha256


class AssetOriginType(str, Enum):
    """Explicitly tags the provenance origin of an on-disk asset."""
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"     # Generated benchmark/testing fixture
    EXTERNAL_DOWNLOAD = "EXTERNAL_DOWNLOAD"     # Genuine satellite file retrieved from remote catalog/API


@dataclass
class STACCatalogItemDeclaration:
    """Declared metadata from an external STAC catalog item."""
    item_id: str
    collection_id: str
    datetime_utc: str
    bbox_latlon: tuple[float, float, float, float]  # (west, south, east, north) in EPSG:4326
    asset_urls: dict[str, str]
    geometry_geojson: dict[str, Any] | None = None
    catalog_content_length_bytes: dict[str, int] | None = None
    catalog_checksum_sha256: dict[str, str] | None = None
    cloud_cover_pct: float = 0.0
    selection_score: float = 0.0
    selection_rank: int = 1
    catalog_candidates_count: int = 1
    eligible_candidates_count: int = 1
    checksum_algorithm: str = "SHA-256"
    checksum_scope: str = "RAW_FILE_BYTES"
    raw_stac_json: dict[str, Any] | None = None
    raw_search_response: dict[str, Any] | None = None
    raw_search_request: dict[str, Any] | None = None


@dataclass
class SCLQualityDistribution:
    """Fine-grained statistical breakdown of Sentinel-2 Scene Classification Layer (SCL)."""
    valid_vegetation_pct: float
    bare_soil_pct: float
    terrestrial_observable_pct: float
    cloud_pct: float
    cloud_shadow_pct: float
    cloud_contamination_pct: float
    snow_ice_pct: float
    water_pct: float
    invalid_or_nodata_pct: float
    is_usable_observation: bool


def compute_scl_quality_distribution(
    scl_data: np.ndarray,
    target_landcover_context: str = "TERRESTRIAL_AGRICULTURE",
) -> SCLQualityDistribution:
    """Compute context-aware pixel percentage distribution across Sentinel-2 SCL classes."""
    total_pixels = float(scl_data.size)
    if total_pixels == 0:
        return SCLQualityDistribution(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100.0, False)

    # SCL Classes:
    # 0: NO_DATA, 1: SATURATED_OR_DEFECTIVE, 2: DARK_AREA_PIXELS, 3: CLOUD_SHADOWS
    # 4: VEGETATION, 5: NOT_VEGETATED, 6: WATER, 7: UNCLASSIFIED
    # 8: CLOUD_MEDIUM_PROBABILITY, 9: CLOUD_HIGH_PROBABILITY, 10: THIN_CIRRUS, 11: SNOW
    veg_count = np.sum((scl_data == 4))
    cloud_count = np.sum((scl_data == 8) | (scl_data == 9) | (scl_data == 10))
    shadow_count = np.sum((scl_data == 3))
    snow_count = np.sum((scl_data == 11))
    water_count = np.sum((scl_data == 6))
    soil_count = np.sum((scl_data == 5))
    invalid_count = np.sum((scl_data == 0) | (scl_data == 1) | (scl_data == 2) | (scl_data == 7))

    veg_pct = float(veg_count / total_pixels) * 100.0
    cloud_pct = float(cloud_count / total_pixels) * 100.0
    shadow_pct = float(shadow_count / total_pixels) * 100.0
    snow_pct = float(snow_count / total_pixels) * 100.0
    water_pct = float(water_count / total_pixels) * 100.0
    soil_pct = float(soil_count / total_pixels) * 100.0
    invalid_pct = float(invalid_count / total_pixels) * 100.0

    terrestrial_obs_pct = veg_pct + soil_pct
    cloud_contam_pct = cloud_pct + shadow_pct

    # Context-aware usability:
    if target_landcover_context == "TERRESTRIAL_AGRICULTURE":
        is_usable = (cloud_contam_pct < 30.0) and (terrestrial_obs_pct >= 40.0)
    elif target_landcover_context == "WATER_BODY":
        is_usable = (cloud_contam_pct < 30.0) and (water_pct >= 40.0)
    else:
        is_usable = cloud_contam_pct < 30.0

    return SCLQualityDistribution(
        valid_vegetation_pct=veg_pct,
        bare_soil_pct=soil_pct,
        terrestrial_observable_pct=terrestrial_obs_pct,
        cloud_pct=cloud_pct,
        cloud_shadow_pct=shadow_pct,
        cloud_contamination_pct=cloud_contam_pct,
        snow_ice_pct=snow_pct,
        water_pct=water_pct,
        invalid_or_nodata_pct=invalid_pct,
        is_usable_observation=is_usable,
    )


@dataclass
class RealEOAssetVerificationRecord:
    """Cryptographically verified record of an on-disk Earth Observation file with full provenance."""
    product_name: str
    asset_key: str
    asset_origin: AssetOriginType
    remote_source_url: str
    remote_asset_id: str
    local_cached_path: str
    file_size_bytes: int
    sha256_checksum: str
    download_timestamp_utc: str
    observed_crs: str
    observed_resolution_m: float
    observed_shape: tuple[int, int]
    observed_dtype: str
    observed_bounds: tuple[float, float, float, float]  # (left, bottom, right, top) in native CRS
    effective_spatial_support_m: float
    qa_summary: str
    catalog_bounds: tuple[float, float, float, float] | None = None
    catalog_checksum: str | None = None
    catalog_content_length: int | None = None
    catalog_datetime_utc: str | None = None
    selection_score: float | None = None
    catalog_candidates_count: int | None = None
    eligible_candidates_count: int | None = None
    checksum_algorithm: str = "SHA-256"
    checksum_source: str = "LOCAL_ONLY_HASH"  # "PROVIDER_CATALOG_MATCH" or "LOCAL_ONLY_HASH"
    checksum_scope: str = "RAW_FILE_BYTES"


def reproject_bounding_box(
    bbox: tuple[float, float, float, float],
    src_crs_str: str,
    dst_crs_str: str,
) -> tuple[float, float, float, float]:
    """Reproject a 2D bounding box (min_x, min_y, max_x, max_y) between two CRSs."""
    if src_crs_str == dst_crs_str:
        return bbox

    transformer = Transformer.from_crs(src_crs_str, dst_crs_str, always_xy=True)
    min_x, min_y, max_x, max_y = bbox

    # Transform 4 corner points
    xs, ys = transformer.transform(
        [min_x, min_x, max_x, max_x],
        [min_y, max_y, min_y, max_y],
    )
    return (float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))


def compute_bounding_box_coverage_fraction(
    reference_box: tuple[float, float, float, float],
    candidate_box: tuple[float, float, float, float],
) -> float:
    """Compute the fractional coverage of reference_box by candidate_box: Area(Intersection) / Area(Reference)."""
    l1, btm1, r1, t1 = reference_box
    l2, btm2, r2, t2 = candidate_box

    inter_left = max(l1, l2)
    inter_bottom = max(btm1, btm2)
    inter_right = min(r1, r2)
    inter_top = min(t1, t2)

    if inter_right <= inter_left or inter_top <= inter_bottom:
        return 0.0

    inter_area = (inter_right - inter_left) * (inter_top - inter_bottom)
    ref_area = (r1 - l1) * (t1 - btm1)
    if ref_area <= 0:
        return 0.0
    return float(inter_area / ref_area)


def compute_bounding_box_overlap_fraction(
    b1: tuple[float, float, float, float],
    b2: tuple[float, float, float, float],
) -> float:
    """Alias for backwards compatibility: coverage of b1 by b2."""
    return compute_bounding_box_coverage_fraction(b1, b2)


class STACDiscoveryEngine:
    """Performs live STAC discovery queries with spectral + QA completeness and temporal proximity ranking."""

    def __init__(self, endpoint_url: str = "https://planetarycomputer.microsoft.com/api/stac/v1"):
        self.endpoint_url = endpoint_url.rstrip("/")

    def search_sentinel2_granule(
        self,
        bbox_wgs84: tuple[float, float, float, float],
        start_datetime_utc: str,
        end_datetime_utc: str,
        target_datetime_utc: str | None = None,
        max_cloud_cover_pct: float = 20.0,
        spectral_required_bands: tuple[str, ...] = ("B02", "B04", "B05", "B08", "B11"),
        qa_required_assets: tuple[str, ...] = ("SCL",),
        custom_search_executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> STACCatalogItemDeclaration:
        """Search STAC collection for Sentinel-2 L2A granules with strict spectral + QA completeness filtering."""
        all_required = tuple(list(spectral_required_bands) + list(qa_required_assets))

        payload = {
            "collections": ["sentinel-2-l2a"],
            "bbox": list(bbox_wgs84),
            "datetime": f"{start_datetime_utc}/{end_datetime_utc}",
            "query": {
                "eo:cloud_cover": {"lt": max_cloud_cover_pct}
            },
            "limit": 10,
        }

        if custom_search_executor is not None:
            data = custom_search_executor(payload)
        else:
            search_url = f"{self.endpoint_url}/search"
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                search_url,
                data=req_data,
                headers={"Content-Type": "application/json", "User-Agent": "Earth-One-Satellite-Client/1.0"},
            )
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

        features = data.get("features", [])
        if not features:
            raise RuntimeError(f"No Sentinel-2 STAC items found for bbox {bbox_wgs84} and time {start_datetime_utc}/{end_datetime_utc}")

        # 1. Hard Completeness Filter: Reject candidates missing required spectral or QA bands
        def item_has_all_required_bands(feat: dict[str, Any]) -> bool:
            assets = feat.get("assets", {})
            asset_keys_upper = {k.upper(): k for k in assets.keys()}
            return all(req.upper() in asset_keys_upper for req in all_required)

        complete_features = [f for f in features if item_has_all_required_bands(f)]
        if not complete_features:
            raise RuntimeError(f"No Sentinel-2 STAC items have all required spectral & QA assets {all_required}")

        # Target datetime parsing for temporal proximity
        t_target = None
        if target_datetime_utc:
            try:
                t_target = datetime.fromisoformat(target_datetime_utc.replace("Z", "+00:00"))
            except ValueError:
                t_target = None

        # 2. Multi-Criteria Ranking Function:
        # Score = 3.0 * AOI_Coverage - 1.0 * (cloud_cover / 100.0) - 0.05 * min(delta_days, 30.0)
        def score_feature(feat: dict[str, Any]) -> float:
            props = feat.get("properties", {})
            cloud = props.get("eo:cloud_cover", 100.0)
            feat_bbox = tuple(feat.get("bbox", bbox_wgs84))
            aoi_cov = compute_bounding_box_coverage_fraction(bbox_wgs84, feat_bbox)

            delta_penalty = 0.0
            if t_target is not None and "datetime" in props:
                try:
                    dt_feat = datetime.fromisoformat(props["datetime"].replace("Z", "+00:00"))
                    delta_days = abs((dt_feat - t_target).total_seconds()) / 86400.0
                    delta_penalty = 0.05 * min(delta_days, 30.0)
                except ValueError:
                    delta_penalty = 0.0

            return (3.0 * aoi_cov) - (cloud / 100.0) - delta_penalty

        best_item = max(complete_features, key=score_feature)
        best_score = score_feature(best_item)
        item_id = best_item["id"]
        props = best_item.get("properties", {})
        dt_utc = props.get("datetime", start_datetime_utc)
        item_bbox = tuple(best_item.get("bbox", bbox_wgs84))
        geom = best_item.get("geometry")
        cloud_pct = float(props.get("eo:cloud_cover", 0.0))

        assets = best_item.get("assets", {})
        urls = {k: v.get("href", "") for k, v in assets.items() if "href" in v}

        return STACCatalogItemDeclaration(
            item_id=item_id,
            collection_id="sentinel-2-l2a",
            datetime_utc=dt_utc,
            bbox_latlon=item_bbox,
            geometry_geojson=geom,
            asset_urls=urls,
            cloud_cover_pct=cloud_pct,
            selection_score=best_score,
            selection_rank=1,
            catalog_candidates_count=len(features),
            eligible_candidates_count=len(complete_features),
            raw_stac_json=best_item,
            raw_search_response=data,
            raw_search_request=payload,
        )


class ExternalSatelliteAcquisitionSession:
    """Manages downloading, local caching, and cryptographic verification of actual EO assets."""

    def __init__(self, cache_root_dir: str = "data/drought_raw/real_cache"):
        self.cache_root = Path(cache_root_dir)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.verified_records: dict[str, RealEOAssetVerificationRecord] = {}
        self.selected_item_declaration: STACCatalogItemDeclaration | None = None

    def register_synthetic_fixture(
        self,
        product_name: str,
        asset_key: str,
        local_file_path: Path | str,
        native_crs: str,
        native_resolution_m: float,
        effective_spatial_support_m: float,
        fixture_label: str = "BENCHMARK_FIXTURE",
    ) -> RealEOAssetVerificationRecord:
        """Register a local synthetic benchmark fixture (strictly assigned SYNTHETIC_FIXTURE origin)."""
        p = Path(local_file_path)
        if not p.exists():
            raise FileNotFoundError(f"Cannot register missing fixture: {p}")
        
        file_bytes = p.stat().st_size
        file_hash = compute_file_sha256(p)
        now_utc = datetime.now(timezone.utc).isoformat()

        # Extract raster properties from file
        with rasterio.open(p) as src:
            obs_crs = src.crs.to_string() if src.crs else native_crs
            obs_shape = (src.height, src.width)
            obs_dtype = str(src.dtypes[0])
            obs_res = float(abs(src.transform.a))
            obs_bounds = (src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top)

        record = RealEOAssetVerificationRecord(
            product_name=product_name,
            asset_key=asset_key,
            asset_origin=AssetOriginType.SYNTHETIC_FIXTURE,
            remote_source_url=f"local://fixtures/{asset_key}",
            remote_asset_id=f"FIXTURE_{asset_key}_{fixture_label}",
            local_cached_path=str(p.resolve()),
            file_size_bytes=file_bytes,
            sha256_checksum=file_hash,
            download_timestamp_utc=now_utc,
            observed_crs=obs_crs,
            observed_resolution_m=obs_res,
            observed_shape=obs_shape,
            observed_dtype=obs_dtype,
            observed_bounds=obs_bounds,
            effective_spatial_support_m=effective_spatial_support_m,
            qa_summary="SYNTHETIC_FIXTURE_QC",
        )
        self.verified_records[asset_key] = record
        return record

    def download_and_register_external_asset(
        self,
        product_name: str,
        asset_key: str,
        remote_source_url: str,
        remote_asset_id: str,
        destination_filename: str,
        expected_crs: str | None = None,
        expected_resolution_m: float | None = None,
        expected_shape: tuple[int, int] | None = None,
        target_aoi_bounds: tuple[float, float, float, float] | None = None,
        target_aoi_crs: str = "EPSG:32615",
        min_aoi_coverage_fraction: float = 0.50,
        catalog_declaration: STACCatalogItemDeclaration | None = None,
        effective_spatial_support_m: float | None = None,
        custom_downloader: Callable[[str, Path], None] | None = None,
        qa_summary: str = "EXTERNAL_DOWNLOAD_VERIFIED",
    ) -> RealEOAssetVerificationRecord:
        """Retrieve an external asset, verify raster authenticity, check AOI coverage threshold, and register."""
        if not (remote_source_url.startswith("http://") or remote_source_url.startswith("https://")):
            raise ValueError(f"remote_source_url must be an HTTP/HTTPS endpoint: {remote_source_url}")

        dest_path = self.cache_root / destination_filename
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Execute Download
        if custom_downloader is not None:
            custom_downloader(remote_source_url, dest_path)
        else:
            req = urllib.request.Request(remote_source_url, headers={"User-Agent": "Earth-One-Satellite-Client/1.0"})
            with urllib.request.urlopen(req, timeout=30.0) as response:
                content_type = response.headers.get("Content-Type", "")
                if "text/html" in content_type.lower():
                    raise ValueError(f"Download failed: received HTML page instead of raster data from {remote_source_url}")
                with open(dest_path, "wb") as out_f:
                    while chunk := response.read(65536):
                        out_f.write(chunk)

        file_bytes = dest_path.stat().st_size
        if file_bytes == 0:
            raise ValueError(f"Downloaded asset from {remote_source_url} is 0 bytes.")

        file_hash = compute_file_sha256(dest_path)
        now_utc = datetime.now(timezone.utc).isoformat()

        # Archive raw STAC query and item JSON if available
        if catalog_declaration is not None:
            self.selected_item_declaration = catalog_declaration
            if catalog_declaration.raw_search_request is not None:
                with open(self.cache_root / "search_request.json", "w", encoding="utf-8") as f:
                    json.dump(catalog_declaration.raw_search_request, f, indent=2)
            if catalog_declaration.raw_search_response is not None:
                with open(self.cache_root / "search_response.json", "w", encoding="utf-8") as f:
                    json.dump(catalog_declaration.raw_search_response, f, indent=2)
            if catalog_declaration.raw_stac_json is not None:
                with open(self.cache_root / f"{catalog_declaration.item_id}_stac_item.json", "w", encoding="utf-8") as f:
                    json.dump(catalog_declaration.raw_stac_json, f, indent=2)
                with open(self.cache_root / "selected_item.json", "w", encoding="utf-8") as f:
                    json.dump(catalog_declaration.raw_stac_json, f, indent=2)

        # 2. Automated Raster Header Extraction & Authenticity Verification Gate
        try:
            with rasterio.open(dest_path) as src:
                obs_crs = src.crs.to_string() if src.crs else "UNKNOWN"
                obs_shape = (src.height, src.width)
                obs_dtype = str(src.dtypes[0])
                obs_res = float(abs(src.transform.a))
                obs_bounds = (src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top)
                band_count = src.count
        except rasterio.errors.RasterioIOError as err:
            raise ValueError(f"Downloaded file at {dest_path} is not a valid readable raster: {err}") from err

        if band_count < 1:
            raise ValueError(f"Downloaded raster has no bands: {dest_path}")

        # 3. Fail-Closed Metadata Integrity Gates
        if expected_crs is not None:
            norm_expected = CRS.from_user_input(expected_crs).to_string()
            norm_obs = CRS.from_user_input(obs_crs).to_string()
            if norm_expected != norm_obs:
                raise ValueError(
                    f"Asset integrity mismatch for {asset_key}: observed CRS '{obs_crs}' does not match expected '{expected_crs}'."
                )

        if expected_resolution_m is not None:
            if abs(obs_res - expected_resolution_m) > 1e-2:
                raise ValueError(
                    f"Asset integrity mismatch for {asset_key}: observed resolution {obs_res}m does not match expected {expected_resolution_m}m."
                )

        if expected_shape is not None:
            if obs_shape != expected_shape:
                raise ValueError(
                    f"Asset integrity mismatch for {asset_key}: observed shape {obs_shape} does not match expected {expected_shape}."
                )

        # 4. Target AOI Coverage Threshold Gate (with CRS reprojection)
        if target_aoi_bounds is not None:
            reproj_aoi_bounds = reproject_bounding_box(target_aoi_bounds, target_aoi_crs, obs_crs)
            aoi_cov = compute_bounding_box_coverage_fraction(reproj_aoi_bounds, obs_bounds)
            if aoi_cov < min_aoi_coverage_fraction:
                raise ValueError(
                    f"Insufficient AOI coverage for {asset_key}: observed raster covers only {aoi_cov*100:.2f}% "
                    f"of target AOI (required >= {min_aoi_coverage_fraction*100:.2f}%). "
                    f"Observed bounds {obs_bounds} vs AOI bounds {reproj_aoi_bounds}."
                )

        # 5. Task D-17 & D-18: STAC Catalog Declaration Geometric Alignment & Content-Length Verification
        cat_bounds = None
        cat_chk = None
        cat_len = None
        cat_dt = None
        sel_score = None
        cand_count = None
        elig_count = None
        chk_src = "LOCAL_ONLY_HASH"  # Explicitly distinguished from PROVIDER_CATALOG_MATCH
        if catalog_declaration is not None:
            cat_bounds = catalog_declaration.bbox_latlon
            cat_dt = catalog_declaration.datetime_utc
            sel_score = catalog_declaration.selection_score
            cand_count = catalog_declaration.catalog_candidates_count
            elig_count = catalog_declaration.eligible_candidates_count

            # Task D-17: Geometric reprojection of WGS84 STAC bbox into raster native CRS
            reproj_cat_bounds = reproject_bounding_box(catalog_declaration.bbox_latlon, "EPSG:4326", obs_crs)
            geom_cov = compute_bounding_box_coverage_fraction(obs_bounds, reproj_cat_bounds)
            if geom_cov <= 0.0:
                raise ValueError(
                    f"Catalog geometry mismatch for {asset_key}: reprojected catalog bbox {reproj_cat_bounds} "
                    f"does not intersect observed raster bounds {obs_bounds}."
                )

            # Task D-18: Catalog Content Length Verification Gate
            if catalog_declaration.catalog_content_length_bytes and asset_key in catalog_declaration.catalog_content_length_bytes:
                cat_len = catalog_declaration.catalog_content_length_bytes[asset_key]
                if cat_len != file_bytes:
                    raise ValueError(
                        f"Catalog content-length mismatch for {asset_key}: declared {cat_len} bytes vs downloaded {file_bytes} bytes."
                    )

            # Task D-18: Catalog Checksum Verification Gate
            if catalog_declaration.catalog_checksum_sha256 and asset_key in catalog_declaration.catalog_checksum_sha256:
                cat_chk = catalog_declaration.catalog_checksum_sha256[asset_key]
                if cat_chk.lower() != file_hash.lower():
                    raise ValueError(
                        f"Catalog checksum mismatch for {asset_key}: declared '{cat_chk}' vs observed '{file_hash}'."
                    )
                chk_src = "PROVIDER_CATALOG_MATCH"

        support_m = effective_spatial_support_m if effective_spatial_support_m is not None else obs_res

        record = RealEOAssetVerificationRecord(
            product_name=product_name,
            asset_key=asset_key,
            asset_origin=AssetOriginType.EXTERNAL_DOWNLOAD,  # Authenticated!
            remote_source_url=remote_source_url,
            remote_asset_id=remote_asset_id,
            local_cached_path=str(dest_path.resolve()),
            file_size_bytes=file_bytes,
            sha256_checksum=file_hash,
            download_timestamp_utc=now_utc,
            observed_crs=obs_crs,
            observed_resolution_m=obs_res,
            observed_shape=obs_shape,
            observed_dtype=obs_dtype,
            observed_bounds=obs_bounds,
            effective_spatial_support_m=support_m,
            qa_summary=qa_summary,
            catalog_bounds=cat_bounds,
            catalog_checksum=cat_chk,
            catalog_content_length=cat_len,
            catalog_datetime_utc=cat_dt,
            selection_score=sel_score,
            catalog_candidates_count=cand_count,
            eligible_candidates_count=elig_count,
            checksum_algorithm="SHA-256",
            checksum_source=chk_src,
            checksum_scope="RAW_FILE_BYTES",
        )
        self.verified_records[asset_key] = record
        return record

    def build_real_observation_manifest(
        self,
        aoi_id: str,
        target_crs: str,
        target_resolution_m: float,
        target_transform: tuple[float, float, float, float, float, float],
        target_shape: tuple[int, int],
        eval_year: int,
        eval_month: int,
        climatology_baseline_years: list[int],
        excluded_years: list[int],
        operational_comparator_id: str,
        in_situ_station_ids: list[str],
        impact_dataset_id: str,
        available_validation_tiers: list[str],
        independence_matrix: list[ReferenceIndependenceRecord],
        software_commit: str = "Phase19_RealEO_Release",
    ) -> DroughtActivationManifest:
        """Construct a validated REAL_OBSERVATION manifest requiring genuine EXTERNAL_DOWNLOAD assets."""
        required_keys = ["s2_b02", "s2_b04", "s2_b05", "s2_b08", "s2_b11", "s2_scl", "gpm_1m", "smap_surf", "modis_lst"]
        missing = [k for k in required_keys if k not in self.verified_records]
        if missing:
            raise RuntimeError(f"Cannot construct REAL_OBSERVATION manifest: missing verified assets for {missing}")

        # Strict Origin Guardrail: EVERY asset MUST be EXTERNAL_DOWNLOAD
        for key in required_keys:
            rec = self.verified_records[key]
            if rec.asset_origin != AssetOriginType.EXTERNAL_DOWNLOAD:
                raise ValueError(
                    f"Cannot construct REAL_OBSERVATION manifest: asset '{key}' has origin '{rec.asset_origin.value}'. "
                    f"REAL_OBSERVATION mode strictly requires AssetOriginType.EXTERNAL_DOWNLOAD."
                )

        s2_rec = self.verified_records["s2_b02"]
        gpm_rec = self.verified_records["gpm_1m"]
        smap_rec = self.verified_records["smap_surf"]
        modis_rec = self.verified_records["modis_lst"]

        supports = {
            "sentinel2": SensorSupportMetadata(
                sensor_name="Sentinel-2_MSI",
                product_id=s2_rec.remote_asset_id,
                native_crs=s2_rec.observed_crs,
                native_resolution_m=s2_rec.observed_resolution_m,
                effective_spatial_support_m=s2_rec.effective_spatial_support_m,
                analysis_grid_resolution_m=target_resolution_m,
                temporal_frequency="5-day",
                qa_filtering_applied="SCL_QA_CLEAN",
            ),
            "precipitation": SensorSupportMetadata(
                sensor_name="GPM_IMERG_FINAL",
                product_id=gpm_rec.remote_asset_id,
                native_crs=gpm_rec.observed_crs,
                native_resolution_m=gpm_rec.observed_resolution_m,
                effective_spatial_support_m=gpm_rec.effective_spatial_support_m,
                analysis_grid_resolution_m=target_resolution_m,
                temporal_frequency="Monthly",
                qa_filtering_applied="NASA_QA_GOOD",
            ),
            "soil_moisture": SensorSupportMetadata(
                sensor_name="SMAP_L3_SM_P",
                product_id=smap_rec.remote_asset_id,
                native_crs=smap_rec.observed_crs,
                native_resolution_m=smap_rec.observed_resolution_m,
                effective_spatial_support_m=smap_rec.effective_spatial_support_m,
                analysis_grid_resolution_m=target_resolution_m,
                temporal_frequency="Daily_Composite",
                qa_filtering_applied="FLAG_CLEAN",
            ),
            "thermal_lst": SensorSupportMetadata(
                sensor_name="MODIS_MOD11A1",
                product_id=modis_rec.remote_asset_id,
                native_crs=modis_rec.observed_crs,
                native_resolution_m=modis_rec.observed_resolution_m,
                effective_spatial_support_m=modis_rec.effective_spatial_support_m,
                analysis_grid_resolution_m=target_resolution_m,
                temporal_frequency="Daily_Composite",
                qa_filtering_applied="QC_GOOD",
            ),
        }

        manifest = DroughtActivationManifest(
            aoi_id=aoi_id,
            archive_mode=ExecutionArchiveMode.REAL_OBSERVATION,
            target_crs=target_crs,
            target_resolution_m=target_resolution_m,
            target_transform=target_transform,
            target_shape=target_shape,
            eval_year=eval_year,
            eval_month=eval_month,
            climatology_baseline_years=climatology_baseline_years,
            excluded_years=excluded_years,
            optical_scene_ids=[s2_rec.remote_asset_id],
            precipitation_product=gpm_rec.remote_asset_id,
            soil_moisture_product=smap_rec.remote_asset_id,
            thermal_lst_product=modis_rec.remote_asset_id,
            operational_comparator_id=operational_comparator_id,
            in_situ_station_ids=in_situ_station_ids,
            impact_dataset_id=impact_dataset_id,
            sensor_supports=supports,
            independence_matrix=independence_matrix,
            software_commit=software_commit,
            available_validation_tiers=available_validation_tiers,
        )
        manifest.manifest_sha256 = manifest.compute_sha256()
        manifest.validate_real_observation_requirements()
        return manifest


def format_execution_provenance_summary(
    session: ExternalSatelliteAcquisitionSession,
    manifest: DroughtActivationManifest,
) -> str:
    """Format an audit-ready Execution Provenance Summary string for Earth One Level 4 runs."""
    lines = [
        "=" * 80,
        "EARTH ONE LEVEL 4 REAL_OBSERVATION PROVENANCE LEDGER",
        "=" * 80,
        f"AOI ID:                {manifest.aoi_id}",
        f"Archive Mode:          {manifest.archive_mode.value}",
        f"Target Grid:           {manifest.target_crs} @ {manifest.target_resolution_m}m, shape={manifest.target_shape}",
        f"Software Commit:       {manifest.software_commit}",
        f"Manifest SHA-256:      {manifest.manifest_sha256}",
    ]

    # Item-Level Selection Summary:
    if session.selected_item_declaration is not None:
        decl = session.selected_item_declaration
        lines.extend([
            "-" * 80,
            "SELECTED STAC ITEM PROVENANCE:",
            f"  Item ID:             {decl.item_id}",
            f"  Collection:          {decl.collection_id}",
            f"  Datetime:            {decl.datetime_utc}",
            f"  Catalog Cloud Cover: {decl.cloud_cover_pct:.2f}%",
            f"  Catalog Candidates:  {decl.catalog_candidates_count}",
            f"  Eligible Candidates: {decl.eligible_candidates_count}",
            f"  Selection Rank:      {decl.selection_rank} / {decl.eligible_candidates_count}",
            f"  Selection Score:     {decl.selection_score:.4f}",
        ])

    lines.extend([
        "-" * 80,
        "VERIFIED SATELLITE ASSETS:",
    ])
    for key, rec in session.verified_records.items():
        lines.extend([
            f"  [{key}] -> {rec.remote_asset_id}",
            f"      Origin:          {rec.asset_origin.value}",
            f"      Remote URL:      {rec.remote_source_url}",
            f"      Local Path:      {rec.local_cached_path}",
            f"      Size:            {rec.file_size_bytes} bytes",
            f"      SHA-256:         {rec.sha256_checksum}",
            f"      Checksum Source: {rec.checksum_source} ({rec.checksum_algorithm})",
            f"      Observed CRS:    {rec.observed_crs} (res={rec.observed_resolution_m}m, shape={rec.observed_shape})",
            f"      Observed Bounds: {rec.observed_bounds}",
        ])
    lines.append("=" * 80)
    return "\n".join(lines)


def execute_live_sentinel2_acquisition(
    bbox_wgs84: tuple[float, float, float, float],
    start_datetime_utc: str,
    end_datetime_utc: str,
    cache_root_dir: str,
    target_datetime_utc: str | None = None,
    max_cloud_cover_pct: float = 20.0,
) -> tuple[STACCatalogItemDeclaration, ExternalSatelliteAcquisitionSession]:
    """Strict zero-mock live acquisition function executing direct external STAC and HTTP transactions."""
    discovery = STACDiscoveryEngine()
    # Zero-mock: custom_search_executor is NOT exposed and strictly None
    decl = discovery.search_sentinel2_granule(
        bbox_wgs84=bbox_wgs84,
        start_datetime_utc=start_datetime_utc,
        end_datetime_utc=end_datetime_utc,
        target_datetime_utc=target_datetime_utc,
        max_cloud_cover_pct=max_cloud_cover_pct,
        spectral_required_bands=("B02", "B04", "B05", "B08", "B11"),
        qa_required_assets=("SCL",),
        custom_search_executor=None,
    )

    session = ExternalSatelliteAcquisitionSession(cache_root_dir=cache_root_dir)
    # Zero-mock: custom_downloader is NOT exposed and strictly None
    for band_key in ("B02", "B04", "B05", "B08", "B11", "SCL"):
        asset_url = decl.asset_urls[band_key]
        session.download_and_register_external_asset(
            product_name=f"s2_{band_key.lower()}",
            asset_key=f"s2_{band_key.lower()}",
            remote_source_url=asset_url,
            remote_asset_id=f"{decl.item_id}_{band_key}",
            destination_filename=f"s2_{band_key.lower()}.tif",
            catalog_declaration=decl,
            custom_downloader=None,
        )

    return decl, session
