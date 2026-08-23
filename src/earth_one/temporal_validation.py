from __future__ import annotations

from pathlib import Path
import json
import pickle

import numpy as np
import rasterio
from sklearn.metrics import balanced_accuracy_score, f1_score


def temporal_validate_model(
    feature_stacks: list[str | Path],
    label_rasters: list[str | Path],
    model_path: str | Path,
) -> dict:
    """
    Validate a fixed model across later/independent observations.

    Each feature stack is treated as a temporal validation unit. Labels must
    align exactly to their corresponding feature stack.
    """
    if len(feature_stacks) != len(label_rasters):
        raise ValueError("Feature stacks and labels must have equal length.")
    if not feature_stacks:
        raise ValueError("At least one temporal validation unit is required.")

    with Path(model_path).open("rb") as f:
        payload = pickle.load(f)
    model = payload["model"]

    units = []
    all_true = []
    all_pred = []

    for stack_path, label_path in zip(feature_stacks, label_rasters):
        with rasterio.open(stack_path) as ds:
            X = ds.read().astype(np.float32)
            profile = ds.profile.copy()
        with rasterio.open(label_path) as ds:
            y = ds.read(1).astype(np.int32)
            lp = ds.profile.copy()

        if X.shape[1:] != y.shape:
            raise ValueError("Temporal validation raster dimensions do not match.")
        if profile["crs"] != lp["crs"] or profile["transform"] != lp["transform"]:
            raise ValueError("Temporal validation rasters are not aligned.")

        X = X.reshape(X.shape[0], -1).T
        y = y.reshape(-1)
        valid = np.all(np.isfinite(X), axis=1) & (y > 0)

        if not valid.any():
            continue

        pred = model.predict(X[valid])
        yt = y[valid]

        all_true.extend(yt.tolist())
        all_pred.extend(pred.tolist())

        units.append({
            "feature_stack": str(stack_path),
            "label_raster": str(label_path),
            "n": int(valid.sum()),
            "balanced_accuracy": float(balanced_accuracy_score(yt, pred)),
            "macro_f1": float(f1_score(yt, pred, average="macro", zero_division=0)),
        })

    if not all_true:
        raise ValueError("No valid temporal validation pixels were found.")

    return {
        "units": units,
        "pooled_balanced_accuracy": float(
            balanced_accuracy_score(all_true, all_pred)
        ),
        "pooled_macro_f1": float(
            f1_score(all_true, all_pred, average="macro", zero_division=0)
        ),
        "validation_type": "temporal_holdout",
        "processor_version": "0.8.0",
    }


def write_result(result: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
