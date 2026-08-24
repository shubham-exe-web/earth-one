from __future__ import annotations

"""Flood Module 2: Autonomous Multimodal Flood & Inundation Monitoring Core.

Five Evidence Channels:
1. Channel A: Sentinel-1 SAR backscatter decrease & specular reflectance (ΔVV, ΔVH)
2. Channel B: Sentinel-2 optical water indices (NDWI, MNDWI) with cloud-aware masking
3. Channel C: Water-baseline novelty (distinguishing new inundation from permanent/seasonal water)
4. Channel D: Rainfall meteorological context (accumulation & anomaly priors)
5. Channel E: Terrain & hydrologic plausibility (slope & elevation constraints)

Decision Engine Architecture:
- Gated Physics-Informed Fusion: Gating water evidence through JRC baseline and terrain constraints
- Morphological Filtering: Removing small isolated speckles and filling internal voids
- Seamlessly integrates with Earth One EventRecord, tracking, and alerting architectures.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import shapes
from scipy import ndimage
from shapely.geometry import shape, mapping

from .events import EventRecord


@dataclass
class FloodEvidenceConfig:
    # Decision Engine Fusion Strategy: "gated_physics" (default) or "linear_blend"
    fusion_strategy: str = "gated_physics"

    # Evidence channel weights
    weight_sar: float = 0.35
    weight_optical: float = 0.25
    weight_novelty: float = 0.20
    weight_rain: float = 0.10
    weight_terrain: float = 0.10

    # SAR change parameters (dB)
    sar_delta_vv_thresh_db: float = -2.0
    sar_delta_vh_thresh_db: float = -2.0
    sar_water_vv_ceiling_db: float = -14.0
    sar_water_vh_ceiling_db: float = -20.0
    sar_input_units: str = "linear"

    # Optical parameters
    optical_mndwi_thresh: float = 0.0
    optical_ndwi_thresh: float = 0.0

    # Novelty parameters
    permanent_water_max_freq: float = 0.80

    # Terrain plausibility parameters
    terrain_max_slope_deg: float = 8.0
    terrain_cutoff_slope_deg: float = 15.0

    # Rainfall context parameters (mm)
    rain_min_accumulation_mm: float = 15.0
    rain_nominal_accumulation_mm: float = 100.0

    # Morphology parameters
    apply_morphological_opening: bool = True
    morphology_kernel_size: int = 2

    # Event segmentation parameters
    min_event_pixels: int = 4
    pixel_resolution_m: float = 20.0
    default_detection_threshold: float = 0.20
    high_sensitivity_threshold: float = 0.15
    high_specificity_threshold: float = 0.50


@dataclass
class FloodDetectionResult:
    status: str  # "accepted", "no_evidence", "rejected"
    flood_score: np.ndarray
    candidate_mask: np.ndarray
    valid_mask: np.ndarray
    score_statistics: dict[str, float]
    evidence_layers: dict[str, dict[str, float]]
    valid_fraction: float
    candidate_pixels: int
    candidate_area_ha: float
    available_channels: list[str]
    configuration: dict[str, Any]
    provenance: dict[str, Any]


def compute_sar_water_evidence(
    vv_before: np.ndarray,
    vv_event: np.ndarray,
    vh_before: np.ndarray | None = None,
    vh_event: np.ndarray | None = None,
    config: FloodEvidenceConfig | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute Channel A (SAR water evidence) from Sentinel-1 backscatter drops.
    Inundated flat water causes specular reflection, dropping both absolute power and ratio.
    """
    if config is None:
        config = FloodEvidenceConfig()

    vv_b = np.asarray(vv_before, dtype=np.float32)
    vv_e = np.asarray(vv_event, dtype=np.float32)

    # Valid SAR pixels
    valid = np.isfinite(vv_b) & np.isfinite(vv_e) & (vv_b > 0) & (vv_e > 0)

    def to_db(arr):
        if config.sar_input_units == "db":
            return np.asarray(arr, dtype=np.float32)
        if config.sar_input_units != "linear":
            raise ValueError("sar_input_units must be linear or db")
        return 10.0 * np.log10(np.clip(arr, 1e-7, 10.0))

    vv_b_db = to_db(vv_b)
    vv_e_db = to_db(vv_e)
    delta_vv_db = vv_e_db - vv_b_db

    # Score component 1: Relative backscatter drop
    vv_break = abs(float(config.sar_delta_vv_thresh_db))
    if vv_break <= 0:
        raise ValueError("sar_delta_vv_thresh_db must be negative and non-zero")
    s_delta_vv = np.clip(((-delta_vv_db) - vv_break) / max(1e-6, 6.0 - vv_break), 0.0, 1.0)

    # Score component 2: Absolute low backscatter
    s_abs_vv = np.clip((config.sar_water_vv_ceiling_db - vv_e_db) / 8.0 + 0.5, 0.0, 1.0)

    sar_score = 0.6 * s_delta_vv + 0.4 * s_abs_vv

    # Incorporate cross-polarization VH if provided
    if vh_before is not None and vh_event is not None:
        vh_b = np.asarray(vh_before, dtype=np.float32)
        vh_e = np.asarray(vh_event, dtype=np.float32)
        vh_valid = np.isfinite(vh_b) & np.isfinite(vh_e) & (vh_b > 0) & (vh_e > 0)
        valid = valid & vh_valid

        vh_b_db = to_db(vh_b)
        vh_e_db = to_db(vh_e)
        delta_vh_db = vh_e_db - vh_b_db

        vh_break = abs(float(config.sar_delta_vh_thresh_db))
        if vh_break <= 0:
            raise ValueError("sar_delta_vh_thresh_db must be negative and non-zero")
        s_delta_vh = np.clip(((-delta_vh_db) - vh_break) / max(1e-6, 6.0 - vh_break), 0.0, 1.0)
        s_abs_vh = np.clip((config.sar_water_vh_ceiling_db - vh_e_db) / 8.0 + 0.5, 0.0, 1.0)
        sar_vh_score = 0.6 * s_delta_vh + 0.4 * s_abs_vh

        sar_score = 0.55 * sar_score + 0.45 * sar_vh_score

    sar_score = np.where(valid, np.clip(sar_score, 0.0, 1.0), 0.0)
    return sar_score, valid


