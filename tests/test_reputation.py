"""
Unit tests for Device Reputation, Honeypot, Flood Detection, and Security Center RBAC (Step 8).
"""
import pytest
import os
import tempfile
from datetime import datetime, timezone

from trust.reputation import ReputationEngine
from trust.engine import TrustEngine, TrustVerdict
from simulator.virtual_machine import VirtualMachine


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def rep_engine(temp_db):
    return ReputationEngine(db_path=temp_db)


@pytest.fixture
def trust_engine(rep_engine):
    return TrustEngine(rep_engine=rep_engine)


def test_new_device_starts_trusted_with_100(rep_engine):
    """Test 1: New device starts Trusted with 100 reputation score."""
    rep = rep_engine.get_reputation("M_TEST_01")
    assert rep["score"] == 100
    assert rep["state"] == "Trusted"


def test_replay_moves_to_watched(rep_engine):
    """Test 2: One replay event drops score 100 -> 75 (Watched)."""
    res = rep_engine.record_security_event("M_TEST_01", "replay")
    assert res["score"] == 75
    assert res["state"] == "Watched"


def test_physics_broken_events_lead_to_quarantined(rep_engine):
    """Test 3: Two physics-broken events (-35 each) drop 100 -> 30 (Quarantined)."""
    rep_engine.record_security_event("M_TEST_01", "physics broken")  # 100 -> 65
    res = rep_engine.record_security_event("M_TEST_01", "physics broken")  # 65 -> 30
    assert res["score"] == 30
    assert res["state"] == "Quarantined"


def test_quarantined_readings_held_in_trust_engine(trust_engine, rep_engine):
    """Test 4: Quarantined readings are marked HELD and not used for diagnosis."""
    # Force quarantine
    rep_engine.record_security_event("M_TEST_01", "honeypot")

    vm = VirtualMachine(machine_id="M_TEST_01", name="Test Unit")
    raw = vm.tick()
    report = trust_engine.evaluate(raw)

    assert report.is_held is True
    assert report.verdict == TrustVerdict.HELD
    assert report.is_trusted is False
    assert any("QUARANTINED" in r for r in report.failure_reasons)


def test_quarantined_device_does_not_auto_recover(rep_engine):
    """Test 5: Quarantined device does not auto-recover via clean readings."""
    rep_engine.record_security_event("M_TEST_01", "honeypot")  # Quarantined, score 0

    # Simulate 50 clean readings
    for _ in range(50):
        res = rep_engine.record_clean_reading("M_TEST_01")

    assert res["state"] == "Quarantined"
    assert res["score"] == 0


def test_honeypot_sends_device_straight_to_quarantined(rep_engine):
    """Test 6: Honeypot message drops device score to 0 and state to Quarantined."""
    res = rep_engine.trigger_honeypot("M_TEST_01")
    assert res["score"] == 0
    assert res["state"] == "Quarantined"


def test_flood_detected_above_threshold(rep_engine):
    """Test 7: Flood detected above 3x normal rate (180 msgs/min)."""
    is_flood = False
    for i in range(185):
        is_fl, rate = rep_engine.check_flood("M_TEST_FLOOD")
        if is_fl:
            is_flood = True
            break

    assert is_flood is True
    rep = rep_engine.get_reputation("M_TEST_FLOOD")
    assert rep["score"] == 80  # 100 - 20 flood penalty


def test_revoked_device_messages_rejected(trust_engine, rep_engine):
    """Test 8: Revoked device messages are rejected immediately."""
    rep_engine.revoke_device("M_REVOKED", admin_username="admin")

    vm = VirtualMachine(machine_id="M_REVOKED", name="Revoked Unit")
    raw = vm.tick()
    report = trust_engine.evaluate(raw)

    assert report.is_trusted is False
    assert report.verdict == TrustVerdict.REJECTED
    assert report.reputation_state == "Revoked"
    assert any("REVOKED" in r for r in report.failure_reasons)


def test_security_score_breakdown_adds_up(rep_engine):
    """Test 9: Security Score breakdown components add up correctly."""
    sec_info = rep_engine.calculate_security_score("M_TEST_01")
    total = sec_info["total_score"]
    comp_sum = sum(v[0] for v in sec_info["components"].values())

    assert total == comp_sum
    assert 0 <= total <= 100


def test_admin_release_revoke_restore(rep_engine):
    """Test 10: Admin release, revoke, and restore functions."""
    # Quarantine machine
    rep_engine.trigger_honeypot("M_ADMIN_TEST")
    assert rep_engine.get_reputation("M_ADMIN_TEST")["state"] == "Quarantined"

    # Admin release
    rel = rep_engine.release_quarantine("M_ADMIN_TEST", admin_username="admin")
    assert rel["state"] == "Watched"
    assert rel["score"] == 50

    # Admin revoke
    rev = rep_engine.revoke_device("M_ADMIN_TEST", admin_username="admin")
    assert rev["state"] == "Revoked"

    # Admin restore
    rst = rep_engine.restore_device("M_ADMIN_TEST", admin_username="admin")
    assert rst["state"] == "Watched"
