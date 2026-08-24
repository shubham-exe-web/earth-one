from __future__ import annotations

"""Drought Module 3 Multi-Epoch Spatial Event Tracking & IoU Association Engine (v0.2)."""

import hashlib
from dataclasses import dataclass, field
import numpy as np

from .events import DroughtEventRecord, DroughtSegmentationResult


@dataclass
class DroughtTrack:
    """Persistent temporal trajectory tracking a drought event across sequential passes."""
    track_id: int
    initiation_epoch: int
    latest_epoch: int
    duration_epochs: int
    area_trajectory_ha: list[float]
    severity_trajectory: list[float]
    peak_area_ha: float
    peak_severity: float
    is_active: bool
    last_event_id: int
    last_centroid: tuple[float, float]
    last_mask: np.ndarray | None
    provenance_hash: str


def compute_mask_iou(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    """Compute Intersection over Union (IoU) between two boolean raster masks."""
    intersection = np.sum(mask_a & mask_b)
    union = np.sum(mask_a | mask_b)
    return float(intersection / union) if union > 0 else 0.0


class MultiEpochDroughtTracker:
    """Maintains persistent state across sequential observation timesteps with true spatial IoU."""

    def __init__(self, iou_overlap_threshold: float = 0.15, max_centroid_distance_px: float = 50.0):
        self.iou_threshold = iou_overlap_threshold
        self.max_distance = max_centroid_distance_px
        self.active_tracks: dict[int, DroughtTrack] = {}
        self.completed_tracks: list[DroughtTrack] = []
        self.next_track_id: int = 1
        self.current_epoch: int = 0

    def update_epoch(
        self,
        current_segmentation: DroughtSegmentationResult,
        epoch_index: int,
    ) -> list[DroughtTrack]:
        """Update tracker with new observation pass using genuine spatial IoU matching."""
        self.current_epoch = epoch_index
        current_events = current_segmentation.events
        current_raster = current_segmentation.labeled_event_raster

        # Build candidate matches
        matched_tracks: set[int] = set()
        matched_events: set[int] = set()

        if self.active_tracks and current_events:
            # Build IoU cost matrix
            active_ids = [tid for tid, tr in self.active_tracks.items() if tr.is_active]
            
            for tr_id in active_ids:
                track = self.active_tracks[tr_id]
                best_ev_id = None
                best_iou = 0.0

                for ev in current_events:
                    if ev.event_id in matched_events:
                        continue
                    
                    ev_mask = (current_raster == ev.event_id)
                    
                    if track.last_mask is not None and track.last_mask.shape == ev_mask.shape:
                        iou = compute_mask_iou(track.last_mask, ev_mask)
                    else:
                        # Centroid proximity fallback if mask not preserved
                        cr, cc = ev.centroid_row, ev.centroid_col
                        tr_r, tr_c = track.last_centroid
                        dist = np.sqrt((cr - tr_r)**2 + (cc - tr_c)**2)
                        iou = 0.50 if dist <= self.max_distance else 0.0

                    if iou >= self.iou_threshold and iou > best_iou:
                        best_iou = iou
                        best_ev_id = ev.event_id

                if best_ev_id is not None:
                    # Match found
                    ev_matched = next(e for e in current_events if e.event_id == best_ev_id)
                    track.latest_epoch = epoch_index
                    track.duration_epochs += 1
                    track.area_trajectory_ha.append(ev_matched.area_expected_ha)
                    track.severity_trajectory.append(ev_matched.mean_severity)
                    track.peak_area_ha = max(track.peak_area_ha, ev_matched.area_expected_ha)
                    track.peak_severity = max(track.peak_severity, ev_matched.peak_severity)
                    track.last_event_id = ev_matched.event_id
                    track.last_centroid = (ev_matched.centroid_row, ev_matched.centroid_col)
                    track.last_mask = (current_raster == ev_matched.event_id)

                    matched_tracks.add(tr_id)
                    matched_events.add(best_ev_id)

        # Spawn new tracks for unmatched current events
        for ev in current_events:
            if ev.event_id not in matched_events:
                new_id = self.next_track_id
                self.next_track_id += 1
                ev_mask = (current_raster == ev.event_id)
                new_track = DroughtTrack(
                    track_id=new_id,
                    initiation_epoch=epoch_index,
                    latest_epoch=epoch_index,
                    duration_epochs=1,
                    area_trajectory_ha=[ev.area_expected_ha],
                    severity_trajectory=[ev.mean_severity],
                    peak_area_ha=ev.area_expected_ha,
                    peak_severity=ev.mean_severity,
                    is_active=True,
                    last_event_id=ev.event_id,
                    last_centroid=(ev.centroid_row, ev.centroid_col),
                    last_mask=ev_mask,
                    provenance_hash=hashlib.sha256(f"TRACK_V2_{new_id}_{epoch_index}".encode()).hexdigest(),
                )
                self.active_tracks[new_id] = new_track
                matched_tracks.add(new_id)

        # De-activate unobserved tracks
        for tr_id, tr in list(self.active_tracks.items()):
            if tr_id not in matched_tracks and tr.is_active:
                tr.is_active = False
                self.completed_tracks.append(tr)

        return list(self.active_tracks.values())
