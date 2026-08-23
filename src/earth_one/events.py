from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import csv
import json

import numpy as np
import rasterio
from .raster_utils import normalize_geotiff_profile
from rasterio.features import shapes
from scipy import ndimage
from shapely.geometry import shape, mapping
from shapely.ops import unary_union


@dataclass
class EventRecord:
    event_id: int
    area_pixels: int
    area_m2: float
    area_ha: float
    mean_change: float | None
    mean_score: float | None
    min_row: int
    min_col: int
    max_row: int
    max_col: int
    geometry: dict | None = None
    event_version: str = "0.9.0"


def _component_mask(binary: np.ndarray, connectivity: int) -> tuple[np.ndarray, int]:
    if connectivity == 8:
        structure = np.ones((3, 3), dtype=np.uint8)
    elif connectivity == 4:
        structure = ndimage.generate_binary_structure(2, 1)
    else:
        raise ValueError("connectivity must be 4 or 8")
    labels, count = ndimage.label(binary, structure=structure)
    return labels, int(count)


def segment_events(
    change_path: str | Path,
    score_path: str | Path,
    event_raster_path: str | Path,
    min_pixels: int = 9,
    score_threshold: float = 0.5,
    connectivity: int = 8,
    geojson_path: str | Path | None = None,
) -> list[EventRecord]:
    """
    Convert pixel-level disturbance evidence into spatial event objects.

    An event is a connected component of pixels satisfying:
        finite(change) AND score >= score_threshold

    Tiny components below min_pixels are discarded.

    This is a deterministic event-construction layer, not a semantic event
    classifier. Event meaning still comes from the validated class layer.
    """
    change_path = Path(change_path)
    score_path = Path(score_path)
    event_raster_path = Path(event_raster_path)

    with rasterio.open(change_path) as c:
        change = c.read(1).astype(np.float32)
        profile = c.profile.copy()
        transform = c.transform
        crs = c.crs
        pixel_area = abs(transform.a * transform.e - transform.b * transform.d)

    with rasterio.open(score_path) as s:
        score = s.read(1).astype(np.float32)
        if score.shape != change.shape:
            raise ValueError("Change and score rasters have different dimensions.")
        if s.crs != crs or s.transform != transform:
            raise ValueError("Change and score rasters are not spatially aligned.")

    candidate = np.isfinite(change) & np.isfinite(score) & (score >= score_threshold)
    labels, count = _component_mask(candidate, connectivity)

    events: list[EventRecord] = []
    event_id = 0
    event_labels = np.zeros(labels.shape, dtype=np.int32)

    for component_id in range(1, count + 1):
        mask = labels == component_id
        n = int(mask.sum())
        if n < min_pixels:
            continue

        event_id += 1
        rows, cols = np.where(mask)

        mean_change = float(np.nanmean(change[mask])) if np.isfinite(change[mask]).any() else None
        mean_score = float(np.nanmean(score[mask])) if np.isfinite(score[mask]).any() else None

        event_labels[mask] = event_id

        events.append(
            EventRecord(
                event_id=event_id,
                area_pixels=n,
                area_m2=float(n * pixel_area),
                area_ha=float(n * pixel_area / 10000.0),
                mean_change=mean_change,
                mean_score=mean_score,
                min_row=int(rows.min()),
                min_col=int(cols.min()),
                max_row=int(rows.max()),
                max_col=int(cols.max()),
            )
        )

    profile.update(
        count=1,
        dtype="int32",
        nodata=0,
        compress="deflate",
        tiled=True,
    )
    event_raster_path.parent.mkdir(parents=True, exist_ok=True)
    profile = normalize_geotiff_profile(
        profile,
        width=profile["width"],
        height=profile["height"],
    )

    with rasterio.open(event_raster_path, "w", **profile) as dst:
        dst.write(event_labels, 1)
        dst.set_band_description(1, "EVENT_ID")
        dst.update_tags(
            EARTH_ONE_PROCESSOR_VERSION="0.9.0",
            EARTH_ONE_PRODUCT="disturbance_event_raster",
            EARTH_ONE_MIN_PIXELS=str(min_pixels),
            EARTH_ONE_SCORE_THRESHOLD=str(score_threshold),
            EARTH_ONE_CONNECTIVITY=str(connectivity),
        )

    if geojson_path:
        geojson_path = Path(geojson_path)
        features = []
        for event in events:
            mask = event_labels == event.event_id
            geoms = [
                shape(geom)
                for geom, value in shapes(
                    mask.astype(np.uint8),
                    mask=mask,
                    transform=transform,
                )
                if value == 1
            ]
            geom = unary_union(geoms) if geoms else None
            event.geometry = mapping(geom) if geom else None
            features.append({
                "type": "Feature",
                "properties": {
                    "event_id": event.event_id,
                    "area_pixels": event.area_pixels,
                    "area_m2": event.area_m2,
                    "area_ha": event.area_ha,
                    "mean_change": event.mean_change,
                    "mean_score": event.mean_score,
                },
                "geometry": event.geometry,
            })

        geojson_path.parent.mkdir(parents=True, exist_ok=True)
        geojson_path.write_text(
            json.dumps({
                "type": "FeatureCollection",
                "name": "earth_one_events_v0_9",
                "crs": {
                    "type": "name",
                    "properties": {"name": str(crs)}
                } if crs else None,
                "features": features,
            }, indent=2),
            encoding="utf-8",
        )

    return events


def write_event_table(events: list[EventRecord], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "event_id", "area_pixels", "area_m2", "area_ha",
        "mean_change", "mean_score",
        "min_row", "min_col", "max_row", "max_col",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for event in events:
            writer.writerow({field: getattr(event, field) for field in fields})


def write_event_json(events: list[EventRecord], path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(event) for event in events], indent=2),
        encoding="utf-8",
    )
