import numpy as np
from earth_one.drought.features import (
    compute_ndvi,
    compute_evi,
    compute_ndre,
    compute_ndwi,
    extract_optical_features,
)


def test_ndvi_computation():
    nir = np.array([0.50, 0.20, 0.05], dtype=np.float32)
    red = np.array([0.10, 0.20, 0.05], dtype=np.float32)
    ndvi = compute_ndvi(nir, red)

    assert np.isclose(ndvi[0], (0.5 - 0.1) / (0.5 + 0.1))  # ~0.667
    assert np.isclose(ndvi[1], 0.0)                         # 0.0
    assert -1.0 <= ndvi[2] <= 1.0


def test_evi_and_ndre_computation():
    nir = np.array([0.60, 0.30], dtype=np.float32)
    red = np.array([0.10, 0.20], dtype=np.float32)
    blue = np.array([0.05, 0.10], dtype=np.float32)
    re = np.array([0.25, 0.25], dtype=np.float32)

    evi = compute_evi(nir, red, blue)
    ndre = compute_ndre(nir, re)

    assert len(evi) == 2
    assert len(ndre) == 2
    assert evi[0] > evi[1]
    assert ndre[0] > ndre[1]


def test_optical_feature_extraction_pipeline():
    shape = (20, 20)
    blue = np.full(shape, 0.05, dtype=np.float32)
    red = np.full(shape, 0.10, dtype=np.float32)
    re = np.full(shape, 0.25, dtype=np.float32)
    nir = np.full(shape, 0.55, dtype=np.float32)
    swir = np.full(shape, 0.20, dtype=np.float32)

    cloud_mask = np.zeros(shape, dtype=bool)
    cloud_mask[0:5, 0:5] = True  # 25 cloud pixels

    opt_feat = extract_optical_features(blue, red, re, nir, swir, cloud_mask=cloud_mask)

    assert opt_feat.valid_mask.shape == shape
    assert np.sum(opt_feat.valid_mask) == (400 - 25)
    assert opt_feat.provenance.valid_fraction == (375 / 400)
    assert len(opt_feat.provenance.provenance_hash) == 64
