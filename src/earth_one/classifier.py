from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import pickle

import numpy as np
import rasterio
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report
from sklearn.model_selection import train_test_split


FEATURES = ("NDVI", "DELTA_NDVI", "VV", "VH")


@dataclass
class TrainingResult:
    model_path: str
    n_samples: int
    n_classes: int
    classes: list[str]
    accuracy: float
    balanced_accuracy: float
    processor_version: str = "0.7.0"


@dataclass
class InferenceResult:
    output: str
    model_path: str
    classes: list[str]
    valid_fraction: float
    processor_version: str = "0.7.0"


def _read_stack(path: str | Path):
    path = Path(path)
    with rasterio.open(path) as ds:
        names = list(ds.descriptions or [])
        arrays = []
        for feature in FEATURES:
            if feature not in names:
                raise ValueError(
                    f"Feature {feature} is required by the v0.7 multimodal classifier. "
                    f"Available bands: {names}"
                )
            arrays.append(ds.read(names.index(feature) + 1).astype(np.float32))
        return np.stack(arrays, axis=0), ds.profile.copy(), names


def _balanced_indices(y: np.ndarray, max_per_class: int | None = None, seed: int = 42):
    rng = np.random.default_rng(seed)
    selected = []
    classes = np.unique(y)
    for cls in classes:
        idx = np.flatnonzero(y == cls)
        if max_per_class is not None and len(idx) > max_per_class:
            idx = rng.choice(idx, size=max_per_class, replace=False)
        selected.extend(idx.tolist())
    return np.array(selected, dtype=np.int64)


def train_classifier(
    feature_stack_path: str | Path,
    label_raster_path: str | Path,
    model_path: str | Path,
    test_size: float = 0.20,
    max_per_class: int | None = 10000,
    random_state: int = 42,
) -> TrainingResult:
    """
    Train a Random Forest baseline on pixel-level multimodal features.

    Label raster must be aligned to the feature stack and contain integer
    class IDs. Pixels with label <= 0 or non-finite features are ignored.

    This is a baseline research model, not the final Earth One classifier.
    """
    Xstack, profile, _ = _read_stack(feature_stack_path)

    with rasterio.open(label_raster_path) as labels_ds:
        labels = labels_ds.read(1).astype(np.int32)
        if (labels.shape != Xstack.shape[1:] or
                labels_ds.crs != profile["crs"] or
                labels_ds.transform != profile["transform"]):
            raise ValueError("Label raster is not aligned with feature stack.")

    X = Xstack.reshape(Xstack.shape[0], -1).T
    y = labels.reshape(-1)

    valid = np.all(np.isfinite(X), axis=1) & (y > 0)
    X = X[valid]
    y = y[valid]

    if len(np.unique(y)) < 2:
        raise ValueError("At least two labeled classes are required.")

    keep = _balanced_indices(y, max_per_class=max_per_class, seed=random_state)
    X, y = X[keep], y[keep]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=test_size,
        random_state=random_state,
        stratify=y,
    )

    model = RandomForestClassifier(
        n_estimators=300,
        max_features="sqrt",
        class_weight="balanced_subsample",
        n_jobs=-1,
        random_state=random_state,
    )
    model.fit(X_train, y_train)

    pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, pred)
    balanced = balanced_accuracy_score(y_test, pred)

    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "model": model,
        "features": FEATURES,
        "earth_one_version": "0.7.0",
        "evaluation": {
            "accuracy": float(accuracy),
            "balanced_accuracy": float(balanced),
            "classification_report": classification_report(
                y_test, pred, output_dict=True, zero_division=0
            ),
        },
    }

    with model_path.open("wb") as f:
        pickle.dump(payload, f)

    classes = [str(x) for x in model.classes_]

    return TrainingResult(
        model_path=str(model_path),
        n_samples=int(len(X)),
        n_classes=len(classes),
        classes=classes,
        accuracy=float(accuracy),
        balanced_accuracy=float(balanced),
    )


def infer_classifier(
    feature_stack_path: str | Path,
    model_path: str | Path,
    class_output_path: str | Path,
    confidence_output_path: str | Path,
) -> InferenceResult:
    Xstack, profile, _ = _read_stack(feature_stack_path)

    with Path(model_path).open("rb") as f:
        payload = pickle.load(f)

    model = payload["model"]
    expected = tuple(payload["features"])
    if expected != FEATURES:
        raise ValueError("Model feature contract does not match v0.7.")

    X = Xstack.reshape(Xstack.shape[0], -1).T
    valid = np.all(np.isfinite(X), axis=1)

    classes = model.classes_
    predicted = np.zeros(len(X), dtype=np.int16)
    confidence = np.full(len(X), np.nan, dtype=np.float32)

    if valid.any():
        predicted[valid] = model.predict(X[valid]).astype(np.int16)
        probabilities = model.predict_proba(X[valid])
        confidence[valid] = probabilities.max(axis=1).astype(np.float32)

    predicted = predicted.reshape(Xstack.shape[1:])
    confidence = confidence.reshape(Xstack.shape[1:])

    class_output_path = Path(class_output_path)
    confidence_output_path = Path(confidence_output_path)
    class_output_path.parent.mkdir(parents=True, exist_ok=True)
    confidence_output_path.parent.mkdir(parents=True, exist_ok=True)

    class_profile = profile.copy()
    class_profile.update(
        count=1,
        dtype="int16",
        nodata=0,
        compress="deflate",
        tiled=True,
    )
    with rasterio.open(class_output_path, "w", **class_profile) as dst:
        dst.write(predicted, 1)
        dst.set_band_description(1, "PREDICTED_CLASS")
        dst.update_tags(
            EARTH_ONE_PROCESSOR_VERSION="0.7.0",
            EARTH_ONE_PRODUCT="disturbance_classification",
            EARTH_ONE_MODEL=str(model_path),
            EARTH_ONE_INTERPRETATION="class IDs require external class legend",
        )

    confidence_profile = profile.copy()
    confidence_profile.update(
        count=1,
        dtype="float32",
        nodata=np.nan,
        compress="deflate",
        predictor=3,
        tiled=True,
    )
    with rasterio.open(confidence_output_path, "w", **confidence_profile) as dst:
        dst.write(confidence, 1)
        dst.set_band_description(1, "MODEL_CONFIDENCE")
        dst.update_tags(
            EARTH_ONE_PROCESSOR_VERSION="0.7.0",
            EARTH_ONE_PRODUCT="classification_confidence",
            EARTH_ONE_MODEL=str(model_path),
            EARTH_ONE_INTERPRETATION="maximum class probability, not calibrated probability",
        )

    return InferenceResult(
        output=str(class_output_path),
        model_path=str(model_path),
        classes=[str(x) for x in classes],
        valid_fraction=float(valid.mean()),
    )


def write_result(result, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
