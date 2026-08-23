from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
from typing import Any

import numpy as np
import rasterio

from .s2 import DEFAULT_MASK_CLASSES

S2_BANDS = {
    "B04": 3,
    "B08": 4,
    "B11": 5,
    "B12": 6,
    "SCL": 7,
    "dataMask": 8,
}

S1_BANDS = {
    "VV": 1,
    "VH": 2,
    "dataMask": 3,
}

INVALID_LABEL = 255
SWIR_THRESHOLD_DN = 1500.0
SWIR_THRESHOLD_REFLECTANCE = SWIR_THRESHOLD_DN / 10000.0
VH_THRESHOLD_DB = -3.0


@dataclass(frozen=True)
class TemporalExperimentConfig:
    name: str
    aoi_bbox: list[float]
    baseline_date: str
    comparison_date: str
    ndvi_baseline: str
    ndvi_comparison: str
    vv_baseline: str | None = None
    vv_comparison: str | None = None
    vh_baseline: str | None = None
    vh_comparison: str | None = None


def _raster_stats(path: str) -> dict[str, Any]:
    p = Path(path)
    with rasterio.open(p) as ds:
        vals = ds.read(1, masked=True).astype(np.float64)
        vals = vals.compressed() if np.ma.isMaskedArray(vals) else vals.ravel()
        vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            raise ValueError(f"No finite pixels: {p}")
        vmin, vmax = float(vals.min()), float(vals.max())
        if vmin >= vmax:
            raise ValueError(f"Constant/invalid raster: {p}")
        return {
            "path": str(p),
            "width": ds.width,
            "height": ds.height,
            "crs": str(ds.crs),
            "transform": tuple(ds.transform),
            "nodata": ds.nodata,
            "min": vmin,
            "max": vmax,
            "mean": float(vals.mean()),
            "valid_pixels": int(vals.size),
        }


def _paired_delta(a_path: str, b_path: str) -> dict[str, Any]:
    with rasterio.open(a_path) as a, rasterio.open(b_path) as b:
        if a.crs != b.crs or a.transform != b.transform or a.width != b.width or a.height != b.height:
            raise ValueError("Baseline/comparison rasters are not on the same grid")
        a1 = a.read(1, masked=True).astype(np.float64)
        b1 = b.read(1, masked=True).astype(np.float64)
        ma = np.ma.getmaskarray(a1)
        mb = np.ma.getmaskarray(b1)
        av = a1.filled(np.nan)
        bv = b1.filled(np.nan)
        valid = (~ma) & (~mb) & np.isfinite(av) & np.isfinite(bv)
        d = bv - av
        v = d[valid]
        if v.size == 0:
            raise ValueError("No common valid pixels for comparison")
        return {
            "valid_pixels": int(v.size),
            "mean_baseline": float(av[valid].mean()),
            "mean_comparison": float(bv[valid].mean()),
            "mean_delta": float(v.mean()),
            "median_delta": float(np.median(v)),
            "p05_delta": float(np.percentile(v, 5)),
            "p95_delta": float(np.percentile(v, 95)),
            "fraction_increase": float((v > 0).mean()),
            "fraction_decrease": float((v < 0).mean()),
            "abs_delta_ge_0.05": float((np.abs(v) >= 0.05).mean()),
            "abs_delta_ge_0.10": float((np.abs(v) >= 0.10).mean()),
        }


