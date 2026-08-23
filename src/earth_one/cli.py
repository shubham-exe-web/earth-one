from __future__ import annotations

import argparse
import json
from pathlib import Path
from dataclasses import asdict
import pickle
import numpy as np
import rasterio

from .config import Settings
from .acquisition import AcquisitionEngine
from .auth import CDSETokenProvider
from .downloader import DownloadManager
from .preprocessing import create_processing_spec, write_spec
from .qa import inspect_file
from .s2 import preprocess_s2_l2a, write_result
from .indices import calculate_indices, write_index_results
from .change_detection import detect_index_change, write_change_result
from .s1_process import request_s1
from .s1_autonomous import run_matched_pair
from .composite import temporal_median
from .feature_stack import build_optical_sar_stack
from .event_score import score_disturbance_candidates
from .router import ModelRouter
from .classifier import train_classifier, infer_classifier, write_result as write_classifier_result
from .validation_v08 import spatial_validate_model, write_result as write_validation_result, calibrate_confidence
from .uncertainty import confidence_to_uncertainty
from .temporal_validation import temporal_validate_model, write_result as write_temporal_result
from .events import segment_events, write_event_table, write_event_json
from .reference import match_events_to_reference
from .event_report import build_event_catalog
from .tracking import track_event_observations
from .biomass import estimate_event_carbon
from .pipeline import build_observation_record


