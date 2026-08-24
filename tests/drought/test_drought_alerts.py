from earth_one.drought.events import DroughtEventRecord
from earth_one.drought.alerting import DroughtAlertStateMachine


def create_dummy_event(ev_id: int, severity: float, area: float) -> DroughtEventRecord:
    return DroughtEventRecord(
        event_id=ev_id,
        area_expected_ha=area,
        area_sensitivity_low_ha=area * 0.8,
        area_sensitivity_high_ha=area * 1.2,
        area_sensitivity_margin_ha=area * 0.2,
        area_sensitivity_pct=20.0,
        pixel_count=int(area / 0.04),
        mean_severity=severity,
        peak_severity=severity,
        mean_observability=0.85,
        is_well_observed=True,
        centroid_row=25.0,
        centroid_col=25.0,
        bounding_box=(10, 10, 40, 40),
        provenance_hash="TEST_EV",
    )


def test_alert_lifecycle_and_idempotency_replay():
    asm = DroughtAlertStateMachine(suppression_window_days=14.0)

    # Sequence of 10 timeline messages to evaluate idempotency and duplicate rate
    ev_initial = create_dummy_event(201, severity=0.48, area=100.0)
    
    # 1. Day 1: New Alert (MODERATE)
    a1 = asm.process_event_alert(ev_initial, current_time_days=1.0)
    assert a1.action == "NEW_ALERT"
    assert a1.severity_tier == "MODERATE"

    # 2. Day 2: Identical Repeat (Duplicate Suppressed)
    a2 = asm.process_event_alert(ev_initial, current_time_days=2.0)
    assert a2.action == "DUPLICATE_SUPPRESSED"

    # 3. Day 5: Minor area fluctuation within same tier (Duplicate Suppressed)
    ev_minor = create_dummy_event(201, severity=0.50, area=108.0)
    a3 = asm.process_event_alert(ev_minor, current_time_days=5.0)
    assert a3.action == "DUPLICATE_SUPPRESSED"

    # 4. Day 8: Severity Escalation to SEVERE (Overrides suppression)
    ev_severe = create_dummy_event(201, severity=0.68, area=180.0)
    a4 = asm.process_event_alert(ev_severe, current_time_days=8.0)
    assert a4.action == "SEVERITY_ESCALATION"
    assert a4.severity_tier == "SEVERE"

    # 5. Day 10: Repeat SEVERE within window (Duplicate Suppressed)
    a5 = asm.process_event_alert(ev_severe, current_time_days=10.0)
    assert a5.action == "DUPLICATE_SUPPRESSED"

    # 6. Day 12: Telemetry Blackout (DATA_BLACKOUT_HOLD - fail safe)
    a6 = asm.process_event_alert(ev_severe, current_time_days=12.0, is_data_blackout=True)
    assert a6.action == "DATA_BLACKOUT_HOLD"

    # 7. Day 20: Re-observation after suppression window expires (ALERT_UPDATE)
    a7 = asm.process_event_alert(ev_severe, current_time_days=23.0)
    assert a7.action == "ALERT_UPDATE"

    # 8. Day 25: De-escalation to MODERATE (SEVERITY_DEESCALATION)
    a8 = asm.process_event_alert(ev_initial, current_time_days=25.0)
    assert a8.action == "SEVERITY_DEESCALATION"
