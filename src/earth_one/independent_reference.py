
from __future__ import annotations

"""Earth One v1.7 independent-reference discovery.

Primary reference source:
Landsat Collection 2 Level-2 Surface Reflectance via a public STAC endpoint.

Why Landsat?
- independent sensor family from Sentinel-2
- analysis-ready surface reflectance
- 30 m product resolution
- independent quality-assessment bands
- global availability for Landsat 8/9

The engine only discovers/selects here; live retrieval must run where network
access is available. It never fabricates a reference product.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import requests


PLANETARY_COMPUTER_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
LANDSAT_COLLECTION = "landsat-c2-l2"


@dataclass(frozen=True)
class ReferenceScene:
    id: str
    datetime: str
    platform: str | None
    cloud_cover: float | None
    bbox: list[float] | None
    assets: dict[str, Any]
    properties: dict[str, Any]


def _scene_from_item(item: dict[str, Any]) -> ReferenceScene:
    props=item.get("properties", {})
    cloud=props.get("eo:cloud_cover")
    return ReferenceScene(
        id=item["id"],
        datetime=props.get("datetime") or props.get("start_datetime"),
        platform=props.get("platform"),
        cloud_cover=float(cloud) if cloud is not None else None,
        bbox=item.get("bbox"),
        assets=item.get("assets", {}),
        properties=props,
    )


def discover_landsat(
    bbox: list[float],
    start: str,
    end: str,
    limit: int = 50,
    max_cloud: float = 80.0,
    session: requests.Session | None = None,
) -> list[ReferenceScene]:
    s=session or requests.Session()
    payload={
        "collections":[LANDSAT_COLLECTION],
        "bbox":bbox,
        "datetime":f"{start}T00:00:00Z/{end}T23:59:59Z",
        "limit":limit,
        "query":{"eo:cloud_cover":{"lte":max_cloud}},
        "sortby":[{"field":"properties.datetime","direction":"asc"}],
    }
    r=s.post(f"{PLANETARY_COMPUTER_STAC}/search",json=payload,timeout=60)
    r.raise_for_status()
    items=r.json().get("features",[])
    return [_scene_from_item(x) for x in items]


def rank_reference_scenes(
    scenes: list[ReferenceScene],
    target_datetime: str,
) -> list[ReferenceScene]:
    target=datetime.fromisoformat(target_datetime.replace("Z","+00:00"))
    def key(s):
        dt=datetime.fromisoformat(s.datetime.replace("Z","+00:00"))
        gap=abs((dt-target).total_seconds())/86400
        cloud=999 if s.cloud_cover is None else s.cloud_cover
        return (gap,cloud,s.id)
    return sorted(scenes,key=key)


def select_best_reference(
    scenes: list[ReferenceScene],
    target_datetime: str,
) -> ReferenceScene:
    if not scenes:
        raise RuntimeError("No independent Landsat reference scene found")
    return rank_reference_scenes(scenes,target_datetime)[0]


def save_reference_manifest(
    scenes: list[ReferenceScene],
    selected: ReferenceScene | None,
    bbox: list[float],
    output: str | Path,
) -> None:
    record={
        "schema":"earth_one_independent_reference_v1.7",
        "provider":"Microsoft Planetary Computer",
        "collection":LANDSAT_COLLECTION,
        "reference_sensor":"Landsat 8/9 Collection 2 Level-2 Surface Reflectance",
        "aoi_bbox":bbox,
        "candidate_count":len(scenes),
        "selected":None if selected is None else asdict(selected),
        "candidates":[asdict(s) for s in scenes],
        "status":"DISCOVERED" if selected else "NOT_DISCOVERED",
        "claim_guardrail":"Discovery is not validation; independent-reference validation occurs only after the selected data are actually retrieved and QA-filtered."
    }
    p=Path(output); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(record,indent=2),encoding="utf-8")
