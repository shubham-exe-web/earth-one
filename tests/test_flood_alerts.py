from earth_one.flood_alerts import FloodAlertManager, run_alert_reliability_benchmark


def test_alert_reliability_benchmark():
    manifest = run_alert_reliability_benchmark()
    summary = manifest["reliability_summary"]
    
    assert summary["total_passes_evaluated"] == 6
    assert summary["state_transition_accuracy"] == 1.0
    assert summary["duplicate_alert_rate"] == 0.0
    assert summary["blackout_safety_rate"] == 1.0
    assert summary["all_gates_passed"] is True
    assert summary["mean_decision_latency_ms"] < 20.0


def test_blackout_safety_contract():
    manager = FloodAlertManager()
    
    # 1. Simulate Blackout on unmonitored AOI
    rec = manager.process_epoch_observation("Test_AOI", "2022-09-01", None, status="cannot_evaluate")
    assert rec.transition_type == "DATA_BLACKOUT_HOLD"
    assert rec.is_dispatchable is False
    assert "Hold" in rec.message_title
