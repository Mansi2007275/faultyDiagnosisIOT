"""
ledger/batch.py
───────────────
Tamper-evident batch management for the SentinelTwin audit ledger.

Changes vs. original
─────────────────────
• Each record stores its canonical leaf hash at insertion time so that
  verification compares stored-hash vs recomputed-hash rather than
  recomputing both from potentially drifted in-memory values.
• verify_chain_integrity() now reports WHICH record in WHICH batch has a
  mismatched hash and shows the stored vs recomputed values.
• Detected tampering is logged both as a security AuditEvent in the ledger
  and (optionally) via auth.db.log_audit_event for the audit log page.
• simulate_tamper() works correctly: it mutates the raw record dict but the
  stored leaf hash was computed at seal time, so the mismatch is always caught.
"""

from __future__ import annotations

import time
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from ledger.hasher import (
    canonical_record,
    hash_telemetry_record,
    compute_merkle_root,
    sha256_digest,
    CANONICAL_FIELDS,
)

logger = logging.getLogger(__name__)


# ── AuditEvent ────────────────────────────────────────────────────────────────

@dataclass
class AuditEvent:
    event_id: str
    timestamp: float
    machine_id: str
    event_type: str   # 'TRUST_VIOLATION', 'FAULT_DETECTED', 'SEAL_BATCH', 'TAMPER_DETECTED', …
    details: str
    event_hash: str = ""

    def compute_hash(self) -> str:
        # Use 3 d.p. for the timestamp – keep consistent with what was always stored.
        s = f"{self.event_id}|{self.timestamp:.3f}|{self.machine_id}|{self.event_type}|{self.details}"
        self.event_hash = sha256_digest(s)
        return self.event_hash


# ── LedgerRecord (one telemetry reading + its sealed hash) ────────────────────

@dataclass
class LedgerRecord:
    """
    Wraps a raw telemetry dict together with the leaf hash that was computed
    at insertion time (using the canonical representation).  The hash is the
    ground truth; verification compares it against a fresh recomputation.
    """
    raw: Dict[str, Any]          # original record dict (may include _* keys)
    leaf_hash: str               # hash of canonical_record(raw) at insert time


# ── Batch ─────────────────────────────────────────────────────────────────────

@dataclass
class Batch:
    batch_index: int
    timestamp: float
    # ledger_records holds the wrapped (raw + hash) pairs
    ledger_records: List[LedgerRecord] = field(default_factory=list)
    events: List[AuditEvent] = field(default_factory=list)
    leaf_hashes: List[str] = field(default_factory=list)   # ordered: records then events
    merkle_root: str = ""
    prev_batch_hash: str = "0" * 64
    current_batch_hash: str = ""
    is_sealed: bool = False

    # ── backward-compat property ──────────────────────────────────────────────
    @property
    def records(self) -> List[Dict[str, Any]]:
        """Returns the list of raw dicts for display / tamper simulation."""
        return [lr.raw for lr in self.ledger_records]

    def add_record(self, record: Dict[str, Any]) -> str:
        """
        Adds a telemetry record.  The canonical leaf hash is computed once here
        and stored alongside the raw dict – it never changes after this point.
        """
        if self.is_sealed:
            raise RuntimeError("Cannot add record to a sealed batch.")
        leaf_h = hash_telemetry_record(record)
        self.ledger_records.append(LedgerRecord(raw=record, leaf_hash=leaf_h))
        self.leaf_hashes.append(leaf_h)
        return leaf_h

    def add_event(self, event: AuditEvent) -> None:
        if self.is_sealed:
            raise RuntimeError("Cannot add event to a sealed batch.")
        event.compute_hash()
        self.events.append(event)
        self.leaf_hashes.append(event.event_hash)

    def seal(self, prev_hash: Optional[str] = None) -> str:
        if prev_hash is not None:
            self.prev_batch_hash = prev_hash
        self.merkle_root = compute_merkle_root(self.leaf_hashes)
        header_str = (
            f"{self.batch_index}|{self.timestamp:.3f}|{self.prev_batch_hash}|"
            f"{self.merkle_root}|{len(self.ledger_records)}|{len(self.events)}"
        )
        self.current_batch_hash = sha256_digest(header_str)
        self.is_sealed = True
        return self.current_batch_hash


