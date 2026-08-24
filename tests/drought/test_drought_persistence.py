from earth_one.drought.persistence import evaluate_temporal_persistence_series


def test_temporal_progression_lifecycle():
    # Sequence: Normal -> Watch -> Emerging -> Active -> Peak -> Recovery -> Resolved
    severity = [0.1, 0.6, 0.7, 0.75, 0.85, 0.90, 0.4, 0.3, 0.2, 0.1]
    resolvable = [True] * len(severity)

    traj = evaluate_temporal_persistence_series(severity, resolvable)
    states = [s.current_state for s in traj]

    assert states[0] == "NORMAL"
    assert states[1] == "WATCH"
    assert states[2] == "EMERGING"
    assert states[3] == "EMERGING"
    assert states[4] == "ACTIVE"
    assert states[5] == "PEAK"
    assert states[6] == "RECOVERY"
    assert states[7] == "RECOVERY"
    assert states[8] == "RESOLVED"
    assert states[9] == "NORMAL"


def test_telemetry_blackout_safety():
    severity = [0.1, 0.8, 0.85, 0.0, 0.0]
    resolvable = [True, True, True, False, False]  # Telemetry drops during active drought

    traj = evaluate_temporal_persistence_series(severity, resolvable)
    states = [s.current_state for s in traj]

    assert states[2] == "EMERGING"
    # Blackout must NOT become NORMAL or RESOLVED; it holds previous state
    assert states[3] == "EMERGING"
    assert states[4] == "EMERGING"