def build_parser():
    parser = argparse.ArgumentParser(prog="earth-one")
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover")
    discover.add_argument("--collection", required=True, choices=["sentinel-1-grd", "sentinel-2-l2a"])
    discover.add_argument("--bbox", required=True)
    discover.add_argument("--start", required=True)
    discover.add_argument("--end", required=True)
    discover.add_argument("--limit", type=int, default=100)
    discover.add_argument("--max-cloud", type=float, default=None)
    discover.add_argument("--config", default="config.yaml")

    download = sub.add_parser("download")
    download.add_argument("--url", required=True)
    download.add_argument("--output", required=True)
    download.add_argument("--config", default="config.yaml")
    download.add_argument("--overwrite", action="store_true")

    prep = sub.add_parser("prep-spec")
    prep.add_argument("--sensor", required=True, choices=["sentinel-1", "sentinel-2"])
    prep.add_argument("--input", required=True)
    prep.add_argument("--output-dir", required=True)
    prep.add_argument("--target-crs", default="EPSG:4326")
    prep.add_argument("--resolution", type=float, default=10.0)
    prep.add_argument("--output", required=True)

    s2 = sub.add_parser("preprocess-s2")
    s2.add_argument("--input", required=True)
    s2.add_argument("--output", required=True)
    s2.add_argument("--target-crs", default=None)
    s2.add_argument("--resolution", type=float, default=10.0)
    s2.add_argument("--result-json", default=None)

    index = sub.add_parser("indices")
    index.add_argument("--input", required=True)
    index.add_argument("--output", required=True)
    index.add_argument("--index", action="append", dest="indices", default=["NDVI"])
    index.add_argument("--result-json", default=None)

    change = sub.add_parser("change")
    change.add_argument("--baseline", required=True)
    change.add_argument("--comparison", required=True)
    change.add_argument("--output", required=True)
    change.add_argument("--threshold", type=float, default=0.20)
    change.add_argument("--result-json", default=None)

    preflight = sub.add_parser("s1-preflight")
    preflight.add_argument("--output", default=None, help="optional JSON report path")

    s1auto = sub.add_parser("s1-auto-pair")
    s1auto.add_argument("--bbox", required=True)
    s1auto.add_argument("--before-start", required=True)
    s1auto.add_argument("--before-end", required=True)
    s1auto.add_argument("--after-start", required=True)
    s1auto.add_argument("--after-end", required=True)
    s1auto.add_argument("--output-dir", required=True)
    s1auto.add_argument("--relative-orbit", type=int, default=None)
    s1auto.add_argument("--width", type=int, default=1024)
    s1auto.add_argument("--height", type=int, default=1024)
    s1auto.add_argument("--dry-run", action="store_true", help="discover and match only; do not call Process API")

    s1 = sub.add_parser("s1-process")
    s1.add_argument("--bbox", required=True)
    s1.add_argument("--start", required=True)
    s1.add_argument("--end", required=True)
    s1.add_argument("--output", required=True)
    s1.add_argument("--width", type=int, default=512)
    s1.add_argument("--height", type=int, default=512)
    s1.add_argument("--backscatter", default="GAMMA0_TERRAIN",
                     choices=["BETA0", "SIGMA0_ELLIPSOID", "GAMMA0_ELLIPSOID", "GAMMA0_TERRAIN"])
    s1.add_argument("--vv-only", action="store_true")

    comp = sub.add_parser("composite")
    comp.add_argument("--input", action="append", dest="inputs", required=True)
    comp.add_argument("--output", required=True)

    stack = sub.add_parser("stack")
    stack.add_argument("--ndvi", required=True)
    stack.add_argument("--vv", required=True)
    stack.add_argument("--vh", default=None)
    stack.add_argument("--output", required=True)
    stack.add_argument("--result-json", default=None)
    stack.add_argument("--target", default="ndvi", choices=["ndvi", "vv", "vh"])

    fusion = sub.add_parser("multimodal-stack")
    fusion.add_argument("--ndvi", required=True)
    fusion.add_argument("--vv", required=True)
    fusion.add_argument("--vh", required=True)
    fusion.add_argument("--output", required=True)
    fusion.add_argument("--result-json", default=None)
    fusion.add_argument("--target", default="ndvi", choices=["ndvi", "vv", "vh"])

    temporal = sub.add_parser("temporal-experiment")
    temporal.add_argument("--config-json", required=True)
    temporal.add_argument("--output-dir", required=True)

    repro = sub.add_parser("reproducibility")
    repro.add_argument("--baseline", required=True)
    repro.add_argument("--comparison", required=True)
    repro.add_argument("--delta", required=True)
    repro.add_argument("--output", required=True)
    evidence = sub.add_parser("promote-evidence")
    evidence.add_argument("--real-data-pass", action="store_true")
    evidence.add_argument("--reproducibility-pass", action="store_true")
    evidence.add_argument("--independent-reference-pass", action="store_true")
    evidence.add_argument("--end-to-end-pass", action="store_true")

    refdisc = sub.add_parser("reference-discover")
    refdisc.add_argument("--bbox", required=True)
    refdisc.add_argument("--start", required=True)
    refdisc.add_argument("--end", required=True)
    refdisc.add_argument("--target-datetime", required=True)
    refdisc.add_argument("--max-cloud", type=float, default=80.0)
    refdisc.add_argument("--output", required=True)

    scope = sub.add_parser("scope-manifest")
    scope.add_argument("--scope-id", required=True)
    scope.add_argument("--scope-type", required=True, choices=["aoi","region","country","continent","global"])
    scope.add_argument("--bbox", required=True)
    scope.add_argument("--sensor", action="append", dest="sensors", required=True)
    scope.add_argument("--operation", required=True)
    scope.add_argument("--start", required=True)
    scope.add_argument("--end", required=True)
    scope.add_argument("--tile-width-deg", type=float, default=5.0)
    scope.add_argument("--tile-height-deg", type=float, default=5.0)
    scope.add_argument("--shard-count", type=int, default=1)
    scope.add_argument("--shard-index", type=int, default=0)
    scope.add_argument("--output", required=True)

    incr = sub.add_parser("incremental-schedule")
    incr.add_argument("--windows-json", required=True)
    incr.add_argument("--state", required=True)
    incr.add_argument("--output", required=True)

    execute = sub.add_parser("execute-jobs")
    execute.add_argument("--jobs", required=True)
    execute.add_argument("--ledger", required=True)
    execute.add_argument("--output", required=True)
    execute.add_argument("--max-retries", type=int, default=2)
    execute.add_argument("--dry-run", action="store_true")

    alert_exec = sub.add_parser("alert-execution")
    alert_exec.add_argument("--result-json", required=True)
    alert_exec.add_argument("--dry-run", action="store_true")

    alert_find = sub.add_parser("alert-finding")
    alert_find.add_argument("--title", required=True)
    alert_find.add_argument("--summary", required=True)
    alert_find.add_argument("--details-json", required=True)
    alert_find.add_argument("--attachment", action="append", default=[])
    alert_find.add_argument("--dry-run", action="store_true")

    cycle = sub.add_parser("autonomous-cycle")
    cycle.add_argument("--jobs", required=True)
    cycle.add_argument("--ledger", required=True)
    cycle.add_argument("--output-root", required=True)
    cycle.add_argument("--result-json", required=True)
    cycle.add_argument("--max-retries", type=int, default=2)
    cycle.add_argument("--dry-run", action="store_true")
    cycle.add_argument("--send-email", action="store_true")

    s2auto = sub.add_parser("s2-auto-process")
    s2auto.add_argument("--bbox", required=True)
    s2auto.add_argument("--start", required=True)
    s2auto.add_argument("--end", required=True)
    s2auto.add_argument("--target-date", required=True)
    s2auto.add_argument("--output", required=True)
    s2auto.add_argument("--max-cloud", type=float, default=50.0)

    service = sub.add_parser("service-run")
    service.add_argument("--jobs", required=True)
    service.add_argument("--ledger", required=True)
    service.add_argument("--output-root", required=True)
    service.add_argument("--result-dir", required=True)
    service.add_argument("--interval-seconds", type=int, default=21600)
    service.add_argument("--send-email", action="store_true")
    service.add_argument("--once", action="store_true")

    config_status = sub.add_parser("config-status")

    s2qc = sub.add_parser("s2-qc")
    s2qc.add_argument("--path", required=True)

    score = sub.add_parser("score")
    score.add_argument("--change", required=True)
    score.add_argument("--output", required=True)
    score.add_argument("--threshold", type=float, default=0.20)

    route = sub.add_parser("route")
    route.add_argument("--features", required=True)

    train = sub.add_parser("train")
    train.add_argument("--features", required=True)
    train.add_argument("--labels", required=True)
    train.add_argument("--model", required=True)
    train.add_argument("--test-size", type=float, default=0.20)
    train.add_argument("--max-per-class", type=int, default=10000)
    train.add_argument("--result-json", default=None)

    infer = sub.add_parser("infer")
    infer.add_argument("--features", required=True)
    infer.add_argument("--model", required=True)
    infer.add_argument("--classes", required=True)
    infer.add_argument("--confidence", required=True)
    infer.add_argument("--result-json", default=None)

    validate_spatial = sub.add_parser("validate-spatial")
    validate_spatial.add_argument("--features", required=True)
    validate_spatial.add_argument("--labels", required=True)
    validate_spatial.add_argument("--model", required=True)
    validate_spatial.add_argument("--block-size", type=int, default=32)
    validate_spatial.add_argument("--test-fraction", type=float, default=0.20)
    validate_spatial.add_argument("--result-json", required=True)

    validate_temporal = sub.add_parser("validate-temporal")
    validate_temporal.add_argument("--features", action="append", required=True)
    validate_temporal.add_argument("--labels", action="append", required=True)
    validate_temporal.add_argument("--model", required=True)
    validate_temporal.add_argument("--result-json", required=True)

    calibrate = sub.add_parser("calibrate")
    calibrate.add_argument("--features", required=True)
    calibrate.add_argument("--labels", required=True)
    calibrate.add_argument("--model", required=True)
    calibrate.add_argument("--output", required=True)

    uncertainty = sub.add_parser("uncertainty")
    uncertainty.add_argument("--confidence", required=True)
    uncertainty.add_argument("--output", required=True)

    events = sub.add_parser("events")
    events.add_argument("--change", required=True)
    events.add_argument("--score", required=True)
    events.add_argument("--event-raster", required=True)
    events.add_argument("--event-table", required=True)
    events.add_argument("--event-json", required=True)
    events.add_argument("--geojson", default=None)
    events.add_argument("--min-pixels", type=int, default=9)
    events.add_argument("--score-threshold", type=float, default=0.5)
    events.add_argument("--connectivity", type=int, default=8, choices=[4, 8])

    ref = sub.add_parser("match-reference")
    ref.add_argument("--events", required=True)
    ref.add_argument("--reference", required=True)
    ref.add_argument("--output", required=True)

    catalog = sub.add_parser("event-catalog")
    catalog.add_argument("--events", required=True)
    catalog.add_argument("--reference", default=None)
    catalog.add_argument("--output", required=True)

    track = sub.add_parser("track-events")
    track.add_argument("--observation", action="append", required=True,
                       help="GeoJSON observation files, each containing observation_date.")
    track.add_argument("--output", required=True)
    track.add_argument("--iou-threshold", type=float, default=0.20)
    track.add_argument("--max-centroid-km", type=float, default=2.0)
    track.add_argument("--source-crs", default=None)

    carbon = sub.add_parser("carbon")
    carbon.add_argument("--biomass-before", required=True)
    carbon.add_argument("--biomass-after", required=True)
    carbon.add_argument("--event-mask", required=True)
    carbon.add_argument("--output", required=True)
    carbon.add_argument("--carbon-fraction", type=float, default=0.47)
    carbon.add_argument("--biomass-uncertainty", type=float, default=None)
    carbon.add_argument("--track-id", default=None)

    observation = sub.add_parser("observation")
    observation.add_argument("--tracks", required=True)
    observation.add_argument("--output", required=True)
    observation.add_argument("--carbon", action="append", default=None)

    qa = sub.add_parser("qa")
    qa.add_argument("--input", required=True)
    return parser


