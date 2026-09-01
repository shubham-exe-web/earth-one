#!/usr/bin/env python3
"""Earth One Drought Module 3: Computational Grid Resolution Sensitivity Analysis.

Evaluates operational concordance stability across multiple computational support resolutions (100 m, 500 m, 1 km).
Aggregates the existing Earth One probability surface and the matching USDM reference mask to coarser computational grids,
then calculates comprehensive classification, spatial agreement, and probabilistic calibration metrics.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine

from earth_one.drought.data_staging import compute_file_sha256
from earth_one.drought.real_usdm_reference import (
    Midwest_USDM_POLYGONS,
    compute_comprehensive_validation_metrics,
    rasterize_usdm_for_target_grid,
)
from earth_one.drought.spatial_harmonization import TargetAnalysisGrid


def find_matching_usdm_key(crs_str: str, bounds: rasterio.coords.BoundingBox) -> str:
    """Infer matching USDM historical polygon dataset key from grid spatial reference and bounds."""
    # Check if bounds roughly overlap Iowa (EPSG:32615, easting ~390k-410k, northing ~4.6M-4.7M)
    if "32615" in crs_str:
        return "IOWA_2022_07"
    elif "32616" in crs_str:
        return "ILLINOIS_2022_07"
    elif "32614" in crs_str:
        return "NEBRASKA_2022_07"
    return "IOWA_2022_07"


def block_aggregate_2d(arr: np.ndarray, factor: int, method: str = "mean") -> np.ndarray:
    """Aggregate a 2D array by integer block factor, properly ignoring nodata/NaNs."""
    h, w = arr.shape
    out_h = int(np.ceil(h / factor))
    out_w = int(np.ceil(w / factor))
    out = np.full((out_h, out_w), np.nan, dtype=np.float32)

    for i in range(out_h):
        r_start = i * factor
        r_end = min((i + 1) * factor, h)
        for j in range(out_w):
            c_start = j * factor
            c_end = min((j + 1) * factor, w)
            block = arr[r_start:r_end, c_start:c_end]
            valid = np.isfinite(block)
            if np.any(valid):
                if method == "mean":
                    out[i, j] = float(np.mean(block[valid]))
                elif method == "majority":
                    out[i, j] = 1.0 if (np.mean(block[valid]) >= 0.5) else 0.0
                elif method == "fraction":
                    out[i, j] = float(np.mean(block[valid] >= 0.5))

    return out


def write_geotiff(
    output_path: Path,
    data: np.ndarray,
    crs: Any,
    transform: Affine,
    nodata_val: float = -9999.0,
) -> None:
    """Write 2D numpy array to GeoTIFF."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    h, w = data.shape
    clean_data = np.where(np.isnan(data), nodata_val, data).astype(np.float32)

    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype=rasterio.float32,
        crs=crs,
        transform=transform,
        nodata=nodata_val,
        compress="lzw",
    ) as dst:
        dst.write(clean_data, 1)


