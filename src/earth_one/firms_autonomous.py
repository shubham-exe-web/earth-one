from __future__ import annotations

"""Autonomous NASA FIRMS Multi-Satellite Active Fire Downloader & Deduplicator.

Retrieves science-quality (SP) and NRT active fire observations from NASA FIRMS Area API:
- S-NPP VIIRS 375m (VIIRS_SNPP_SP / VIIRS_SNPP_NRT)
- NOAA-20 VIIRS 375m (VIIRS_NOAA20_SP / VIIRS_NOAA20_NRT)
- NOAA-21 VIIRS 375m (VIIRS_NOAA21_SP / VIIRS_NOAA21_NRT)
- MODIS 1km (MODIS_SP / MODIS_NRT)

Features:
- Automated 5-day chunking across annual intervals
- Rate-limit aware backoff and retry
- True WGS-84 geodesic distance cross-constellation deduplication (pyproj.Geod)
- Explicit Standard-Processing (SP) vs Near-Real-Time (NRT) provenance tracking
- Full provenance manifest generation
"""

import os
import sys
import time
import csv
import json
import io
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Sequence
from pyproj import Geod


@dataclass(frozen=True)
class FIRMSQueryConfig:
    """Configuration for NASA FIRMS Area API query."""
    aoi_bbox: tuple[float, float, float, float] = (82.60, 22.30, 82.80, 22.45)  # west, south, east, north
    start_date: str = "2025-01-04"
    end_date: str = "2026-01-04"
    sources: tuple[str, ...] = (
        "VIIRS_SNPP_SP",
        "VIIRS_NOAA20_SP",
        "VIIRS_NOAA21_SP",
    )
    fallback_nrt: bool = True
    output_dir: str = "data/results/firms_reference"
    chunk_days: int = 5
    rate_limit_delay_sec: float = 0.5
    spatial_tolerance_meters: float = 250.0
    temporal_tolerance_minutes: int = 30


