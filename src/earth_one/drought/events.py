from __future__ import annotations

"""Drought Module 3 Spatial Event Segmentation & Sensitivity-Bounded Area Layer (v0.2)."""

import hashlib
from dataclasses import dataclass
import numpy as np
from scipy import ndimage

from .config import DroughtConfig
from .classifier import TriStateDroughtDecision
from .observability import DroughtObservabilityResult


@dataclass
class DroughtEventRecord:
    """Discrete tracked spatial drought event with sensitivity-bounded area intervals."""
    event_id: int
    area_expected_ha: float
    area_sensitivity_low_ha: float
    area_sensitivity_high_ha: float
    area_sensitivity_margin_ha: float
    area_sensitivity_pct: float
    pixel_count: int
    mean_severity: float
    peak_severity: float
    mean_observability: float
    is_well_observed: bool
    centroid_row: float
    centroid_col: float
    bounding_box: tuple[int, int, int, int]  # (min_row, min_col, max_row, max_col)
    provenance_hash: str


@dataclass
class DroughtSegmentationResult:
    """Collection of segmented drought event objects and spatial label raster."""
    event_count: int
    total_drought_area_ha: float
    events: list[DroughtEventRecord]
    labeled_event_raster: np.ndarray
    pixel_area_ha: float
    provenance_hash: str


def extract_drought_events(
    decision: TriStateDroughtDecision,
    fused_score: np.ndarray,
    observability: DroughtObservabilityResult,
    resolution_m: float = 20.0,
    config: DroughtConfig = DroughtConfig(),
) -> DroughtSegmentationResult:
    """Segment connected drought components and compute multi-threshold sensitivity bounds."""
    drought_mask = decision.drought_mask
    
    # Compute true pixel area from spatial resolution
    pixel_area_ha = (resolution_m * resolution_m) / 10000.0

    # Sensitivity bounds: conservative severe threshold vs expansive watch threshold
    res_mask = observability.resolvable_mask
    mask_severe = res_mask & (fused_score >= config.drought_severe_threshold)
    mask_watch = res_mask & (fused_score >= config.drought_watch_threshold)

    labeled_raster, num_features = ndimage.label(drought_mask, structure=np.ones((3, 3), dtype=np.uint8))
    events: list[DroughtEventRecord] = []
    total_area_ha = 0.0

    for ev_id in range(1, num_features + 1):
        ev_mask = (labeled_raster == ev_id)
        px_count = int(np.sum(ev_mask))

        if px_count < config.min_event_pixels:
            continue

        # Area quantification
        area_std = px_count * pixel_area_ha
        total_area_ha += area_std

        # Sensitivity bounds
        px_severe = int(np.sum(mask_severe & ev_mask))
        ev_dilated = ndimage.binary_dilation(ev_mask, structure=np.ones((3, 3), dtype=bool))
        px_watch = int(np.sum(mask_watch & ev_dilated))

        area_low = max(pixel_area_ha, px_severe * pixel_area_ha)
        area_high = max(area_std, px_watch * pixel_area_ha)

        margin_ha = (area_high - area_low) / 2.0
        sens_pct = (margin_ha / max(0.1, area_std)) * 100.0

        # Severity & Observability metrics
        ev_scores = fused_score[ev_mask]
        ev_obs = observability.observability_index[ev_mask]

        mean_sev = float(np.mean(ev_scores))
        peak_sev = float(np.max(ev_scores))
        mean_o = float(np.mean(ev_obs))

        # Centroid & BBox
        coords = np.argwhere(ev_mask)
        min_r, min_c = coords.min(axis=0)
        max_r, max_c = coords.max(axis=0)
        cent_r, cent_c = coords.mean(axis=0)

        prov = hashlib.sha256(
            f"DROUGHT_EV_V2_{ev_id}_{area_std:.2f}_{mean_sev:.3f}_{mean_o:.3f}".encode()
        ).hexdigest()

        rec = DroughtEventRecord(
            event_id=ev_id,
            area_expected_ha=round(area_std, 2),
            area_sensitivity_low_ha=round(area_low, 2),
            area_sensitivity_high_ha=round(area_high, 2),
            area_sensitivity_margin_ha=round(margin_ha, 2),
            area_sensitivity_pct=round(sens_pct, 1),
            pixel_count=px_count,
            mean_severity=round(mean_sev, 3),
            peak_severity=round(peak_sev, 3),
            mean_observability=round(mean_o, 3),
            is_well_observed=bool(mean_o >= config.observability_threshold),
            centroid_row=round(float(cent_r), 1),
            centroid_col=round(float(cent_c), 1),
            bounding_box=(int(min_r), int(min_c), int(max_r), int(max_c)),
            provenance_hash=prov,
        )
        events.append(rec)

    overall_hash = hashlib.sha256(
        f"DROUGHT_SEG_V2_{len(events)}_{total_area_ha:.2f}".encode()
    ).hexdigest()

    return DroughtSegmentationResult(
        event_count=len(events),
        total_drought_area_ha=round(total_area_ha, 2),
        events=events,
        labeled_event_raster=labeled_raster,
        pixel_area_ha=pixel_area_ha,
        provenance_hash=overall_hash,
    )
