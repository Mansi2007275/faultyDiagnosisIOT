"""
tests/test_merkle_proof.py
──────────────────────────
Covers the Merkle Proof Explorer and Audit Proof Report:

  1. A valid proof passes.
  2. Changing one value in a reading makes its proof fail.
  3. A proof file whose stated root has been edited fails.
  4. An odd number of leaves works (the duplicate-last-node rule).
  5. The proof tree's root is bit-identical to compute_merkle_root().
  6. derive_batch_hash() stays pinned to Batch.seal().
  7. An unreachable chain is reported as inconclusive, never as a failure.
"""

import json

import pytest

from ledger.batch import AuditLedger
from ledger.hasher import compute_merkle_root, hash_telemetry_record, sha256_digest
from ledger.proof import (
    build_merkle_tree,
    get_merkle_proof,
    merkle_root_from_tree,
    recompute_root_from_proof,
    verify_merkle_proof,
)
from ledger.report import (
    CHAIN_OFFLINE,
    INCONCLUSIVE_CHAIN_STATES,
    build_proof_payload,
    check_onchain_root,
    derive_batch_hash,
    proof_json_bytes,
    proof_pdf_bytes,
    verify_proof_payload,
)
from ledger import store


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_reading(seed: float = 1.0, machine_id: str = "VM-PROOF-01") -> dict:
    return {
        "machine_id": machine_id,
        "timestamp": 1700000000.0 + seed,
        "type": "M",
        "air_temperature_k": round(298.1 + seed * 0.01, 4),
        "process_temperature_k": round(308.6 + seed * 0.02, 4),
        "rotational_speed_rpm": int(1500 + seed),
        "torque_nm": round(40.0 + seed * 0.1, 4),
        "tool_wear_min": int(10 + seed),
        "_trust_score": 95,
    }


def _sealed_ledger(n_records: int = 6, limit: int = 100) -> AuditLedger:
    ledger = AuditLedger(batch_size_limit=limit)
    for i in range(n_records):
        ledger.record_telemetry(_make_reading(seed=float(i)))
    ledger.seal_current_batch()
    return ledger


def _batch_meta(batch, sealed_at: str = "2026-10-01T00:00:00Z") -> dict:
    return {
        "batch_index": batch.batch_index,
        "timestamp": batch.timestamp,
        "merkle_root": batch.merkle_root,
        "batch_hash": batch.current_batch_hash,
        "prev_batch_hash": batch.prev_batch_hash,
        "record_count": len(batch.ledger_records),
        "event_count": len(batch.events),
        "sealed_at": sealed_at,
    }


def _payload_for(ledger: AuditLedger, leaf_index: int) -> dict:
    """Builds a proof payload for one reading of the ledger's first batch."""
    batch = ledger.sealed_batches[0]
    meta = _batch_meta(batch)
    reading = batch.records[leaf_index]
    leaf_hash = hash_telemetry_record(reading)
    proof = get_merkle_proof(batch.leaf_hashes, leaf_index)
    root = recompute_root_from_proof(leaf_hash, proof)
    chain = check_onchain_root(meta, root, anchor_client=None)
    return build_proof_payload(
        batch_meta=meta,
        leaf_index=leaf_index,
        reading=reading,
        leaf_hash=leaf_hash,
        proof_path=proof,
        recomputed_root=root,
        chain_check=chain,
        generated_by="auditor",
        generated_by_role="Auditor",
    )


# ── 1. A valid proof passes ───────────────────────────────────────────────────

def test_valid_proof_passes():
    ledger = _sealed_ledger(6)
    batch = ledger.sealed_batches[0]

    for idx in range(len(batch.ledger_records)):
        leaf = batch.leaf_hashes[idx]
        proof = get_merkle_proof(batch.leaf_hashes, idx)
        assert verify_merkle_proof(leaf, proof, batch.merkle_root), (
            f"Leaf {idx} failed to prove against the sealed root"
        )


def test_valid_proof_payload_reports_proof_valid():
    payload = _payload_for(_sealed_ledger(6), leaf_index=2)
    assert payload["result"] == "PROOF VALID"
    assert payload["merkle_root"]["match"] is True

    outcome = verify_proof_payload(payload, anchor_client=None)
    assert outcome["valid"] is True


# ── 2. Changing one value makes the proof fail ────────────────────────────────

def test_changing_one_value_fails_the_proof():
    ledger = _sealed_ledger(6)
    batch = ledger.sealed_batches[0]
    idx = 3

    proof = get_merkle_proof(batch.leaf_hashes, idx)
    assert verify_merkle_proof(batch.leaf_hashes[idx], proof, batch.merkle_root)

    # An adversary edits a single sensor value after sealing.
    ledger.simulate_tamper(0, idx, "torque_nm", 999.99)

    tampered_leaf = hash_telemetry_record(batch.records[idx])
    assert tampered_leaf != batch.leaf_hashes[idx]
    assert not verify_merkle_proof(tampered_leaf, proof, batch.merkle_root)


