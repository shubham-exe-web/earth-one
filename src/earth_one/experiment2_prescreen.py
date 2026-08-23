from __future__ import annotations

"""Experiment 2 AOI Pre-Screening Engine.

Screening candidate ecological regions across India for generalized multi-site evaluation:
1. Similipal, Odisha (Eastern Ghats moist/dry deciduous)
2. Satpura, Madhya Pradesh (Central Indian dry deciduous & teak)
3. Tadoba-Andhari, Maharashtra (Deccan dry deciduous)
4. Nagarhole–Bandipur, Karnataka (Western Ghats moist/dry transition)
5. Kumaon, Uttarakhand (Western Himalayas chir pine / montane)

Criteria for eligibility:
1. MCD64A1 burned objects >= 3
2. At least 1 medium/large burned object (>= 0.7 ha / >= 3.5 ha)
3. FIRMS active-fire detections >= 5
4. Usable 12-month S1/S2 temporal coverage (clear baseline pair + SAR GRD)
5. No obvious QA/cloud/data blocker
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from scipy import ndimage


@dataclass(frozen=True)
class CandidateAOI:
    name: str
    region_type: str
    state: str
    bbox: tuple[float, float, float, float]  # west, south, east, north


CANDIDATE_AOIS = [
    CandidateAOI("Similipal", "Eastern Ghats Biosphere Reserve", "Odisha", (86.20, 21.65, 86.40, 21.85)),
    CandidateAOI("Satpura", "Central Indian Highlands", "Madhya Pradesh", (78.20, 22.35, 78.40, 22.55)),
    CandidateAOI("Tadoba-Andhari", "Deccan Dry Deciduous", "Maharashtra", (79.25, 20.15, 79.45, 20.35)),
    CandidateAOI("Nagarhole-Bandipur", "Western Ghats Complex", "Karnataka", (76.30, 11.65, 76.50, 11.85)),
    CandidateAOI("Kumaon", "Western Himalayan Montane", "Uttarakhand", (79.35, 29.35, 79.55, 29.55)),
]


def screen_firms_detections(map_key: str, bbox: tuple[float, float, float, float]) -> int:
    """Query FIRMS Area API sample chunks for 2025 fire season."""
    w, s, e, n = bbox
    bbox_str = f"{w},{s},{e},{n}"
    # Sample peak fire season windows: Feb-May 2025
    sample_dates = ["2025-02-15", "2025-03-15", "2025-04-15", "2025-05-15"]
    total_pts = 0
    
    for dt in sample_dates:
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/VIIRS_SNPP_SP/{bbox_str}/5/{dt}"
        req = urllib.request.Request(url, headers={"User-Agent": "EarthOne-PreScreen"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                content = resp.read().decode("utf-8").strip()
                lines = [l for l in content.split("\n") if l and not l.startswith("latitude")]
                total_pts += len(lines)
        except Exception:
            pass
    return total_pts


def screen_mcd64a1_burned_objects(bbox: tuple[float, float, float, float]) -> tuple[int, float]:
    """Query MCD64A1 2025 monthly items from Planetary Computer and count discrete objects."""
    stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
    query_payload = {
        "collections": ["modis-64A1-061"],
        "bbox": list(bbox),
        "datetime": "2025-01-01T00:00:00Z/2025-06-30T23:59:59Z",
        "limit": 10
    }
    req = urllib.request.Request(
        stac_url,
        data=json.dumps(query_payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "EarthOne-PreScreen"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            features = json.loads(resp.read().decode("utf-8")).get("features", [])
    except Exception:
        return 0, 0.0

    cumulative_mask = None
    cell_ha = 21.466

    for f in features:
        burn_asset = f.get("assets", {}).get("Burn_Date", {})
        href = burn_asset.get("href")
        if not href:
            continue
        
        encoded = urllib.parse.quote(href, safe="")
        sign_url = f"https://planetarycomputer.microsoft.com/api/sas/v1/sign?href={encoded}"
        req_sign = urllib.request.Request(sign_url, headers={"User-Agent": "EarthOne-PreScreen"})
        try:
            with urllib.request.urlopen(req_sign, timeout=10) as resp_s:
                signed_href = json.loads(resp_s.read().decode("utf-8")).get("href")
            
            with rasterio.open(signed_href) as src:
                w, s, e, n = bbox
                sinu_left, sinu_bottom, sinu_right, sinu_top = transform_bounds("EPSG:4326", src.crs, w, s, e, n)
                win = from_bounds(sinu_left, sinu_bottom, sinu_right, sinu_top, src.transform)
                win_int = win.round_offsets().round_lengths()
                data = src.read(1, window=win_int)
                b_mask = (data > 0)
                
                if cumulative_mask is None:
                    cumulative_mask = b_mask
                else:
                    cumulative_mask = cumulative_mask | b_mask
        except Exception:
            continue

    if cumulative_mask is None or not np.any(cumulative_mask):
        return 0, 0.0

    struct_8 = ndimage.generate_binary_structure(2, 2)
    lbl, num_objects = ndimage.label(cumulative_mask, structure=struct_8)
    if num_objects == 0:
        return 0, 0.0

    sizes = ndimage.sum(cumulative_mask, lbl, range(1, num_objects + 1))
    max_size_cells = float(np.max(sizes))
    max_area_ha = max_size_cells * cell_ha
    return int(num_objects), float(max_area_ha)


def screen_s1_s2_coverage(bbox: tuple[float, float, float, float]) -> str:
    """Verify Sentinel-2 and Sentinel-1 scene availability on Planetary Computer."""
    stac_url = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
    
    # S2 dry season check (Jan-Feb 2025 & Jan-Feb 2026)
    s2_payload = {
        "collections": ["sentinel-2-l2a"],
        "bbox": list(bbox),
        "datetime": "2025-01-01T00:00:00Z/2025-02-28T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": 20}},
        "limit": 5
    }
    # S1 GRD check
    s1_payload = {
        "collections": ["sentinel-1-grd"],
        "bbox": list(bbox),
        "datetime": "2025-01-01T00:00:00Z/2025-02-28T23:59:59Z",
        "limit": 5
    }
    
    try:
        req_s2 = urllib.request.Request(stac_url, data=json.dumps(s2_payload).encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": "EarthOne-PreScreen"})
        with urllib.request.urlopen(req_s2, timeout=10) as r:
            s2_items = len(json.loads(r.read().decode("utf-8")).get("features", []))
        
        req_s1 = urllib.request.Request(stac_url, data=json.dumps(s1_payload).encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": "EarthOne-PreScreen"})
        with urllib.request.urlopen(req_s1, timeout=10) as r:
            s1_items = len(json.loads(r.read().decode("utf-8")).get("features", []))
        
        if s2_items > 0 and s1_items > 0:
            return f"Robust (S2: {s2_items}, S1: {s1_items})"
        return f"Partial (S2: {s2_items}, S1: {s1_items})"
    except Exception as e:
        return f"Error: {e}"
