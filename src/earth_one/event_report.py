from __future__ import annotations

from pathlib import Path
import json
import csv


def build_event_catalog(
    event_table_csv: str | Path,
    classification_csv: str | Path | None,
    output_json: str | Path,
) -> dict:
    """
    Combine event attributes with optional class/reference attributes.

    The catalog is deliberately a flat, auditable object. Later versions can
    turn it into a persistent event database.
    """
    with Path(event_table_csv).open(encoding="utf-8") as f:
        events = list(csv.DictReader(f))

    classifications = {}
    if classification_csv:
        with Path(classification_csv).open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                classifications[str(row["event_id"])] = row

    catalog = []
    for event in events:
        eid = str(event["event_id"])
        record = dict(event)
        if eid in classifications:
            record["reference"] = classifications[eid]
        catalog.append(record)

    result = {
        "schema": "earth_one_event_catalog_v0.9",
        "event_count": len(catalog),
        "events": catalog,
        "catalog_version": "0.9.0",
    }

    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