def test_tampered_reading_yields_proof_failed_payload():
    ledger = _sealed_ledger(6)
    ledger.simulate_tamper(0, 1, "rotational_speed_rpm", 9999)

    payload = _payload_for(ledger, leaf_index=1)
    assert payload["result"] == "PROOF FAILED"

    # A file built around a tampered reading is internally self-consistent, so
    # it is the binding to the sealed batch hash that must expose it -- and it
    # must do so with no database and no chain access.
    outcome = verify_proof_payload(payload, anchor_client=None)
    assert outcome["valid"] is False
    failed = [c["name"] for c in outcome["checks"] if c["passed"] is False]
    assert "Root reproduces the sealed batch hash" in failed
    assert "Root matches the sealed root in the file" in failed


def test_sibling_reading_still_proves_after_a_tamper():
    """Tampering with one reading must not invalidate its neighbours' proofs."""
    ledger = _sealed_ledger(6)
    batch = ledger.sealed_batches[0]
    ledger.simulate_tamper(0, 1, "torque_nm", 123.456)

    untouched = 4
    leaf = hash_telemetry_record(batch.records[untouched])
    proof = get_merkle_proof(batch.leaf_hashes, untouched)
    assert verify_merkle_proof(leaf, proof, batch.merkle_root)


# ── 3. A proof file with a wrong root fails ───────────────────────────────────

def test_proof_file_with_edited_root_fails():
    payload = _payload_for(_sealed_ledger(6), leaf_index=2)
    assert verify_proof_payload(payload, anchor_client=None)["valid"] is True

    payload["merkle_root"]["recomputed_from_proof"] = sha256_digest("a different root")

    outcome = verify_proof_payload(payload, anchor_client=None)
    assert outcome["valid"] is False
    failed = [c["name"] for c in outcome["checks"] if c["passed"] is False]
    assert "Proof path reconstructs the stated root" in failed


def test_proof_file_with_edited_reading_fails():
    payload = _payload_for(_sealed_ledger(6), leaf_index=2)
    payload["reading"]["torque_nm"] = 777.0

    outcome = verify_proof_payload(payload, anchor_client=None)
    assert outcome["valid"] is False
    failed = [c["name"] for c in outcome["checks"] if c["passed"] is False]
    assert "Reading matches its leaf hash" in failed


def test_malformed_proof_file_is_rejected_cleanly():
    outcome = verify_proof_payload({"reading": {}}, anchor_client=None)
    assert outcome["valid"] is False
    assert "Malformed" in outcome["reason"]


def test_proof_file_survives_json_round_trip():
    payload = _payload_for(_sealed_ledger(5), leaf_index=0)
    reloaded = json.loads(proof_json_bytes(payload).decode("utf-8"))
    assert verify_proof_payload(reloaded, anchor_client=None)["valid"] is True


# ── 4. Odd numbers of leaves work ─────────────────────────────────────────────

@pytest.mark.parametrize("n", [1, 3, 5, 7, 9, 11, 13])
def test_odd_leaf_counts_prove_correctly(n):
    ledger = _sealed_ledger(n)
    batch = ledger.sealed_batches[0]
    assert len(batch.leaf_hashes) == n

    for idx in range(n):
        proof = get_merkle_proof(batch.leaf_hashes, idx)
        assert verify_merkle_proof(batch.leaf_hashes[idx], proof, batch.merkle_root), (
            f"n={n}: leaf {idx} failed"
        )


def test_single_leaf_batch_has_empty_proof_and_leaf_is_root():
    ledger = _sealed_ledger(1)
    batch = ledger.sealed_batches[0]
    proof = get_merkle_proof(batch.leaf_hashes, 0)
    assert proof == []
    assert batch.merkle_root == batch.leaf_hashes[0]
    assert verify_merkle_proof(batch.leaf_hashes[0], proof, batch.merkle_root)


# ── 5. Tree root is identical to compute_merkle_root() ────────────────────────

@pytest.mark.parametrize("n", list(range(1, 25)))
def test_tree_root_matches_compute_merkle_root(n):
    leaves = [sha256_digest(f"leaf-{n}-{i}") for i in range(n)]
    assert merkle_root_from_tree(build_merkle_tree(leaves)) == compute_merkle_root(leaves)


@pytest.mark.parametrize("n", list(range(1, 25)))
def test_every_leaf_proves_for_every_size(n):
    leaves = [sha256_digest(f"leaf-{n}-{i}") for i in range(n)]
    root = compute_merkle_root(leaves)
    for i in range(n):
        assert verify_merkle_proof(leaves[i], get_merkle_proof(leaves, i), root)


