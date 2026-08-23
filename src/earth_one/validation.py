from __future__ import annotations

from pathlib import Path
import json


def validate_model_result(
    training_result: dict,
    minimum_balanced_accuracy: float = 0.60,
) -> dict:
    """
    Research gate for v0.7.

    A model is marked 'candidate' only if it clears a minimum balanced-accuracy
    threshold. This is not a claim of publication-quality validation.
    """
    score = float(training_result["balanced_accuracy"])
    passed = score >= minimum_balanced_accuracy

    return {
        "status": "candidate" if passed else "rejected",
        "balanced_accuracy": score,
        "minimum_required": minimum_balanced_accuracy,
        "scientific_note": (
            "This gate is a development safeguard. Independent spatial/temporal "
            "validation and uncertainty analysis are still required."
        ),
        "validator_version": "0.7.0",
    }


def write_validation(result: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
