from earth_one.flood_fault_injection import run_fault_injection_suite


def test_fault_injection_suite_all_pass():
    res = run_fault_injection_suite()
    assert res["summary"]["total_fault_modes_tested"] == 7
    assert res["summary"]["passed_safe_modes"] == 7
    assert res["summary"]["all_modes_safe"] is True

    # Validate critical safety distinction: cannot_evaluate / no_evidence != no_flood
    fault_map = {f["fault_mode"]: f for f in res["fault_evaluations"]}
    assert fault_map["FAULT_ALL_SENSORS_UNAVAILABLE"]["actual_status"] == "no_evidence"
    assert fault_map["FAULT_CORRUPT_SAR_ZERO_POWER"]["actual_status"] == "no_evidence"
    assert fault_map["FAULT_OPTICAL_100PCT_CLOUD"]["actual_status"] == "accepted"
