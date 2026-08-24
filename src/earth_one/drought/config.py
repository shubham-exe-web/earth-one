from __future__ import annotations

"""Drought Module 3 Configuration & Parameter Specifications (v0.2)."""

from dataclasses import dataclass, field
from typing import Literal


DroughtRegimeType = Literal[
    "RAINFED_AGRICULTURE",
    "IRRIGATED_AGRICULTURE",
    "GRASSLAND_SHRUBLAND",
    "FOREST",
    "DRYLAND_SPARSE",
    "WETLAND_HIGH_MOISTURE",
    "MIXED_UNCERTAIN",
]

DroughtLifecycleState = Literal[
    "NORMAL",
    "WATCH",
    "EMERGING",
    "ACTIVE",
    "PEAK",
    "RECOVERY",
    "RESOLVED",
    "UNRESOLVED",
]

TriStateDroughtLabel = Literal[
    "DROUGHT",
    "NO_DROUGHT",
    "UNRESOLVED",
]


@dataclass(frozen=True)
class TemporalWindowWeights:
    """Multi-temporal window weighting coefficients."""
    window_1m: float = 0.25   # Rapid meteorological stress
    window_3m: float = 0.50   # Seasonal / agricultural stress
    window_6m: float = 0.25   # Prolonged hydrological / ecosystem stress


@dataclass(frozen=True)
class ModalityWeights:
    """Multi-modal evidence fusion weights."""
    vegetation: float = 0.35
    precipitation: float = 0.30
    soil_moisture: float = 0.25
    thermal: float = 0.10


@dataclass(frozen=True)
class DroughtConfig:
    """Master configuration for Earth One Drought Module 3."""
    # Anomaly z-score thresholds (negative z indicates deficit/stress)
    z_score_mild_stress: float = -0.80       # ~21st percentile
    z_score_moderate_stress: float = -1.25   # ~10th percentile
    z_score_severe_stress: float = -1.60     # ~5th percentile
    z_score_extreme_stress: float = -2.00    # ~2.3rd percentile

    # Standard decision thresholds
    drought_detection_threshold: float = 0.50
    drought_watch_threshold: float = 0.35
    drought_severe_threshold: float = 0.70

    # Observability parameters
    observability_threshold: float = 0.50
    min_vegetation_cover_ndvi: float = 0.15
    max_cloud_cover_fraction: float = 0.40

    # Attribution ambiguity thresholds
    attribution_ambiguity_threshold: float = 0.60
    no_drought_min_required_modalities: int = 2
    no_drought_max_stress_z: float = -0.50

    # Persistence parameters
    watch_consecutive_epochs: int = 2
    emerging_consecutive_epochs: int = 3
    active_consecutive_epochs: int = 4
    recovery_consecutive_epochs: int = 3

    # Multi-temporal & modality weights
    temporal_weights: TemporalWindowWeights = field(default_factory=TemporalWindowWeights)
    modality_weights: ModalityWeights = field(default_factory=ModalityWeights)

    # Spatial clustering
    min_event_pixels: int = 16

    # Alerting parameters
    alert_suppression_window_days: float = 14.0
    blackout_fail_safe_state: str = "DATA_BLACKOUT_HOLD"
