
from earth_one.execution_orchestrator import ExecutionJob, ExecutionLedger, execute_jobs

def job(i):
    return ExecutionJob(str(i), f"T{i}", "sentinel-1", "monitor", "2026-01-01","2026-01-31", {})

def test_success_is_persisted_and_resume_skips(tmp_path):
    ledger=ExecutionLedger(tmp_path/"ledger.json")
    calls=[]
    def worker(j):
        calls.append(j.job_id)
        return {"success":True,"value":42}
    out=execute_jobs([job("1"),job("2")],ledger,worker)
    assert out["summary"]["SUCCEEDED"]==2
    assert calls==["1","2"]
    calls.clear()
    out2=execute_jobs([job("1"),job("2")],ledger,worker)
    assert calls==[]
    assert out2["summary"]["SUCCEEDED"]==2

def test_retry_then_success(tmp_path):
    ledger=ExecutionLedger(tmp_path/"ledger.json")
    calls={"n":0}
    def worker(j):
        calls["n"]+=1
        if calls["n"]<2: raise RuntimeError("temporary")
        return {"success":True}
    out=execute_jobs([job("1")],ledger,worker,max_retries=2)
    assert out["summary"]["SUCCEEDED"]==1
    assert calls["n"]==2

def test_failed_worker_is_never_marked_success(tmp_path):
    ledger=ExecutionLedger(tmp_path/"ledger.json")
    def worker(j): raise RuntimeError("bad data")
    out=execute_jobs([job("1")],ledger,worker,max_retries=1)
    assert out["summary"]["FAILED"]==1
    rec=ledger.get("1")
    assert rec.status=="FAILED"
    assert rec.result is None

def test_dry_run_does_not_execute_worker(tmp_path):
    ledger=ExecutionLedger(tmp_path/"ledger.json")
    called=[]
    def worker(j):
        called.append(j.job_id)
        return {"success":True}
    out=execute_jobs([job("1")],ledger,worker,dry_run=True)
    assert called==[]
    assert out["summary"]["PLANNED"]==1
