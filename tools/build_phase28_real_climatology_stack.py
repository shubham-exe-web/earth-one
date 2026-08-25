#!/usr/bin/env python3
"""Build real leave-2022-out Sentinel-2 optical climatology and anomalies with strict SCL masking (Phase 28.1)."""

import json
from pathlib import Path
import numpy as np
import rasterio
from pyproj import Transformer

from earth_one.drought.spatial_harmonization import TargetAnalysisGrid
from earth_one.drought.external_acquisition import (
    STACDiscoveryEngine,
    ExternalSatelliteAcquisitionSession,
    compute_scl_quality_distribution,
)
from earth_one.drought.real_climatology import (
    HistoricalVegetationCompositeRecord,
    build_historical_vegetation_composite,
    compute_leave_out_climatology_and_anomalies,
    get_grid_bounds,
)
from earth_one.drought.data_staging import compute_file_sha256, write_geotiff_raster

# Iowa Corn Belt AOI
BBOX_WGS84 = (-94.25, 41.95, -94.15, 42.05)
TARGET_CRS = "EPSG:32615"
RESOLUTION_M = 100.0

# Define Target Analysis Grid in EPSG:32615
trans = Transformer.from_crs("EPSG:4326", TARGET_CRS, always_xy=True)
min_x, min_y = trans.transform(BBOX_WGS84[0], BBOX_WGS84[1])
max_x, max_y = trans.transform(BBOX_WGS84[2], BBOX_WGS84[3])

# Align to 100m boundary
min_x = np.floor(min_x / RESOLUTION_M) * RESOLUTION_M
min_y = np.floor(min_y / RESOLUTION_M) * RESOLUTION_M
max_x = np.ceil(max_x / RESOLUTION_M) * RESOLUTION_M
max_y = np.ceil(max_y / RESOLUTION_M) * RESOLUTION_M

width = int(round((max_x - min_x) / RESOLUTION_M))
height = int(round((max_y - min_y) / RESOLUTION_M))
geotransform = (min_x, RESOLUTION_M, 0.0, max_y, 0.0, -RESOLUTION_M)

TARGET_GRID = TargetAnalysisGrid(
    crs=TARGET_CRS,
    transform=geotransform,
    width=width,
    height=height,
    pixel_size_x_m=RESOLUTION_M,
    pixel_size_y_m=RESOLUTION_M,
)


