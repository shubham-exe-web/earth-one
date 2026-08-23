from __future__ import annotations

from pathlib import Path
import csv
import json
from collections import Counter

import numpy as np
import rasterio
from sklearn.metrics import confusion_matrix, f1_score


def match_events_to_reference(
    event_raster_path: str | Path,
    reference_raster_path: str | Path,
    output_csv: str | Path,
) -> dict:
    """
    Match each Earth One event to a reference label raster by majority class.

    Reference convention:
      0 = unlabeled / ignored
      >0 = reference class ID

    The method reports event-level majority agreement. It does not claim that
    the reference itself is error-free.
    """
    with rasterio.open(event_raster_path) as ev:
        event_ids = ev.read(1).astype(np.int32)
        ev_profile = ev.profile.copy()

    with rasterio.open(reference_raster_path) as ref:
        reference = ref.read(1).astype(np.int32)
        if reference.shape != event_ids.shape:
            raise ValueError("Event and reference rasters have different dimensions.")
        if ref.crs != ev_profile["crs"] or ref.transform != ev_profile["transform"]:
            raise ValueError("Event and reference rasters are not aligned.")

    rows = []
    y_true = []
    y_pred = []

    for event_id in sorted(x for x in np.unique(event_ids) if x > 0):
        mask = event_ids == event_id
        ref_values = reference[mask]
        ref_values = ref_values[ref_values > 0]

        if len(ref_values) == 0:
            rows.append({
                "event_id": int(event_id),
                "reference_class": None,
                "reference_coverage_pixels": 0,
                "agreement_fraction": None,
            })
            continue

        counts = Counter(ref_values.tolist())
        reference_class, majority_count = counts.most_common(1)[0]
        agreement = majority_count / len(ref_values)

        rows.append({
            "event_id": int(event_id),
            "reference_class": int(reference_class),
            "reference_coverage_pixels": int(len(ref_values)),
            "agreement_fraction": float(agreement),
        })
        y_true.append(int(reference_class))
        y_pred.append(1)  # event presence

    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "event_id",
                "reference_class",
                "reference_coverage_pixels",
                "agreement_fraction",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    covered = [r for r in rows if r["reference_class"] is not None]
    return {
        "events_total": len(rows),
        "events_with_reference": len(covered),
        "mean_agreement": (
            float(np.mean([r["agreement_fraction"] for r in covered]))
            if covered else None
        ),
        "output": str(output_csv),
        "matching_version": "0.9.0",
    }
