
from __future__ import annotations

"""Earth One v2.0 execution orchestrator.

Turns deterministic jobs into restartable executable tasks.

Properties:
- explicit lifecycle: PENDING -> RUNNING -> SUCCEEDED/FAILED
- bounded retries
- persistent checkpoint/state ledger
- per-job isolation
- resumability
- dry-run execution planning
- deterministic results
- no fabricated success: a worker must return success explicitly
"""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Iterable
import hashlib
import json
import time
import traceback


TERMINAL = {"SUCCEEDED", "FAILED"}


@dataclass(frozen=True)
class ExecutionJob:
    job_id: str
    tile_id: str
    sensor: str
    operation: str
    start: str
    end: str
    payload: dict[str, Any]


@dataclass
class JobRecord:
    job_id: str
    status: str
    attempts: int = 0
    started_at: float | None = None
    finished_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class ExecutionLedger:
    def __init__(self, path: str | Path):
        self.path=Path(path)
        if self.path.exists():
            self.data=json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data={"schema":"earth_one_execution_ledger_v2.0","jobs":{}}

    def get(self, job_id: str) -> JobRecord:
        raw=self.data.setdefault("jobs",{}).get(job_id)
        if raw is None:
            return JobRecord(job_id=job_id,status="PENDING")
        return JobRecord(**raw)

    def save(self, record: JobRecord) -> None:
        self.data.setdefault("jobs",{})[record.job_id]=asdict(record)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix(self.path.suffix+".tmp")
        tmp.write_text(json.dumps(self.data,indent=2),encoding="utf-8")
        tmp.replace(self.path)

    def summary(self) -> dict[str,int]:
        out={}
        for raw in self.data.get("jobs",{}).values():
            s=raw["status"]
            out[s]=out.get(s,0)+1
        return out


def stable_job_id(payload: dict[str, Any]) -> str:
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def execute_jobs(
    jobs: Iterable[ExecutionJob],
    ledger: ExecutionLedger,
    worker: Callable[[ExecutionJob], dict[str, Any]],
    max_retries: int = 2,
    dry_run: bool = False,
) -> dict[str, Any]:
    jobs=list(jobs)
    results=[]

    for job in jobs:
        rec=ledger.get(job.job_id)

        if rec.status == "SUCCEEDED":
            results.append(asdict(rec))
            continue

        if dry_run:
            rec.status="PLANNED"
            rec.result={"job_id":job.job_id,"sensor":job.sensor,"operation":job.operation}
            ledger.save(rec)
            results.append(asdict(rec))
            continue

        attempts_allowed=max_retries+1
        while rec.attempts < attempts_allowed and rec.status != "SUCCEEDED":
            rec.status="RUNNING"
            rec.attempts += 1
            rec.started_at=time.time()
            rec.error=None
            ledger.save(rec)

            try:
                result=worker(job)
                if not isinstance(result,dict) or result.get("success") is not True:
                    raise RuntimeError("Worker did not return explicit success=True")
                rec.status="SUCCEEDED"
                rec.result=result
                rec.finished_at=time.time()
                rec.error=None
                ledger.save(rec)
            except Exception as exc:
                rec.error="".join(traceback.format_exception_only(type(exc),exc)).strip()
                rec.finished_at=time.time()
                if rec.attempts >= attempts_allowed:
                    rec.status="FAILED"
                    ledger.save(rec)
                else:
                    rec.status="RETRY_PENDING"
                    ledger.save(rec)

        results.append(asdict(rec))

    return {
        "schema":"earth_one_execution_result_v2.0",
        "jobs_submitted":len(jobs),
        "summary":ledger.summary(),
        "results":results,
    }


def load_jobs(path: str | Path) -> list[ExecutionJob]:
    raw=json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw,dict) and "jobs" in raw:
        raw=raw["jobs"]
    return [ExecutionJob(**x) for x in raw]
