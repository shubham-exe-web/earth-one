from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import requests


class STACClient:
    def __init__(self, endpoint: str, timeout: int = 60, max_retries: int = 4, backoff: int = 2):
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.endpoint}/{path.lstrip('/')}"
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self.session.post(url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                if attempt == self.max_retries - 1:
                    raise
                import time
                time.sleep(self.backoff ** attempt)
        raise last_error

    def get_collections(self) -> dict[str, Any]:
        response = self.session.get(
            f"{self.endpoint}/collections",
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def search(
        self,
        collection: str,
        bbox: list[float],
        start: str,
        end: str,
        limit: int = 100,
        max_cloud: float | None = None,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "collections": [collection],
            "bbox": bbox,
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
            "limit": limit,
        }

        # STAC query extension. Different collections expose different
        # property names, so cloud filtering is only added for Sentinel-2.
        if max_cloud is not None and collection == "sentinel-2-l2a":
            payload["query"] = {
                "eo:cloud_cover": {"lte": max_cloud}
            }

        data = self._post("/search", payload)
        features = data.get("features", [])

        # Normalize only the metadata Earth One needs at this stage.
        observations = []
        for item in features:
            props = item.get("properties", {})
            observations.append({
                "id": item.get("id"),
                "collection": (item.get("collection") or [collection])[0],
                "bbox": item.get("bbox"),
                "geometry": item.get("geometry"),
                "datetime": props.get("datetime"),
                "created": props.get("created"),
                "updated": props.get("updated"),
                "cloud_cover": props.get("eo:cloud_cover"),
                "platform": props.get("platform"),
                "instruments": props.get("instruments"),
                "orbit_state": props.get("sat:orbit_state"),
                "assets": {
                    key: {
                        "href": value.get("href"),
                        "type": value.get("type"),
                        "roles": value.get("roles"),
                        "title": value.get("title"),
                    }
                    for key, value in item.get("assets", {}).items()
                },
                "stac_links": item.get("links", []),
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            })
        return observations
