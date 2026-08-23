from __future__ import annotations
from pathlib import Path
import json
from datetime import datetime, timezone

def build_cycle_report(result: dict, output: str | Path) -> dict:
    summary=result.get("summary",{})
    failed=summary.get("FAILED",0)
    succeeded=summary.get("SUCCEEDED",0)
    report={
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "status":"FAILED" if failed else "SUCCESS",
        "headline":(f"Earth One completed with {failed} failed jobs." if failed else f"Earth One completed with {succeeded} successful jobs."),
        "summary":summary,
        "evidence_guardrail":"Execution success is not scientific validation; scientific findings require data QC and evidence-tier promotion.",
        "result_file":str(output),
    }
    p=Path(output); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(report,indent=2),encoding="utf-8")
    return report
