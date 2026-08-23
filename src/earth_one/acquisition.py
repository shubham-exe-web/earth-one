from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from .config import Settings
from .manifest import write_jsonl
from .stac import STACClient
from .state import StateStore


class AcquisitionEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        cfg = settings.config["acquisition"]
        self.client = STACClient(
            settings.stac_endpoint,
            timeout=int(cfg["request_timeout_seconds"]),
            max_retries=int(cfg["max_retries"]),
            backoff=int(cfg["backoff_seconds"]),
        )
        self.state = StateStore(settings.state_db)

    def discover(
        self,
        collection: str,
        bbox: list[float],
        start: str,
        end: str,
        limit: int,
        max_cloud: float | None = None,
    ) -> dict:
        observations = self.client.search(
            collection=collection,
            bbox=bbox,
            start=start,
            end=end,
            limit=limit,
            max_cloud=max_cloud,
        )

        new_items = []
        for obs in observations:
            if self.state.upsert_observation(obs):
                new_items.append(obs)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        manifest = self.settings.manifest_dir / f"discovery_{collection}_{stamp}.jsonl"
        written = write_jsonl(manifest, new_items)

        return {
            "collection": collection,
            "found": len(observations),
            "new": len(new_items),
            "manifest": str(manifest),
            "state_total": self.state.count(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "written": written,
        }

    def close(self):
        self.state.close()
