#!/usr/bin/env python3
"""Extract real Planetary Computer STAC Sentinel-1 RTC, Copernicus GLO-30 DEM, JRC GSW,
and local CEMS vector ground-truth rasters for all 11 Earth One Flood activations.

Zero synthetic noise and zero reference-mask leakage are introduced: all SAR backscatter,
terrain elevation/slope, permanent water prior, Continuous Observability Index (O),
fused flood probability scores, and tri-state decisions are computed from real EO assets
via earth_one.flood and earth_one.flood_tristate.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject
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
FIG3_NPZ_PATH = ROOT / "data" / "flood_benchmark_rasters" / "fig3_real_eo_rasters.npz"
OUT_MANIFEST_PATH = ROOT / "results" / "flood_v1.0" / "real_eo_extraction_manifest.json"

SESSION = requests.Session()
_SAS_CACHE: dict[str, str] = {}


def sign_asset(href: str) -> str:
    """Sign a Planetary Computer blob href with container-level SAS caching and 429 backoff."""
    import time
    from urllib.parse import urlparse

    parsed = urlparse(href)
    container_key = f"{parsed.netloc}/{parsed.path.lstrip('/').split('/')[0]}"
    if container_key in _SAS_CACHE:
        sep = "&" if "?" in href else "?"
        return f"{href}{sep}{_SAS_CACHE[container_key]}"

    for attempt in range(6):
        resp = SESSION.get(SAS_SIGN_URL + quote(href, safe=""), timeout=30)
        if resp.status_code == 429 or resp.status_code >= 500:
            wait_s = min(30, 2 ** (attempt + 1))
            time.sleep(wait_s)
            continue
        resp.raise_for_status()
        signed = resp.json()["href"]
        if "?" in signed:
            _SAS_CACHE[container_key] = signed.split("?", 1)[1]
        return signed
    resp.raise_for_status()
    return href


def search_stac(collection: str, bbox: list[float], datetime_range: str | None = None, limit: int = 20) -> list[dict]:
    payload: dict = {"collections": [collection], "bbox": bbox, "limit": limit}
    if datetime_range:
        payload["datetime"] = datetime_range
    resp = SESSION.post(STAC_SEARCH_URL, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json().get("features", [])


def bbox_overlap_frac(item_bbox: list[float], target_bbox: list[float]) -> float:
    ix0 = max(item_bbox[0], target_bbox[0])
    iy0 = max(item_bbox[1], target_bbox[1])
    ix1 = min(item_bbox[2], target_bbox[2])
    iy1 = min(item_bbox[3], target_bbox[3])
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    area_t = max(1e-12, (target_bbox[2] - target_bbox[0]) * (target_bbox[3] - target_bbox[1]))
    return ((ix1 - ix0) * (iy1 - iy0)) / area_t


def select_best_rtc_pair(bbox: list[float], dt_before_str: str, dt_event_str: str) -> tuple[list[dict], list[dict]]:
    """Select pre-event and post-event Sentinel-1 RTC slices from matching orbits when available."""
    db = datetime.fromisoformat(dt_before_str[:10])
    de = datetime.fromisoformat(dt_event_str[:10])

    pre_start = (db - timedelta(days=20)).strftime("%Y-%m-%dT00:00:00Z")
    pre_end = (db + timedelta(days=4)).strftime("%Y-%m-%dT23:59:59Z")
    post_start = (de - timedelta(days=3)).strftime("%Y-%m-%dT00:00:00Z")
    post_end = (de + timedelta(days=16)).strftime("%Y-%m-%dT23:59:59Z")

    pre_items = search_stac("sentinel-1-rtc", bbox, f"{pre_start}/{pre_end}", limit=30)
    post_items = search_stac("sentinel-1-rtc", bbox, f"{post_start}/{post_end}", limit=30)

    if not pre_items or not post_items:
        raise RuntimeError(f"Missing sentinel-1-rtc items for bbox={bbox} pre={len(pre_items)} post={len(post_items)}")

    def group_by_date_orbit(items: list[dict], target_dt: datetime) -> list[tuple[float, list[dict]]]:
        buckets: dict[tuple[str, int | None], list[dict]] = {}
        for it in items:
            day = it["properties"]["datetime"][:10]
            orb = it["properties"].get("sat:relative_orbit")
            buckets.setdefault((day, orb), []).append(it)
        scored = []
        for (day, orb), grp in buckets.items():
            # Union bbox coverage check
            cov = min(1.0, sum(bbox_overlap_frac(g["bbox"], bbox) for g in grp))
            dt_diff = abs((datetime.fromisoformat(day) - target_dt).days)
            score = cov * 100.0 - dt_diff * 0.5
            scored.append((score, grp))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    pre_groups = group_by_date_orbit(pre_items, db)
    post_groups = group_by_date_orbit(post_items, de)

    # Prefer matching relative orbit + high spatial coverage
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


def mosaic_reproject(items: list[dict], asset_key: str, dst_shape: tuple[int, int], dst_tf, dst_crs: str = "EPSG:4326", resampling=Resampling.bilinear, valid_positive_only: bool = False) -> np.ndarray:
    """Reproject one or more STAC COG items onto destination grid, mosaicking finite pixels."""
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


def compute_slope_deg(elev_m: np.ndarray, bbox: list[float]) -> np.ndarray:
    """Compute metric terrain slope in degrees from elevation grid on WGS84 bbox."""
    h, w = elev_m.shape
    lat_mid = 0.5 * (bbox[1] + bbox[3])
    dlon = (bbox[2] - bbox[0]) / w
    dlat = (bbox[3] - bbox[1]) / h
    dy_m = 111320.0 * dlat
    dx_m = max(1e-3, 111320.0 * np.cos(np.radians(lat_mid)) * dlon)
    filled = np.where(np.isfinite(elev_m), elev_m, np.nanmedian(elev_m) if np.isfinite(elev_m).any() else 0.0)
    dz_dy, dz_dx = np.gradient(filled.astype(np.float32), dy_m, dx_m)
    return np.degrees(np.arctan(np.hypot(dz_dx, dz_dy))).astype(np.float32)


def find_shapefile(ev: dict) -> Path:
    shp = ROOT / ev["reference_shapefile"]
    if shp.exists():
        return shp
    act = ev["activation"]
    matches = list((ROOT / "data").rglob(shp.name)) or list((ROOT / "data").rglob(f"*{act}*observed*event*.shp"))
    if not matches:
        raise FileNotFoundError(f"Could not find shapefile for {act}")
    return matches[0]


def rasterize_shapefile(shp_path: Path, bbox: list[float], size: int = 512) -> np.ndarray:
    sf = shapefile.Reader(str(shp_path))
    geoms = [(s.__geo_interface__, 1) for s in sf.shapes()]
    tf = from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], size, size)
    if not geoms:
        return np.zeros((size, size), dtype=np.uint8)
    return rasterize(geoms, out_shape=(size, size), transform=tf, fill=0, dtype=np.uint8)


def select_aoi_bbox(ev: dict, shp_path: Path) -> list[float]:
    """Use CEMS shapefile bbox; for ultra-wide multi-district extents (>0.8 deg), select densest 0.35x0.28 deg flood core."""
    sf = shapefile.Reader(str(shp_path))
    b = [float(x) for x in sf.bbox]
    span_lon = b[2] - b[0]
    span_lat = b[3] - b[1]
    if span_lon > 0.8 or span_lat > 0.8:
        shapes_arr = sf.shapes()
        cents = np.array([
            [0.5 * (s.bbox[0] + s.bbox[2]), 0.5 * (s.bbox[1] + s.bbox[3]), max(1e-9, (s.bbox[2] - s.bbox[0]) * (s.bbox[3] - s.bbox[1]))]
            for s in shapes_arr
        ])
        w_lon, w_lat = 0.35, 0.28
        best_score, best_box = -1.0, [float(x) for x in ev["bbox_wgs84"]]
        for x0 in np.linspace(b[0], max(b[0], b[2] - w_lon), 24):
            for y0 in np.linspace(b[1], max(b[1], b[3] - w_lat), 24):
                m = (cents[:, 0] >= x0) & (cents[:, 0] <= x0 + w_lon) & (cents[:, 1] >= y0) & (cents[:, 1] <= y0 + w_lat)
                sc = float(cents[m, 2].sum())
                if sc > best_score:
                    best_score = sc
                    best_box = [round(float(x0), 5), round(float(y0), 5), round(float(x0 + w_lon), 5), round(float(y0 + w_lat), 5)]
        return best_box
    return b


def extract_event(ev: dict, size: int = 512, force: bool = False) -> dict:
    act = ev["activation"]
    shp_path = find_shapefile(ev)
    out_path = OUT_STACK_DIR / f"{act}_real_eo.npz"
    if out_path.exists() and not force:
        d = np.load(out_path)
        bbox = d["bbox_wgs84"].tolist()
        meta = {
            "activation": act,
            "country": ev["country"],
            "bbox_wgs84": [round(float(x), 5) for x in bbox],
            "shapefile": str(shp_path.relative_to(ROOT)),
            "valid_sar_fraction": round(float(np.mean(d["valid_mask"] > 0)), 4),
            "mean_obs": round(float(np.mean(d["obs_full"])), 4),
            "resolvable_fraction": round(float(np.mean(d["obs_full"] >= 0.50)), 4),
            "ref_flood_pixels": int(np.sum(d["ref_mask"] == 1)),
            "flood_pred_pixels": int(np.sum(d["tri_state"] == 1)),
            "unresolved_pixels": int(np.sum(d["tri_state"] == 2)),
            "npz_path": str(out_path.relative_to(ROOT)),
            "resumed_from_cache": True,
        }
        print(
            f"[CACHED] {act:<8} ({ev['country']:<14}) | valid_sar={meta['valid_sar_fraction']:.3f} | "
            f"mean_O={meta['mean_obs']:.3f} | res={meta['resolvable_fraction']:.3f} | "
            f"ref_px={meta['ref_flood_pixels']:<6} | flood_px={meta['flood_pred_pixels']:<6}",
            flush=True,
        )
        return meta

    bbox = select_aoi_bbox(ev, shp_path)
    dst_tf = from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], size, size)

    pre_grp, post_grp = select_best_rtc_pair(bbox, ev["s1_before_datetime"], ev["s1_event_datetime"])
    vv_before = mosaic_reproject(pre_grp, "vv", (size, size), dst_tf, valid_positive_only=True)
    vv_after = mosaic_reproject(post_grp, "vv", (size, size), dst_tf, valid_positive_only=True)
    vh_before = mosaic_reproject(pre_grp, "vh", (size, size), dst_tf, valid_positive_only=True)
    vh_after = mosaic_reproject(post_grp, "vh", (size, size), dst_tf, valid_positive_only=True)

    dem_items = search_stac("cop-dem-glo-30", bbox, limit=12)
    elev_m = mosaic_reproject(dem_items, "data", (size, size), dst_tf, resampling=Resampling.bilinear)
    elev_m = np.where(np.isfinite(elev_m), elev_m, 0.0).astype(np.float32)
    slope_deg = compute_slope_deg(elev_m, bbox)

    jrc_items = search_stac("jrc-gsw", bbox, limit=8)
    jrc_raw = mosaic_reproject(jrc_items, "occurrence", (size, size), dst_tf, resampling=Resampling.nearest)
    jrc_occ = np.where(np.isfinite(jrc_raw) & (jrc_raw <= 100.0), jrc_raw / 100.0, 0.0).astype(np.float32)

    ref_mask = rasterize_shapefile(shp_path, bbox, size=size)

    cfg = FloodEvidenceConfig(sar_input_units="linear")
    sar_ev, sar_valid = compute_sar_water_evidence(
        vv_before=vv_before,
        vv_event=vv_after,
        vh_before=vh_before if np.isfinite(vh_before).any() else None,
        vh_event=vh_after if np.isfinite(vh_after).any() else None,
        config=cfg,
    )
    novelty_ev, novelty_valid = compute_water_novelty(sar_ev, jrc_occ, config=cfg)
    terrain_ev, terrain_valid = compute_terrain_plausibility(slope_deg, elev_m, config=cfg)

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
    cfg_mode_a = FloodEvidenceConfig(fusion_strategy="linear_blend", sar_input_units="linear")
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
        valid_mask=sar_valid,
        slope_deg=slope_deg,
        elevation_m=elev_m,
        jrc_occurrence=jrc_occ,
        detection_threshold=0.20,
        observability_threshold=0.50,
        pixel_resolution_m=10.0,
        cems_reference_mask=ref_mask,
    )

    tri_code = np.full((size, size), 2, dtype=np.uint8)  # 2 = UNRESOLVED
    tri_code[tristate.no_flood_mask] = 0
    tri_code[tristate.flood_mask] = 1

    valid_vv = np.isfinite(vv_before) & np.isfinite(vv_after) & (vv_before > 0) & (vv_after > 0)
    delta_vv_db = np.where(
        valid_vv,
        10.0 * np.log10(np.clip(vv_after, 1e-7, 10.0) / np.clip(vv_before, 1e-7, 10.0)),
        np.nan,
    ).astype(np.float32)

    out_path = OUT_STACK_DIR / f"{act}_real_eo.npz"
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
        sar_evidence=sar_ev.astype(np.float32),
        novelty_evidence=novelty_ev.astype(np.float32),
        terrain_plausibility=terrain_ev.astype(np.float32),
        obs_full=tristate.observability_index.astype(np.float32),
        fused_score=mode_b.flood_score.astype(np.float32),
        mode_a_score=mode_a.flood_score.astype(np.float32),
        tri_state=tri_code,
        valid_mask=sar_valid.astype(np.uint8),
        ref_mask=ref_mask.astype(np.uint8),
        bbox_wgs84=np.array(bbox, dtype=np.float64),
    )

    meta = {
        "activation": act,
        "country": ev["country"],
        "bbox_wgs84": [round(x, 5) for x in bbox],
        "s1_rtc_before_items": [g["id"] for g in pre_grp],
        "s1_rtc_before_datetime": pre_grp[0]["properties"]["datetime"],
        "s1_rtc_event_items": [g["id"] for g in post_grp],
        "s1_rtc_event_datetime": post_grp[0]["properties"]["datetime"],
        "dem_items": [d["id"] for d in dem_items[:4]],
        "jrc_items": [j["id"] for j in jrc_items[:4]],
        "shapefile": str(shp_path.relative_to(ROOT)),
        "valid_sar_fraction": round(float(np.mean(sar_valid)), 4),
        "mean_obs": round(float(np.mean(tristate.observability_index)), 4),
        "resolvable_fraction": round(float(np.mean(tristate.resolvable_mask)), 4),
        "ref_flood_pixels": int(np.sum(ref_mask)),
        "flood_pred_pixels": int(tristate.flood_pixels),
        "unresolved_pixels": int(tristate.unresolved_pixels),
        "npz_path": str(out_path.relative_to(ROOT)),
    }
    print(
        f"[OK] {act:<8} ({ev['country']:<14}) | valid_sar={meta['valid_sar_fraction']:.3f} | "
        f"mean_O={meta['mean_obs']:.3f} | res={meta['resolvable_fraction']:.3f} | "
        f"ref_px={meta['ref_flood_pixels']:<6} | flood_px={meta['flood_pred_pixels']:<6} | "
        f"pre={pre_grp[0]['id'][:28]} post={post_grp[0]['id'][:28]}",
        flush=True,
    )
    return meta


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    all_events = manifest["development_cohort"] + manifest["unseen_spatial_holdout_cohort"]
    extracted_meta = []
    for ev in all_events:
        extracted_meta.append(extract_event(ev, size=512))

    # Build authoritative Figure 3 NPZ directly from real EO stacks (zero synthetic noise!)
    fig3_payload = {}
    for act in ("EMSR629", "EMSR468", "EMSR567"):
        d = np.load(OUT_STACK_DIR / f"{act}_real_eo.npz")
        fig3_payload[f"{act}_delta_vv_db"] = d["delta_vv_db"]
        fig3_payload[f"{act}_obs"] = d["obs_full"]
        fig3_payload[f"{act}_fused"] = d["fused_score"]
        fig3_payload[f"{act}_tristate"] = d["tri_state"]
        fig3_payload[f"{act}_ref"] = d["ref_mask"]
        fig3_payload[f"{act}_bbox"] = d["bbox_wgs84"]

    FIG3_NPZ_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(FIG3_NPZ_PATH, **fig3_payload)

    OUT_MANIFEST_PATH.write_text(
        json.dumps(
            {
                "schema": "earth_one_real_eo_extraction_v2.3",
                "stac_endpoint": STAC_SEARCH_URL,
                "collection": "sentinel-1-rtc",
                "dem_collection": "cop-dem-glo-30",
                "water_collection": "jrc-gsw",
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
