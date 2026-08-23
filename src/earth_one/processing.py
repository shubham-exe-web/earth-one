from __future__ import annotations

import json
from pathlib import Path


def build_processing_record(observation: dict, local_path: str) -> dict:
    """
    Creates the hand-off contract between acquisition and preprocessing.

    No scientific transformation happens here yet. This keeps acquisition
    auditable and makes the next module independently testable.
    """
    return {
        "schema_version": "earth-one-observation-0.1",
        "source": {
            "item_id": observation.get("id"),
            "collection": observation.get("collection"),
            "datetime": observation.get("datetime"),
            "platform": observation.get("platform"),
        },
        "local": {
            "path": local_path,
        },
        "quality": {
            "cloud_cover": observation.get("cloud_cover"),
        },
        "lineage": {
            "stac_endpoint": observation.get("_stac_endpoint"),
            "discovered_at": observation.get("discovered_at"),
        },
        "processing": {
            "status": "pending",
            "processor_version": "0.1.0",
        },
    }


def write_processing_record(path: Path, record: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