def run_grid_sensitivity(
    prob_path: Path,
    usdm_mask_path: Path | None = None,
    threshold: float = 0.25,
    out_csv: Path = Path("audit/grid_resolution_sensitivity.csv"),
    export_rasters_dir: Path | None = Path("audit/rasters"),
) -> list[dict[str, Any]]:
    """Execute computational grid resolution sensitivity analysis across 100 m, 500 m, and 1 km."""
    if not prob_path.exists():
        raise FileNotFoundError(f"Input probability raster not found at: {prob_path}")

    print("=" * 80)
    print("EARTH ONE DROUGHT MODULE 3: COMPUTATIONAL GRID RESOLUTION SENSITIVITY")
    print(f"  Input Probability Raster: {prob_path}")
    print(f"  Classification Threshold: {threshold:.2f}")
    print(f"  Output CSV Destination:   {out_csv}")
    print("=" * 80)

    # 1. Read Native 100 m Probability Raster
    with rasterio.open(prob_path) as src:
        prob_100 = src.read(1).astype(np.float32)
        crs = src.crs
        trans_100 = src.transform
        h_100, w_100 = src.shape
        bounds = src.bounds

    # Create TargetAnalysisGrid representation
    trans_tuple_100 = (trans_100.c, trans_100.a, trans_100.b, trans_100.f, trans_100.d, trans_100.e)
    grid_100 = TargetAnalysisGrid(
        crs=str(crs),
        transform=trans_tuple_100,
        width=w_100,
        height=h_100,
        pixel_size_x_m=trans_100.a,
        pixel_size_y_m=-trans_100.e,
    )

    # 2. Obtain or Rasterize USDM Reference at 100 m
    if usdm_mask_path is not None and usdm_mask_path.exists():
        print(f"[+] Loading provided USDM mask from {usdm_mask_path}...")
        with rasterio.open(usdm_mask_path) as u_src:
            usdm_100_raw = u_src.read(1, out_shape=(h_100, w_100), resampling=Resampling.nearest)
            usdm_100 = (usdm_100_raw > 0).astype(np.float32)
        usdm_src_label = str(usdm_mask_path.name)
    else:
        usdm_key = find_matching_usdm_key(str(crs), bounds)
        print(f"[+] Automatically rasterizing matching USDM reference '{usdm_key}' for target grid...")
        usdm_rec_100 = rasterize_usdm_for_target_grid(
            dataset_key=usdm_key,
            target_grid=grid_100,
            drought_threshold_category="D1_PLUS",
        )
        usdm_100 = usdm_rec_100.binary_drought_mask.astype(np.float32)
        usdm_src_label = f"USDM_VECTOR_{usdm_key}_D1_PLUS"

    # Set up resolutions to analyze
    # Factor: 1 (100m), 5 (500m), 10 (1000m)
    resolutions = [
        {"res_m": 100.0, "factor": 1, "label": "100 m"},
        {"res_m": 500.0, "factor": 5, "label": "500 m"},
        {"res_m": 1000.0, "factor": 10, "label": "1 km"},
    ]

    results = []

    for r_info in resolutions:
        res_m = r_info["res_m"]
        factor = r_info["factor"]
        label = r_info["label"]

        if factor == 1:
            prob_grid = prob_100
            usdm_grid = usdm_100
            trans_grid = trans_100
        else:
            prob_grid = block_aggregate_2d(prob_100, factor=factor, method="mean")
            usdm_grid = block_aggregate_2d(usdm_100, factor=factor, method="mean")
            # Build Affine transform for coarsened grid
            trans_grid = Affine(
                trans_100.a * factor,
                trans_100.b,
                trans_100.c,
                trans_100.d,
                trans_100.e * factor,
                trans_100.f,
            )

        h_g, w_g = prob_grid.shape

        # Valid mask
        valid = np.isfinite(prob_grid) & np.isfinite(usdm_grid)
        total_valid = int(np.sum(valid))

        if total_valid == 0:
            raise RuntimeError(f"No valid overlapping pixels for resolution {label}")

        p_vals = prob_grid[valid]
        # Binary prediction using threshold
        yp_binary = (p_vals >= threshold).astype(bool)
        # Binary truth (majority area fraction >= 0.5)
        yt_binary = (usdm_grid[valid] >= 0.5).astype(bool)

        # Compute comprehensive metrics
        m = compute_comprehensive_validation_metrics(
            y_pred_binary=yp_binary,
            y_prob_continuous=p_vals,
            y_true_binary=yt_binary,
        )

        pred_drought_fraction = float(np.mean(yp_binary))
        ref_drought_fraction = float(np.mean(yt_binary))
        mean_p = float(np.mean(p_vals))

        # Save raster files if requested
        prob_raster_rel = ""
        usdm_raster_rel = ""
        if export_rasters_dir is not None:
            export_rasters_dir.mkdir(parents=True, exist_ok=True)
            res_tag = f"{int(res_m)}m" if res_m < 1000 else "1km"
            prob_file = export_rasters_dir / f"drought_probability_{res_tag}.tif"
            usdm_file = export_rasters_dir / f"usdm_reference_{res_tag}.tif"
            write_geotiff(prob_file, prob_grid, crs, trans_grid)
            write_geotiff(usdm_file, usdm_grid, crs, trans_grid)
            prob_raster_rel = str(prob_file.relative_to(out_csv.parent.parent) if out_csv.parent.parent in prob_file.parents else prob_file)
            usdm_raster_rel = str(usdm_file.relative_to(out_csv.parent.parent) if out_csv.parent.parent in usdm_file.parents else usdm_file)

        prov_str = f"GRID_SENS_{res_m}_{m.f1_score}_{m.iou_jaccard}_{m.brier_score}_{m.expected_calibration_error}"
        prov_hash = hashlib.sha256(prov_str.encode()).hexdigest()

        row = {
            "grid_resolution_m": int(res_m),
            "grid_label": label,
            "grid_dimensions": f"{h_g}x{w_g}",
            "total_pixels": total_valid,
            "decision_threshold": float(threshold),
            "f1_score": m.f1_score,
            "iou_jaccard": m.iou_jaccard,
            "precision": m.precision,
            "recall": m.recall,
            "specificity": m.specificity,
            "brier_score": m.brier_score,
            "expected_calibration_error": m.expected_calibration_error,
            "matthews_corr_coef": m.matthews_corr_coef,
            "predicted_drought_fraction": round(pred_drought_fraction, 6),
            "reference_drought_fraction": round(ref_drought_fraction, 6),
            "mean_earth_one_prob": round(mean_p, 6),
            "usdm_source": usdm_src_label,
            "probability_raster_path": prob_raster_rel,
            "usdm_raster_path": usdm_raster_rel,
            "provenance_hash": prov_hash,
        }
        results.append(row)

        print(
            f"  * [{label:5s}] Grid={h_g:3d}x{w_g:3d} (N={total_valid:5d}) | "
            f"F1={m.f1_score:.4f} | IoU={m.iou_jaccard:.4f} | "
            f"Brier={m.brier_score:.6f} | ECE={m.expected_calibration_error*100.0:5.2f}% | "
            f"Pred Frac={pred_drought_fraction*100:5.1f}% | Ref Frac={ref_drought_fraction*100:5.1f}%"
        )

    # 3. Write Output CSV and JSON
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    out_json = out_csv.with_suffix(".json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(
            {
                "analysis": "GRID_RESOLUTION_SENSITIVITY",
                "methodological_note": "Aggregates the existing Earth One probability surface and matched USDM reference to coarser computational grids (100m, 500m, 1km) to quantify support-scale numerical stability.",
                "threshold": threshold,
                "resolutions_evaluated": [r["grid_label"] for r in results],
                "results": results,
            },
            f,
            indent=2,
        )

    print(f"\n[+] Successfully saved grid resolution sensitivity results to:")
    print(f"    - CSV:  {out_csv}")
    print(f"    - JSON: {out_json}")
    if export_rasters_dir is not None:
        print(f"    - Rasters: {export_rasters_dir}")
    print("=" * 80)

    return results


