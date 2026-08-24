from __future__ import annotations

"""Drought Module 3 Reference Taxonomy & Multi-Format Validation Layer (Phase 2).

Disentangles ground truth roles and supports multi-scale reference formats:
1. REFERENCE ROLES:
   - DEVELOPMENT_CONTEXT: Climatological context, ancillary maps.
   - COMPETING_OPERATIONAL_PRODUCT: Operational indices (USDM, EDO CDI, AEMET).
   - INDEPENDENT_VALIDATION: Independent in-situ soil probes, streamflow records.
   - IMPACT_CORROBORATION: Agricultural yield loss, crop insurance claims, disaster declarations.

2. REFERENCE FORMATS:
   - BINARY_MASK: Boolean drought/non-drought raster.
   - ORDINAL_SEVERITY: Graded drought categories (e.g., D0 to D4, Watch/Warning/Alert).
   - CONTINUOUS_INDEX: Continuous drought indicator (e.g., SPEI, VCI, PDSI in [-4, +4]).
   - EVENT_POLYGON: Vector/polygon disaster footprint with start/peak/end dates.
"""

import hashlib
from dataclasses import dataclass
from typing import Any, Literal
import numpy as np


ReferenceRole = Literal[
    "DEVELOPMENT_CONTEXT",
    "COMPETING_OPERATIONAL_PRODUCT",
    "INDEPENDENT_VALIDATION",
    "IMPACT_CORROBORATION",
]

ReferenceFormat = Literal[
    "BINARY_MASK",
    "ORDINAL_SEVERITY",
    "CONTINUOUS_INDEX",
    "EVENT_POLYGON",
]


@dataclass
class DroughtReferenceTarget:
    """Standardized multi-format drought reference target with explicit role definition."""
    name: str
    role: ReferenceRole
    format_type: ReferenceFormat
    source_agency: str
    temporal_coverage: str
    spatial_resolution_m: float
    
    # Payload
    binary_mask: np.ndarray | None = None
    ordinal_grid: np.ndarray | None = None         # e.g., 0=None, 1=D0, 2=D1, 3=D2, 4=D3, 5=D4
    continuous_values: np.ndarray | None = None   # e.g., SPEI values
    event_metadata: dict[str, Any] | None = None
    provenance_hash: str = ""

    def get_eval_binary_mask(self, ordinal_threshold: int = 2) -> np.ndarray:
        """Derive standard binary evaluation mask depending on format type."""
        if self.binary_mask is not None:
            return self.binary_mask
        if self.ordinal_grid is not None:
            # e.g., D2+ (Severe Drought) threshold
            return self.ordinal_grid >= ordinal_threshold
        if self.continuous_values is not None:
            # e.g., SPEI <= -1.25 (Moderate/Severe Drought)
            return self.continuous_values <= -1.25
        raise ValueError(f"No valid raster payload found in reference target {self.name}")
