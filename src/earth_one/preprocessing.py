from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class ProcessingSpec:
    """
    Deterministic preprocessing contract.

    This module records the operations Earth One intends to apply. The actual
    raster operations are intentionally isolated behind optional backends so
    the scientific pipeline can be tested without silently inventing a
    transformation.
    """
    sensor: str
    input_path: str
    output_dir: str
    target_crs: str = "EPSG:4326"
    target_resolution_m: float = 10.0
    cloud_mask: bool = True
    nodata: float = -9999.0
    resampling: str = "bilinear"
    processor_version: str = "0.3.0"


def write_spec(spec: ProcessingSpec, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(spec), indent=2),
        encoding="utf-8",
    )


def validate_spec(spec: ProcessingSpec) -> list[str]:
    errors = []

    if spec.sensor not in {"sentinel-1", "sentinel-2"}:
        errors.append("sensor must be sentinel-1 or sentinel-2")

    if spec.target_resolution_m <= 0:
        errors.append("target_resolution_m must be > 0")

    if not spec.target_crs.startswith("EPSG:"):
        errors.append("target_crs must use EPSG notation")

    if spec.resampling not in {
        "nearest",
        "bilinear",
        "cubic",
        "average",
    }:
        errors.append("unsupported resampling method")

    return errors


def create_processing_spec(
    sensor: str,
    input_path: str,
    output_dir: str,
    target_crs: str = "EPSG:4326",
    target_resolution_m: float = 10.0,
) -> ProcessingSpec:
    spec = ProcessingSpec(
        sensor=sensor,
        input_path=input_path,
        output_dir=output_dir,
        target_crs=target_crs,
        target_resolution_m=target_resolution_m,
    )
    errors = validate_spec(spec)
    if errors:
        raise ValueError("; ".join(errors))
    return spec
