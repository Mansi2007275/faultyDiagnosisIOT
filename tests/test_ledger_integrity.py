"""
tests/test_ledger_integrity.py
───────────────────────────────
Tests that the deterministic hashing fix works correctly:

  1. Sealing a batch and immediately verifying it → VALID (no false alarm).
  2. Sealing a batch, simulating a tamper, re-verifying → TAMPERED detected,
     with the correct batch and record identified.
  3. The canonical hash of the same logical record is always identical
     regardless of float arithmetic path.
  4. Modifying an _internal key (like _trust_score) does NOT affect the hash
     (only CANONICAL_FIELDS matter).
"""

import pytest
from ledger.batch import AuditLedger, LedgerRecord
from ledger.hasher import hash_telemetry_record, canonical_record, CANONICAL_FIELDS


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_reading(machine_id: str = "VM-TEST-01", seed: float = 1.0) -> dict:
    """Returns a realistic telemetry dict including internal _* keys."""
    return {
        "machine_id": machine_id,
        "timestamp": 1700000000.0 + seed,
        "type": "M",
        "air_temperature_k": round(298.1 + seed * 0.01, 4),
        "process_temperature_k": round(308.6 + seed * 0.02, 4),
        "rotational_speed_rpm": int(1500 + seed),
        "torque_nm": round(40.0 + seed * 0.1, 4),
        "tool_wear_min": int(10 + seed),
        # Internal keys that must NOT affect the hash
        "_trust_score": 95,
        "_is_unusual": False,
        "_anomaly_exp": "normal",
    }


# ── 1. Seal then verify immediately → VALID ───────────────────────────────────

def test_seal_then_verify_is_valid():
    ledger = AuditLedger(batch_size_limit=5)
    for i in range(3):
        ledger.record_telemetry(_make_reading(seed=float(i)))

    sealed = ledger.seal_current_batch()
    assert sealed is not None

    ok, findings = ledger.verify_chain_integrity(log_tampering=False)
    assert ok is True, f"Expected VALID but got issues: {findings}"
    assert "verified" in findings[0].lower()


# ── 2. Seal → tamper → verify → TAMPERED (correct record identified) ──────────

def test_tamper_is_detected_with_correct_record():
    ledger = AuditLedger(batch_size_limit=5)
    for i in range(4):
        ledger.record_telemetry(_make_reading(seed=float(i)))

    sealed = ledger.seal_current_batch()
    assert sealed is not None

    # First verify clean → must be VALID
    ok, _ = ledger.verify_chain_integrity(log_tampering=False)
    assert ok is True

    # Tamper record #2 in batch 0
    success = ledger.simulate_tamper(
        batch_idx=0, record_idx=2, field_name="torque_nm", new_value=999.99
    )
    assert success is True

    ok, findings = ledger.verify_chain_integrity(log_tampering=False)
    assert ok is False, "Expected tampering to be detected"
    # The finding must mention record #2
    combined = " ".join(findings)
    assert "Record #2" in combined, f"Expected 'Record #2' in findings: {findings}"
    assert "Batch #0" in combined


# ── 3. Same logical reading always hashes identically ─────────────────────────

def test_hash_is_deterministic():
    rec = _make_reading(seed=42.0)

    h1 = hash_telemetry_record(rec)
    # Simulate float drift (arithmetic noise)
    rec2 = dict(rec)
    rec2["torque_nm"] = 44.2 + 0.0 + 0.0  # same value, different expression
    h2 = hash_telemetry_record(rec2)
    assert h1 == h2, "Hash must be identical for the same canonical values"


# ── 4. Float rounding eliminates arithmetic noise ─────────────────────────────

def test_float_noise_does_not_affect_hash():
    rec_a = {**_make_reading(), "torque_nm": 0.1 + 0.2}         # = 0.30000000000000004
    rec_b = {**_make_reading(), "torque_nm": 0.3}               # = 0.3

    h_a = hash_telemetry_record(rec_a)
    h_b = hash_telemetry_record(rec_b)
    assert h_a == h_b, (
        "Floating-point noise (0.1+0.2 vs 0.3) must not produce different hashes"
    )


# ── 5. Internal _* keys do NOT affect the hash ────────────────────────────────

def test_internal_keys_excluded_from_hash():
    rec = _make_reading()
    h1 = hash_telemetry_record(rec)

    rec_modified = dict(rec)
    rec_modified["_trust_score"] = 0        # completely different internal value
    rec_modified["_new_internal"] = "xyz"   # new internal key
    h2 = hash_telemetry_record(rec_modified)

    assert h1 == h2, "Internal _* keys must not affect the canonical hash"


# ── 6. Multiple batches – chain linkage verified ──────────────────────────────

def test_multi_batch_chain_valid():
    ledger = AuditLedger(batch_size_limit=2)
    for i in range(6):   # 3 auto-sealed batches
        ledger.record_telemetry(_make_reading(seed=float(i)))

    assert len(ledger.sealed_batches) == 3

    ok, findings = ledger.verify_chain_integrity(log_tampering=False)
    assert ok is True, f"Multi-batch chain should be valid: {findings}"


# ── 7. Tampering in second batch is caught correctly ─────────────────────────

def test_tamper_in_second_batch():
    ledger = AuditLedger(batch_size_limit=2)
    for i in range(4):   # 2 batches
        ledger.record_telemetry(_make_reading(seed=float(i)))

    assert len(ledger.sealed_batches) == 2

    # Tamper the first record of the second batch
    ledger.simulate_tamper(
        batch_idx=1, record_idx=0, field_name="rotational_speed_rpm", new_value=9999
    )

    ok, findings = ledger.verify_chain_integrity(log_tampering=False)
    assert ok is False
    combined = " ".join(findings)
    assert "Batch #1" in combined
    assert "Record #0" in combined