def check_firms_availability(map_key: str, source: str) -> list[str]:
    """Query NASA FIRMS Data Availability API for a given source."""
    url = f"https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/{map_key}/{source}"
    req = urllib.request.Request(url, headers={"User-Agent": "EarthOne-Research/0.1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8").strip()
            lines = content.split("\n")
            if len(lines) > 1:
                return lines[1:]
            return []
    except Exception as e:
        return [f"ERROR: {e}"]


def fetch_firms_area_chunk(
    map_key: str,
    source: str,
    bbox: tuple[float, float, float, float],
    day_range: int,
    date_str: str,
    max_retries: int = 3,
) -> list[dict[str, Any]]:
    """
    Fetch a single date chunk from FIRMS Area API.
    URL format: /api/area/csv/[MAP_KEY]/[SOURCE]/[WEST,SOUTH,EAST,NORTH]/[DAY_RANGE]/[YYYY-MM-DD]
    """
    west, south, east, north = bbox
    bbox_str = f"{west},{south},{east},{north}"
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{source}/{bbox_str}/{day_range}/{date_str}"
    
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers={"User-Agent": "EarthOne-Research/0.1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                content = resp.read().decode("utf-8").strip()
                if not content or content.startswith("Invalid") or content.startswith("No data"):
                    return []
                reader = csv.DictReader(io.StringIO(content))
                records = list(reader)
                return records
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            if e.code == 429:
                time.sleep(5.0 * (attempt + 1))
            else:
                time.sleep(1.0)
        except Exception:
            time.sleep(1.0)
    return []


def deduplicate_active_fire_records(
    records: Sequence[dict[str, Any]],
    spatial_tolerance_meters: float = 250.0,
    temporal_tolerance_min: int = 30,
) -> tuple[list[dict[str, Any]], int]:
    """
    Conservative multi-constellation deduplication using true WGS-84 geodesic inverse computation.
    Merges detections with matching location (within spatial_tolerance_meters) and timestamp (within temporal_tolerance_min).
    """
    if not records:
        return [], 0

    geod = Geod(ellps="WGS84")
    unique_records: list[dict[str, Any]] = []
    dup_count = 0

    for rec in records:
        try:
            lat = float(rec["latitude"])
            lon = float(rec["longitude"])
            d_str = str(rec.get("acq_date", "")).strip()
            t_str = str(rec.get("acq_time", "0000")).strip().zfill(4)
            dt_rec = datetime.strptime(f"{d_str} {t_str}", "%Y-%m-%d %H%M")
        except Exception:
            unique_records.append(dict(rec))
            continue

        is_dup = False
        for u in unique_records:
            try:
                u_lat = float(u["latitude"])
                u_lon = float(u["longitude"])
                u_d = str(u.get("acq_date", "")).strip()
                u_t = str(u.get("acq_time", "0000")).strip().zfill(4)
                dt_u = datetime.strptime(f"{u_d} {u_t}", "%Y-%m-%d %H%M")

                # True WGS-84 geodesic distance calculation
                _, _, dist_m = geod.inv(lon, lat, u_lon, u_lat)
                time_diff_min = abs((dt_rec - dt_u).total_seconds()) / 60.0

                if dist_m <= spatial_tolerance_meters and time_diff_min <= temporal_tolerance_min:
                    is_dup = True
                    dup_count += 1
                    # Retain maximum Fire Radiative Power (FRP)
                    if float(rec.get("frp", 0)) > float(u.get("frp", 0)):
                        u["frp"] = rec.get("frp")
                    break
            except Exception:
                continue

        if not is_dup:
            unique_records.append(dict(rec))

    return unique_records, dup_count


def download_firms_holdout_dataset(
    map_key: str | None = None,
    config: FIRMSQueryConfig | None = None,
) -> dict[str, Any]:
    """
    Execute full autonomous multi-sensor retrieval for the holdout period.
    Tracks explicit Standard-Processing (SP) vs Near-Real-Time (NRT) provenance per record.
    """
    cfg = config or FIRMSQueryConfig()
    key = map_key or os.getenv("FIRMS_MAP_KEY")
    if not key:
        raise ValueError("FIRMS_MAP_KEY is not set. Please set FIRMS_MAP_KEY environment variable.")

    out_path = Path(cfg.output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    dt_start = datetime.strptime(cfg.start_date, "%Y-%m-%d")
    dt_end = datetime.strptime(cfg.end_date, "%Y-%m-%d")

    all_raw_records: list[dict[str, Any]] = []
    source_stats: dict[str, Any] = {}

    for src in cfg.sources:
        cur_dt = dt_start
        src_records = []
        queries_made = 0
        sp_records_count = 0
        nrt_records_count = 0

        while cur_dt <= dt_end:
            chunk_end = min(cur_dt + timedelta(days=cfg.chunk_days - 1), dt_end)
            actual_days = (chunk_end - cur_dt).days + 1
            date_str = cur_dt.strftime("%Y-%m-%d")

            recs = fetch_firms_area_chunk(
                map_key=key,
                source=src,
                bbox=cfg.aoi_bbox,
                day_range=actual_days,
                date_str=date_str,
            )
            tier_used = "SP" if src.endswith("_SP") else "NRT"
            
            # Fallback to NRT if SP returns empty and fallback is enabled
            if not recs and cfg.fallback_nrt and src.endswith("_SP"):
                nrt_src = src.replace("_SP", "_NRT")
                recs = fetch_firms_area_chunk(
                    map_key=key,
                    source=nrt_src,
                    bbox=cfg.aoi_bbox,
                    day_range=actual_days,
                    date_str=date_str,
                )
                if recs:
                    tier_used = "NRT"

            for r in recs:
                r["firms_source"] = src
                r["processing_tier"] = tier_used
                if tier_used == "SP":
                    sp_records_count += 1
                else:
                    nrt_records_count += 1

            src_records.extend(recs)
            queries_made += 1

            cur_dt += timedelta(days=cfg.chunk_days)
            time.sleep(cfg.rate_limit_delay_sec)

        source_stats[src] = {
            "queries_made": queries_made,
            "raw_records": len(src_records),
            "standard_processing_records": sp_records_count,
            "nrt_fallback_records": nrt_records_count,
        }
        all_raw_records.extend(src_records)

    # True WGS-84 geodesic deduplication
    unique_records, dup_count = deduplicate_active_fire_records(
        all_raw_records,
        spatial_tolerance_meters=cfg.spatial_tolerance_meters,
        temporal_tolerance_min=cfg.temporal_tolerance_minutes,
    )

    # Filter to exact AOI and temporal range
    final_records = []
    w, s, e, n = cfg.aoi_bbox
    for r in unique_records:
        try:
            lat = float(r["latitude"])
            lon = float(r["longitude"])
            d = str(r.get("acq_date", ""))
            if w <= lon <= e and s <= lat <= n and cfg.start_date <= d <= cfg.end_date:
                final_records.append(r)
        except Exception:
            continue

    holdout_json_path = out_path / "firms_viirs_2025_2026_aoi.json"
    holdout_json_path.write_text(json.dumps(final_records, indent=2), encoding="utf-8")

    total_sp = sum(s["standard_processing_records"] for s in source_stats.values())
    total_nrt = sum(s["nrt_fallback_records"] for s in source_stats.values())

    manifest = {
        "retrieval_timestamp": datetime.utcnow().isoformat() + "Z",
        "aoi_bbox": list(cfg.aoi_bbox),
        "temporal_interval": {"start_date": cfg.start_date, "end_date": cfg.end_date},
        "queried_sources": list(cfg.sources),
        "source_breakdown": source_stats,
        "processing_tier_summary": {
            "total_standard_processing_sp": total_sp,
            "total_nrt_fallback": total_nrt,
            "sp_percentage": float(total_sp / len(all_raw_records)) if all_raw_records else 0.0,
        },
        "total_raw_detections": len(all_raw_records),
        "cross_sensor_duplicates_merged": dup_count,
        "final_unique_aoi_detections": len(final_records),
        "output_file": str(holdout_json_path),
    }

    manifest_path = out_path / "firms_2025_2026_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return manifest