def run_temporal_experiment(cfg: TemporalExperimentConfig, output_dir: str | Path) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Required optical evidence.
    ndvi_b = _raster_stats(cfg.ndvi_baseline)
    ndvi_c = _raster_stats(cfg.ndvi_comparison)
    optical = {"NDVI": _paired_delta(cfg.ndvi_baseline, cfg.ndvi_comparison)}

    # Optional SAR evidence. Missing SAR is explicitly recorded, never invented.
    sar = {}
    if cfg.vv_baseline and cfg.vv_comparison:
        _raster_stats(cfg.vv_baseline)
        _raster_stats(cfg.vv_comparison)
        sar["VV"] = _paired_delta(cfg.vv_baseline, cfg.vv_comparison)
    if cfg.vh_baseline and cfg.vh_comparison:
        _raster_stats(cfg.vh_baseline)
        _raster_stats(cfg.vh_comparison)
        sar["VH"] = _paired_delta(cfg.vh_baseline, cfg.vh_comparison)

    multimodal = {}
    if "VV" in sar and "VH" in sar:
        vv = sar["VV"]["mean_delta"]
        vh = sar["VH"]["mean_delta"]
        nd = optical["NDVI"]["mean_delta"]
        multimodal = {
            "modalities_present": ["NDVI", "VV", "VH"],
            "mean_direction": {
                "NDVI": "increase" if nd > 0 else "decrease" if nd < 0 else "zero",
                "VV": "increase" if vv > 0 else "decrease" if vv < 0 else "zero",
                "VH": "increase" if vh > 0 else "decrease" if vh < 0 else "zero",
            },
            "all_three_same_direction": bool(
                (nd > 0 and vv > 0 and vh > 0) or (nd < 0 and vv < 0 and vh < 0)
            ),
        }
    else:
        multimodal = {
            "status": "not_available",
            "reason": "Complete VV+VH paired inputs are not yet available.",
        }

    result = {
        "schema": "earth_one_temporal_experiment_v1.5",
        "status": "complete" if multimodal.get("status") != "not_available" else "optical_or_partial_sar",
        "config": asdict(cfg),
        "baseline_ndvi_qc": ndvi_b,
        "comparison_ndvi_qc": ndvi_c,
        "optical": optical,
        "sar": sar,
        "multimodal": multimodal,
        "guardrail": "Descriptive temporal comparison only; no causal attribution.",
    }

    (out / "experiment_manifest.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


def _read_aligned(path: str | Path):
    path = Path(path)
    with rasterio.open(path) as ds:
        profile = ds.profile.copy()
        arrays = ds.read()
        descriptions = list(ds.descriptions or [])
        return arrays, profile, descriptions


def _assert_same_grid(*profiles):
    ref = profiles[0]
    for p in profiles[1:]:
        if (
            p["width"] != ref["width"]
            or p["height"] != ref["height"]
            or p["crs"] != ref["crs"]
            or p["transform"] != ref["transform"]
        ):
            raise ValueError("Temporal input rasters are not on the same spatial grid.")


def _safe_ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    denom = nir + red
    out = np.full(nir.shape, np.nan, dtype=np.float32)

    valid = np.isfinite(nir) & np.isfinite(red) & (denom != 0)
    out[valid] = ((nir[valid] - red[valid]) / denom[valid]).astype(np.float32)
    return out


def _to_db(linear: np.ndarray) -> np.ndarray:
    out = np.full(linear.shape, np.nan, dtype=np.float32)
    valid = np.isfinite(linear) & (linear > 0)
    out[valid] = (10.0 * np.log10(linear[valid])).astype(np.float32)
    return out


def _write_single(path: Path, arr: np.ndarray, profile: dict, description: str, dtype="float32"):
    p = profile.copy()
    p.update(
        driver="GTiff",
        count=1,
        dtype=dtype,
        nodata=np.nan if dtype != "uint8" else INVALID_LABEL,
        tiled=False,
    )
    p.pop("blockxsize", None)
    p.pop("blockysize", None)

    path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(path, "w", **p) as dst:
        dst.write(arr.astype(dtype), 1)
        dst.set_band_description(1, description)


def build_experiment1(
    s2_before_path: str | Path,
    s2_after_path: str | Path,
    s1_before_path: str | Path,
    s1_after_path: str | Path,
    output_dir: str | Path,
) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    s2b, s2_profile, _ = _read_aligned(s2_before_path)
    s2a, s2a_profile, _ = _read_aligned(s2_after_path)
    s1b, s1_profile, _ = _read_aligned(s1_before_path)
    s1a, s1a_profile, _ = _read_aligned(s1_after_path)

    _assert_same_grid(s2_profile, s2a_profile, s1_profile, s1a_profile)

    # S2 analytical/QA bands.
    b04_b = s2b[S2_BANDS["B04"] - 1].astype(np.float32)
    b08_b = s2b[S2_BANDS["B08"] - 1].astype(np.float32)
    b11_b = s2b[S2_BANDS["B11"] - 1].astype(np.float32)
    b12_b = s2b[S2_BANDS["B12"] - 1].astype(np.float32)
    scl_b = s2b[S2_BANDS["SCL"] - 1].astype(np.int16)
    dm_b = s2b[S2_BANDS["dataMask"] - 1].astype(np.float32)

    b04_a = s2a[S2_BANDS["B04"] - 1].astype(np.float32)
    b08_a = s2a[S2_BANDS["B08"] - 1].astype(np.float32)
    b11_a = s2a[S2_BANDS["B11"] - 1].astype(np.float32)
    b12_a = s2a[S2_BANDS["B12"] - 1].astype(np.float32)
    scl_a = s2a[S2_BANDS["SCL"] - 1].astype(np.int16)
    dm_a = s2a[S2_BANDS["dataMask"] - 1].astype(np.float32)

    # S1 QA and VH.
    vh_b = s1b[S1_BANDS["VH"] - 1].astype(np.float32)
    vh_a = s1a[S1_BANDS["VH"] - 1].astype(np.float32)
    s1dm_b = s1b[S1_BANDS["dataMask"] - 1].astype(np.float32)
    s1dm_a = s1a[S1_BANDS["dataMask"] - 1].astype(np.float32)

    # Established SCL policy from Earth One s2.py.
    s2_valid_b = (~np.isin(scl_b, list(DEFAULT_MASK_CLASSES))) & (dm_b > 0)
    s2_valid_a = (~np.isin(scl_a, list(DEFAULT_MASK_CLASSES))) & (dm_a > 0)

    s1_valid_b = np.isfinite(vh_b) & (vh_b > 0) & (s1dm_b > 0)
    s1_valid_a = np.isfinite(vh_a) & (vh_a > 0) & (s1dm_a > 0)

    joint_valid = (
        s2_valid_b
        & s2_valid_a
        & s1_valid_b
        & s1_valid_a
    )

    ndvi_b = _safe_ndvi(b08_b, b04_b)
    ndvi_a = _safe_ndvi(b08_a, b04_a)
    delta_ndvi = ndvi_a - ndvi_b

    delta_b11 = b11_a - b11_b
    delta_b12 = b12_a - b12_b

    vh_db_b = _to_db(vh_b)
    vh_db_a = _to_db(vh_a)
    delta_vh_db = vh_db_a - vh_db_b

    # Mask all derived products outside the joint temporal evidence mask.
    for arr in (ndvi_b, ndvi_a, delta_ndvi, delta_b11, delta_b12, delta_vh_db):
        arr[~joint_valid] = np.nan

    labels = np.full(joint_valid.shape, INVALID_LABEL, dtype=np.uint8)

    event = joint_valid & (
        (delta_b12 > SWIR_THRESHOLD_REFLECTANCE)
        | (delta_vh_db < VH_THRESHOLD_DB)
    )

    non_event = joint_valid & ~event
    labels[non_event] = 0
    labels[event] = 1

    _write_single(output_dir / "joint_valid_mask.tif",
                  joint_valid.astype(np.uint8),
                  s2_profile,
                  "JOINT_VALID_MASK",
                  dtype="uint8")

    _write_single(output_dir / "ndvi_before.tif",
                  ndvi_b,
                  s2_profile,
                  "NDVI_BEFORE")

    _write_single(output_dir / "ndvi_after.tif",
                  ndvi_a,
                  s2_profile,
                  "NDVI_AFTER")

    _write_single(output_dir / "delta_ndvi.tif",
                  delta_ndvi,
                  s2_profile,
                  "DELTA_NDVI")

    _write_single(output_dir / "delta_b11.tif",
                  delta_b11,
                  s2_profile,
                  "DELTA_B11")

    _write_single(output_dir / "delta_b12.tif",
                  delta_b12,
                  s2_profile,
                  "DELTA_B12")

    _write_single(output_dir / "delta_vh_db.tif",
                  delta_vh_db,
                  s1_profile,
                  "DELTA_VH_DB")

    _write_single(output_dir / "development_labels.tif",
                  labels,
                  s2_profile,
                  "DEVELOPMENT_LABEL",
                  dtype="uint8")

    valid_count = int(np.count_nonzero(joint_valid))
    event_count = int(np.count_nonzero(event))

    provenance = {
        "experiment": "Earth One Experiment 1",
        "mask_policy": {
            "s2_mask_classes": sorted(int(x) for x in DEFAULT_MASK_CLASSES),
            "s2_requires_dataMask": True,
            "s1_requires_dataMask": True,
        },
        "swir": {
            "primary_band": "B12",
            "secondary_band": "B11",
            "threshold_dn": SWIR_THRESHOLD_DN,
            "threshold_reflectance": SWIR_THRESHOLD_REFLECTANCE,
            "target_rule": "DELTA_B12 > 0.15 OR DELTA_VH_DB < -3.0",
        },
        "vh": {
            "input_units": "linear_gamma0",
            "output_units": "dB",
            "threshold_db": VH_THRESHOLD_DB,
        },
        "label_encoding": {
            "0": "valid_non_event",
            "1": "valid_event",
            "255": "invalid_or_unknown",
        },
        "grid": {
            "width": int(s2_profile["width"]),
            "height": int(s2_profile["height"]),
            "crs": str(s2_profile["crs"]),
            "transform": list(s2_profile["transform"]),
        },
        "joint_valid_pixels": valid_count,
        "total_pixels": int(joint_valid.size),
        "joint_valid_fraction": float(valid_count / joint_valid.size),
        "event_pixels": event_count,
        "event_fraction_among_valid": (
            float(event_count / valid_count) if valid_count else 0.0
        ),
    }

    (output_dir / "experiment1_provenance.json").write_text(
        json.dumps(provenance, indent=2),
        encoding="utf-8",
    )

    return provenance
