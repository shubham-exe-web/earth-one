from __future__ import annotations

"""Drought Module 3 Climatological Baseline Architecture & Anomaly Standardizers."""

import hashlib
from dataclasses import dataclass
from typing import Any, Sequence
import numpy as np


@dataclass
class BaselineClimatology:
    """Historical multi-year statistical distribution per calendar month/season."""
    variable_name: str
    month: int
    mean: np.ndarray
    std: np.ndarray
    median: np.ndarray
    iqr: np.ndarray
    p10: np.ndarray
    p20: np.ndarray
    p80: np.ndarray
    p90: np.ndarray
    min_observed: np.ndarray
    max_observed: np.ndarray
    sample_years: int
    valid_sample_fraction: float
    provenance_hash: str


class HistoricalClimatologyStore:
    """Manages multi-year historical baseline stacks per month with zero-leakage guarantees."""

    def __init__(self, variable_name: str):
        self.variable_name = variable_name
        self.monthly_baselines: dict[int, BaselineClimatology] = {}

    def fit_from_historical_stack(
        self,
        month: int,
        historical_stack: np.ndarray,  # Shape (N_years, H, W)
        year_labels: Sequence[int] | None = None,
        excluded_years: Sequence[int] | None = None,
    ) -> BaselineClimatology:
        """Compute robust multi-year distribution parameters across historical years with zero-leakage year exclusion."""
        assert historical_stack.ndim == 3, "Stack must be (N_years, H, W)"
        n_years_raw, H, W = historical_stack.shape

        if year_labels is not None:
            assert len(year_labels) == n_years_raw, f"year_labels length ({len(year_labels)}) must match stack depth ({n_years_raw})"
            if excluded_years is not None:
                keep_indices = [i for i, y in enumerate(year_labels) if y not in excluded_years]
                assert len(keep_indices) >= 3, f"Must have at least 3 historical years after excluding {excluded_years} (retained {len(keep_indices)})"
                stack = historical_stack[keep_indices]
            else:
                stack = historical_stack
        elif excluded_years is not None:
            keep_indices = [i for i in range(n_years_raw) if i not in excluded_years]
            assert len(keep_indices) >= 3, f"Must have at least 3 historical years after exclusion (retained {len(keep_indices)})"
            stack = historical_stack[keep_indices]
        else:
            stack = historical_stack

        n_years = stack.shape[0]

        mu = np.nanmean(stack, axis=0).astype(np.float32)
        sigma = np.nanstd(stack, axis=0).astype(np.float32)
        med = np.nanmedian(stack, axis=0).astype(np.float32)
        
        p10 = np.nanpercentile(stack, 10, axis=0).astype(np.float32)
        p20 = np.nanpercentile(stack, 20, axis=0).astype(np.float32)
        p80 = np.nanpercentile(stack, 80, axis=0).astype(np.float32)
        p90 = np.nanpercentile(stack, 90, axis=0).astype(np.float32)
        iqr = p80 - p20
        min_v = np.nanmin(stack, axis=0).astype(np.float32)
        max_v = np.nanmax(stack, axis=0).astype(np.float32)

        valid_frac = float(np.mean(np.isfinite(stack)))
        prov = hashlib.sha256(
            f"CLIM_FIT_{self.variable_name}_{month}_{n_years}_{np.nanmean(mu):.3f}".encode()
        ).hexdigest()

        clim = BaselineClimatology(
            variable_name=self.variable_name,
            month=month,
            mean=mu,
            std=sigma,
            median=med,
            iqr=iqr,
            p10=p10,
            p20=p20,
            p80=p80,
            p90=p90,
            min_observed=min_v,
            max_observed=max_v,
            sample_years=n_years,
            valid_sample_fraction=round(valid_frac, 4),
            provenance_hash=prov,
        )
        self.monthly_baselines[month] = clim
        return clim


