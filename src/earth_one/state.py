from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    collection TEXT NOT NULL,
    datetime TEXT,
    discovered_at TEXT NOT NULL,
    bbox_json TEXT,
    cloud_cover REAL,
    platform TEXT,
    status TEXT NOT NULL DEFAULT 'discovered',
    error TEXT,
    metadata_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observations_collection
ON observations(collection);

CREATE INDEX IF NOT EXISTS idx_observations_datetime
ON observations(datetime);

CREATE INDEX IF NOT EXISTS idx_observations_status
ON observations(status);
"""


class StateStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def upsert_observation(self, obs: dict[str, Any]) -> bool:
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO observations
            (id, collection, datetime, discovered_at, bbox_json,
             cloud_cover, platform, status, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'discovered', ?)
            """,
            (
                obs["id"],
                obs["collection"],
                obs.get("datetime"),
                obs["discovered_at"],
                json.dumps(obs.get("bbox")),
                obs.get("cloud_cover"),
                obs.get("platform"),
                json.dumps(obs),
            ),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM observations"
        ).fetchone()[0]
