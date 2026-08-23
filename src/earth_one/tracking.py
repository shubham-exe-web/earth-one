from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import math

import numpy as np
from shapely.geometry import shape
from shapely.ops import transform
from pyproj import Transformer


@dataclass
class ObservationEvent:
    observation_date: str
    source_event_id: int
    area_ha: float
    mean_change: float | None
    mean_score: float | None
    geometry: dict


@dataclass
class EventTrack:
    track_id: str
    first_observation: str
    last_observation: str
    observation_count: int
    cumulative_area_ha: float
    peak_area_ha: float
    max_abs_change: float | None
    mean_score: float | None
    status: str
    observations: list[dict]
    tracker_version: str = "1.0.0"


def _project_geometry(geometry: dict, source_crs: str, target_crs: str = "EPSG:6933"):
    if not source_crs:
        return shape(geometry)
    geom = shape(geometry)
    if str(source_crs) == target_crs:
        return geom
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    return transform(transformer.transform, geom)


def _iou(a, b):
    if a.is_empty or b.is_empty:
        return 0.0
    inter = a.intersection(b).area
    union = a.union(b).area
    return float(inter / union) if union else 0.0


def _centroid_distance_km(a, b):
    # Geometries are projected to a metric CRS before this operation.
    return float(a.centroid.distance(b.centroid) / 1000.0)


def track_event_observations(
    observation_files: list[str | Path],
    output_json: str | Path,
    iou_threshold: float = 0.20,
    max_centroid_distance_km: float = 2.0,
    source_crs: str | None = None,
) -> dict:
    """
    Link event polygons across ordered observations.

    Each observation file is an Earth One v0.9 GeoJSON FeatureCollection.
    Events are linked when they satisfy either:
      - IoU >= iou_threshold, OR
      - centroid distance <= max_centroid_distance_km

    The tracker is deliberately deterministic and auditable. It does not yet
    solve complex split/merge identity with a probabilistic tracker.
    """
    if len(observation_files) < 2:
        raise ValueError("At least two observation files are required.")

    observations = []
    for path in observation_files:
        path = Path(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        date = payload.get("observation_date") or path.stem
        features = payload.get("features", [])
        observations.append((date, features))

    observations.sort(key=lambda x: x[0])

    tracks: dict[str, EventTrack] = {}
    active: dict[int, str] = {}
    next_track = 1

    # Previous geometries are retained for matching.
    previous = {}

    for date, features in observations:
        current = {}

        for feature in features:
            props = feature.get("properties", {})
            source_event_id = int(props.get("event_id"))
            geom = feature.get("geometry")
            if not geom:
                continue

            projected = _project_geometry(
                geom,
                source_crs or payload.get("crs", {}).get("properties", {}).get("name", "EPSG:4326"),
            )

            best_track = None
            best_score = -1.0

            for prev_id, prev_data in previous.items():
                prev_geom = prev_data["geometry"]
                iou = _iou(projected, prev_geom)
                dist = _centroid_distance_km(projected, prev_geom)
                eligible = iou >= iou_threshold or dist <= max_centroid_distance_km
                if not eligible:
                    continue

                # Favor overlap, then proximity.
                score = iou + max(0.0, 1.0 - dist / max_centroid_distance_km) * 0.25
                if score > best_score:
                    best_score = score
                    best_track = prev_data["track_id"]

            if best_track is None:
                best_track = f"EO1-{next_track:06d}"
                next_track += 1
                tracks[best_track] = EventTrack(
                    track_id=best_track,
                    first_observation=date,
                    last_observation=date,
                    observation_count=0,
                    cumulative_area_ha=0.0,
                    peak_area_ha=0.0,
                    max_abs_change=None,
                    mean_score=None,
                    status="active",
                    observations=[],
                )

            area_ha = float(props.get("area_ha", 0.0))
            mean_change = props.get("mean_change")
            mean_score = props.get("mean_score")

            obs = ObservationEvent(
                observation_date=date,
                source_event_id=source_event_id,
                area_ha=area_ha,
                mean_change=float(mean_change) if mean_change is not None else None,
                mean_score=float(mean_score) if mean_score is not None else None,
                geometry=geom,
            )

            track = tracks[best_track]
            track.last_observation = date
            track.observation_count += 1
            track.cumulative_area_ha += area_ha
            track.peak_area_ha = max(track.peak_area_ha, area_ha)

            if mean_change is not None:
                value = abs(float(mean_change))
                track.max_abs_change = value if track.max_abs_change is None else max(track.max_abs_change, value)

            if mean_score is not None:
                previous_scores = [
                    x["mean_score"] for x in track.observations
                    if x.get("mean_score") is not None
                ]
                previous_scores.append(float(mean_score))
                track.mean_score = float(np.mean(previous_scores))

            track.observations.append(asdict(obs))
            current[source_event_id] = {
                "track_id": best_track,
                "geometry": projected,
            }

        # Anything not observed this date is retained as an historical track.
        previous = current

    result = {
        "schema": "earth_one_event_tracks_v1.0",
        "track_count": len(tracks),
        "tracks": [asdict(t) for t in tracks.values()],
        "tracking_parameters": {
            "iou_threshold": iou_threshold,
            "max_centroid_distance_km": max_centroid_distance_km,
        },
        "tracker_version": "1.0.0",
    }

    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
