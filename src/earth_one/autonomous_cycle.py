
from __future__ import annotations

"""Earth One v2.2 autonomous cycle.

Runs an execution plan, persists its ledger, creates an execution report,
and optionally emails the report. No result is promoted unless the worker
explicitly returns success=True.
"""

from pathlib import Path
import json
from dataclasses import asdict

from .execution_orchestrator import load_jobs, ExecutionLedger, execute_jobs
from .worker_adapters import WorkerContext, worker_for
from .alerting import SMTPAlertSender, alert_from_execution
from .result_report import build_cycle_report


def run_cycle(
    jobs_path: str | Path,
    ledger_path: str | Path,
    output_root: str | Path,
    result_json: str | Path,
    max_retries: int = 2,
    dry_run: bool = False,
    send_email: bool = False,
) -> dict:
    from .runtime_config import load_env_file
    load_env_file()

    jobs = load_jobs(jobs_path)
    context = WorkerContext(str(output_root))

    # Worker dispatcher is created per job because sensor adapters may have
    # independent external dependencies.
    def dispatch(job):
        worker = worker_for(job, context)
        return worker(job)

    ledger = ExecutionLedger(ledger_path)
    result = execute_jobs(
        jobs,
        ledger,
        dispatch,
        max_retries=max_retries,
        dry_run=dry_run,
    )
    rp = Path(result_json)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(result, indent=2), encoding="utf-8")
    report_path = rp.with_name("cycle_report.json")
    report = build_cycle_report(result, report_path)
    result["report"] = report
    if send_email:
        sender = SMTPAlertSender()
        alert = alert_from_execution(result)
        alert = alert.__class__(
            severity=alert.severity,
            title=alert.title,
            summary=alert.summary,
            details=alert.details,
            attachments=(str(rp), str(report_path)),
        )
        result["email"] = sender.send(alert, dry_run=False)
    rp.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
