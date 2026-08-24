import numpy as np
from earth_one.drought.regime import classify_drought_regime


def test_classify_forest_vs_dense_cropland():
    # Dense forest: high baseline (0.70) AND low seasonal amplitude (0.15)
    ndvi_forest = np.full((10, 10), 0.70, dtype=np.float32)
    res_forest = classify_drought_regime(
        baseline_mean_ndvi=ndvi_forest,
        baseline_min_ndvi=np.full((10, 10), 0.60, dtype=np.float32),
        baseline_max_ndvi=np.full((10, 10), 0.75, dtype=np.float32),
    )
    assert res_forest.regime == "FOREST"
    assert res_forest.recommended_modality_weights.vegetation == 0.40

    # Dense cropland: high peak (0.75) but HIGH seasonal phenology amplitude (0.50)
    ndvi_crop = np.full((10, 10), 0.65, dtype=np.float32)
    res_crop = classify_drought_regime(
        baseline_mean_ndvi=ndvi_crop,
        baseline_min_ndvi=np.full((10, 10), 0.20, dtype=np.float32),
        baseline_max_ndvi=np.full((10, 10), 0.75, dtype=np.float32),
    )
    assert res_crop.regime == "RAINFED_AGRICULTURE"
    assert res_crop.evidence_context.seasonal_phenology_amplitude >= 0.35


def test_classify_irrigated_agriculture():
    ndvi = np.full((10, 10), 0.55, dtype=np.float32)
    irrig = np.ones((10, 10), dtype=bool)
    res = classify_drought_regime(ndvi, is_irrigation_active=irrig)
    assert res.regime == "IRRIGATED_AGRICULTURE"
    assert res.is_irrigated is True
    assert res.recommended_modality_weights.vegetation < res.recommended_modality_weights.precipitation


def test_classify_dryland_sparse():
    ndvi = np.full((10, 10), 0.12, dtype=np.float32)
    res = classify_drought_regime(
        baseline_mean_ndvi=ndvi,
        baseline_min_ndvi=np.full((10, 10), 0.08, dtype=np.float32),
        baseline_max_ndvi=np.full((10, 10), 0.18, dtype=np.float32),
    )
    assert res.regime == "DRYLAND_SPARSE"
    assert res.recommended_modality_weights.thermal == 0.15