def test_proof_index_out_of_range_raises():
    leaves = [sha256_digest(f"x{i}") for i in range(4)]
    with pytest.raises(IndexError):
        get_merkle_proof(leaves, 4)
    with pytest.raises(IndexError):
        get_merkle_proof([], 0)


# ── 6. derive_batch_hash() stays pinned to Batch.seal() ───────────────────────

def test_derive_batch_hash_matches_seal():
    """If Batch.seal()'s header format ever drifts, every on-chain check breaks."""
    ledger = _sealed_ledger(6)
    batch = ledger.sealed_batches[0]

    derived = derive_batch_hash(
        batch_index=batch.batch_index,
        timestamp=batch.timestamp,
        prev_batch_hash=batch.prev_batch_hash,
        merkle_root=batch.merkle_root,
        record_count=len(batch.ledger_records),
        event_count=len(batch.events),
    )
    assert derived == batch.current_batch_hash


def test_derive_batch_hash_changes_with_root():
    ledger = _sealed_ledger(4)
    batch = ledger.sealed_batches[0]
    other = derive_batch_hash(
        batch_index=batch.batch_index,
        timestamp=batch.timestamp,
        prev_batch_hash=batch.prev_batch_hash,
        merkle_root=sha256_digest("wrong"),
        record_count=len(batch.ledger_records),
        event_count=len(batch.events),
    )
    assert other != batch.current_batch_hash


# ── 7. Offline chain is inconclusive, never a failure ─────────────────────────

def test_offline_chain_is_inconclusive_not_failed():
    ledger = _sealed_ledger(4)
    meta = _batch_meta(ledger.sealed_batches[0])

    result = check_onchain_root(meta, meta["merkle_root"], anchor_client=None)
    assert result["status"] == CHAIN_OFFLINE
    assert result["status"] in INCONCLUSIVE_CHAIN_STATES

    payload = _payload_for(ledger, leaf_index=0)
    assert payload["result"] == "PROOF VALID"

    outcome = verify_proof_payload(payload, anchor_client=None)
    assert outcome["valid"] is True
    chain_check = [c for c in outcome["checks"] if c["name"] == "Root confirmed on-chain"][0]
    assert chain_check["passed"] is None


class _DisabledClient:
    is_enabled = False
    network = "localhost"
    contract_address = ""


def test_disabled_anchor_client_is_inconclusive():
    ledger = _sealed_ledger(4)
    meta = _batch_meta(ledger.sealed_batches[0])
    result = check_onchain_root(meta, meta["merkle_root"], anchor_client=_DisabledClient())
    assert result["status"] in INCONCLUSIVE_CHAIN_STATES


# ── SQLite store ──────────────────────────────────────────────────────────────

def test_sqlite_keeps_sealed_root_immutable_after_tamper(tmp_path):
    db = str(tmp_path / "ledger.db")
    ledger = _sealed_ledger(6)
    assert store.sync_ledger(ledger, db) == 1

    before = store.get_batch(0, db)
    ledger.simulate_tamper(0, 2, "torque_nm", 999.99)
    store.sync_ledger(ledger, db)
    after = store.get_batch(0, db)

    assert after["merkle_root"] == before["merkle_root"]
    assert after["batch_hash"] == before["batch_hash"]
    assert after["records"] != before["records"]


def test_proof_against_sqlite_root_fails_after_tamper(tmp_path):
    db = str(tmp_path / "ledger.db")
    ledger = _sealed_ledger(6)
    store.sync_ledger(ledger, db)
    ledger.simulate_tamper(0, 2, "process_temperature_k", 999.99)

    sqlite_batch = store.get_batch(0, db)
    payload = _payload_for(ledger, leaf_index=2)

    outcome = verify_proof_payload(payload, anchor_client=None, sqlite_batch=sqlite_batch)
    assert outcome["valid"] is False


# ── Report rendering ──────────────────────────────────────────────────────────

def test_pdf_is_produced_for_valid_and_failed_proofs():
    ok = proof_pdf_bytes(_payload_for(_sealed_ledger(6), leaf_index=1))
    assert ok.startswith(b"%PDF") and len(ok) > 1000

    tampered = _sealed_ledger(6)
    tampered.simulate_tamper(0, 1, "torque_nm", 999.99)
    bad = proof_pdf_bytes(_payload_for(tampered, leaf_index=1))
    assert bad.startswith(b"%PDF") and len(bad) > 1000


def test_pdf_handles_non_ascii_machine_names():
    """fpdf2 core fonts are latin-1 only; the report must not crash on unicode."""
    ledger = AuditLedger(batch_size_limit=100)
    for i in range(3):
        ledger.record_telemetry(_make_reading(seed=float(i), machine_id="VM—Fräse—01 ✅"))
    ledger.seal_current_batch()

    pdf = proof_pdf_bytes(_payload_for(ledger, leaf_index=0))
    assert pdf.startswith(b"%PDF")
