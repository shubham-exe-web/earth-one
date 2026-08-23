
from __future__ import annotations

"""Earth One v1.6 evidence and validation engine.

Distinguishes:
- internal reproducibility checks (same source products / derived outputs)
- independent-reference validation
- evidence promotion status

No candidate is promoted to a scientific finding without an explicit
independent-reference requirement unless the user deliberately configures
a lower evidence tier.
"""

from pathlib import Path
import json
from typing import Any
import numpy as np
import rasterio


EVIDENCE_TIERS = {
    "INTERNAL_REPRODUCIBILITY": 1,
    "REAL_DATA_VALIDATED": 2,
    "INDEPENDENT_REFERENCE_VALIDATED": 3,
    "END_TO_END_VALIDATED": 4,
}


def _read(path: str | Path):
    with rasterio.open(path) as ds:
        arr = ds.read(1, masked=True).astype(np.float64)
        meta = {
            "crs": str(ds.crs),
            "transform": tuple(ds.transform),
            "width": ds.width,
            "height": ds.height,
            "nodata": ds.nodata,
        }
        return arr, meta


def compare_rasters(observed: str | Path, expected: str | Path, tolerance: float = 1e-6) -> dict[str, Any]:
    a, am = _read(observed)
    b, bm = _read(expected)
    if am["crs"] != bm["crs"] or am["transform"] != bm["transform"] or am["width"] != bm["width"] or am["height"] != bm["height"]:
        raise ValueError("Raster grids are not aligned.")
    av = a.filled(np.nan)
    bv = b.filled(np.nan)
    valid = np.isfinite(av) & np.isfinite(bv)
    if not valid.any():
        raise ValueError("No common valid pixels.")
    d = av[valid] - bv[valid]
    rmse = float(np.sqrt(np.mean(d * d)))
    mae = float(np.mean(np.abs(d)))
    max_abs = float(np.max(np.abs(d)))
    corr = None
    if np.std(av[valid]) > 0 and np.std(bv[valid]) > 0:
        corr = float(np.corrcoef(av[valid], bv[valid])[0, 1])
    return {
        "valid": bool(rmse <= tolerance),
        "valid_pixels": int(valid.sum()),
        "rmse": rmse,
        "mae": mae,
        "max_abs_error": max_abs,
        "correlation": corr,
        "tolerance": tolerance,
    }


def validate_against_reference(
    observed_change: str | Path,
    reference_change: str | Path,
    threshold: float = 0.0,
    agreement_tolerance: float = 0.0,
) -> dict[str, Any]:
    obs, om = _read(observed_change)
    ref, rm = _read(reference_change)
    if om["crs"] != rm["crs"] or om["transform"] != rm["transform"] or om["width"] != rm["width"] or om["height"] != rm["height"]:
        raise ValueError("Observed/reference rasters are not aligned.")
    o = obs.filled(np.nan)
    r = ref.filled(np.nan)
    valid = np.isfinite(o) & np.isfinite(r)
    if not valid.any():
        raise ValueError("No common valid reference pixels.")
    ov, rv = o[valid], r[valid]
    obs_sign = np.sign(ov - threshold)
    ref_sign = np.sign(rv - threshold)
    agreement = np.abs(ov - rv) <= agreement_tolerance if agreement_tolerance > 0 else (obs_sign == ref_sign)
    return {
        "valid_pixels": int(valid.sum()),
        "agreement_fraction": float(np.mean(agreement)),
        "observed_positive_fraction": float(np.mean(obs_sign > 0)),
        "reference_positive_fraction": float(np.mean(ref_sign > 0)),
        "independent_reference": True,
        "evidence_tier": "INDEPENDENT_REFERENCE_VALIDATED",
    }


def promote_evidence(
    *,
    real_data_pass: bool,
    reproducibility_pass: bool,
    independent_reference_pass: bool,
    end_to_end_pass: bool,
) -> dict[str, Any]:
    if end_to_end_pass and real_data_pass and reproducibility_pass and independent_reference_pass:
        status = "END_TO_END_VALIDATED"
    elif independent_reference_pass and real_data_pass and reproducibility_pass:
        status = "INDEPENDENT_REFERENCE_VALIDATED"
    elif real_data_pass and reproducibility_pass:
        status = "REAL_DATA_VALIDATED"
    elif reproducibility_pass:
        status = "INTERNAL_REPRODUCIBILITY"
    else:
        status = "NOT_VALIDATED"
    return {
        "status": status,
        "tier": EVIDENCE_TIERS.get(status, 0),
        "paper_claim_allowed": status in {"INDEPENDENT_REFERENCE_VALIDATED", "END_TO_END_VALIDATED"},
        "causal_claim_allowed": False,
    }


def write_evidence_record(record: dict[str, Any], output: str | Path) -> None:
    p=Path(output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(record, indent=2), encoding="utf-8")
