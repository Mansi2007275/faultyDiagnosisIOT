"""
Unit and Integration Tests for SentinelTwin Verdict Engine & Response Ladder (Step 7).
"""
import os
import pytest
import tempfile
from engine.verdict import decide
from engine.db import get_recent_verdict_changes, get_machine_state, init_db


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database file for isolated test execution."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    init_db(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


def test_rejected_message_triggers_data_attack(temp_db):
    """
    Test 1: Rejected message (bad signature / replay / invalid HMAC) -> Data Attack,
    response "Verify data: no machine action".
    """
    reading = {"type": "M", "power_w": 9500}
    trust_result = {
        "valid": False,
        "status": "REJECTED_HMAC",
        "reasons": ["Invalid HMAC signature signature_mismatch"]
    }

    res = decide(reading, trust_result=trust_result, machine_id="M-TEST1", db_path=temp_db)

    assert res["verdict"] == "Data Attack"
    assert res["response"] == "Verify data: no machine action"
    assert res["severity"] == "CRITICAL"
    assert any("Data Attack" in r for r in res["reasons"])


def test_stuck_sensor_triggers_sensor_failure(temp_db):
    """
    Test 2: Stuck sensor flag -> Sensor Failure,
    response "Verify data: no machine action".
    """
    reading = {"type": "M", "rotational_speed_rpm": 1400}
    trust_result = {
        "valid": True,
        "sensor_failure": True,
        "status": "STUCK_SENSOR",
        "reasons": ["Sensor rotational_speed_rpm stuck at 1400 over rolling window"]
    }

    res = decide(reading, trust_result=trust_result, machine_id="M-TEST2", db_path=temp_db)

    assert res["verdict"] == "Sensor Failure"
    assert res["response"] == "Verify data: no machine action"
    assert res["severity"] == "HIGH"
    assert any("Sensor Failure" in r for r in res["reasons"])


def test_high_rule_fault_escalates_after_3_readings(temp_db):
    """
    Test 3: HIGH rule fault -> Machine Fault with at least 'Reduce load (recommend)' after 3 readings.
    Verifies hysteresis delay on 1st and 2nd readings before escalating on 3rd reading.
    """
    reading = {"type": "M", "torque_nm": 70, "tool_wear_min": 220}
    trust_result = {"valid": True, "reasons": []}
    rule_faults = [{
        "code": "OSF",
        "name": "Overstrain Failure",
        "risk_level": "HIGH",
        "explanation": "Torque x tool wear exceeds 11,000 Nm-min"
    }]

    # Reading 1: Candidate level is Reduce load, but current state is OK -> stays OK (pending count = 1)
    res1 = decide(reading, trust_result=trust_result, rule_faults=rule_faults, machine_id="M-TEST3", db_path=temp_db)
    assert res1["verdict"] == "Machine Fault"
    assert res1["response"] == "OK"

    # Reading 2: pending count = 2 -> stays OK
    res2 = decide(reading, trust_result=trust_result, rule_faults=rule_faults, machine_id="M-TEST3", db_path=temp_db)
    assert res2["response"] == "OK"

    # Reading 3: pending count = 3 -> escalates to Reduce load (recommend)!
    res3 = decide(reading, trust_result=trust_result, rule_faults=rule_faults, machine_id="M-TEST3", db_path=temp_db)
    assert res3["response"] == "Reduce load (recommend)"


def test_high_fault_for_5_readings_triggers_safe_stop(temp_db):
    """
    Test 4: Persistent HIGH fault for 5 readings -> Safe stop (recommend).
    """
    reading = {"type": "M", "torque_nm": 70, "tool_wear_min": 220}
    trust_result = {"valid": True, "reasons": []}
    rule_faults = [{
        "code": "OSF",
        "name": "Overstrain Failure",
        "risk_level": "HIGH",
        "explanation": "Torque x tool wear exceeds 11,000 Nm-min"
    }]

    responses = []
    for i in range(5):
        r = decide(reading, trust_result=trust_result, rule_faults=rule_faults, machine_id="M-TEST4", db_path=temp_db)
        responses.append(r["response"])

    # By the 5th reading, Safe stop (recommend) must be triggered!
    assert responses[-1] == "Safe stop (recommend)"


