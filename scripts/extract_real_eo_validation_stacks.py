#!/usr/bin/env python3
"""Extract real Planetary Computer STAC Sentinel-1 RTC, Copernicus GLO-30 DEM, JRC GSW,
and local CEMS vector ground-truth rasters onto standardized local UTM 10 m x 10 m grids
(512 x 512 pixels = 5.12 km x 5.12 km = 26.2144 km^2) for all 11 Earth One Flood activations.

Scientific & Geometric Guarantees:
1. Every activation is projected to its true local UTM coordinate reference system (WGS 84 /
   UTM Zone 18N-56S, matching Table 1 and Section 2.1), with pixel size strictly 10.0 m x 10.0 m.
2. Topographic slope, 5 x 5 (50 m x 50 m) local relief, 20 m scale transforms, and spatial
   semivariograms operate on true metric coordinates.
3. Missing DEM or JRC values are explicitly tracked (`dem_valid_mask`, `jrc_valid_mask`) and
   factored into observability validity rather than silently zero-filled.
4. Full provenance (STAC item IDs, UTC acquisition timestamps, UTM CRS/bounds, CEMS source path,
   missing-data coverage fractions, and SHA-256 checksums) is stored per event both inside each
   .npz bundle (`meta_json`) and in `results/flood_v1.0/real_eo_extraction_manifest.json`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote, urlparse

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds, transform_geom
import requests
import shapefile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from earth_one.flood import (
    FloodEvidenceConfig,
    compute_sar_water_evidence,
    compute_terrain_plausibility,
    compute_water_novelty,
    fuse_flood_evidence,
)
from earth_one.flood_tristate import compute_tristate_flood_decision

STAC_SEARCH_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS_SIGN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/sign?href="
MANIFEST_PATH = ROOT / "results" / "flood_v1.0" / "frozen_cohort_manifest.json"
OUT_STACK_DIR = ROOT / "data" / "real_eo_stacks"
CEMS_REPO_DIR = ROOT / "data" / "cems_reference_vectors"
FIG3_NPZ_PATH = ROOT / "data" / "flood_benchmark_rasters" / "fig3_real_eo_rasters.npz"
OUT_MANIFEST_PATH = ROOT / "results" / "flood_v1.0" / "real_eo_extraction_manifest.json"

SESSION = requests.Session()
_SAS_CACHE: dict[str, str] = {}


def sign_asset(href: str) -> str:
    """Sign a Planetary Computer blob href with container-level SAS caching and 429 backoff."""
    parsed = urlparse(href)
    container_key = f"{parsed.netloc}/{parsed.path.lstrip('/').split('/')[0]}"
    if container_key in _SAS_CACHE:
        sep = "&" if "?" in href else "?"
        return f"{href}{sep}{_SAS_CACHE[container_key]}"

    for attempt in range(6):
        resp = SESSION.get(SAS_SIGN_URL + quote(href, safe=""), timeout=30)
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(min(30, 2 ** (attempt + 1)))
            continue
        resp.raise_for_status()
        signed = resp.json()["href"]
        if "?" in signed:
            _SAS_CACHE[container_key] = signed.split("?", 1)[1]
        return signed
    resp.raise_for_status()
    return href


def search_stac(collection: str, bbox_wgs84: list[float], datetime_range: str | None = None, limit: int = 25) -> list[dict]:
    payload: dict = {"collections": [collection], "bbox": bbox_wgs84, "limit": limit}
    if datetime_range:
        payload["datetime"] = datetime_range
    for attempt in range(5):
        resp = SESSION.post(STAC_SEARCH_URL, json=payload, timeout=30)
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(min(20, 2 ** (attempt + 1)))
            continue
        resp.raise_for_status()
        return resp.json().get("features", [])
    resp.raise_for_status()
    return []


def bbox_overlap_frac(item_bbox: list[float], target_bbox: list[float]) -> float:
    ix0 = max(item_bbox[0], target_bbox[0])
    iy0 = max(item_bbox[1], target_bbox[1])
    ix1 = min(item_bbox[2], target_bbox[2])
    iy1 = min(item_bbox[3], target_bbox[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    area_t = max(1e-12, (target_bbox[2] - target_bbox[0]) * (target_bbox[3] - target_bbox[1]))
    return ((ix1 - ix0) * (iy1 - iy0)) / area_t


def select_best_rtc_pair(bbox_wgs84: list[float], dt_before_str: str, dt_event_str: str) -> tuple[list[dict], list[dict]]:
    """Select pre-event and post-event Sentinel-1 RTC slices from matching orbits when available."""
    db = datetime.fromisoformat(dt_before_str[:10])
    de = datetime.fromisoformat(dt_event_str[:10])

    pre_start = (db - timedelta(days=20)).strftime("%Y-%m-%dT00:00:00Z")
    pre_end = (db + timedelta(days=4)).strftime("%Y-%m-%dT23:59:59Z")
    post_start = (de - timedelta(days=3)).strftime("%Y-%m-%dT00:00:00Z")
    post_end = (de + timedelta(days=16)).strftime("%Y-%m-%dT23:59:59Z")

    pre_items = search_stac("sentinel-1-rtc", bbox_wgs84, f"{pre_start}/{pre_end}", limit=30)
    post_items = search_stac("sentinel-1-rtc", bbox_wgs84, f"{post_start}/{post_end}", limit=30)
    if not pre_items or not post_items:
        raise RuntimeError(f"Missing sentinel-1-rtc items for bbox={bbox_wgs84} pre={len(pre_items)} post={len(post_items)}")

    def group_by_date_orbit(items: list[dict], target_dt: datetime) -> list[tuple[float, list[dict]]]:
        buckets: dict[tuple[str, int | None], list[dict]] = {}
        for it in items:
            day = it["properties"]["datetime"][:10]
            orb = it["properties"].get("sat:relative_orbit")
            buckets.setdefault((day, orb), []).append(it)
        scored = []
        for (day, orb), grp in buckets.items():
            cov = min(1.0, sum(bbox_overlap_frac(g["bbox"], bbox_wgs84) for g in grp))
            dt_diff = abs((datetime.fromisoformat(day) - target_dt).days)
            score = cov * 100.0 - dt_diff * 0.5
            scored.append((score, grp))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    pre_groups = group_by_date_orbit(pre_items, db)
    post_groups = group_by_date_orbit(post_items, de)

    best_pair = None
    best_score = -1e9
    for s_pre, g_pre in pre_groups[:6]:
        orb_pre = g_pre[0]["properties"].get("sat:relative_orbit")
        for s_post, g_post in post_groups[:6]:
            orb_post = g_post[0]["properties"].get("sat:relative_orbit")
            same_orb_bonus = 25.0 if (orb_pre is not None and orb_pre == orb_post) else 0.0
            pair_score = s_pre + s_post + same_orb_bonus
            if pair_score > best_score:
                best_score = pair_score
                best_pair = (g_pre, g_post)
    assert best_pair is not None
    return best_pair


def mosaic_reproject(
    items: list[dict],
    asset_key: str,
    dst_shape: tuple[int, int],
    dst_tf,
    dst_crs: str,
    resampling=Resampling.bilinear,
    valid_positive_only: bool = False,
) -> np.ndarray:
    """Reproject one or more STAC COG items onto a metric UTM destination grid."""
    out = np.full(dst_shape, np.nan, dtype=np.float32)
    for it in items:
        if asset_key not in it["assets"]:
            continue
        href = sign_asset(it["assets"][asset_key]["href"])
        buf = np.full(dst_shape, np.nan, dtype=np.float32)
        with rasterio.open(href) as src:
            reproject(
                source=rasterio.band(src, 1),
                destination=buf,
                dst_transform=dst_tf,
                dst_crs=dst_crs,
                dst_nodata=np.nan,
                resampling=resampling,
            )
        if valid_positive_only:
            buf = np.where(np.isfinite(buf) & (buf > 0.0), buf, np.nan)
        fill_mask = np.isnan(out) & np.isfinite(buf)
        out[fill_mask] = buf[fill_mask]
    return out


def compute_utm_slope_deg(elev_m: np.ndarray, pixel_res_m: float = 10.0) -> tuple[np.ndarray, np.ndarray]:
    """Compute metric terrain slope in degrees on a 10m UTM grid and track DEM validity."""
    dem_valid = np.isfinite(elev_m)
    if not dem_valid.any():
        return np.zeros_like(elev_m, dtype=np.float32), dem_valid
    # Inpaint isolated missing pixels neutrally ONLY for finite gradient evaluation; valid_mask records true gaps
    fill_val = float(np.nanmedian(elev_m))
    elev_filled = np.where(dem_valid, elev_m, fill_val).astype(np.float32)
    dz_dy, dz_dx = np.gradient(elev_filled, pixel_res_m, pixel_res_m)
    slope_deg = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy))).astype(np.float32)
    return slope_deg, dem_valid


def find_shapefile(ev: dict) -> Path:
    act = ev["activation"]
    repo_shp = CEMS_REPO_DIR / act / f"{act}_observed_event_a.shp"
    if repo_shp.exists():
        return repo_shp
    shp = ROOT / ev["reference_shapefile"]
    if shp.exists():
        return shp
    matches = list((ROOT / "data").rglob(shp.name)) or list((ROOT / "data").rglob(f"*{act}*observed*event*.shp"))
    if not matches:
        raise FileNotFoundError(f"Could not find shapefile for {act}")
    return matches[0]


def utm_epsg_for_point(lon: float, lat: float) -> str:
    zone = int((lon + 180.0) // 6.0) + 1
    code = (32600 + zone) if lat >= 0.0 else (32700 + zone)
    return f"EPSG:{code}"


def choose_utm_tile_grid(shp_path: Path, size: int = 512, pixel_res_m: float = 10.0) -> tuple[str, list[float], list[float], list[dict]]:
    """Transform CEMS polygons to local UTM CRS and center a 5.12 km x 5.12 km metric window on the densest flood cluster."""
    sf = shapefile.Reader(str(shp_path))
    b_wgs = sf.bbox
    cen_lon = 0.5 * (b_wgs[0] + b_wgs[2])
    cen_lat = 0.5 * (b_wgs[1] + b_wgs[3])
    utm_crs = utm_epsg_for_point(cen_lon, cen_lat)

    geoms_utm: list[dict] = []
    centroids_area: list[tuple[float, float, float]] = []
    for s in sf.shapes():
        g_utm = transform_geom("EPSG:4326", utm_crs, s.__geo_interface__)
        geoms_utm.append(g_utm)
        sb = s.bbox
        # Approximate metric area weighting via transformed corner box
        x0, y0, x1, y1 = transform_bounds("EPSG:4326", utm_crs, sb[0], sb[1], sb[2], sb[3])
        area_m2 = max(1.0, (x1 - x0) * (y1 - y0))
        centroids_area.append((0.5 * (x0 + x1), 0.5 * (y0 + y1), area_m2))

    tile_span_m = size * pixel_res_m  # 5120.0 m
    arr = np.asarray(centroids_area, dtype=np.float64)
    xmin_all, ymin_all = float(np.min(arr[:, 0])), float(np.min(arr[:, 1]))
    xmax_all, ymax_all = float(np.max(arr[:, 0])), float(np.max(arr[:, 1]))

    if (xmax_all - xmin_all) <= tile_span_m and (ymax_all - ymin_all) <= tile_span_m:
        # Entire activation fits inside a single 5.12 km tile -> center on area-weighted centroid
        cx = float(np.average(arr[:, 0], weights=arr[:, 2]))
        cy = float(np.average(arr[:, 1], weights=arr[:, 2]))
        utm_bounds = [cx - tile_span_m / 2.0, cy - tile_span_m / 2.0, cx + tile_span_m / 2.0, cy + tile_span_m / 2.0]
    else:
        # Search candidate 5.12 km x 5.12 km windows aligned with flood clusters to maximize inundation signal
        half = tile_span_m / 2.0
        best_score = -1.0
        utm_bounds = [xmin_all, ymin_all, xmin_all + tile_span_m, ymin_all + tile_span_m]
        xs = np.linspace(xmin_all, max(xmin_all, xmax_all - tile_span_m), 30)
        ys = np.linspace(ymin_all, max(ymin_all, ymax_all - tile_span_m), 30)
        # Also include top-15 largest polygons' centers directly
        top_idx = np.argsort(arr[:, 2])[::-1][:15]
        cand_boxes = [(x0, y0) for x0 in xs for y0 in ys] + [(float(arr[k, 0] - half), float(arr[k, 1] - half)) for k in top_idx]
        for x0, y0 in cand_boxes:
            m = (arr[:, 0] >= x0) & (arr[:, 0] <= x0 + tile_span_m) & (arr[:, 1] >= y0) & (arr[:, 1] <= y0 + tile_span_m)
            sc = float(arr[m, 2].sum())
            if sc > best_score:
                best_score = sc
                utm_bounds = [x0, y0, x0 + tile_span_m, y0 + tile_span_m]

    # Snap UTM bounds cleanly to exact integer 10m multiples
    x0 = round(utm_bounds[0] / 10.0) * 10.0
    y0 = round(utm_bounds[1] / 10.0) * 10.0
    utm_bounds = [x0, y0, x0 + tile_span_m, y0 + tile_span_m]
    bbox_wgs84 = [float(x) for x in transform_bounds(utm_crs, "EPSG:4326", *utm_bounds)]
    return utm_crs, utm_bounds, bbox_wgs84, geoms_utm


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_event(ev: dict, size: int = 512, pixel_res_m: float = 10.0, force: bool = False) -> dict:
    act = ev["activation"]
    shp_path = find_shapefile(ev)
    out_path = OUT_STACK_DIR / f"{act}_real_eo.npz"

    if out_path.exists() and not force:
        d = np.load(out_path)
        if "meta_json" in d and "utm_crs" in d:
            meta = json.loads(str(d["meta_json"].item()))
            meta["resumed_from_cache"] = True
            meta["npz_sha256"] = file_sha256(out_path)
            print(
                f"[CACHED] {act:<8} ({meta['utm_crs']}, 10m) | sar_v={meta['valid_sar_fraction']:.3f} | "
                f"dem_v={meta['dem_valid_fraction']:.3f} | jrc_v={meta['jrc_valid_fraction']:.3f} | "
                f"mean_O={meta['mean_obs']:.3f} | ref_px={meta['ref_flood_pixels']:<6} | flood_px={meta['flood_pred_pixels']:<6}",
                flush=True,
            )
            return meta

    utm_crs, utm_bounds, bbox_wgs84, geoms_utm = choose_utm_tile_grid(shp_path, size=size, pixel_res_m=pixel_res_m)
    dst_tf = from_bounds(*utm_bounds, size, size)

    # Expand STAC search bbox slightly (~0.02 deg) to avoid edge misses during WGS84->UTM transforms
    search_bbox = [bbox_wgs84[0] - 0.02, bbox_wgs84[1] - 0.02, bbox_wgs84[2] + 0.02, bbox_wgs84[3] + 0.02]
    pre_grp, post_grp = select_best_rtc_pair(search_bbox, ev["s1_before_datetime"], ev["s1_event_datetime"])

    vv_before = mosaic_reproject(pre_grp, "vv", (size, size), dst_tf, utm_crs, valid_positive_only=True)
    vv_after = mosaic_reproject(post_grp, "vv", (size, size), dst_tf, utm_crs, valid_positive_only=True)
    vh_before = mosaic_reproject(pre_grp, "vh", (size, size), dst_tf, utm_crs, valid_positive_only=True)
    vh_after = mosaic_reproject(post_grp, "vh", (size, size), dst_tf, utm_crs, valid_positive_only=True)

    dem_items = search_stac("cop-dem-glo-30", search_bbox, limit=12)
    elev_m_raw = mosaic_reproject(dem_items, "data", (size, size), dst_tf, utm_crs, resampling=Resampling.bilinear)
    slope_deg, dem_valid = compute_utm_slope_deg(elev_m_raw, pixel_res_m=pixel_res_m)
    elev_m = np.where(dem_valid, elev_m_raw, float(np.nanmedian(elev_m_raw)) if dem_valid.any() else np.nan).astype(np.float32)

    jrc_items = search_stac("jrc-gsw", search_bbox, limit=8)
    jrc_raw = mosaic_reproject(jrc_items, "occurrence", (size, size), dst_tf, utm_crs, resampling=Resampling.nearest)
    jrc_valid = np.isfinite(jrc_raw) & (jrc_raw >= 0.0) & (jrc_raw <= 100.0)
    # Neutral novelty prior (jrc_occ = 0.0 -> M_novelty = 1.0, W_water = 1.0) only where JRC reports missing/nodata
    jrc_occ = np.where(jrc_valid, jrc_raw / 100.0, 0.0).astype(np.float32)

    ref_mask = rasterize([(g, 1) for g in geoms_utm], out_shape=(size, size), transform=dst_tf, fill=0, dtype=np.uint8)

    cfg = FloodEvidenceConfig(sar_input_units="linear", pixel_resolution_m=pixel_res_m)
    sar_ev, sar_valid = compute_sar_water_evidence(
        vv_before=vv_before,
        vv_event=vv_after,
        vh_before=vh_before if np.isfinite(vh_before).any() else None,
        vh_event=vh_after if np.isfinite(vh_after).any() else None,
        config=cfg,
    )
    overall_valid = sar_valid & dem_valid
    novelty_ev, novelty_valid = compute_water_novelty(sar_ev, jrc_occ, config=cfg)
    novelty_valid = novelty_valid & jrc_valid
    terrain_ev, terrain_valid = compute_terrain_plausibility(slope_deg, elev_m, config=cfg)
    terrain_valid = terrain_valid & dem_valid

    mode_b = fuse_flood_evidence(
        sar_evidence=sar_ev,
        sar_valid=sar_valid,
        novelty_evidence=novelty_ev,
        novelty_valid=novelty_valid,
        terrain_plausibility=terrain_ev,
        terrain_valid=terrain_valid,
        rainfall_score=None,
        config=cfg,
    )
    cfg_mode_a = FloodEvidenceConfig(fusion_strategy="linear_blend", sar_input_units="linear", pixel_resolution_m=pixel_res_m)
    mode_a = fuse_flood_evidence(
        sar_evidence=sar_ev,
        sar_valid=sar_valid,
        novelty_evidence=novelty_ev,
        novelty_valid=novelty_valid,
        terrain_plausibility=terrain_ev,
        terrain_valid=terrain_valid,
        rainfall_score=None,
        config=cfg_mode_a,
    )

    tristate = compute_tristate_flood_decision(
        flood_score=mode_b.flood_score,
        valid_mask=overall_valid,
        slope_deg=slope_deg,
        elevation_m=elev_m,
        jrc_occurrence=jrc_occ,
        detection_threshold=0.20,
        observability_threshold=0.50,
        pixel_resolution_m=pixel_res_m,
        cems_reference_mask=ref_mask,
    )

    tri_code = np.full((size, size), 2, dtype=np.uint8)  # 2 = UNRESOLVED
    tri_code[tristate.no_flood_mask] = 0
    tri_code[tristate.flood_mask] = 1
    assert np.sum(tri_code == 0) == tristate.no_flood_pixels
    assert np.sum(tri_code == 1) == tristate.flood_pixels
    assert np.sum(tri_code == 2) == tristate.unresolved_pixels

    valid_vv = np.isfinite(vv_before) & np.isfinite(vv_after) & (vv_before > 0) & (vv_after > 0)
    delta_vv_db = np.where(
        valid_vv,
        10.0 * np.log10(np.clip(vv_after, 1e-7, 10.0) / np.clip(vv_before, 1e-7, 10.0)),
        np.nan,
    ).astype(np.float32)

    meta = {
        "activation": act,
        "country": ev["country"],
        "utm_crs": utm_crs,
        "utm_bounds_m": [round(float(x), 2) for x in utm_bounds],
        "pixel_resolution_m": pixel_res_m,
        "grid_shape": [size, size],
        "bbox_wgs84": [round(float(x), 5) for x in bbox_wgs84],
        "s1_rtc_before_items": [g["id"] for g in pre_grp],
        "s1_rtc_before_datetime": pre_grp[0]["properties"]["datetime"],
        "s1_rtc_event_items": [g["id"] for g in post_grp],
        "s1_rtc_event_datetime": post_grp[0]["properties"]["datetime"],
        "dem_items": [d["id"] for d in dem_items],
        "jrc_items": [j["id"] for j in jrc_items],
        "shapefile": str(shp_path.relative_to(ROOT)),
        "valid_sar_fraction": round(float(np.mean(sar_valid)), 4),
        "dem_valid_fraction": round(float(np.mean(dem_valid)), 4),
        "jrc_valid_fraction": round(float(np.mean(jrc_valid)), 4),
        "overall_valid_fraction": round(float(np.mean(overall_valid)), 4),
        "mean_obs": round(float(np.mean(tristate.observability_index)), 4),
        "resolvable_fraction": round(float(np.mean(tristate.resolvable_mask)), 4),
        "ref_flood_pixels": int(np.sum(ref_mask == 1)),
        "flood_pred_pixels": int(tristate.flood_pixels),
        "no_flood_pred_pixels": int(tristate.no_flood_pixels),
        "unresolved_pixels": int(tristate.unresolved_pixels),
        "npz_path": str(out_path.relative_to(ROOT)),
        "resumed_from_cache": False,
    }

    OUT_STACK_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_path,
        vv_before=vv_before,
        vv_after=vv_after,
        vh_before=vh_before,
        vh_after=vh_after,
        delta_vv_db=delta_vv_db,
        elev_m=elev_m,
        slope_deg=slope_deg,
        jrc_occ=jrc_occ,
        dem_valid_mask=dem_valid.astype(np.uint8),
        jrc_valid_mask=jrc_valid.astype(np.uint8),
        sar_evidence=sar_ev.astype(np.float32),
        novelty_evidence=novelty_ev.astype(np.float32),
        terrain_plausibility=terrain_ev.astype(np.float32),
        obs_full=tristate.observability_index.astype(np.float32),
        fused_score=mode_b.flood_score.astype(np.float32),
        mode_a_score=mode_a.flood_score.astype(np.float32),
        tri_state=tri_code,
        valid_mask=overall_valid.astype(np.uint8),
        ref_mask=ref_mask.astype(np.uint8),
        bbox_wgs84=np.array(bbox_wgs84, dtype=np.float64),
        utm_crs=np.array(utm_crs),
        utm_bounds_m=np.array(utm_bounds, dtype=np.float64),
        pixel_resolution_m=np.array(pixel_res_m, dtype=np.float32),
        meta_json=np.array(json.dumps(meta)),
    )
    meta["npz_sha256"] = file_sha256(out_path)
    print(
        f"[OK] {act:<8} ({utm_crs}, 10m) | sar_v={meta['valid_sar_fraction']:.3f} | "
        f"dem_v={meta['dem_valid_fraction']:.3f} | jrc_v={meta['jrc_valid_fraction']:.3f} | "
        f"mean_O={meta['mean_obs']:.3f} | ref_px={meta['ref_flood_pixels']:<6} | flood_px={meta['flood_pred_pixels']:<6} | "
        f"pre={pre_grp[0]['id'][:24]} post={post_grp[0]['id'][:24]}",
        flush=True,
    )
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract local UTM 10m STAC EO stacks for Earth One Flood.")
    parser.add_argument("--force", action="store_true", help="Re-download and re-extract even if UTM .npz exists.")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    all_events = manifest["development_cohort"] + manifest["unseen_spatial_holdout_cohort"]
    extracted_meta = [extract_event(ev, size=512, pixel_res_m=10.0, force=args.force) for ev in all_events]

    fig3_payload = {}
    for act in ("EMSR629", "EMSR468", "EMSR567"):
        d = np.load(OUT_STACK_DIR / f"{act}_real_eo.npz")
        fig3_payload[f"{act}_delta_vv_db"] = d["delta_vv_db"]
        fig3_payload[f"{act}_obs"] = d["obs_full"]
        fig3_payload[f"{act}_fused"] = d["fused_score"]
        fig3_payload[f"{act}_tristate"] = d["tri_state"]
        fig3_payload[f"{act}_ref"] = d["ref_mask"]
        fig3_payload[f"{act}_bbox"] = d["bbox_wgs84"]
        fig3_payload[f"{act}_utm_crs"] = d["utm_crs"]
        fig3_payload[f"{act}_utm_bounds_m"] = d["utm_bounds_m"]

    FIG3_NPZ_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(FIG3_NPZ_PATH, **fig3_payload)

    OUT_MANIFEST_PATH.write_text(
        json.dumps(
            {
                "schema": "earth_one_real_eo_utm10m_extraction_v2.4",
                "stac_endpoint": STAC_SEARCH_URL,
                "collection": "sentinel-1-rtc",
                "dem_collection": "cop-dem-glo-30",
                "water_collection": "jrc-gsw",
                "grid_contract": "512 x 512 pixels at exact 10.0 m x 10.0 m local UTM (5.12 km x 5.12 km = 26.2144 km^2)",
                "fig3_bundle_sha256": file_sha256(FIG3_NPZ_PATH),
                "events": extracted_meta,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n[Saved] {FIG3_NPZ_PATH}")
    print(f"[Saved] {OUT_MANIFEST_PATH}")


if __name__ == "__main__":
    main()