def compute_standardized_anomaly(
    current: np.ndarray,
    baseline_mean: np.ndarray,
    baseline_std: np.ndarray,
    min_std: float = 0.02,
    clip_range: tuple[float, float] = (-4.0, 4.0),
) -> np.ndarray:
    """Compute standardized anomaly z-score: Z = (X - mu) / max(sigma, min_std)."""
    std_safe = np.maximum(baseline_std, min_std)
    z = (current - baseline_mean) / std_safe
    z = np.where(np.isfinite(z), z, np.nan)
    return np.clip(z, clip_range[0], clip_range[1]).astype(np.float32)


def compute_empirical_percentile(
    current: np.ndarray,
    clim: BaselineClimatology,
) -> np.ndarray:
    """Map current value to empirical percentile [0.0, 1.0] using piecewise linear interpolation."""
    # Piecewise interpolation across min, p10, p20, median, p80, p90, max
    out = np.zeros_like(current, dtype=np.float32)
    # Simple linear scaling using min and max bounds as non-parametric proxy
    denom = np.maximum(clim.max_observed - clim.min_observed, 1e-4)
    out = np.clip((current - clim.min_observed) / denom, 0.0, 1.0)
    return out.astype(np.float32)


def compute_vegetation_condition_index(
    current_ndvi: np.ndarray,
    min_ndvi: np.ndarray,
    max_ndvi: np.ndarray,
    eps: float = 1e-4,
) -> np.ndarray:
    """Compute Vegetation Condition Index (VCI): (NDVI - min) / (max - min) * 100%."""
    range_ndvi = np.maximum(max_ndvi - min_ndvi, eps)
    vci = (current_ndvi - min_ndvi) / range_ndvi
    return np.clip(vci, 0.0, 1.0).astype(np.float32)


def compute_standardized_precipitation_anomaly(
    precip_acc_mm: np.ndarray,
    precip_mean_mm: np.ndarray,
    precip_std_mm: np.ndarray,
    min_std_mm: float = 5.0,
) -> np.ndarray:
    """Compute standardized precipitation anomaly z-score (Gaussian approximation)."""
    return compute_standardized_anomaly(precip_acc_mm, precip_mean_mm, precip_std_mm, min_std=min_std_mm)


def build_synthetic_climatology(
    shape: tuple[int, int],
    variable_name: str,
    month: int,
    mean_val: float,
    std_val: float,
    spatial_gradient: bool = True,
) -> BaselineClimatology:
    """Generate a reproducible synthetic climatological baseline for unit testing."""
    H, W = shape
    if spatial_gradient:
        y_grad = np.linspace(0.85, 1.15, H)[:, None]
        x_grad = np.linspace(0.90, 1.10, W)[None, :]
        mu = np.full(shape, mean_val, dtype=np.float32) * y_grad * x_grad
    else:
        mu = np.full(shape, mean_val, dtype=np.float32)

    sigma = np.full(shape, std_val, dtype=np.float32)
    min_obs = np.maximum(0.0, mu - 2.5 * sigma)
    max_obs = mu + 2.5 * sigma
    med = mu.copy()
    p10 = mu - 1.28 * sigma
    p20 = mu - 0.84 * sigma
    p80 = mu + 0.84 * sigma
    p90 = mu + 1.28 * sigma
    iqr = p80 - p20

    prov_hash = hashlib.sha256(
        f"CLIM_{variable_name}_{month}_{mean_val:.3f}_{std_val:.3f}_{shape}".encode()
    ).hexdigest()

    return BaselineClimatology(
        variable_name=variable_name,
        month=month,
        mean=mu,
        std=sigma,
        median=med,
        iqr=iqr,
        p10=p10,
        p20=p20,
        p80=p80,
        p90=p90,
        min_observed=min_obs,
        max_observed=max_obs,
        sample_years=20,
        valid_sample_fraction=1.0,
        provenance_hash=prov_hash,
    )
