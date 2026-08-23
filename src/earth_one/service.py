
from __future__ import annotations

"""Earth One autonomous service loop.

A long-running process that:
- loads local secrets
- executes the configured global/incremental job plan
- persists execution state
- emits email alerts
- waits and repeats

The service is restartable and does not require QGIS or manual scene selection.
"""

from pathlib import Path
import json
import os
import time
import traceback
from datetime import datetime, timezone

from .runtime_config import load_env_file, env_status
from .autonomous_cycle import run_cycle


def run_service(
    jobs_path: str,
    ledger_path: str,
    output_root: str,
    result_dir: str,
    interval_seconds: int,
    send_email: bool,
    once: bool = False,
) -> None:
    load_env_file()
    result_dir_p = Path(result_dir)
    result_dir_p.mkdir(parents=True, exist_ok=True)

    while True:
        started = datetime.now(timezone.utc)
        stamp = started.strftime("%Y%m%dT%H%M%SZ")
        result_json = result_dir_p / f"cycle_{stamp}.json"

        try:
            result = run_cycle(
                jobs_path=jobs_path,
                ledger_path=ledger_path,
                output_root=output_root,
                result_json=result_json,
                max_retries=2,
                dry_run=False,
                send_email=send_email,
            )
            (result_dir_p / "LATEST.json").write_text(
                json.dumps(result, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            error = {
                "status": "SERVICE_ERROR",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
            (result_dir_p / f"service_error_{stamp}.json").write_text(
                json.dumps(error, indent=2), encoding="utf-8"
            )
            # Service continues; the next cycle retries the whole process.
        if once:
            return
        time.sleep(max(60, int(interval_seconds)))


def configured() -> bool:
    status = env_status()
    return bool(
        status["CDSE_CLIENT_ID"] and
        status["CDSE_CLIENT_SECRET"]
    )