def test_normal_reading_low_anomaly_gives_ok(temp_db):
    """
    Test 5: Normal reading + low anomaly -> OK.
    """
    reading = {"type": "M", "air_temperature_k": 300, "process_temperature_k": 310, "rotational_speed_rpm": 1500}
    trust_result = {"valid": True}
    anomaly = {"anomaly_score": 0.25, "is_anomaly": False}
    ml_pred = ("none", 0.99)

    res = decide(reading, trust_result=trust_result, anomaly=anomaly, ml_prediction=ml_pred, machine_id="M-TEST5", db_path=temp_db)

    assert res["verdict"] == "Normal"
    assert res["response"] == "OK"
    assert res["severity"] == "LOW"


def test_normal_reading_high_anomaly_gives_watch(temp_db):
    """
    Test 6: Normal reading + high anomaly -> Watch (after 3 consecutive readings due to hysteresis).
    """
    reading = {"type": "M", "air_temperature_k": 300}
    trust_result = {"valid": True}
    anomaly = {"anomaly_score": 0.85, "is_anomaly": True}

    # Run 3 times to allow hysteresis escalation from OK to Watch
    res1 = decide(reading, trust_result=trust_result, anomaly=anomaly, machine_id="M-TEST6", db_path=temp_db)
    res2 = decide(reading, trust_result=trust_result, anomaly=anomaly, machine_id="M-TEST6", db_path=temp_db)
    res3 = decide(reading, trust_result=trust_result, anomaly=anomaly, machine_id="M-TEST6", db_path=temp_db)

    assert res3["verdict"] == "Normal"
    assert res3["response"] == "Watch"


def test_one_noisy_reading_does_not_jump_to_safe_stop(temp_db):
    """
    Test 7: One noisy reading does not jump straight to Safe stop (hysteresis protects against flicker).
    """
    healthy_reading = {"type": "M", "torque_nm": 40}
    noisy_reading = {"type": "M", "torque_nm": 70, "tool_wear_min": 220}
    trust_result = {"valid": True}
    high_fault = [{"code": "OSF", "risk_level": "HIGH"}]

    # Establish baseline OK
    res_base = decide(healthy_reading, trust_result=trust_result, machine_id="M-TEST7", db_path=temp_db)
    assert res_base["response"] == "OK"

    # Single noisy reading occurs
    res_noisy = decide(noisy_reading, trust_result=trust_result, rule_faults=high_fault, machine_id="M-TEST7", db_path=temp_db)
    assert res_noisy["response"] == "OK"  # Hysteresis blocks immediate jump!

    # Return to healthy reading
    res_calm = decide(healthy_reading, trust_result=trust_result, machine_id="M-TEST7", db_path=temp_db)
    assert res_calm["response"] == "OK"


def test_response_steps_down_only_after_10_calm_readings(temp_db):
    """
    Test 8: Response steps down to a lower level ONLY after 10 consecutive calm readings.
    """
    healthy_reading = {"type": "M", "torque_nm": 40}
    noisy_reading = {"type": "M", "torque_nm": 70, "tool_wear_min": 220}
    trust_result = {"valid": True}
    high_fault = [{"code": "OSF", "risk_level": "HIGH"}]

    # Escalate to Reduce load (recommend) with 3 noisy readings
    for _ in range(3):
        decide(noisy_reading, trust_result=trust_result, rule_faults=high_fault, machine_id="M-TEST8", db_path=temp_db)

    state = get_machine_state("M-TEST8", db_path=temp_db)
    assert state["current_response"] == "Reduce load (recommend)"

    # Feed 9 calm readings -> response should STILL be Reduce load (recommend)
    for i in range(9):
        r = decide(healthy_reading, trust_result=trust_result, machine_id="M-TEST8", db_path=temp_db)
        assert r["response"] == "Reduce load (recommend)"

    # Feed 10th calm reading -> now it steps down to OK!
    r10 = decide(healthy_reading, trust_result=trust_result, machine_id="M-TEST8", db_path=temp_db)
    assert r10["response"] == "OK"


def test_verdict_timeline_audit_logging(temp_db):
    """
    Test that verdict changes are correctly logged into SQLite verdict_changes table.
    """
    reading_ok = {"type": "M"}
    reading_attack = {"type": "M"}
    trust_ok = {"valid": True}
    trust_attack = {"valid": False, "reasons": ["Invalid HMAC"]}

    decide(reading_ok, trust_result=trust_ok, machine_id="M-AUDIT", db_path=temp_db)
    decide(reading_attack, trust_result=trust_attack, machine_id="M-AUDIT", db_path=temp_db)

    changes = get_recent_verdict_changes(machine_id="M-AUDIT", limit=10, db_path=temp_db)
    assert len(changes) >= 1
    assert changes[0]["to_verdict"] == "Data Attack"
    assert changes[0]["to_response"] == "Verify data: no machine action"