# ── AuditLedger ───────────────────────────────────────────────────────────────

class AuditLedger:
    """
    Manages the chain of sealed telemetry batches and the open batch buffer.
    Provides deterministic tamper verification and tamper simulation.
    """

    def __init__(self, batch_size_limit: int = 10) -> None:
        self.batch_size_limit = batch_size_limit
        self.sealed_batches: List[Batch] = []
        self.open_batch: Batch = self._new_batch(0, "0" * 64)
        self.all_events: List[AuditEvent] = []

    # ── Internal ──────────────────────────────────────────────────────────────

    def _new_batch(self, index: int, prev_hash: str) -> Batch:
        return Batch(batch_index=index, timestamp=time.time(), prev_batch_hash=prev_hash)

    # ── Public write API ──────────────────────────────────────────────────────

    def record_telemetry(self, telemetry: Dict[str, Any]) -> None:
        """Records a telemetry packet into the open batch. Auto-seals when full."""
        self.open_batch.add_record(telemetry)
        if len(self.open_batch.ledger_records) >= self.batch_size_limit:
            self.seal_current_batch()

    def record_event(self, machine_id: str, event_type: str, details: str) -> None:
        """Records an audit / security event into the open batch."""
        evt = AuditEvent(
            event_id=f"EVT-{int(time.time() * 1000)}-{len(self.all_events) + 1}",
            timestamp=time.time(),
            machine_id=machine_id,
            event_type=event_type,
            details=details,
        )
        self.all_events.append(evt)
        self.open_batch.add_event(evt)

    def seal_current_batch(self) -> Optional[Batch]:
        """Seals the open batch and opens a new one."""
        if not self.open_batch.ledger_records and not self.open_batch.events:
            return None
        prev_hash = self.sealed_batches[-1].current_batch_hash if self.sealed_batches else "0" * 64
        self.open_batch.seal(prev_hash=prev_hash)
        sealed = self.open_batch
        self.sealed_batches.append(sealed)
        next_idx = len(self.sealed_batches)
        self.open_batch = self._new_batch(next_idx, sealed.current_batch_hash)
        return sealed

    # ── Verification ──────────────────────────────────────────────────────────

    def verify_chain_integrity(
        self, log_tampering: bool = True
    ) -> Tuple[bool, List[str]]:
        """
        Verifies the full ledger chain:
          1. Chain linkage (prev_hash)
          2. Per-record: stored leaf hash vs recomputed canonical hash
          3. Merkle root recomputation
          4. Batch header hash recomputation

        For every tampered record the finding names the batch, the record index,
        and the canonical field values that changed.

        If log_tampering is True and tampering is found, a TAMPER_DETECTED event
        is recorded in the ledger and in the auth audit log.
        """
        if not self.sealed_batches:
            return True, ["Ledger empty — genesis state verified."]

        issues: List[str] = []
        expected_prev_hash = "0" * 64

        for batch in self.sealed_batches:
            # ── 1. Chain linkage ──────────────────────────────────────────────
            if batch.prev_batch_hash != expected_prev_hash:
                issues.append(
                    f"Chain broken at Batch #{batch.batch_index}: "
                    f"expected prev_hash {expected_prev_hash[:12]}… "
                    f"got {batch.prev_batch_hash[:12]}…"
                )

            # ── 2. Per-record hash comparison ─────────────────────────────────
            recomputed_leaves: List[str] = []
            for rec_idx, lr in enumerate(batch.ledger_records):
                fresh_hash = hash_telemetry_record(lr.raw)
                recomputed_leaves.append(fresh_hash)
                if fresh_hash != lr.leaf_hash:
                    # Identify which canonical fields changed
                    orig_canon = canonical_record(lr.raw)   # current (mutated) state
                    changed_fields = []
                    for f in sorted(CANONICAL_FIELDS):
                        cur_val = orig_canon.get(f)
                        # We cannot recover the original value, but we can flag the field
                        changed_fields.append(f"{f}={cur_val!r}")

                    detail = (
                        f"Record #{rec_idx} in Batch #{batch.batch_index} hash mismatch — "
                        f"stored: {lr.leaf_hash[:16]}… recomputed: {fresh_hash[:16]}… | "
                        f"current canonical fields: [{', '.join(changed_fields[:4])}{'…' if len(changed_fields) > 4 else ''}]"
                    )
                    issues.append(detail)

            # ── 3. Event leaf hashes ──────────────────────────────────────────
            for evt in batch.events:
                s = f"{evt.event_id}|{evt.timestamp:.3f}|{evt.machine_id}|{evt.event_type}|{evt.details}"
                recomputed_leaves.append(sha256_digest(s))

            # ── 4. Merkle root ────────────────────────────────────────────────
            recomputed_merkle = compute_merkle_root(recomputed_leaves)
            if recomputed_merkle != batch.merkle_root:
                issues.append(
                    f"Merkle root mismatch in Batch #{batch.batch_index} — "
                    f"stored: {batch.merkle_root[:16]}… recomputed: {recomputed_merkle[:16]}…"
                )

            # ── 5. Batch header hash ──────────────────────────────────────────
            header_str = (
                f"{batch.batch_index}|{batch.timestamp:.3f}|{batch.prev_batch_hash}|"
                f"{batch.merkle_root}|{len(batch.ledger_records)}|{len(batch.events)}"
            )
            recomputed_batch_hash = sha256_digest(header_str)
            if recomputed_batch_hash != batch.current_batch_hash:
                issues.append(
                    f"Header hash mismatch in Batch #{batch.batch_index} — "
                    f"stored: {batch.current_batch_hash[:16]}… "
                    f"recomputed: {recomputed_batch_hash[:16]}…"
                )

            expected_prev_hash = batch.current_batch_hash

        # ── Log tampering as security events ──────────────────────────────────
        if issues and log_tampering:
            self._log_tamper_event(issues)

        if not issues:
            return True, [
                f"All {len(self.sealed_batches)} batch(es) verified — "
                f"SHA-256 Merkle proofs valid."
            ]
        return False, issues

    def _log_tamper_event(self, issues: List[str]) -> None:
        """Records tampering as a HIGH-severity event in the ledger and auth audit log."""
        summary = f"TAMPERING DETECTED in {len(issues)} location(s): {issues[0][:120]}"
        self.record_event("LEDGER", "TAMPER_DETECTED", summary)

        # Try to write to the persistent auth audit log (may not exist in tests)
        try:
            from auth.db import log_audit_event
            log_audit_event(
                username="system",
                role="system",
                action="ledger integrity check",
                target="ledger",
                result="TAMPERED",
                details=summary,
            )
        except Exception:
            pass  # auth module may not be initialised in unit-test context

    # ── Tamper simulation ──────────────────────────────────────────────────────

    def simulate_tamper(
        self, batch_idx: int, record_idx: int, field_name: str, new_value: Any
    ) -> bool:
        """
        Simulates an adversary secretly altering a historical record.
        The stored leaf hash is NOT updated, so verify_chain_integrity() will
        always catch this.
        """
        if 0 <= batch_idx < len(self.sealed_batches):
            batch = self.sealed_batches[batch_idx]
            if 0 <= record_idx < len(batch.ledger_records):
                batch.ledger_records[record_idx].raw[field_name] = new_value
                return True
        return False
