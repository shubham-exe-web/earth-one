from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import pickle

import numpy as np
import rasterio
from scipy.ndimage import label
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.isotonic import IsotonicRegression


@dataclass
class SpatialValidationResult:
    n_train: int
    n_test: int
    accuracy: float
    balanced_accuracy: float
    macro_f1: float
    weighted_f1: float
    precision_macro: float
    recall_macro: float
    confusion_matrix: list[list[int]]
    validation_version: str = "0.8.0"


@dataclass
class CalibrationResult:
    method: str
    n_samples: int
    brier_score: float
    mean_confidence: float
    mean_correct_confidence: float
    calibration_version: str = "0.8.0"


def _read_feature_stack(path: str | Path, names=("NDVI", "DELTA_NDVI", "VV", "VH")):
    with rasterio.open(path) as ds:
        descriptions = list(ds.descriptions or [])
        arrays = []
        for name in names:
            if name not in descriptions:
                raise ValueError(f"Missing feature: {name}")
            arrays.append(ds.read(descriptions.index(name) + 1).astype(np.float32))
        return np.stack(arrays, axis=0), ds.profile.copy()


def _read_labels(path: str | Path):
    with rasterio.open(path) as ds:
        return ds.read(1).astype(np.int32), ds.profile.copy()


def _block_ids(height: int, width: int, block_size: int):
    rows = np.arange(height)[:, None] // block_size
    cols = np.arange(width)[None, :] // block_size
    return rows * (width // block_size + 1) + cols


def spatial_block_split(
    feature_stack_path: str | Path,
    label_path: str | Path,
    block_size: int = 32,
    test_fraction: float = 0.20,
    seed: int = 42,
):
    """
    Create a spatially separated train/test split.

    Whole blocks are assigned to either train or test, preventing neighboring
    pixels from being split across both sets.
    """
    Xstack, profile = _read_feature_stack(feature_stack_path)
    labels, label_profile = _read_labels(label_path)

    if labels.shape != Xstack.shape[1:]:
        raise ValueError("Feature stack and labels have different dimensions.")
    if labels_profile_crs_mismatch(profile, label_profile):
        raise ValueError("Feature stack and labels are not spatially aligned.")

    X = Xstack.reshape(Xstack.shape[0], -1).T
    y = labels.reshape(-1)

    valid = np.all(np.isfinite(X), axis=1) & (y > 0)
    X = X[valid]
    y = y[valid]

    h, w = labels.shape
    blocks = _block_ids(h, w, block_size).reshape(-1)[valid]
    unique_blocks = np.unique(blocks)

    rng = np.random.default_rng(seed)
    rng.shuffle(unique_blocks)
    n_test_blocks = max(1, int(round(len(unique_blocks) * test_fraction)))
    test_blocks = set(unique_blocks[:n_test_blocks].tolist())

    is_test = np.array([b in test_blocks for b in blocks], dtype=bool)
    return X[~is_test], X[is_test], y[~is_test], y[is_test]


def labels_profile_crs_mismatch(feature_profile, label_profile):
    return (
        feature_profile.get("crs") != label_profile.get("crs")
        or feature_profile.get("transform") != label_profile.get("transform")
        or feature_profile.get("width") != label_profile.get("width")
        or feature_profile.get("height") != label_profile.get("height")
    )


def evaluate_predictions(y_true, y_pred, labels=None) -> SpatialValidationResult:
    labels = labels if labels is not None else sorted(set(y_true) | set(y_pred))
    cm = confusion_matrix(y_true, y_pred, labels=labels)

    return SpatialValidationResult(
        n_train=0,
        n_test=int(len(y_true)),
        accuracy=float(accuracy_score(y_true, y_pred)),
        balanced_accuracy=float(balanced_accuracy_score(y_true, y_pred)),
        macro_f1=float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        weighted_f1=float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        precision_macro=float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        recall_macro=float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        confusion_matrix=cm.tolist(),
    )


def spatial_validate_model(
    feature_stack_path: str | Path,
    label_path: str | Path,
    model_path: str | Path,
    block_size: int = 32,
    test_fraction: float = 0.20,
    seed: int = 42,
) -> SpatialValidationResult:
    X_train, X_test, y_train, y_test = spatial_block_split(
        feature_stack_path,
        label_path,
        block_size=block_size,
        test_fraction=test_fraction,
        seed=seed,
    )

    with Path(model_path).open("rb") as f:
        payload = pickle.load(f)
    model = payload["model"]

    model.fit(X_train, y_train)
    pred = model.predict(X_test)

    result = evaluate_predictions(y_test, pred)
    result.n_train = int(len(y_train))
    return result


def calibrate_confidence(
    y_true,
    probabilities,
    predicted,
    method: str = "isotonic",
) -> CalibrationResult:
    """
    Calibrate maximum-class confidence against correctness.

    This is a one-dimensional correctness calibration, not a full multiclass
    probability calibration. It is intentionally conservative for v0.8.
    """
    confidence = np.max(probabilities, axis=1).astype(float)
    correct = (predicted == y_true).astype(float)

    if method != "isotonic":
        raise ValueError("v0.8 supports isotonic calibration only")

    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrated = calibrator.fit_transform(confidence, correct)

    brier = float(np.mean((calibrated - correct) ** 2))
    return CalibrationResult(
        method="isotonic_correctness",
        n_samples=len(y_true),
        brier_score=brier,
        mean_confidence=float(np.mean(calibrated)),
        mean_correct_confidence=float(
            np.mean(calibrated[correct.astype(bool)])
        ) if correct.any() else 0.0,
    )


def write_result(result, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
