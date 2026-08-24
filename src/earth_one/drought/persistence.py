from __future__ import annotations

"""Drought Module 3 Temporal Persistence & State Machine (v0.2)."""

from dataclasses import dataclass
from typing import Sequence
import numpy as np

from .config import DroughtConfig, DroughtLifecycleState


@dataclass
class PixelPersistenceState:
    """Tracks historical streak and current lifecycle state for an individual pixel/unit."""
    current_state: DroughtLifecycleState
    consecutive_stress_epochs: int
    consecutive_normal_epochs: int
    peak_severity_observed: float
    total_active_epochs: int


def update_pixel_lifecycle_state(
    prev_state: PixelPersistenceState,
    current_is_drought: bool,
    current_severity: float,
    is_unresolved: bool,
    config: DroughtConfig = DroughtConfig(),
) -> PixelPersistenceState:
    """Deterministic state transition function strictly adhering to config parameters."""
    if is_unresolved:
        # Fail-safe blackout / missing telemetry: hold previous state without advancing recovery
        return PixelPersistenceState(
            current_state="UNRESOLVED" if prev_state.current_state == "NORMAL" else prev_state.current_state,
            consecutive_stress_epochs=prev_state.consecutive_stress_epochs,
            consecutive_normal_epochs=prev_state.consecutive_normal_epochs,
            peak_severity_observed=prev_state.peak_severity_observed,
            total_active_epochs=prev_state.total_active_epochs,
        )

    if current_is_drought:
        stress_streak = prev_state.consecutive_stress_epochs + 1
        normal_streak = 0
        is_new_peak = current_severity > prev_state.peak_severity_observed
        peak_sev = max(prev_state.peak_severity_observed, current_severity)
        active_tot = prev_state.total_active_epochs + 1

        # Strict config-driven state transitions
        if stress_streak < config.watch_consecutive_epochs:
            new_state = "WATCH"
        elif stress_streak < config.active_consecutive_epochs:
            new_state = "EMERGING"
        else:
            # Active or Peak phase
            if current_severity >= config.drought_severe_threshold and is_new_peak and stress_streak > config.active_consecutive_epochs:
                new_state = "PEAK"
            else:
                new_state = "ACTIVE"

        return PixelPersistenceState(
            current_state=new_state,
            consecutive_stress_epochs=stress_streak,
            consecutive_normal_epochs=normal_streak,
            peak_severity_observed=peak_sev,
            total_active_epochs=active_tot,
        )
    else:
        stress_streak = 0
        normal_streak = prev_state.consecutive_normal_epochs + 1
        peak_sev = prev_state.peak_severity_observed
        active_tot = prev_state.total_active_epochs

        if prev_state.current_state in ["ACTIVE", "PEAK", "EMERGING"]:
            new_state = "RECOVERY" if normal_streak < config.recovery_consecutive_epochs else "RESOLVED"
        elif prev_state.current_state == "RECOVERY":
            new_state = "RECOVERY" if normal_streak < config.recovery_consecutive_epochs else "RESOLVED"
        elif prev_state.current_state == "WATCH":
            new_state = "NORMAL"
        else:
            new_state = "NORMAL"

        return PixelPersistenceState(
            current_state=new_state,
            consecutive_stress_epochs=stress_streak,
            consecutive_normal_epochs=normal_streak,
            peak_severity_observed=0.0 if new_state in ["NORMAL", "RESOLVED"] else peak_sev,
            total_active_epochs=0 if new_state in ["NORMAL", "RESOLVED"] else active_tot,
        )


def evaluate_temporal_persistence_series(
    severity_series: Sequence[float],
    resolvable_series: Sequence[bool],
    config: DroughtConfig = DroughtConfig(),
) -> list[PixelPersistenceState]:
    """Replay a temporal sequence of epochs and compute full state trajectory."""
    state = PixelPersistenceState(
        current_state="NORMAL",
        consecutive_stress_epochs=0,
        consecutive_normal_epochs=0,
        peak_severity_observed=0.0,
        total_active_epochs=0,
    )
    trajectory = []

    for sev, res in zip(severity_series, resolvable_series):
        is_unres = not res
        is_dr = (sev >= config.drought_detection_threshold) and res
        state = update_pixel_lifecycle_state(state, is_dr, sev, is_unres, config=config)
        trajectory.append(state)

    return trajectory
