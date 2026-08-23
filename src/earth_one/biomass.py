from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import numpy as np
import rasterio


@dataclass
class BiomassCarbonResult:
    biomass_before_t_ha: float | None
    biomass_after_t_ha: float | None
    biomass_change_t_ha: float | None
    carbon_fraction: float
    carbon_change_t_ha: float | None
    carbon_method: str
    uncertainty_t_ha: float | None
    version: str = "1.0.0"


def estimate_event_carbon(
    biomass_before_path: str | Path,
    biomass_after_path: str | Path,
    event_mask_path: str | Path,
    output_json: str | Path,
    carbon_fraction: float = 0.47,
    biomass_uncertainty_fraction: float | None = None,
) -> BiomassCarbonResult:
    """
    Convert a supplied biomass product into event-level biomass/carbon change.

    Earth One v1.0 deliberately requires biomass as an external or separately
    validated layer. It does not invent biomass from NDVI alone.

    carbon_change = (biomass_after - biomass_before) * carbon_fraction

    A negative value represents carbon loss.
    """
    if not 0 < carbon_fraction < 1:
        raise ValueError("carbon_fraction must be between 0 and 1")

    with rasterio.open(biomass_before_path) as b0, rasterio.open(biomass_after_path) as b1:
        before = b0.read(1).astype(np.float32)
        after = b1.read(1).astype(np.float32)

        if before.shape != after.shape:
            raise ValueError("Biomass rasters have different dimensions.")
        if b0.crs != b1.crs or b0.transform != b1.transform:
            raise ValueError("Biomass rasters are not spatially aligned.")

        profile = b0.profile.copy()

    with rasterio.open(event_mask_path) as ev:
        event_mask = ev.read(1).astype(np.int32)
        if event_mask.shape != before.shape:
            raise ValueError("Event mask and biomass rasters have different dimensions.")
        if ev.crs != profile["crs"] or ev.transform != profile["transform"]:
            raise ValueError("Event mask and biomass rasters are not aligned.")

    valid = (event_mask > 0) & np.isfinite(before) & np.isfinite(after)
    if not valid.any():
        result = BiomassCarbonResult(
            None, None, None, carbon_fraction, None,
            "supplied_biomass_difference", None
        )
    else:
        before_mean = float(np.mean(before[valid]))
        after_mean = float(np.mean(after[valid]))
        change = after_mean - before_mean
        uncertainty = (
            abs(change) * biomass_uncertainty_fraction
            if biomass_uncertainty_fraction is not None else None
        )

        result = BiomassCarbonResult(
            biomass_before_t_ha=before_mean,
            biomass_after_t_ha=after_mean,
            biomass_change_t_ha=change,
            carbon_fraction=carbon_fraction,
            carbon_change_t_ha=change * carbon_fraction,
            carbon_method="supplied_biomass_difference",
            uncertainty_t_ha=uncertainty,
        )

    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result
