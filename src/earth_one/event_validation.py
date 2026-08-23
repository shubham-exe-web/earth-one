from __future__ import annotations

"""Hazard-Independent Event Validation & Thermal Corroboration Framework for Earth One.

Provides:
- Ingestion and grid harmonization for raster, GeoJSON vector, and point references
- Extraction of 8-connected raster-objects
- Optimal 1-to-1 maximum-weight bipartite IoU matching (scipy.optimize.linear_sum_assignment)
- Decoupled pixel-level, object-level, area-level, and size-stratified metrics
- Point-to-event boundary distance and temporal-lag active fire corroboration (NASA FIRMS)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from datetime import datetime
import json

import numpy as np
import rasterio
from rasterio import features as rfeatures
from rasterio.warp import reproject, Resampling
from scipy import ndimage
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree
from pyproj import Geod


@dataclass(frozen=True)
class EventValidationConfig:
    """Configuration parameters for event matching and validation."""
    hazard_type: str = "disturbance"
    reference_source: str = "independent_reference"
    primary_iou_threshold: float = 0.10
    iou_thresholds: tuple[float, ...] = (0.05, 0.10, 0.20, 0.50)
    min_alarm_pixels: int = 4
    connectivity: int = 8  # 4 or 8
    small_event_max_ha: float = 0.70
    medium_event_max_ha: float = 3.50


def _calculate_geodetic_pixel_area(profile: dict[str, Any]) -> tuple[float, float]:
    """Calculate total AOI area in km² and per-pixel area in hectares."""
    width = profile["width"]
    height = profile["height"]
    transform = profile["transform"]

    left = transform[2]
    top = transform[5]
    right = left + transform[0] * width
    bottom = top + transform[4] * height

    geod = Geod(ellps="WGS84")
    lons = [left, right, right, left, left]
    lats = [bottom, bottom, top, top, bottom]
    area_m2, _ = geod.polygon_area_perimeter(lons, lats)
    total_km2 = abs(area_m2) / 1e6
    total_ha = abs(area_m2) / 1e4
    pixel_ha = total_ha / (width * height)
    return float(total_km2), float(pixel_ha)


def ingest_reference_mask(
    reference_source: str | Path | dict | list | np.ndarray,
    target_profile: dict[str, Any],
    valid_mask: np.ndarray | None = None,
) -> np.ndarray:
    """
    Ingest a reference source and reproject/rasterize it onto the target grid.
    
    Supports:
    - Path to GeoTIFF raster (reprojects with nearest-neighbor if grids differ)
    - GeoJSON dictionary, FeatureCollection, or list of geometries (rasterizes polygons)
    - Boolean/uint8 numpy array matching target dimensions
    """
    height = target_profile["height"]
    width = target_profile["width"]

    if isinstance(reference_source, np.ndarray):
        if reference_source.shape != (height, width):
            raise ValueError(f"Array shape {reference_source.shape} does not match target grid ({height}, {width})")
        mask = reference_source.astype(bool)
        if valid_mask is not None:
            mask = mask & valid_mask.astype(bool)
        return mask

    if isinstance(reference_source, (str, Path)):
        p = Path(reference_source)
        if not p.exists():
            raise FileNotFoundError(f"Reference source file not found: {p}")

        if p.suffix.lower() in [".tif", ".tiff", ".geotiff"]:
            with rasterio.open(p) as src:
                if (
                    src.width == width
                    and src.height == height
                    and src.crs == target_profile["crs"]
                    and src.transform == target_profile["transform"]
                ):
                    raw_data = src.read(1)
                    mask = (raw_data > 0) & (raw_data != 255)
                else:
                    dest = np.zeros((height, width), dtype=np.uint8)
                    reproject(
                        source=rasterio.band(src, 1),
                        destination=dest,
                        src_transform=src.transform,
                        src_crs=src.crs,
                        dst_transform=target_profile["transform"],
                        dst_crs=target_profile["crs"],
                        resampling=Resampling.nearest,
                    )
                    mask = (dest > 0) & (dest != 255)
            if valid_mask is not None:
                mask = mask & valid_mask.astype(bool)
            return mask

        if p.suffix.lower() in [".json", ".geojson"]:
            content = json.loads(p.read_text(encoding="utf-8"))
            return ingest_reference_mask(content, target_profile, valid_mask)

        raise ValueError(f"Unsupported reference file extension: {p.suffix}")

    if isinstance(reference_source, dict):
        shapes = []
        if reference_source.get("type") == "FeatureCollection":
            for feat in reference_source.get("features", []):
                geom = feat.get("geometry")
                if geom:
                    shapes.append(geom)
        elif reference_source.get("type") in ["Feature"]:
            geom = reference_source.get("geometry")
            if geom:
                shapes.append(geom)
        elif "coordinates" in reference_source:
            shapes.append(reference_source)

        if not shapes:
            mask = np.zeros((height, width), dtype=bool)
        else:
            rasterized = rfeatures.rasterize(
                shapes=((s, 1) for s in shapes),
                out_shape=(height, width),
                transform=target_profile["transform"],
                fill=0,
                default_value=1,
                dtype=np.uint8,
            )
            mask = rasterized.astype(bool)
        if valid_mask is not None:
            mask = mask & valid_mask.astype(bool)
        return mask

    raise TypeError(f"Unsupported reference source type: {type(reference_source)}")


def evaluate_event_detection(
    predicted_binary_grid: np.ndarray,
    reference_binary_grid: np.ndarray,
    target_profile: dict[str, Any],
    valid_mask: np.ndarray | None = None,
    config: EventValidationConfig | None = None,
) -> dict[str, Any]:
    """
    Execute full hazard-independent validation:
    1. Pixel-level confusion matrix & classification metrics.
    2. 8-connected raster-object extraction for reference and alarm bodies.
    3. Minimum alarm size filtering.
    4. Optimal 1-to-1 maximum-weight bipartite IoU matching (linear_sum_assignment).
    5. Size-stratified event recall and geographic area accounting.
    """
    cfg = config or EventValidationConfig()
    height = target_profile["height"]
    width = target_profile["width"]

    if valid_mask is None:
        valid_mask = np.ones((height, width), dtype=bool)
    else:
        valid_mask = valid_mask.astype(bool)

    pred = predicted_binary_grid.astype(bool) & valid_mask
    ref = reference_binary_grid.astype(bool) & valid_mask

    total_km2, pixel_ha = _calculate_geodetic_pixel_area(target_profile)
    valid_count = int(np.count_nonzero(valid_mask))

    # --- 1. Pixel-Level Accounting ---
    tp_pix = int(np.count_nonzero(pred & ref))
    fp_pix = int(np.count_nonzero(pred & ~ref))
    fn_pix = int(np.count_nonzero(~pred & ref))
    tn_pix = int(np.count_nonzero(~pred & ~ref & valid_mask))

    pixel_prec = float(tp_pix / (tp_pix + fp_pix)) if (tp_pix + fp_pix) > 0 else 0.0
    pixel_rec = float(tp_pix / (tp_pix + fn_pix)) if (tp_pix + fn_pix) > 0 else 0.0
    pixel_f1 = float(2 * pixel_prec * pixel_rec / (pixel_prec + pixel_rec)) if (pixel_prec + pixel_rec) > 0 else 0.0
    
    denom_mcc = np.sqrt(float((tp_pix + fp_pix) * (tp_pix + fn_pix) * (tn_pix + fp_pix) * (tn_pix + fn_pix)))
    pixel_mcc = float(((tp_pix * tn_pix) - (fp_pix * fn_pix)) / denom_mcc) if denom_mcc > 0 else 0.0

    pixel_metrics = {
        "valid_pixels": valid_count,
        "prevalence": float(np.count_nonzero(ref) / valid_count) if valid_count > 0 else 0.0,
        "true_positives": tp_pix,
        "false_positives": fp_pix,
        "false_negatives": fn_pix,
        "true_negatives": tn_pix,
        "precision": pixel_prec,
        "recall": pixel_rec,
        "f1": pixel_f1,
        "mcc": pixel_mcc,
        "true_positive_area_ha": tp_pix * pixel_ha,
        "false_positive_area_ha": fp_pix * pixel_ha,
        "false_negative_area_ha": fn_pix * pixel_ha,
    }

    # --- 2. Raster-Object Segmentation ---
    struct = ndimage.generate_binary_structure(2, 2 if cfg.connectivity == 8 else 1)

    # Reference objects
    lbl_ref, num_ref = ndimage.label(ref, structure=struct)
    if num_ref > 0:
        ref_sizes = ndimage.sum(ref, lbl_ref, range(1, num_ref + 1)).astype(int)
    else:
        ref_sizes = np.array([], dtype=int)
    ref_areas_ha = ref_sizes * pixel_ha

    # Predicted alarms
    lbl_pred_raw, num_pred_raw = ndimage.label(pred, structure=struct)
    if num_pred_raw > 0 and cfg.min_alarm_pixels > 1:
        p_sizes_raw = ndimage.sum(pred, lbl_pred_raw, range(1, num_pred_raw + 1)).astype(int)
        keep = np.isin(lbl_pred_raw, np.where(p_sizes_raw >= cfg.min_alarm_pixels)[0] + 1)
        pred_filtered = pred & keep
        lbl_pred, num_pred = ndimage.label(pred_filtered, structure=struct)
        p_sizes = ndimage.sum(pred_filtered, lbl_pred, range(1, num_pred + 1)).astype(int)
    else:
        pred_filtered = pred
        lbl_pred, num_pred = lbl_pred_raw, num_pred_raw
        if num_pred > 0:
            p_sizes = ndimage.sum(pred, lbl_pred, range(1, num_pred + 1)).astype(int)
        else:
            p_sizes = np.array([], dtype=int)

    # Size-stratified reference masks
    small_ref = (ref_areas_ha < cfg.small_event_max_ha)
    med_ref = (ref_areas_ha >= cfg.small_event_max_ha) & (ref_areas_ha < cfg.medium_event_max_ha)
    large_ref = (ref_areas_ha >= cfg.medium_event_max_ha)

    # --- 3. Optimal Bipartite IoU Assignment ---
    overlap_mask = (lbl_pred > 0) & (lbl_ref > 0)
    p_inter = lbl_pred[overlap_mask]
    r_inter = lbl_ref[overlap_mask]

    intersections: dict[tuple[int, int], int] = {}
    for p_id, r_id in zip(p_inter, r_inter):
        pair = (int(p_id), int(r_id))
        intersections[pair] = intersections.get(pair, 0) + 1

    iou_matrix: dict[tuple[int, int], float] = {}
    for (p_id, r_id), inter_px in intersections.items():
        p_px = p_sizes[p_id - 1]
        r_px = ref_sizes[r_id - 1]
        union_px = p_px + r_px - inter_px
        iou_matrix[(p_id, r_id)] = float(inter_px / union_px)

    object_results_by_tau = {}

    for tau in cfg.iou_thresholds:
        valid_pairs = [(p_id, r_id, iou) for (p_id, r_id), iou in iou_matrix.items() if iou >= tau]

        if not valid_pairs or num_pred == 0 or num_ref == 0:
            matched_p: set[int] = set()
            matched_r: set[int] = set()
            matched_ious: list[float] = []
        else:
            active_p = sorted(list(set(p for p, _, _ in valid_pairs)))
            active_r = sorted(list(set(r for _, r, _ in valid_pairs)))
            p_to_idx = {p: i for i, p in enumerate(active_p)}
            r_to_idx = {r: j for j, r in enumerate(active_r)}

            cost = np.full((len(active_p), len(active_r)), 1000.0, dtype=np.float64)
            for p_id, r_id, iou in valid_pairs:
                cost[p_to_idx[p_id], r_to_idx[r_id]] = -iou

            row_ind, col_ind = linear_sum_assignment(cost)
            matched_p = set()
            matched_r = set()
            matched_ious = []

            for r_idx, c_idx in zip(row_ind, col_ind):
                if cost[r_idx, c_idx] < 0:
                    matched_p.add(active_p[r_idx])
                    matched_r.add(active_r[c_idx])
                    matched_ious.append(-cost[r_idx, c_idx])

        n_matched = len(matched_ious)
        obj_prec = float(n_matched / num_pred) if num_pred > 0 else 0.0
        obj_rec = float(n_matched / num_ref) if num_ref > 0 else 0.0
        obj_f1 = float(2 * obj_prec * obj_rec / (obj_prec + obj_rec)) if (obj_prec + obj_rec) > 0 else 0.0

        matched_r_arr = np.array([r_id in matched_r for r_id in range(1, num_ref + 1)]) if num_ref > 0 else np.array([], dtype=bool)
        rec_s = float(np.mean(matched_r_arr[small_ref])) if np.any(small_ref) else 0.0
        rec_m = float(np.mean(matched_r_arr[med_ref])) if np.any(med_ref) else 0.0
        rec_l = float(np.mean(matched_r_arr[large_ref])) if np.any(large_ref) else 0.0

        matched_ref_area = float(np.sum(ref_areas_ha[matched_r_arr])) if len(matched_r_arr) else 0.0
        missed_ref_area = float(np.sum(ref_areas_ha[~matched_r_arr])) if len(matched_r_arr) else 0.0
        
        alarm_p_arr = np.array([p_id in matched_p for p_id in range(1, num_pred + 1)]) if num_pred > 0 else np.array([], dtype=bool)
        false_alarm_area = float(np.sum(p_sizes[~alarm_p_arr] * pixel_ha)) if len(alarm_p_arr) else 0.0

        object_results_by_tau[f"tau_{tau:.2f}"] = {
            "tau_iou_threshold": tau,
            "matched_events": n_matched,
            "object_precision": obj_prec,
            "object_recall": obj_rec,
            "object_f1": obj_f1,
            "mean_matched_iou": float(np.mean(matched_ious)) if matched_ious else 0.0,
            "median_matched_iou": float(np.median(matched_ious)) if matched_ious else 0.0,
            "size_stratified_recall": {
                f"small_events_lt_{cfg.small_event_max_ha:.2f}ha": rec_s,
                f"medium_events_{cfg.small_event_max_ha:.2f}_to_{cfg.medium_event_max_ha:.2f}ha": rec_m,
                f"large_events_ge_{cfg.medium_event_max_ha:.2f}ha": rec_l,
            },
            "area_metrics_ha": {
                "matched_reference_area_ha": matched_ref_area,
                "missed_reference_area_ha": missed_ref_area,
                "false_alarm_area_ha": false_alarm_area,
            }
        }

    return {
        "hazard_type": cfg.hazard_type,
        "reference_source": cfg.reference_source,
        "aoi_extent": {
            "total_area_km2": total_km2,
            "total_area_ha": total_km2 * 100.0,
            "pixel_area_m2": pixel_ha * 10000.0,
            "width": width,
            "height": height,
            "crs": str(target_profile["crs"]),
            "transform": list(target_profile["transform"]),
        },
        "event_summary": {
            "total_reference_objects": int(num_ref),
            "total_predicted_alarms": int(num_pred),
            "filtered_alarms_count": int(num_pred_raw - num_pred) if num_pred_raw > num_pred else 0,
            "primary_match_criterion": f"tau_{cfg.primary_iou_threshold:.2f}",
        },
        "pixel_metrics": pixel_metrics,
        "object_metrics_by_iou": object_results_by_tau,
    }


def evaluate_point_event_corroboration(
    predicted_binary_grid: np.ndarray,
    point_records: list[dict[str, Any]],
    target_profile: dict[str, Any],
    valid_mask: np.ndarray | None = None,
    spatial_tolerance_meters: Sequence[float] = (375.0, 500.0, 1000.0),
    min_alarm_pixels: int = 4,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    Evaluate spatial-temporal active-fire corroboration (NASA FIRMS / VIIRS / MODIS)
    against Earth One predicted disturbance objects.
    
    Provides:
    1. Point-to-event boundary distance (minimum distance from FIRMS point to ANY alarm pixel).
    2. Centroid distance matching.
    3. Temporal-lag stratification (0–30d, 31–90d, 91–180d, 181–365d from anchor date).
    4. FRP and confidence stratification.
    """
    height = target_profile["height"]
    width = target_profile["width"]
    transform = target_profile["transform"]

    if valid_mask is None:
        valid_mask = np.ones((height, width), dtype=bool)
    else:
        valid_mask = valid_mask.astype(bool)

    pred = predicted_binary_grid.astype(bool) & valid_mask
    struct_8 = ndimage.generate_binary_structure(2, 2)

    lbl_pred_raw, num_pred_raw = ndimage.label(pred, structure=struct_8)
    if num_pred_raw > 0 and min_alarm_pixels > 1:
        p_sizes_raw = ndimage.sum(pred, lbl_pred_raw, range(1, num_pred_raw + 1)).astype(int)
        keep = np.isin(lbl_pred_raw, np.where(p_sizes_raw >= min_alarm_pixels)[0] + 1)
        pred_filtered = pred & keep
        lbl_pred, num_pred = ndimage.label(pred_filtered, structure=struct_8)
    else:
        pred_filtered = pred
        lbl_pred, num_pred = lbl_pred_raw, num_pred_raw

    # Extract all alarm pixel coordinates (for exact boundary/pixel distance)
    alarm_pixel_rows, alarm_pixel_cols = np.where(pred_filtered)
    if len(alarm_pixel_rows) > 0:
        alarm_px_lons = transform[2] + alarm_pixel_cols * transform[0]
        alarm_px_lats = transform[5] + alarm_pixel_rows * transform[4]
        alarm_pixels_arr = np.column_stack([alarm_px_lons, alarm_px_lats])
        alarm_pixel_labels = lbl_pred[alarm_pixel_rows, alarm_pixel_cols]
    else:
        alarm_pixels_arr = np.empty((0, 2))
        alarm_pixel_labels = np.empty((0,), dtype=int)

    # Filter point records by temporal window
    filtered_points = []
    anchor_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None

    for pt in point_records:
        d_str = pt.get("acq_date", "")
        if start_date and d_str < start_date:
            continue
        if end_date and d_str > end_date:
            continue
        
        # Calculate lag days from anchor date
        pt_copy = dict(pt)
        if anchor_dt and d_str:
            try:
                pt_dt = datetime.strptime(d_str, "%Y-%m-%d")
                pt_copy["lag_days"] = (pt_dt - anchor_dt).days
            except ValueError:
                pt_copy["lag_days"] = None
        else:
            pt_copy["lag_days"] = None
        filtered_points.append(pt_copy)

    if not filtered_points or num_pred == 0:
        return {
            "total_predicted_alarms": int(num_pred),
            "total_active_fire_points": len(filtered_points),
            "corroboration_by_radius": {},
            "temporal_lag_breakdown": {},
        }

    pt_lons = np.array([float(p["longitude"]) for p in filtered_points])
    pt_lats = np.array([float(p["latitude"]) for p in filtered_points])
    pt_coords_arr = np.column_stack([pt_lons, pt_lats])

    mean_lat_rad = np.radians(float(np.mean(pt_lats))) if len(pt_lats) > 0 else np.radians(22.375)
    meters_per_deg_lat = 110750.0
    meters_per_deg_lon = 111320.0 * np.cos(mean_lat_rad)

    def to_metric(coords):
        return np.column_stack([coords[:, 0] * meters_per_deg_lon, coords[:, 1] * meters_per_deg_lat])

    metric_pts = to_metric(pt_coords_arr)
    metric_tree_pts = cKDTree(metric_pts)

    metric_alarm_pixels = to_metric(alarm_pixels_arr)
    metric_tree_alarm_pixels = cKDTree(metric_alarm_pixels)

    # 1. Point-to-Event Minimum Pixel Distance
    dists_pt_to_alarm, nearest_px_idx = metric_tree_alarm_pixels.query(metric_pts, k=1)
    
    # Map each point to the closest alarm object ID
    closest_alarm_id_per_pt = alarm_pixel_labels[nearest_px_idx]

    corroboration_by_radius = {}

    for rad_m in spatial_tolerance_meters:
        # Recovered active fire points within rad_m of ANY alarm pixel
        pt_recovered_mask = (dists_pt_to_alarm <= rad_m)
        num_recovered_pts = int(np.count_nonzero(pt_recovered_mask))
        hotspot_recovery_rate = float(num_recovered_pts / len(filtered_points))

        # Alarm objects that have at least one recovered active fire point
        corroborated_alarm_ids = set(closest_alarm_id_per_pt[pt_recovered_mask])
        num_corroborated_alarms = len(corroborated_alarm_ids)
        alarm_corroboration_rate = float(num_corroborated_alarms / num_pred) if num_pred > 0 else 0.0

        frp_vals = np.array([float(p.get("frp", 0.0)) for p in filtered_points])
        high_frp = (frp_vals >= 5.0)
        rec_high_frp = float(np.mean(pt_recovered_mask[high_frp])) if np.any(high_frp) else 0.0

        corroboration_by_radius[f"radius_{int(rad_m)}m"] = {
            "tolerance_radius_meters": float(rad_m),
            "corroborated_alarm_objects": num_corroborated_alarms,
            "total_predicted_alarms": int(num_pred),
            "alarm_corroboration_rate": alarm_corroboration_rate,
            "recovered_active_fire_points": num_recovered_pts,
            "total_active_fire_points": len(filtered_points),
            "hotspot_recovery_rate": hotspot_recovery_rate,
            "high_frp_ge_5mw_recovery_rate": rec_high_frp,
        }

    # Temporal-lag breakdown (evaluated at primary 375m radius)
    lag_bins = {
        "lag_0_to_30_days": (0, 30),
        "lag_31_to_90_days": (31, 90),
        "lag_91_to_180_days": (91, 180),
        "lag_181_to_365_days": (181, 365),
    }
    temporal_lag_breakdown = {}
    pt_recovered_375 = (dists_pt_to_alarm <= 375.0)
    lags = np.array([p.get("lag_days") if p.get("lag_days") is not None else -1 for p in filtered_points])

    for bin_name, (min_d, max_d) in lag_bins.items():
        bin_mask = (lags >= min_d) & (lags <= max_d)
        n_in_bin = int(np.count_nonzero(bin_mask))
        if n_in_bin > 0:
            rec_in_bin = float(np.mean(pt_recovered_375[bin_mask]))
        else:
            rec_in_bin = 0.0
        temporal_lag_breakdown[bin_name] = {
            "interval_days": f"{min_d}-{max_d}",
            "total_points_in_interval": n_in_bin,
            "recovery_rate_at_375m": rec_in_bin,
        }

    return {
        "validation_type": "spatial_temporal_active_fire_corroboration",
        "reference_source": "nasa_firms_viirs",
        "temporal_window": {
            "start_date": start_date,
            "end_date": end_date,
            "total_points_in_window": len(filtered_points),
        },
        "total_predicted_alarms": int(num_pred),
        "corroboration_by_radius": corroboration_by_radius,
        "temporal_lag_breakdown": temporal_lag_breakdown,
    }
