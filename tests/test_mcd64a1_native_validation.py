import pytest
import numpy as np
import rasterio
from earth_one.mcd64a1_native_validation import (
    NativeMCDConfig,
    decode_mcd64a1_qa_bits,
    evaluate_native_mcd64a1_agreement,
)


def test_decode_mcd64a1_qa_bits():
    # Value 3 = 0b00000011 -> Land=1, Valid=1, Unshortened=1, Not Contextually Relabeled=1 -> High Confidence True
    # Value 2 = 0b00000010 -> Water=0, Valid=1 -> Land False -> High Confidence False
    # Value 7 = 0b00000111 -> Land=1, Valid=1, Shortened=1 -> High Confidence False
    # Value 11 = 0b00001011 -> Land=1, Valid=1, Relabeled=1 -> High Confidence False
    # Value 67 = 0b01000011 -> Land=1, Valid=1, Unburned special code
    qa = np.array([3, 2, 7, 11, 67], dtype=np.uint8)
    res = decode_mcd64a1_qa_bits(qa)
    
    assert res["is_land"][0] == True
    assert res["is_land"][1] == False  # Water
    assert res["is_valid_data"][0] == True
    assert res["is_unshortened"][0] == True
    assert res["is_unshortened"][2] == False  # Shortened period
    assert res["is_not_contextually_relabeled"][0] == True
    assert res["is_not_contextually_relabeled"][3] == False  # Contextually relabeled
    assert res["high_confidence_burn"][0] == True
    assert res["high_confidence_burn"][1] == False
    assert res["high_confidence_burn"][2] == False
    assert res["high_confidence_burn"][3] == False


def test_evaluate_native_mcd64a1_agreement():
    fine_pred = np.zeros((100, 100), dtype=bool)
    fine_pred[10:30, 10:30] = True
    fine_valid = np.ones((100, 100), dtype=bool)
    
    fine_prof = {
        "height": 100, "width": 100, "crs": "EPSG:4326",
        "transform": rasterio.transform.from_origin(82.6, 22.45, 0.001, 0.001)
    }
    
    native_burn = np.zeros((10, 10), dtype=np.int16)
    native_burn[1:3, 1:3] = 20
    native_qa = np.full((10, 10), 3, dtype=np.uint8)
    
    native_prof = {
        "height": 10, "width": 10, "crs": "EPSG:4326",
        "transform": rasterio.transform.from_origin(82.6, 22.45, 0.01, 0.01)
    }
    
    res = evaluate_native_mcd64a1_agreement(
        fine_prediction_grid=fine_pred,
        fine_valid_mask=fine_valid,
        fine_profile=fine_prof,
        native_burn_date=native_burn,
        native_qa=native_qa,
        native_profile=native_prof,
        fraction_threshold=0.10,
        filter_qa_high_confidence=True,
    )
    
    assert res["metrics"]["recall"] > 0.0
    assert res["confusion_matrix"]["tp"] > 0
    assert res["valid_land_cells"] == 100
