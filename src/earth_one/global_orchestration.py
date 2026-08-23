
from __future__ import annotations

"""Earth One v1.8 global scope and orchestration foundation.

This layer makes geographic scale an orchestration concern rather than a
processing concern. The same sensor/analysis modules can operate on:
- a fixed AOI
- a named region
- a country
- a continent
- a global scope represented by a deterministic tile grid

The global grid is deterministic, restartable and job-manifest driven.
No sensor processing is performed here.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable
import hashlib
import json
import math


@dataclass(frozen=True)
class Scope:
    scope_id: str
    scope_type: str
    bbox: tuple[float, float, float, float]

    def validate(self) -> None:
        west, south, east, north = self.bbox
        if not (-180 <= west < east <= 180):
            raise ValueError(f"Invalid longitude bounds: {self.bbox}")
        if not (-90 <= south < north <= 90):
            raise ValueError(f"Invalid latitude bounds: {self.bbox}")
        if self.scope_type not in {"aoi", "region", "country", "continent", "global"}:
            raise ValueError(f"Unsupported scope type: {self.scope_type}")


@dataclass(frozen=True)
class Tile:
    tile_id: str
    row: int
    col: int
    bbox: tuple[float, float, float, float]
    scope_id: str

    def as_dict(self) -> dict:
        d=asdict(self)
        d["bbox"]=list(self.bbox)
        return d


@dataclass(frozen=True)
class Job:
    job_id: str
    tile_id: str
    scope_id: str
    sensor: str
    operation: str
    start: str
    end: str
    payload: dict

    def as_dict(self) -> dict:
        return asdict(self)


def global_scope() -> Scope:
    return Scope("GLOBAL", "global", (-180.0, -90.0, 180.0, 90.0))


def make_scope(scope_id: str, scope_type: str, bbox: Iterable[float]) -> Scope:
    b=tuple(float(x) for x in bbox)
    if len(b)!=4:
        raise ValueError("bbox must contain west,south,east,north")
    s=Scope(scope_id, scope_type, b)
    s.validate()
    return s


def tile_scope(scope: Scope, tile_width_deg: float=5.0, tile_height_deg: float=5.0) -> list[Tile]:
    if tile_width_deg <= 0 or tile_height_deg <= 0:
        raise ValueError("Tile dimensions must be positive")
    scope.validate()
    west,south,east,north=scope.bbox
    cols=max(1, math.ceil((east-west)/tile_width_deg))
    rows=max(1, math.ceil((north-south)/tile_height_deg))
    tiles=[]
    for r in range(rows):
        s=south+r*tile_height_deg
        n=min(north,s+tile_height_deg)
        for c in range(cols):
            w=west+c*tile_width_deg
            e=min(east,w+tile_width_deg)
            tid=f"{scope.scope_id}:{r:04d}:{c:04d}"
            tiles.append(Tile(tid,r,c,(w,s,e,n),scope.scope_id))
    return tiles


def stable_job_id(tile_id: str, sensor: str, operation: str, start: str, end: str) -> str:
    raw="|".join([tile_id,sensor,operation,start,end])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def build_jobs(scope: Scope, sensors: Iterable[str], operation: str, start: str, end: str,
               tile_width_deg: float=5.0, tile_height_deg: float=5.0) -> list[Job]:
    tiles=tile_scope(scope,tile_width_deg,tile_height_deg)
    jobs=[]
    for t in tiles:
        for sensor in sensors:
            jid=stable_job_id(t.tile_id,sensor,operation,start,end)
            jobs.append(Job(
                jid,t.tile_id,scope.scope_id,sensor,operation,start,end,
                {"bbox":list(t.bbox),"tile_row":t.row,"tile_col":t.col},
            ))
    return jobs


def partition_jobs(jobs: list[Job], shard_count: int, shard_index: int) -> list[Job]:
    if shard_count <= 0 or not (0 <= shard_index < shard_count):
        raise ValueError("Invalid shard_count/shard_index")
    return [job for i,job in enumerate(jobs) if i % shard_count == shard_index]


def write_manifest(scope: Scope, jobs: list[Job], output: str | Path) -> dict:
    scope.validate()
    p=Path(output)
    p.parent.mkdir(parents=True,exist_ok=True)
    record={
        "schema":"earth_one_global_manifest_v1.8",
        "scope":asdict(scope),
        "job_count":len(jobs),
        "jobs":[j.as_dict() for j in jobs],
        "orchestration":"deterministic_restartable_manifest",
    }
    p.write_text(json.dumps(record,indent=2),encoding="utf-8")
    return record
