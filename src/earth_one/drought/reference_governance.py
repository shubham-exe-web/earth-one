from __future__ import annotations

"""Drought Module 3 Reference Governance & Validation Independence Engine."""

from dataclasses import dataclass
from typing import Sequence
from .reference_taxonomy import DroughtReferenceTarget, ReferenceRole


@dataclass
class ValidationGovernanceAudit:
    """Audit report verifying reference independence and scientific usage rules."""
    reference_name: str
    declared_role: ReferenceRole
    is_independent_truth: bool
    overlapping_forcing_inputs: list[str]
    is_pixel_truth_allowed: bool
    scientific_disclaimer: str


def audit_reference_governance(
    reference: DroughtReferenceTarget,
    candidate_overlapping_inputs: Sequence[str] | None = None,
) -> ValidationGovernanceAudit:
    """Enforce programmatic governance rules over drought reference targets."""
    role = reference.role
    overlaps = list(candidate_overlapping_inputs) if candidate_overlapping_inputs else []

    if role == "COMPETING_OPERATIONAL_PRODUCT":
        # USDM, EDO CDI, AEMET use SPI, soil moisture, and NDVI; cannot be claimed as pure ground truth
        is_independent = False
        pixel_allowed = True  # Useful for spatial comparison / concordance, but not independent accuracy
        disclaimer = (
            f"Reference '{reference.name}' is an operational comparator (Role: COMPETING_OPERATIONAL_PRODUCT). "
            f"Agreement represents operational concordance, not independent physical validation."
        )

    elif role == "INDEPENDENT_VALIDATION":
        # Physical in-situ probes, streamflow, or groundwater
        is_independent = True
        pixel_allowed = True
        disclaimer = (
            f"Reference '{reference.name}' is an independent physical measurement (Role: INDEPENDENT_VALIDATION)."
        )

    elif role == "IMPACT_CORROBORATION":
        # Crop yield, insurance payouts, famine declarations
        is_independent = True
        pixel_allowed = False  # Must not be forced into a binary pixel grid!
        disclaimer = (
            f"Reference '{reference.name}' is an impact metric (Role: IMPACT_CORROBORATION). "
            f"Evaluated at regional/event scale; pixel-level accuracy metrics are prohibited."
        )

    else:  # DEVELOPMENT_CONTEXT
        is_independent = False
        pixel_allowed = True
        disclaimer = "Reference used solely for development and environmental context."

    return ValidationGovernanceAudit(
        reference_name=reference.name,
        declared_role=role,
        is_independent_truth=is_independent,
        overlapping_forcing_inputs=overlaps,
        is_pixel_truth_allowed=pixel_allowed,
        scientific_disclaimer=disclaimer,
    )