def compute_optical_water_evidence(
    b03_green: np.ndarray,
    b08_nir: np.ndarray,
    b11_swir: np.ndarray | None = None,
    scl_mask: np.ndarray | None = None,
    config: FloodEvidenceConfig | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute Channel B (Optical water evidence) via NDWI & MNDWI.
    Cloud-obscured pixels are masked as invalid (NOT non-flood).
    """
    if config is None:
        config = FloodEvidenceConfig()

    green = np.asarray(b03_green, dtype=np.float32)
    nir = np.asarray(b08_nir, dtype=np.float32)

    valid = np.isfinite(green) & np.isfinite(nir) & (green > 0) & (nir > 0)

    # Standard S2 clear classes: 4 (veg), 5 (bare), 6 (water), 7 (unclassified)
    if scl_mask is not None:
        scl = np.asarray(scl_mask, dtype=np.int32)
        valid_scl = np.isin(scl, [4, 5, 6, 7])
        valid = valid & valid_scl

    # Standard NDWI: (Green - NIR) / (Green + NIR)
    ndwi = (green - nir) / np.clip(green + nir, 1e-4, 2.0)
    s_ndwi = np.clip((ndwi - config.optical_ndwi_thresh) / 0.5 + 0.5, 0.0, 1.0)

    if b11_swir is not None:
        swir = np.asarray(b11_swir, dtype=np.float32)
        valid = valid & np.isfinite(swir) & (swir > 0)
        # Modified NDWI (MNDWI): (Green - SWIR) / (Green + SWIR)
        mndwi = (green - swir) / np.clip(green + swir, 1e-4, 2.0)
        s_mndwi = np.clip((mndwi - config.optical_mndwi_thresh) / 0.5 + 0.5, 0.0, 1.0)
        optical_score = 0.4 * s_ndwi + 0.6 * s_mndwi
    else:
        optical_score = s_ndwi

    optical_score = np.where(valid, np.clip(optical_score, 0.0, 1.0), 0.0)
    return optical_score, valid


def compute_water_novelty(
    water_evidence_score: np.ndarray,
    permanent_water_frequency: np.ndarray,
    config: FloodEvidenceConfig | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute Channel C (Water Novelty).
    Differentiates permanent rivers/lakes/reservoirs from new anomalous flood inundation.
    FloodNovelty = EventWater ∩ ¬NormalWater
    """
    if config is None:
        config = FloodEvidenceConfig()

    w_score = np.asarray(water_evidence_score, dtype=np.float32)
    perm_freq = np.asarray(permanent_water_frequency, dtype=np.float32)

    valid = np.isfinite(w_score) & np.isfinite(perm_freq)

    novelty_multiplier = np.clip(1.0 - (perm_freq / config.permanent_water_max_freq), 0.0, 1.0)
    novelty_score = w_score * novelty_multiplier

    novelty_score = np.where(valid, np.clip(novelty_score, 0.0, 1.0), 0.0)
    return novelty_score, valid


def compute_terrain_plausibility(
    slope_degrees: np.ndarray,
    elevation_m: np.ndarray | None = None,
    config: FloodEvidenceConfig | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute Channel E (Terrain / Hydrologic plausibility constraint).
    Standing inundation accumulates in flat / low-slope terrain (slope <= 5-8°).
    Steep slopes (>15°) are physically constrained against standing surface water.
    """
    if config is None:
        config = FloodEvidenceConfig()

    slope = np.asarray(slope_degrees, dtype=np.float32)
    valid = np.isfinite(slope) & (slope >= 0)

    terrain_score = np.ones_like(slope)
    steep_mask = slope > config.terrain_max_slope_deg
    terrain_score[steep_mask] = np.clip(
        1.0 - (slope[steep_mask] - config.terrain_max_slope_deg) / 
        (config.terrain_cutoff_slope_deg - config.terrain_max_slope_deg),
        0.0, 1.0
    )

    terrain_score = np.where(valid, np.clip(terrain_score, 0.0, 1.0), 0.0)
    return terrain_score, valid


def compute_rainfall_context(
    accumulation_mm: float,
    anomaly_std: float = 0.0,
    hours_since_peak: float = 12.0,
    config: FloodEvidenceConfig | None = None,
) -> float:
    """
    Compute Channel D (Rainfall meteorological context).
    Provides meteorological prior context (NOT ground truth).
    """
    if config is None:
        config = FloodEvidenceConfig()

    if accumulation_mm < config.rain_min_accumulation_mm:
        return 0.05

    acc_factor = np.clip(accumulation_mm / config.rain_nominal_accumulation_mm, 0.0, 1.0)
    anom_factor = np.clip((anomaly_std + 1.0) / 4.0, 0.0, 1.0)
    time_decay = np.exp(-max(0.0, hours_since_peak) / 72.0)

    rain_score = float(np.clip(0.6 * acc_factor + 0.4 * anom_factor, 0.0, 1.0) * (0.5 + 0.5 * time_decay))
    return float(np.clip(rain_score, 0.0, 1.0))


def fuse_flood_evidence(
    sar_evidence: np.ndarray | None = None,
    sar_valid: np.ndarray | None = None,
    optical_evidence: np.ndarray | None = None,
    optical_valid: np.ndarray | None = None,
    novelty_evidence: np.ndarray | None = None,
    novelty_valid: np.ndarray | None = None,
    terrain_plausibility: np.ndarray | None = None,
    terrain_valid: np.ndarray | None = None,
    rainfall_score: float | None = None,
    config: FloodEvidenceConfig | None = None,
    aoi_metadata: dict[str, Any] | None = None,
) -> FloodDetectionResult:
    """
    Fuse multi-source evidence channels into a calibrated Flood Score S_flood.
    Supports:
    - gated_physics (default): Gating water surface change by JRC baseline and terrain physics
    - linear_blend: Weighted average blend for backward compatibility and ablation
    """
    if config is None:
        config = FloodEvidenceConfig()

    # Determine reference grid shape
    ref_shape = None
    for arr in [sar_evidence, optical_evidence, novelty_evidence, terrain_plausibility]:
        if arr is not None:
            ref_shape = arr.shape
            break
    if ref_shape is None:
        raise ValueError("At least one spatial evidence raster must be provided to fuse_flood_evidence.")

    overall_valid = np.zeros(ref_shape, dtype=bool)
    available_channels = []
    layer_stats: dict[str, dict[str, float]] = {}

    v_sar = sar_valid if (sar_evidence is not None and sar_valid is not None) else (np.isfinite(sar_evidence) if sar_evidence is not None else np.zeros(ref_shape, dtype=bool))
    v_opt = optical_valid if (optical_evidence is not None and optical_valid is not None) else (np.isfinite(optical_evidence) if optical_evidence is not None else np.zeros(ref_shape, dtype=bool))
    v_nov = novelty_valid if (novelty_evidence is not None and novelty_valid is not None) else (np.isfinite(novelty_evidence) if novelty_evidence is not None else np.zeros(ref_shape, dtype=bool))
    v_terr = terrain_valid if (terrain_plausibility is not None and terrain_valid is not None) else (np.isfinite(terrain_plausibility) if terrain_plausibility is not None else np.zeros(ref_shape, dtype=bool))

    if sar_evidence is not None and v_sar.any():
        overall_valid |= v_sar
        available_channels.append("sar")
        layer_stats["sar"] = {"mean": float(np.mean(sar_evidence[v_sar])) if v_sar.any() else 0.0, "max": float(np.max(sar_evidence[v_sar])) if v_sar.any() else 0.0}

    if optical_evidence is not None and v_opt.any():
        overall_valid |= v_opt
        available_channels.append("optical")
        layer_stats["optical"] = {"mean": float(np.mean(optical_evidence[v_opt])) if v_opt.any() else 0.0, "max": float(np.max(optical_evidence[v_opt])) if v_opt.any() else 0.0}

    if novelty_evidence is not None:
        available_channels.append("novelty")
        layer_stats["novelty"] = {"mean": float(np.mean(novelty_evidence[v_nov])) if v_nov.any() else 0.0, "max": float(np.max(novelty_evidence[v_nov])) if v_nov.any() else 0.0}

    if terrain_plausibility is not None and v_terr.any():
        available_channels.append("terrain")
        layer_stats["terrain"] = {"mean": float(np.mean(terrain_plausibility[v_terr])) if v_terr.any() else 0.0}

    if rainfall_score is not None:
        available_channels.append("rainfall")
        layer_stats["rainfall"] = {"score": float(rainfall_score)}

    fused_score = np.zeros(ref_shape, dtype=np.float32)

    if config.fusion_strategy == "gated_physics":
        # 1. Primary Inundation Signal (SAR + Optical conditional blend)
        has_sar = sar_evidence is not None and v_sar.any()
        has_opt = optical_evidence is not None and v_opt.any()

        primary_water = np.zeros(ref_shape, dtype=np.float32)
        if has_sar and has_opt:
            w_sar = config.weight_sar
            w_opt = config.weight_optical
            w_sum = np.where(v_sar & v_opt, w_sar + w_opt, np.where(v_sar, w_sar, np.where(v_opt, w_opt, 1e-5)))
            primary_water = np.where(v_sar & v_opt, (w_sar * sar_evidence + w_opt * optical_evidence) / w_sum,
                                     np.where(v_sar, sar_evidence, np.where(v_opt, optical_evidence, 0.0)))
        elif has_sar:
            primary_water = np.where(v_sar, sar_evidence, 0.0)
        elif has_opt:
            primary_water = np.where(v_opt, optical_evidence, 0.0)

        # 2. Multiplicative Gating
        m_nov = novelty_evidence if (novelty_evidence is not None and v_nov.any()) else np.ones(ref_shape, dtype=np.float32)
        m_terr = terrain_plausibility if (terrain_plausibility is not None and v_terr.any()) else np.ones(ref_shape, dtype=np.float32)
        m_rain = (0.70 + 0.30 * rainfall_score) if rainfall_score is not None else 1.0

        gated = primary_water * m_nov * m_terr * m_rain
        fused_score[overall_valid] = np.clip(gated[overall_valid], 0.0, 1.0)

    else:  # linear_blend
        num = np.zeros(ref_shape, dtype=np.float32)
        den = np.zeros(ref_shape, dtype=np.float32)

        if sar_evidence is not None:
            num += np.where(v_sar, sar_evidence * config.weight_sar, 0.0)
            den += np.where(v_sar, config.weight_sar, 0.0)
        if optical_evidence is not None:
            num += np.where(v_opt, optical_evidence * config.weight_optical, 0.0)
            den += np.where(v_opt, config.weight_optical, 0.0)
        if novelty_evidence is not None:
            num += np.where(v_nov, novelty_evidence * config.weight_novelty, 0.0)
            den += np.where(v_nov, config.weight_novelty, 0.0)
        if terrain_plausibility is not None:
            num += np.where(v_terr, terrain_plausibility * config.weight_terrain, 0.0)
            den += np.where(v_terr, config.weight_terrain, 0.0)
        if rainfall_score is not None:
            num += np.where(overall_valid, rainfall_score * config.weight_rain, 0.0)
            den += np.where(overall_valid, config.weight_rain, 0.0)

        has_w = overall_valid & (den > 0)
        fused_score[has_w] = np.clip(num[has_w] / den[has_w], 0.0, 1.0)

    # Candidate mask at default operational threshold
    candidate_mask = overall_valid & (fused_score >= config.default_detection_threshold)

    # Optional morphological opening to remove isolated speckle noise
    if config.apply_morphological_opening and candidate_mask.any():
        struct = np.ones((config.morphology_kernel_size, config.morphology_kernel_size), dtype=bool)
        candidate_mask = ndimage.binary_opening(candidate_mask, structure=struct)

    candidate_px = int(np.sum(candidate_mask))
    pixel_area_ha = (config.pixel_resolution_m * config.pixel_resolution_m) / 10000.0
    candidate_ha = float(candidate_px * pixel_area_ha)

    v_scores = fused_score[overall_valid] if overall_valid.any() else np.array([0.0])
    stats = {
        "mean": float(np.mean(v_scores)),
        "median": float(np.median(v_scores)),
        "max": float(np.max(v_scores)),
        "p90": float(np.percentile(v_scores, 90)),
        "p95": float(np.percentile(v_scores, 95)),
    }

    has_primary_water = (has_sar or has_opt) if config.fusion_strategy == "gated_physics" else overall_valid.any()
    status = "accepted" if has_primary_water and overall_valid.any() else "no_evidence"
    valid_fraction = float(np.mean(overall_valid))

    provenance_payload = {
        "module": "flood",
        "configuration": asdict(config),
        "valid_fraction": float(valid_fraction),
        "candidate_pixels": int(candidate_px),
        "score_statistics": stats,
        "available_channels": list(available_channels),
        "aoi_metadata": aoi_metadata or {},
    }
    prov_str = json.dumps(provenance_payload, sort_keys=True, separators=(",", ":"))
    prov_hash = hashlib.sha256(prov_str.encode("utf-8")).hexdigest()

    return FloodDetectionResult(
        status=status,
        flood_score=fused_score,
        candidate_mask=candidate_mask,
        valid_mask=overall_valid,
        score_statistics=stats,
        evidence_layers=layer_stats,
        valid_fraction=valid_fraction,
        candidate_pixels=candidate_px,
        candidate_area_ha=candidate_ha,
        available_channels=available_channels,
        configuration=asdict(config),
        provenance={"hash": prov_hash, "aoi_metadata": aoi_metadata or {}}
    )


def segment_flood_events(
    flood_score: np.ndarray,
    valid_mask: np.ndarray,
    transform: rasterio.Affine | None = None,
    crs: str = "EPSG:4326",
    threshold: float = 0.20,
    min_pixels: int = 4,
    connectivity: int = 8,
    pixel_resolution_m: float = 20.0,
) -> list[EventRecord]:
    """
    Segment continuous flood score raster into discrete spatial EventRecords.
    Integrates directly with Earth One EventRecord architecture.
    """
    score = np.asarray(flood_score, dtype=np.float32)
    valid = np.asarray(valid_mask, dtype=bool)

    candidate = valid & (score >= threshold) & np.isfinite(score)

    if connectivity == 8:
        struct = np.ones((3, 3), dtype=np.uint8)
    else:
        struct = ndimage.generate_binary_structure(2, 1)

    labels, num_features = ndimage.label(candidate, structure=struct)
    if num_features == 0:
        return []

    pixel_area_m2 = pixel_resolution_m * pixel_resolution_m
    pixel_area_ha = pixel_area_m2 / 10000.0

    events: list[EventRecord] = []
    event_id = 0

    for comp_idx in range(1, num_features + 1):
        comp_mask = (labels == comp_idx)
        n_px = int(np.sum(comp_mask))
        if n_px < min_pixels:
            continue

        event_id += 1
        rows, cols = np.where(comp_mask)
        mean_sc = float(np.mean(score[comp_mask]))

        geom_dict = None
        if transform is not None:
            for geom, val in shapes(comp_mask.astype(np.uint8), mask=comp_mask, transform=transform):
                if val == 1:
                    geom_dict = geom
                    break

        ev = EventRecord(
            event_id=event_id,
            area_pixels=n_px,
            area_m2=float(n_px * pixel_area_m2),
            area_ha=float(n_px * pixel_area_ha),
            mean_change=float(mean_sc),
            mean_score=float(mean_sc),
            min_row=int(np.min(rows)),
            min_col=int(np.min(cols)),
            max_row=int(np.max(rows)),
            max_col=int(np.max(cols)),
            geometry=geom_dict,
            event_version="2.0.0-flood"
        )
        events.append(ev)

    return events


def build_flood_alert_payload(
    events: list[EventRecord],
    aoi_name: str,
    target_date: str,
    detection_result: FloodDetectionResult,
    config: FloodEvidenceConfig | None = None,
) -> dict[str, Any]:
    """
    Construct structured operational Alert Package compatible with Earth One alerting engine.
    """
    if config is None:
        config = FloodEvidenceConfig()

    total_events = len(events)
    total_area_ha = sum(ev.area_ha for ev in events)
    peak_event_ha = max((ev.area_ha for ev in events), default=0.0)
    mean_conf = float(np.mean([ev.mean_score for ev in events])) if events else 0.0

    severity = "CRITICAL" if total_area_ha >= 100.0 else ("WARNING" if total_area_ha >= 10.0 else "ADVISORY")
    clean_date = str(target_date).replace("-", "")
    seed = hashlib.sha256(f"{aoi_name}_{clean_date}".encode("utf-8")).hexdigest()[:8]
    alert_id = f"FLOOD_ALERT_{aoi_name.upper()}_{clean_date}_{seed}"

    event_payloads = []
    for ev in events:
        event_payloads.append({
            "event_id": ev.event_id,
            "area_ha": ev.area_ha,
            "area_pixels": ev.area_pixels,
            "mean_confidence": ev.mean_score,
            "bounding_box": [ev.min_col, ev.min_row, ev.max_col, ev.max_row],
            "geometry": ev.geometry
        })

    return {
        "alert_id": alert_id,
        "hazard_type": "FLOOD_INUNDATION",
        "aoi_name": aoi_name,
        "event_date": target_date,
        "severity": severity,
        "total_event_count": total_events,
        "total_flooded_area_ha": round(total_area_ha, 2),
        "peak_single_event_ha": round(peak_event_ha, 2),
        "mean_confidence": round(mean_conf, 3),
        "available_evidence_channels": detection_result.available_channels,
        "evidence_layer_summaries": detection_result.evidence_layers,
        "provenance_hash": detection_result.provenance.get("hash", ""),
        "events": event_payloads
    }