def parse_bbox(value: str):
    values = [float(x.strip()) for x in value.split(",")]
    if len(values) != 4:
        raise ValueError("bbox must contain west,south,east,north")
    west, south, east, north = values
    if not (-180 <= west <= east <= 180):
        raise ValueError("invalid longitude range")
    if not (-90 <= south <= north <= 90):
        raise ValueError("invalid latitude range")
    return values


def main():
    args = build_parser().parse_args()

    if args.command == "s1-preflight":
        from .s1_autonomous import local_preflight
        result = local_preflight()
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))

    elif args.command == "discover":
        settings = Settings.load(args.config)
        engine = AcquisitionEngine(settings)
        try:
            print(json.dumps(engine.discover(
                collection=args.collection, bbox=parse_bbox(args.bbox),
                start=args.start, end=args.end, limit=args.limit,
                max_cloud=args.max_cloud,
            ), indent=2))
        finally:
            engine.close()

    elif args.command == "download":
        settings = Settings.load(args.config)
        manager = DownloadManager(CDSETokenProvider(timeout=settings.timeout), timeout=settings.timeout)
        print(json.dumps(manager.download(args.url, Path(args.output), overwrite=args.overwrite), indent=2))

    elif args.command == "prep-spec":
        spec = create_processing_spec(args.sensor, args.input, args.output_dir, args.target_crs, args.resolution)
        write_spec(spec, Path(args.output))
        print(json.dumps({"status": "spec_created", "output": args.output}, indent=2))

    elif args.command == "preprocess-s2":
        result = preprocess_s2_l2a(args.input, args.output, args.target_crs, args.resolution)
        if args.result_json:
            write_result(result, Path(args.result_json))
        print(json.dumps(result.__dict__, indent=2))

    elif args.command == "indices":
        results = calculate_indices(args.input, args.output, args.indices)
        if args.result_json:
            write_index_results(results, Path(args.result_json))
        print(json.dumps([r.__dict__ for r in results], indent=2))

    elif args.command == "change":
        result = detect_index_change(args.baseline, args.comparison, args.output, args.threshold)
        if args.result_json:
            write_change_result(result, Path(args.result_json))
        print(json.dumps(result.__dict__, indent=2))

    elif args.command == "s1-auto-pair":
        print(json.dumps(run_matched_pair(
            parse_bbox(args.bbox), args.before_start, args.before_end,
            args.after_start, args.after_end, args.output_dir,
            preferred_relative_orbit=args.relative_orbit,
            width=args.width, height=args.height, dry_run=args.dry_run,
        ), indent=2))

    elif args.command == "s1-process":
        print(json.dumps(request_s1(
            parse_bbox(args.bbox), args.start, args.end, args.output,
            args.width, args.height,
            ["VV"] if args.vv_only else ["VV", "VH"], args.backscatter,
        ), indent=2))

    elif args.command == "composite":
        print(json.dumps(temporal_median(args.inputs, args.output), indent=2))

    elif args.command == "stack":
        # Legacy stack remains available.
        print(json.dumps(build_optical_sar_stack(args.ndvi, args.vv, args.vh, args.output), indent=2))

    elif args.command == "multimodal-stack":
        from .multimodal_fusion import FeatureSpec, build_multimodal_stack
        specs = [
            FeatureSpec("NDVI", args.ndvi, "sentinel-2", 1, "average"),
        FeatureSpec("VV", args.vv, "sentinel-1", 1, "average"),
        FeatureSpec("VH", args.vh, "sentinel-1", 2, "average"),
        ]
        result = build_multimodal_stack(
            specs,
            args.output,
            target_feature=args.target.upper(),
            result_json=args.result_json,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "temporal-experiment":
        from .temporal_experiment import TemporalExperimentConfig, run_temporal_experiment
        cfg = TemporalExperimentConfig(**json.loads(Path(args.config_json).read_text(encoding="utf-8")))
        result = run_temporal_experiment(cfg, args.output_dir)
        print(json.dumps(result, indent=2))

    elif args.command == "reproducibility":
        from .reproducibility import verify_change_reconstruction
        result = verify_change_reconstruction(args.baseline, args.comparison, args.delta, output=args.output)
        print(json.dumps(result, indent=2))

    elif args.command == "promote-evidence":
        from .evidence_validation import promote_evidence
        result = promote_evidence(
            real_data_pass=args.real_data_pass,
            reproducibility_pass=args.reproducibility_pass,
            independent_reference_pass=args.independent_reference_pass,
            end_to_end_pass=args.end_to_end_pass,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "reference-discover":
        from .independent_reference import discover_landsat, select_best_reference, save_reference_manifest
        scenes = discover_landsat(
            parse_bbox(args.bbox), args.start, args.end, max_cloud=args.max_cloud
        )
        selected = select_best_reference(scenes, args.target_datetime) if scenes else None
        save_reference_manifest(scenes, selected, parse_bbox(args.bbox), args.output)
        print(json.dumps({
            "status": "DISCOVERED" if selected else "NOT_DISCOVERED",
            "candidate_count": len(scenes),
            "selected": None if selected is None else selected.id,
        }, indent=2))

    elif args.command == "scope-manifest":
        from .global_orchestration import make_scope, build_jobs, partition_jobs, write_manifest
        scope_obj = make_scope(args.scope_id, args.scope_type, parse_bbox(args.bbox))
        jobs = build_jobs(
            scope_obj, args.sensors, args.operation, args.start, args.end,
            args.tile_width_deg, args.tile_height_deg
        )
        jobs = partition_jobs(jobs, args.shard_count, args.shard_index)
        result = write_manifest(scope_obj, jobs, args.output)
        print(json.dumps({
            "status": "READY",
            "scope_id": args.scope_id,
            "jobs": len(jobs),
            "shard_count": args.shard_count,
            "shard_index": args.shard_index,
            "output": args.output,
        }, indent=2))

    elif args.command == "incremental-schedule":
        from .incremental_scheduler import ObservationWindow, StateLedger, schedule_new, summarize
        raw = json.loads(Path(args.windows_json).read_text(encoding="utf-8"))
        windows = [ObservationWindow(**x) for x in raw]
        ledger = StateLedger(args.state)
        new = schedule_new(windows, ledger)
        payload = [asdict(x) | {"job_key": x.job_key()} for x in new]
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps({"status":"READY","new_jobs":len(new),"summary":summarize(new),"output":args.output}, indent=2))

    elif args.command == "execute-jobs":
        from .execution_orchestrator import load_jobs, ExecutionLedger, execute_jobs
        jobs=load_jobs(args.jobs)

        def worker(job):
            # v2.0 execution contract: real sensor adapters replace this dispatcher.
            # Unknown operations are deliberately rejected, never marked successful.
            raise RuntimeError(
                f"No live worker adapter registered for sensor={job.sensor} operation={job.operation}"
            )

        result=execute_jobs(
            jobs,
            ExecutionLedger(args.ledger),
            worker,
            max_retries=args.max_retries,
            dry_run=args.dry_run,
        )
        Path(args.output).parent.mkdir(parents=True,exist_ok=True)
        Path(args.output).write_text(json.dumps(result,indent=2),encoding="utf-8")
        print(json.dumps({"status":"COMPLETE","jobs":result["jobs_submitted"],"summary":result["summary"]},indent=2))

    elif args.command == "alert-execution":
        from .alerting import SMTPAlertSender, alert_from_execution
        result=json.loads(Path(args.result_json).read_text(encoding="utf-8"))
        alert=alert_from_execution(result)
        print(json.dumps(SMTPAlertSender().send(alert,dry_run=args.dry_run),indent=2))

    elif args.command == "alert-finding":
        from .alerting import SMTPAlertSender, alert_from_finding
        details=json.loads(Path(args.details_json).read_text(encoding="utf-8"))
        alert=alert_from_finding(args.title,args.summary,details,args.attachment)
        print(json.dumps(SMTPAlertSender().send(alert,dry_run=args.dry_run),indent=2))

    elif args.command == "autonomous-cycle":
        from .autonomous_cycle import run_cycle
        result = run_cycle(
            args.jobs,
            args.ledger,
            args.output_root,
            args.result_json,
            max_retries=args.max_retries,
            dry_run=args.dry_run,
            send_email=args.send_email,
        )
        print(json.dumps({
            "status": "COMPLETE",
            "summary": result.get("summary"),
            "email": result.get("email"),
            "result_json": args.result_json,
        }, indent=2))

    elif args.command == "s2-auto-process":
        from .s2_autonomous import S2AutonomousEngine
        result=S2AutonomousEngine().discover_and_process(
            parse_bbox(args.bbox), args.start, args.end, args.target_date,
            args.output, max_cloud=args.max_cloud
        )
        print(json.dumps(result,indent=2))

    elif args.command == "service-run":
        from .service import run_service
        from .runtime_config import load_env_file
        load_env_file()
        run_service(
            args.jobs, args.ledger, args.output_root, args.result_dir,
            args.interval_seconds, args.send_email, args.once
        )

    elif args.command == "config-status":
        from .runtime_config import load_env_file, env_status
        p = load_env_file()
        print(json.dumps({
            "env_file": str(p) if p else None,
            "configured": env_status(),
        }, indent=2))

    elif args.command == "s2-qc":
        from .s2_autonomous import S2AutonomousEngine
        from pathlib import Path
        p = Path(args.path)
        qc = S2AutonomousEngine.validate(p)
        print(json.dumps(qc, indent=2))
        if not qc.get("valid"):
            raise SystemExit(1)

    elif args.command == "score":
        print(json.dumps(score_disturbance_candidates(args.change, args.output, args.threshold), indent=2))

    elif args.command == "route":
        decision = ModelRouter().route({x.strip() for x in args.features.split(",") if x.strip()})
        print(json.dumps(decision.__dict__, indent=2))

    elif args.command == "train":
        result = train_classifier(args.features, args.labels, args.model, args.test_size, args.max_per_class)
        if args.result_json:
            write_classifier_result(result, Path(args.result_json))
        print(json.dumps(result.__dict__, indent=2))

    elif args.command == "infer":
        result = infer_classifier(args.features, args.model, args.classes, args.confidence)
        if args.result_json:
            write_classifier_result(result, Path(args.result_json))
        print(json.dumps(result.__dict__, indent=2))

    elif args.command == "validate-spatial":
        result = spatial_validate_model(
            args.features, args.labels, args.model,
            block_size=args.block_size, test_fraction=args.test_fraction,
        )
        write_validation_result(result, Path(args.result_json))
        print(json.dumps(result.__dict__, indent=2))

    elif args.command == "validate-temporal":
        result = temporal_validate_model(args.features, args.labels, args.model)
        write_temporal_result(result, Path(args.result_json))
        print(json.dumps(result, indent=2))

    elif args.command == "calibrate":
        with rasterio.open(args.features) as ds:
            X = ds.read().astype(np.float32)
            profile = ds.profile.copy()
        with rasterio.open(args.labels) as ds:
            y = ds.read(1).astype(np.int32)
            if ds.crs != profile["crs"] or ds.transform != profile["transform"]:
                raise ValueError("Feature and label rasters are not aligned.")
        with Path(args.model).open("rb") as f:
            payload = pickle.load(f)
        model = payload["model"]
        X = X.reshape(X.shape[0], -1).T
        y = y.reshape(-1)
        valid = np.all(np.isfinite(X), axis=1) & (y > 0)
        pred = model.predict(X[valid])
        proba = model.predict_proba(X[valid])
        from .validation_v08 import calibrate_confidence
        result = calibrate_confidence(y[valid], proba, pred)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result.__dict__, indent=2), encoding="utf-8")
        print(json.dumps(result.__dict__, indent=2))

    elif args.command == "uncertainty":
        print(json.dumps(confidence_to_uncertainty(args.confidence, args.output), indent=2))

    elif args.command == "events":
        events = segment_events(
            args.change, args.score, args.event_raster,
            min_pixels=args.min_pixels,
            score_threshold=args.score_threshold,
            connectivity=args.connectivity,
            geojson_path=args.geojson,
        )
        write_event_table(events, Path(args.event_table))
        write_event_json(events, Path(args.event_json))
        print(json.dumps({
            "event_count": len(events),
            "event_raster": args.event_raster,
            "event_table": args.event_table,
            "event_json": args.event_json,
            "geojson": args.geojson,
            "processor_version": "0.9.0",
        }, indent=2))

    elif args.command == "match-reference":
        print(json.dumps(match_events_to_reference(args.events, args.reference, args.output), indent=2))

    elif args.command == "event-catalog":
        print(json.dumps(build_event_catalog(args.events, args.reference, args.output), indent=2))

    elif args.command == "track-events":
        print(json.dumps(track_event_observations(
            args.observation, args.output,
            iou_threshold=args.iou_threshold,
            max_centroid_distance_km=args.max_centroid_km,
            source_crs=args.source_crs,
        ), indent=2))

    elif args.command == "carbon":
        result = estimate_event_carbon(
            args.biomass_before, args.biomass_after, args.event_mask, args.output,
            carbon_fraction=args.carbon_fraction,
            biomass_uncertainty_fraction=args.biomass_uncertainty,
        )
        payload = result.__dict__
        if args.track_id:
            payload["track_id"] = args.track_id
            Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2))

    elif args.command == "observation":
        print(json.dumps(build_observation_record(
            args.tracks, args.output, args.carbon
        ), indent=2))

    elif args.command == "qa":
        print(json.dumps(inspect_file(Path(args.input)).__dict__, indent=2))


if __name__ == "__main__":
    main()
