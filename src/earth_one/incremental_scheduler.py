
from __future__ import annotations

"""Earth One v1.9 incremental global monitoring scheduler.

Key property:
Only new/changed observation windows are scheduled. Previously completed
tile-sensor-window jobs are skipped using a persistent state ledger.
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Any
import hashlib, json


@dataclass(frozen=True)
class ObservationWindow:
    tile_id: str
    sensor: str
    start: str
    end: str
    observation_key: str

    def job_key(self) -> str:
        raw="|".join([self.tile_id,self.sensor,self.start,self.end,self.observation_key])
        return hashlib.sha256(raw.encode()).hexdigest()[:24]


class StateLedger:
    def __init__(self, path: str | Path):
        self.path=Path(path)
        if self.path.exists():
            self.data=json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data={"schema":"earth_one_state_v1.9","completed":{}}

    def is_complete(self, job_key: str) -> bool:
        return job_key in self.data.get("completed",{})

    def mark_complete(self, job_key: str, metadata: dict[str,Any] | None=None) -> None:
        self.data.setdefault("completed",{})[job_key]=metadata or {}
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.path.write_text(json.dumps(self.data,indent=2),encoding="utf-8")


def schedule_new(
    windows: Iterable[ObservationWindow],
    ledger: StateLedger,
) -> list[ObservationWindow]:
    out=[]
    for w in windows:
        if not ledger.is_complete(w.job_key()):
            out.append(w)
    return out


def summarize(windows: Iterable[ObservationWindow]) -> dict[str,Any]:
    xs=list(windows)
    sensors=sorted({w.sensor for w in xs})
    tiles=sorted({w.tile_id for w in xs})
    return {
        "count":len(xs),
        "sensors":sensors,
        "tiles":len(tiles),
        "by_sensor":{s:sum(1 for w in xs if w.sensor==s) for s in sensors},
    }
