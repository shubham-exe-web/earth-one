#!/usr/bin/env python3
"""Execute live Sentinel-2 acquisition against Microsoft Planetary Computer for Iowa AOI."""

import json
from pathlib import Path
import numpy as np
import rasterio

from earth_one.drought.external_acquisition import (
    execute_live_sentinel2_acquisition,
    compute_scl_quality_distribution,
    format_execution_provenance_summary,
)
from earth_one.drought.data_staging import compute_file_sha256

BBOX = (-94.25, 41.95, -94.15, 42.05)
START = "2022-07-01T00:00:00Z"
END = "2022-07-31T23:59:59Z"
TARGET = "2022-07-22T00:00:00Z"


def main():
    repo = Path(__file__).resolve().parents[1]
    out = repo / "data" / "drought_raw" / "phase27_iowa_live"
    assets_dir = out / "assets"
    out.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Executing live Sentinel-2 acquisition for bbox {BBOX} across {START} to {END}...")
    decl, session = execute_live_sentinel2_acquisition(
        bbox_wgs84=BBOX,
        start_datetime_utc=START,
        end_datetime_utc=END,
        target_datetime_utc=TARGET,
        cache_root_dir=str(assets_dir),
        max_cloud_cover_pct=20.0,
    )

    if not session.verified_records or any(r.asset_origin.value != "EXTERNAL_DOWNLOAD" for r in session.verified_records.values()):
        raise RuntimeError("Live run did not produce exclusively external assets")

    print(f"[+] Successfully acquired item: {decl.item_id}")
    print(f"[+] Total catalog candidates: {decl.catalog_candidates_count}, eligible: {decl.eligible_candidates_count}")

    # Compute live NDVI from acquired B04 and B08 rasters
    b04_path = Path(session.verified_records["s2_b04"].local_cached_path)
    b08_path = Path(session.verified_records["s2_b08"].local_cached_path)
    scl_path = Path(session.verified_records["s2_scl"].local_cached_path)

    with rasterio.open(b04_path) as src4, rasterio.open(b08_path) as src8:
        b4 = src4.read(1).astype(np.float32)
        b8 = src8.read(1).astype(np.float32)
        profile = src4.profile.copy()
        profile.update(dtype=rasterio.float32, count=1)

        denom = b8 + b4
        denom[denom == 0] = 1e-6
        ndvi = (b8 - b4) / denom

        ndvi_out = out / "real_ndvi.tif"
        with rasterio.open(ndvi_out, "w", **profile) as dst:
            dst.write(ndvi.astype(np.float32), 1)

    # Compute live SCL quality distribution
    with rasterio.open(scl_path) as src_scl:
        scl_data = src_scl.read(1)
        scl_dist = compute_scl_quality_distribution(scl_data)

    # Write SCL distribution metrics JSON
    with open(out / "scl_quality.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "valid_vegetation_pct": scl_dist.valid_vegetation_pct,
                "bare_soil_pct": scl_dist.bare_soil_pct,
                "terrestrial_observable_pct": scl_dist.terrestrial_observable_pct,
                "cloud_pct": scl_dist.cloud_pct,
                "cloud_shadow_pct": scl_dist.cloud_shadow_pct,
                "cloud_contamination_pct": scl_dist.cloud_contamination_pct,
                "snow_ice_pct": scl_dist.snow_ice_pct,
                "water_pct": scl_dist.water_pct,
                "invalid_or_nodata_pct": scl_dist.invalid_or_nodata_pct,
                "scl_terrestrial_observability_contribution": scl_dist.scl_terrestrial_observability_contribution,
                "is_usable_observation": scl_dist.is_usable_observation,
            },
            f,
            indent=2,
        )

    # Write live receipt
    receipt = {
        "status": "LIVE_SATELLITE_ACQUISITION_SUCCESS",
        "stac_item_id": decl.item_id,
        "collection": decl.collection_id,
        "datetime_utc": decl.datetime_utc,
        "cloud_cover_pct": decl.cloud_cover_pct,
        "catalog_candidates": decl.catalog_candidates_count,
        "eligible_candidates": decl.eligible_candidates_count,
        "selection_score": decl.selection_score,
        "ndvi_mean": float(np.nanmean(ndvi)),
        "ndvi_min": float(np.nanmin(ndvi)),
        "ndvi_max": float(np.nanmax(ndvi)),
        "scl_terrestrial_observability": scl_dist.scl_terrestrial_observability_contribution,
    }
    with open(out / "live_receipt.json", "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)

    # Write SHA-256 checksums
    checksums = {}
    for p in out.rglob("*"):
        if p.is_file() and p.name != "checksums.sha256":
            rel = str(p.relative_to(out))
            checksums[rel] = compute_file_sha256(p)

    with open(out / "checksums.sha256", "w", encoding="utf-8") as f:
        for rel_k, h_val in sorted(checksums.items()):
            f.write(f"{h_val}  {rel_k}\n")

    print("[+] Live Sentinel-2 Acquisition Completed Successfully!")
    print(f"[+] Real NDVI mean: {receipt['ndvi_mean']:.4f}, min: {receipt['ndvi_min']:.4f}, max: {receipt['ndvi_max']:.4f}")


if __name__ == "__main__":
    main()