def main():
    repo = Path(__file__).resolve().parents[1]
    out_dir = repo / "data" / "drought_raw" / "phase28_iowa_climatology"
    cache_root = out_dir / "cache"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)

    print(f"[*] Target Analysis Grid: shape=({TARGET_GRID.height}, {TARGET_GRID.width}) at {TARGET_GRID.pixel_size_x_m}m in {TARGET_GRID.crs}")
    print(f"[*] Target Bounds: {get_grid_bounds(TARGET_GRID)}")

    discovery = STACDiscoveryEngine()
    
    # 7 historical baseline years + target 2022 (2015 is omitted as Sentinel-2 L2A begins in 2016)
    years = [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023]
    composites: list[HistoricalVegetationCompositeRecord] = []

    for y in years:
        start = f"{y}-07-01T00:00:00Z"
        end = f"{y}-07-31T23:59:59Z"
        target = f"{y}-07-20T00:00:00Z"

        print(f"\n[+] STAC Discovery Query for July {y}...")
        decl = discovery.search_sentinel2_granule(
            bbox_wgs84=BBOX_WGS84,
            start_datetime_utc=start,
            end_datetime_utc=end,
            target_datetime_utc=target,
            max_cloud_cover_pct=25.0,
        )
        print(f"    Selected STAC item: {decl.item_id}")
        print(f"    Acquisition datetime: {decl.datetime_utc}, cloud cover: {decl.cloud_cover_pct:.2f}%")

        # Acquisition session
        session = ExternalSatelliteAcquisitionSession(cache_root_dir=str(cache_root / f"s2_{y}"))
        for band in ("B02", "B04", "B05", "B08", "B11", "SCL"):
            canonical_url = decl.canonical_asset_urls.get(band, decl.asset_urls.get(band, ""))
            session.download_and_register_external_asset(
                product_name=f"s2_{band.lower()}",
                asset_key=f"s2_{band.lower()}",
                remote_source_url=canonical_url,
                remote_asset_id=f"{decl.item_id}_{band}",
                destination_filename=f"s2_{band.lower()}.tif",
                catalog_declaration=decl,
            )

        # Build Historical Vegetation Composite with SCL Masking
        comp = build_historical_vegetation_composite(
            year=y,
            month=7,
            session=session,
            target_grid=TARGET_GRID,
            s2_item_id=decl.item_id,
            datetime_utc=decl.datetime_utc,
            cloud_cover_pct=decl.cloud_cover_pct,
            apply_scl_mask=True,
        )
        composites.append(comp)
        print(f"    [OK] July {y} Composite (SCL-Masked): Mean NDVI={comp.mean_ndvi:.4f}, Valid Pct={comp.valid_pixel_pct:.1f}%, Observability={comp.scl_observability_score:.4f}")

    # Separate target 2022 from baseline years
    target_comp = next(c for c in composites if c.year == 2022)
    baseline_comps = [c for c in composites if c.year != 2022]

    # Compute Leave-2022-Out Climatology and Anomalies
    print("\n[*] Computing Leave-2022-Out Climatology Distributions & Anomalies (7-Year Baseline)...")
    clim_result = compute_leave_out_climatology_and_anomalies(
        target_composite=target_comp,
        baseline_composites=baseline_comps,
        excluded_years=[2022],
        min_valid_baseline_observations=2,
    )

    print(f"[+] Baseline Years: {clim_result.baseline_years} ({len(clim_result.baseline_years)} years)")
    print(f"[+] Excluded Years: {clim_result.excluded_years}")
    print(f"[+] Historical Baseline Mean NDVI: {float(np.nanmean(clim_result.mean_baseline_ndvi)):.4f}")
    print(f"[+] Historical Baseline Std NDVI:  {float(np.nanmean(clim_result.std_baseline_ndvi)):.4f}")
    print(f"[+] Target July 2022 Mean NDVI:    {float(np.nanmean(clim_result.target_ndvi)):.4f}")
    print(f"[+] Standardized NDVI z-anomaly:   {clim_result.mean_target_z_anomaly:.4f} (median: {clim_result.median_target_z_anomaly:.4f})")
    print(f"[+] Vegetation Condition Index:    {clim_result.mean_target_vci:.2f}% (median: {clim_result.median_target_vci:.2f}%)")

    # Write Anomaly GeoTIFFs
    rasters_to_write = {
        "baseline_mean_ndvi.tif": clim_result.mean_baseline_ndvi,
        "baseline_std_ndvi.tif": clim_result.std_baseline_ndvi,
        "baseline_se_ndvi.tif": clim_result.se_baseline_ndvi,
        "baseline_sample_count.tif": clim_result.n_valid_baseline_observations.astype(np.float32),
        "target_2022_ndvi.tif": clim_result.target_ndvi,
        "target_2022_ndvi_z_anomaly.tif": clim_result.standardized_ndvi_anomaly_z,
        "target_2022_standard_error_z.tif": clim_result.standard_error_z,
        "target_2022_vci.tif": clim_result.vegetation_condition_index_vci,
    }
    
    gdal_transform = TARGET_GRID.transform
    for fname, arr in rasters_to_write.items():
        write_geotiff_raster(
            output_path=out_dir / fname,
            data=arr,
            crs=TARGET_GRID.crs,
            transform=gdal_transform,
            nodata_val=-9999.0,
        )

    # Write Climatology Summary JSON
    summary = {
        "target_year": clim_result.target_year,
        "target_month": clim_result.target_month,
        "baseline_years": clim_result.baseline_years,
        "excluded_years": clim_result.excluded_years,
        "historical_baseline_mean_ndvi": float(np.nanmean(clim_result.mean_baseline_ndvi)),
        "historical_baseline_std_ndvi": float(np.nanmean(clim_result.std_baseline_ndvi)),
        "historical_baseline_mean_se": float(np.nanmean(clim_result.se_baseline_ndvi)),
        "target_2022_mean_ndvi": float(np.nanmean(clim_result.target_ndvi)),
        "target_2022_mean_z_anomaly": clim_result.mean_target_z_anomaly,
        "target_2022_median_z_anomaly": clim_result.median_target_z_anomaly,
        "target_2022_mean_standard_error_z": float(np.nanmean(clim_result.standard_error_z)),
        "target_2022_mean_vci": clim_result.mean_target_vci,
        "target_2022_median_vci": clim_result.median_target_vci,
        "target_optical_observability": clim_result.optical_observability_score,
        "yearly_records": [
            {
                "year": c.year,
                "stac_item_id": c.stac_item_id,
                "acquisition_datetime_utc": c.acquisition_datetime_utc,
                "mean_ndvi": c.mean_ndvi,
                "mean_evi": c.mean_evi,
                "mean_ndre": c.mean_ndre,
                "mean_ndwi": c.mean_ndwi,
                "valid_pixel_pct": c.valid_pixel_pct,
                "observability_score": c.scl_observability_score,
            }
            for c in composites
        ],
    }

    with open(out_dir / "climatology_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Write Checksums
    checksums = {}
    for p in out_dir.rglob("*"):
        if p.is_file() and p.name != "checksums.sha256":
            rel = str(p.relative_to(out_dir))
            checksums[rel] = compute_file_sha256(p)

    with open(out_dir / "checksums.sha256", "w", encoding="utf-8") as f:
        for rel_k, h_val in sorted(checksums.items()):
            f.write(f"{h_val}  {rel_k}\n")

    print(f"\n[+] Expanded 7-Year SCL-Masked Climatology stack successfully generated in {out_dir}!")


if __name__ == "__main__":
    main()