def main():
    parser = argparse.ArgumentParser(description="Run Earth One Drought Grid Resolution Sensitivity Analysis.")
    parser.add_argument(
        "--probability",
        type=Path,
        default=Path("data/drought_raw/phase29_scientific_release/drought_probability.tif"),
        help="Path to input 100m Earth One drought probability GeoTIFF.",
    )
    parser.add_argument(
        "--usdm-mask",
        type=Path,
        default=None,
        help="Optional path to matching USDM reference binary mask GeoTIFF.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.25,
        help="Decision threshold for binary drought classification (default: 0.25).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("audit/grid_resolution_sensitivity.csv"),
        help="Path to output CSV file (default: audit/grid_resolution_sensitivity.csv).",
    )
    parser.add_argument(
        "--export-rasters-dir",
        type=Path,
        default=Path("audit/rasters"),
        help="Directory to save coarsened GeoTIFF rasters (default: audit/rasters).",
    )
    args = parser.parse_args()

    # Resolve relative paths with respect to repository root
    repo = Path(__file__).resolve().parent
    prob_p = args.probability if args.probability.is_absolute() else (repo / args.probability)
    usdm_p = (args.usdm_mask if args.usdm_mask.is_absolute() else (repo / args.usdm_mask)) if args.usdm_mask else None
    out_p = args.out if args.out.is_absolute() else (repo / args.out)
    rasters_dir = (args.export_rasters_dir if args.export_rasters_dir.is_absolute() else (repo / args.export_rasters_dir)) if args.export_rasters_dir else None

    run_grid_sensitivity(
        prob_path=prob_p,
        usdm_mask_path=usdm_p,
        threshold=args.threshold,
        out_csv=out_p,
        export_rasters_dir=rasters_dir,
    )


if __name__ == "__main__":
    main()
