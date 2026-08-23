
from pathlib import Path
import json
import pytest

from earth_one.execution_orchestrator import ExecutionJob, ExecutionLedger, execute_jobs
from earth_one.worker_adapters import WorkerContext, worker_for


def test_unknown_sensor_fails_closed():
    job=ExecutionJob("1","T","unknown","monitor","2026-01-01","2026-01-31",{})
    with pytest.raises(RuntimeError):
        worker_for(job, WorkerContext("/tmp/earth-one-test"))


def test_s2_worker_refuses_missing_real_input():
    job=ExecutionJob("1","T","sentinel-2","monitor","2026-01-01","2026-01-31",{})
    worker=worker_for(job, WorkerContext("/tmp/earth-one-test"))
    with pytest.raises(RuntimeError):
        worker(job)


def test_end_to_end_orchestrator_planning():
    job=ExecutionJob("1","T","unknown","monitor","2026-01-01","2026-01-31",{})
    ledger=ExecutionLedger(Path("/tmp/earth-one-worker-test-state.json"))
    # dry-run bypasses worker invocation for planning only
    result=execute_jobs([job],ledger,lambda j: {"success":True},dry_run=True)
    assert result["summary"]["PLANNED"]==1
