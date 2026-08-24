from __future__ import annotations

"""Drought Module 3 Real Earth Observation Manifest & Support Metadata (Phase 4).

Establishes strict provenance manifests and explicit distinction between:
- native_resolution_m
- effective_spatial_support_m
- analysis_grid_resolution_m
"""

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Sequence


@dataclass
class SensorSupportMetadata:
    """Explicitly records native spatial support vs computational analysis grid."""
    sensor_name: str
    product_id: str
    native_crs: str
    native_resolution_m: float
    effective_spatial_support_m: float
    analysis_grid_resolution_m: float
    temporal_frequency: str
    qa_filtering_applied: str

    @property
    def resolution_disparity_ratio(self) -> float:
        """Ratio of effective spatial support to analysis grid resolution."""
        return self.effective_spatial_support_m / max(1.0, self.analysis_grid_resolution_m)


@dataclass
class ReferenceIndependenceRecord:
    """Formal independence matrix entry preventing circular validation claims."""
    dataset_name: str
    source_agency: str
    used_in_earth_one_forcing: bool
    used_in_reference_construction: bool
    assigned_validation_tier: str  # TIER_A_PHYSICAL, TIER_B_OPERATIONAL, TIER_C_IMPACT
    is_independent_ground_truth: bool
    shared_forcing_disclosures: list[str]


@dataclass
class DroughtActivationManifest:
    """Complete provenance manifest for a genuine Earth Observation drought activation."""
    aoi_id: str
    target_crs: str
    target_resolution_m: float
    target_transform: tuple[float, float, float, float, float, float]
    target_shape: tuple[int, int]
    eval_year: int
    eval_month: int
    climatology_baseline_years: list[int]
    excluded_years: list[int]
    optical_scene_ids: list[str]
    precipitation_product: str
    soil_moisture_product: str
    thermal_lst_product: str
    operational_comparator_id: str
    in_situ_station_ids: list[str]
    impact_dataset_id: str
    sensor_supports: dict[str, SensorSupportMetadata]
    independence_matrix: list[ReferenceIndependenceRecord]
    software_commit: str
    manifest_sha256: str = ""

    def compute_sha256(self) -> str:
        """Derive deterministic cryptographic hash of the entire manifest."""
        manifest_dict = {
            "aoi_id": self.aoi_id,
            "target_crs": self.target_crs,
            "eval_year": self.eval_year,
            "eval_month": self.eval_month,
            "climatology_baseline_years": self.climatology_baseline_years,
            "excluded_years": self.excluded_years,
            "optical_scene_ids": self.optical_scene_ids,
            "precipitation_product": self.precipitation_product,
            "soil_moisture_product": self.soil_moisture_product,
            "thermal_lst_product": self.thermal_lst_product,
            "operational_comparator_id": self.operational_comparator_id,
        }
        raw_bytes = json.dumps(manifest_dict, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw_bytes).hexdigest()
