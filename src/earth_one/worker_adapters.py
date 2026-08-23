
from __future__ import annotations

"""Earth One v2.2 live worker adapters.

Adapters are deliberately explicit:
- Sentinel-1 adapter uses the existing autonomous CDSE engine.
- Sentinel-2 adapter executes only when a local real-input product is supplied.
- Unknown worker types fail closed.
- Every adapter returns success=True only after an underlying QC gate passes.

This module is intentionally not a simulator.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

from .s1_autonomous import S1AutonomousEngine, normalize_scene
from .s2 import preprocess_s2_l2a
from .qa import inspect_file


@dataclass(frozen=True)
class WorkerContext:
    output_root: str


def _result_manifest(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def run_s1_job(job, context: WorkerContext) -> dict[str, Any]:
    """Execute a Sentinel-1 AOI job using the existing autonomous CDSE path."""
    if job.operation not in {"monitor", "s1-monitor", "s1-process"}:
        raise RuntimeError(f"Unsupported Sentinel-1 operation: {job.operation}")

    engine = S1AutonomousEngine()
    bbox = job.payload["bbox"]
    out_dir = Path(context.output_root) / job.sensor / job.tile_id.replace(":", "_") / job.job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # For a single job we use the job window itself. Pairwise temporal analysis
    # remains a separate experiment layer.
    scenes = engine.discover(bbox, job.start, job.end, limit=20)
    if not scenes:
        raise RuntimeError(f"No Sentinel-1 scene discovered for {job.job_id}")

    # Choose the strongest real scene inside the requested window.
    scene = sorted(
        scenes,
        key=lambda s: (
            0 if s.polarization == "DV" else 1,
            0 if s.acquisition_mode == "IW" else 1,
            s.datetime or "",
            s.product_id,
        ),
    )[0]

    output = out_dir / "s1_vv_vh.tif"
    result = engine.process_exact_scene(
        scene,
        bbox,
        output,
        width=1024,
        height=1024,
        polarizations=["VV", "VH"],
        backscatter="GAMMA0_TERRAIN",
    )
    if not result["qc"]["valid"]:
        raise RuntimeError(f"S1 QC failed for {job.job_id}: {result['qc']}")

    manifest = {
        "success": True,
        "sensor": "sentinel-1",
        "job_id": job.job_id,
        "tile_id": job.tile_id,
        "scene": result["scene"],
        "output": result["output"],
        "qc": result["qc"],
        "provenance": result["process_provenance"],
    }
    return _result_manifest(out_dir / "worker_result.json", manifest)


def run_s2_job(job, context: WorkerContext) -> dict[str, Any]:
    """Autonomously discover and process a real Sentinel-2 L2A scene."""
    if job.operation not in {"monitor", "s2-monitor", "s2-process"}:
        raise RuntimeError(f"Unsupported Sentinel-2 operation: {job.operation}")
    from .s2_autonomous import S2AutonomousEngine
    if "bbox" not in job.payload:
        raise RuntimeError(f"No AOI bbox supplied for Sentinel-2 job {job.job_id}")
    bbox=job.payload["bbox"]
    out_dir=Path(context.output_root) / job.sensor / job.tile_id.replace(":", "_") / job.job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    result=S2AutonomousEngine().discover_and_process(
        bbox=bbox, start=job.start, end=job.end, target_date=job.start,
        output_path=out_dir/"s2_bands_scl.tif",
        max_cloud=float(job.payload.get("max_cloud",50.0)),
    )
    if not result["success"] or not result["qc"]["valid"]:
        raise RuntimeError(f"S2 QC failed for {job.job_id}: {result}")
    return result


def worker_for(job, context: WorkerContext):
    if job.sensor == "sentinel-1":
        return lambda j: run_s1_job(j, context)
    if job.sensor == "sentinel-2":
        return lambda j: run_s2_job(j, context)
    raise RuntimeError(f"No worker adapter registered for sensor={job.sensor}")
