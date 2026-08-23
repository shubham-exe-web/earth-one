from __future__ import annotations

from pathlib import Path
import json


def build_observation_record(
    event_tracks_json: str | Path,
    output_json: str | Path,
    carbon_results: list[str | Path] | None = None,
) -> dict:
    """
    Build the first research-ready Earth One observation package.

    The package combines persistent event tracks with optional biomass/carbon
    results. Missing carbon is explicitly represented as unavailable rather
    than inferred.
    """
    tracks_payload = json.loads(Path(event_tracks_json).read_text(encoding="utf-8"))

    carbon_by_track = {}
    for path in carbon_results or []:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        track_id = payload.get("track_id")
        if track_id:
            carbon_by_track[track_id] = payload

    observations = []
    for track in tracks_payload.get("tracks", []):
        track_id = track["track_id"]
        record = dict(track)
        record["carbon"] = carbon_by_track.get(track_id)
        record["carbon_status"] = (
            "available" if track_id in carbon_by_track else "not_estimated"
        )
        observations.append(record)

    result = {
        "schema": "earth_one_research_observation_v1.0",
        "observation_count": len(observations),
        "observations": observations,
        "pipeline_version": "1.0.0",
    }

    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
