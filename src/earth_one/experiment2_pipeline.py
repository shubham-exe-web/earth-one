from __future__ import annotations

"""Experiment 2: Multi-AOI External Generalization Pipeline.

Executes standardized evaluation of the frozen Model B2 across 3 independent biomes:
- AOI-1: Similipal, Odisha (Eastern Ghats Biosphere Reserve)
- AOI-2: Satpura, Madhya Pradesh (Central Indian Highlands)
- AOI-3: Kumaon, Uttarakhand (Western Himalayas Montane Forest)

Protocol per site:
1. Harmonize S2 & S1 multi-temporal inputs onto common 1024x1024 grid (EPSG:4326)
2. Generate features: [NDVI_after, ΔNDVI, VV_after, VH_after, ΔVH_db]
3. Evaluate FROZEN Model B2 (trained on Korba 2024->2025)
4. Evaluate NASA FIRMS VIIRS active-fire corroboration (boundary distance + seasonal lags)
5. Evaluate NASA MCD64A1 500m native-scale agreement + fine-scale bipartite IoU
6. Aggregate cross-AOI statistics (Median, IQR, Range)
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling, transform_bounds
from rasterio.windows import from_bounds
from scipy import ndimage
from sklearn.ensemble import RandomForestClassifier

from earth_one.event_validation import evaluate_event_detection, evaluate_point_event_corroboration, EventValidationConfig
from earth_one.mcd64a1_native_validation import evaluate_native_mcd64a1_agreement


@dataclass(frozen=True)
class SiteDefinition:
    key: str
    name: str
    region: str
    state: str
    bbox: tuple[float, float, float, float]  # west, south, east, north


EXPERIMENT2_SITES = [
    SiteDefinition("similipal", "Similipal", "Eastern Ghats Biosphere Reserve", "Odisha", (86.20, 21.65, 86.40, 21.85)),
    SiteDefinition("satpura", "Satpura", "Central Indian Highlands", "Madhya Pradesh", (78.20, 22.35, 78.40, 22.55)),
    SiteDefinition("kumaon", "Kumaon", "Western Himalayas Montane", "Uttarakhand", (79.35, 29.35, 79.55, 29.55)),
]


def load_frozen_b2_model(train_dir: Path) -> RandomForestClassifier:
    """Fit Model B2 strictly on Korba 2024->2025 development data."""
    with rasterio.open(train_dir / "joint_valid_mask.tif") as ds: jv_tr = (ds.read(1) == 1)
    with rasterio.open(train_dir / "delta_b11.tif") as ds: db11_tr = ds.read(1)
    with rasterio.open(train_dir / "delta_b12.tif") as ds: db12_tr = ds.read(1)
    with rasterio.open(train_dir / "ndvi_after.tif") as ds: ndvi_tr = ds.read(1)
    with rasterio.open(train_dir / "delta_ndvi.tif") as ds: dndvi_tr = ds.read(1)
    with rasterio.open(train_dir / "delta_vh_db.tif") as ds: dvh_tr = ds.read(1)
    with rasterio.open("data/results/s1_pair/before_vv_vh.tif") as ds:
        vv_tr = ds.read(1).astype(np.float32)
        vh_tr = ds.read(2).astype(np.float32)

    struct_8 = ndimage.generate_binary_structure(2, 2)
    raw_d3_tr = jv_tr & ((db12_tr > 0.10) | (db11_tr > 0.10))
    lbl_tr, num_tr = ndimage.label(raw_d3_tr, structure=struct_8)
    sz_tr = ndimage.sum(raw_d3_tr, lbl_tr, range(1, num_tr + 1))
    target_d3_tr = raw_d3_tr & np.isin(lbl_tr, np.where(sz_tr >= 4)[0] + 1)

    v_tr = np.where(jv_tr)
    f_valid_tr = (
        np.isfinite(ndvi_tr[v_tr]) & np.isfinite(dndvi_tr[v_tr]) &
        np.isfinite(vv_tr[v_tr]) & np.isfinite(vh_tr[v_tr]) &
        np.isfinite(dvh_tr[v_tr]) & (vv_tr[v_tr] > 0) & (vh_tr[v_tr] > 0)
    )
    r_tr, c_tr = v_tr[0][f_valid_tr], v_tr[1][f_valid_tr]
    X_train = np.column_stack([ndvi_tr[r_tr, c_tr], dndvi_tr[r_tr, c_tr], vv_tr[r_tr, c_tr], vh_tr[r_tr, c_tr], dvh_tr[r_tr, c_tr]])
    y_train = target_d3_tr[r_tr, c_tr].astype(int)

    clf = RandomForestClassifier(n_estimators=300, max_features="sqrt", class_weight="balanced_subsample", random_state=42, n_jobs=-1)
    clf.fit(X_train, y_train)
    return clf


def fetch_site_firms_records(map_key: str, bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    """Query FIRMS VIIRS detections for 2025-01-04 to 2026-01-04."""
    from earth_one.firms_autonomous import fetch_firms_area_chunk, deduplicate_active_fire_records
    w, s, e, n = bbox
    dt_start = "2025-01-04"
    dt_end = "2026-01-04"
    
    # Query 5-day chunks across standard VIIRS platforms
    sources = ["VIIRS_SNPP_SP", "VIIRS_NOAA20_SP", "VIIRS_NOAA21_SP"]
    all_recs = []
    
    for src in sources:
        # Sample chunks across year
        cur_dt = np.datetime64("2025-01-04")
        end_dt = np.datetime64("2026-01-04")
        while cur_dt <= end_dt:
            date_str = str(cur_dt)
            recs = fetch_firms_area_chunk(map_key, src, bbox, 5, date_str)
            if not recs and src.endswith("_SP"):
                recs = fetch_firms_area_chunk(map_key, src.replace("_SP", "_NRT"), bbox, 5, date_str)
            all_recs.extend(recs)
            cur_dt += np.timedelta64(5, "D")

    unique_recs, _ = deduplicate_active_fire_records(all_recs)
    return unique_recs


def fetch_site_mcd64a1_native(bbox: tuple[float, float, float, float]) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Fetch native Sinusoidal MCD64A1 Burn_Date and QA for 2025."""
    stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
    query_payload = {
        "collections": ["modis-64A1-061"],
        "bbox": list(bbox),
        "datetime": "2025-01-01T00:00:00Z/2025-12-31T23:59:59Z",
        "limit": 30
    }
    req = urllib.request.Request(stac_url, data=json.dumps(query_payload).encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": "EarthOne"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        features = json.loads(resp.read().decode("utf-8")).get("features", [])

    def sign_href(href):
        encoded = urllib.parse.quote(href, safe="")
        sign_url = f"https://planetarycomputer.microsoft.com/api/sas/v1/sign?href={encoded}"
        req_s = urllib.request.Request(sign_url, headers={"User-Agent": "EarthOne"})
        with urllib.request.urlopen(req_s, timeout=10) as r:
            return json.loads(r.read().decode("utf-8")).get("href")

    cum_burn = None
    cum_qa = None
    native_prof = None

    for f in features:
        burn_asset = f.get("assets", {}).get("Burn_Date", {})
        qa_asset = f.get("assets", {}).get("QA", {})
        b_href = burn_asset.get("href")
        q_href = qa_asset.get("href")
        if not b_href:
            continue
        try:
            with rasterio.open(sign_href(b_href)) as src_b:
                w, s, e, n = bbox
                sinu_l, sinu_b, sinu_r, sinu_t = transform_bounds("EPSG:4326", src_b.crs, w, s, e, n)
                win = from_bounds(sinu_l, sinu_b, sinu_r, sinu_t, src_b.transform).round_offsets().round_lengths()
                b_data = src_b.read(1, window=win)
                native_t = rasterio.windows.transform(win, src_b.transform)
                if native_prof is None:
                    native_prof = {"height": b_data.shape[0], "width": b_data.shape[1], "crs": src_b.crs, "transform": native_t}

            if q_href:
                with rasterio.open(sign_href(q_href)) as src_q:
                    q_data = src_q.read(1, window=win)
            else:
                q_data = np.full(b_data.shape, 3, dtype=np.uint8)

            if cum_burn is None:
                cum_burn = b_data
                cum_qa = q_data
            else:
                cum_burn = np.maximum(cum_burn, b_data)
                cum_qa = np.maximum(cum_qa, q_data)
        except Exception:
            continue

    if cum_burn is None:
        cum_burn = np.zeros((36, 64), dtype=np.int16)
        cum_qa = np.full((36, 64), 3, dtype=np.uint8)
        native_prof = {"height": 36, "width": 64, "crs": "EPSG:4326", "transform": None}

    return cum_burn, cum_qa, native_prof
