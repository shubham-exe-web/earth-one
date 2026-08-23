from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json


@dataclass(frozen=True)
class RouteDecision:
    model_family: str
    required_features: tuple[str, ...]
    reason: str
    router_version: str = "0.7.0"


class ModelRouter:
    """
    Deterministic model-selection layer.

    v0.7 deliberately routes by evidence availability. It does not claim that
    one model is universally optimal. A future meta-router can learn routing
    from validation performance.
    """

    def route(self, available_features: set[str]) -> RouteDecision:
        has_optical = {"NDVI", "DELTA_NDVI"} <= available_features
        has_sar = {"VV", "VH"} <= available_features
        has_context = bool({"landcover", "elevation", "weather"} & available_features)

        if has_optical and has_sar and has_context:
            return RouteDecision(
                model_family="multimodal_context_classifier",
                required_features=("NDVI", "DELTA_NDVI", "VV", "VH"),
                reason="Optical, SAR, and contextual evidence are available.",
            )

        if has_optical and has_sar:
            return RouteDecision(
                model_family="multimodal_classifier",
                required_features=("NDVI", "DELTA_NDVI", "VV", "VH"),
                reason="Optical and SAR evidence are available.",
            )

        if has_optical:
            return RouteDecision(
                model_family="optical_temporal_classifier",
                required_features=("NDVI", "DELTA_NDVI"),
                reason="Only optical temporal evidence is available.",
            )

        if has_sar:
            return RouteDecision(
                model_family="sar_change_classifier",
                required_features=("VV", "VH"),
                reason="Only SAR evidence is available.",
            )

        return RouteDecision(
            model_family="insufficient_evidence",
            required_features=(),
            reason="Available evidence is insufficient for v0.7 classification.",
        )

    def save_decision(self, decision: RouteDecision, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(decision), indent=2), encoding="utf-8")
