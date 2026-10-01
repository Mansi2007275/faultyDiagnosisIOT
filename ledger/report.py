"""
ledger/report.py
────────────────
Audit Proof Report generation and standalone proof-file verification.

What a proof file contains
──────────────────────────
Everything an external auditor needs to re-derive the result without access to
this application: the reading itself, its leaf hash, the sibling path, the
Merkle root that path reconstructs, and the batch header fields required to
re-derive the on-chain commitment.

On-chain verification is derivation-only
────────────────────────────────────────
The AuditAnchor contract stores the batch *header* hash, not the Merkle root.
The header string committed at seal time is::

    "{index}|{timestamp:.3f}|{prev_batch_hash}|{merkle_root}|{n_records}|{n_events}"

so the root is already bound into the anchored hash.  To check a root against
the chain we rebuild that header string using the *recomputed* root and compare
its SHA-256 with the hash stored on-chain.  A single anchoring transaction per
batch therefore proves the root, with no second transaction needed.

Inconclusive is not failure
───────────────────────────
If the chain is unreachable or the batch was never anchored, the on-chain check
reports CHAIN_OFFLINE / NOT_ANCHORED.  Those states never turn a cryptographically
sound proof into a failure — they are reported as "not proven on-chain".
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ledger.hasher import canonical_record, hash_telemetry_record, sha256_digest
from ledger.proof import recompute_root_from_proof

__all__ = [
    "PROOF_FORMAT_VERSION",
    "PLAIN_ENGLISH_SUMMARY",
    "derive_batch_hash",
    "check_onchain_root",
    "build_proof_payload",
    "verify_proof_payload",
    "proof_json_bytes",
    "proof_pdf_bytes",
]

PROOF_FORMAT_VERSION = "1.0"

PLAIN_ENGLISH_SUMMARY = (
    "Each reading gets a fingerprint (hash). Fingerprints are combined in pairs "
    "until one final fingerprint remains: the Merkle root. Only the root is "
    "stored on the blockchain. To prove one reading, we only need its small "
    "proof path."
)

# On-chain check outcomes
CHAIN_VERIFIED = "VERIFIED_ONCHAIN"
CHAIN_MISMATCH = "MISMATCH_ONCHAIN"
CHAIN_NOT_ANCHORED = "NOT_ANCHORED"
CHAIN_OFFLINE = "CHAIN_OFFLINE"

# Outcomes that mean "we could not check", as opposed to "the check failed".
INCONCLUSIVE_CHAIN_STATES = {CHAIN_NOT_ANCHORED, CHAIN_OFFLINE}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def derive_batch_hash(
    batch_index: int,
    timestamp: float,
    prev_batch_hash: str,
    merkle_root: str,
    record_count: int,
    event_count: int,
) -> str:
    """
    Re-derives a batch header hash from its component fields.

    This mirrors ``Batch.seal()`` exactly; any drift between the two would make
    every on-chain check fail, so the test-suite pins them together.
    """
    header = (
        f"{batch_index}|{timestamp:.3f}|{prev_batch_hash}|"
        f"{merkle_root}|{record_count}|{event_count}"
    )
    return sha256_digest(header)


def check_onchain_root(
    batch_meta: Dict[str, Any],
    candidate_root: str,
    anchor_client: Any = None,
    stored_anchor: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Checks ``candidate_root`` against the commitment anchored on-chain.

    Parameters
    ----------
    batch_meta
        Persisted batch row: batch_index, timestamp, prev_batch_hash,
        record_count, event_count.
    candidate_root
        The root recomputed from the reading and its proof path.
    anchor_client
        An ``AnchorClient``; may be None or disabled.
    stored_anchor
        Anchor metadata previously saved by ``ledger.store.save_anchor``, used
        to enrich the report with tx hash / block number / explorer link.

    Returns
    -------
    dict
        Always contains ``status`` (one of the CHAIN_* constants) and
        ``detail``.  Never raises.
    """
    derived = derive_batch_hash(
        batch_index=batch_meta["batch_index"],
        timestamp=batch_meta["timestamp"],
        prev_batch_hash=batch_meta["prev_batch_hash"],
        merkle_root=candidate_root,
        record_count=batch_meta["record_count"],
        event_count=batch_meta["event_count"],
    )

    result: Dict[str, Any] = {
        "status": CHAIN_OFFLINE,
        "detail": "Blockchain unavailable - on-chain check not performed.",
        "method": "derivation",
        "derived_batch_hash": derived,
        "onchain_hash": None,
        "network": None,
        "contract_address": None,
        "tx_hash": None,
        "block_number": None,
        "record_id": None,
        "explorer_url": None,
    }

    if stored_anchor:
        result.update({
            "network":          stored_anchor.get("network"),
            "contract_address": stored_anchor.get("contract_address"),
            "tx_hash":          stored_anchor.get("tx_hash"),
            "block_number":     stored_anchor.get("block_number"),
            "record_id":        stored_anchor.get("record_id"),
        })

    if anchor_client is None or not getattr(anchor_client, "is_enabled", False):
        return result

    result["network"] = anchor_client.network
    result["contract_address"] = anchor_client.contract_address

    try:
        record = anchor_client.find_batch_anchor(batch_meta["batch_index"])
    except Exception as exc:  # pragma: no cover - defensive
        result["detail"] = f"On-chain lookup failed: {exc}"
        return result

    if record is None:
        result["status"] = CHAIN_NOT_ANCHORED
        result["detail"] = (
            f"Batch #{batch_meta['batch_index']} has not been anchored on-chain yet."
        )
        return result

    onchain_hash = str(record["hash"]).lower().removeprefix("0x")
    result["onchain_hash"] = onchain_hash
    result["record_id"] = record.get("record_id")

    if result["tx_hash"]:
        result["explorer_url"] = anchor_client.explorer_tx_url(result["tx_hash"])

    if onchain_hash == derived.lower():
        result["status"] = CHAIN_VERIFIED
        result["detail"] = (
            "The recomputed Merkle root reproduces the batch hash stored on-chain."
        )
    else:
        result["status"] = CHAIN_MISMATCH
        result["detail"] = (
            "The recomputed Merkle root does NOT reproduce the batch hash "
            "stored on-chain."
        )

    return result


def build_proof_payload(
    batch_meta: Dict[str, Any],
    leaf_index: int,
    reading: Dict[str, Any],
    leaf_hash: str,
    proof_path: List[Dict[str, str]],
    recomputed_root: str,
    chain_check: Dict[str, Any],
    generated_by: str = "unknown",
    generated_by_role: str = "unknown",
) -> Dict[str, Any]:
    """
    Assembles the canonical proof payload shared by the JSON file and the PDF.

    ``result`` is PROOF VALID only when the proof path reconstructs the root
    sealed in SQLite *and* the on-chain check did not actively contradict it.
    """
    sqlite_root = batch_meta["merkle_root"]
    root_matches_sqlite = recomputed_root == sqlite_root
    chain_status = chain_check.get("status")
    chain_contradicts = chain_status == CHAIN_MISMATCH

    valid = root_matches_sqlite and not chain_contradicts

    return {
        "format_version": PROOF_FORMAT_VERSION,
        "report_id": f"STP-{uuid.uuid4().hex[:12].upper()}",
        "generated_at": _utc_now(),
        "generated_by": {"username": generated_by, "role": generated_by_role},
        "machine_id": reading.get("machine_id", "unknown"),
        "reading": canonical_record(reading),
        "leaf_index": leaf_index,
        "leaf_hash": leaf_hash,
        "proof_path": proof_path,
        "merkle_root": {
            "recomputed_from_proof": recomputed_root,
            "stored_in_sqlite": sqlite_root,
            "match": root_matches_sqlite,
        },
        "batch": {
            "batch_index": batch_meta["batch_index"],
            "timestamp": batch_meta["timestamp"],
            "prev_batch_hash": batch_meta["prev_batch_hash"],
            "batch_hash": batch_meta["batch_hash"],
            "record_count": batch_meta["record_count"],
            "event_count": batch_meta["event_count"],
            "sealed_at": batch_meta.get("sealed_at"),
        },
        "chain": chain_check,
        "result": "PROOF VALID" if valid else "PROOF FAILED",
        "explanation": PLAIN_ENGLISH_SUMMARY,
    }


def verify_proof_payload(
    payload: Dict[str, Any],
    anchor_client: Any = None,
    sqlite_batch: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Independently verifies an uploaded proof file.

    Nothing in ``payload`` is trusted: the leaf hash is recomputed from the
    reading, the root is recomputed from the proof path, and both are compared
    against the values the file claims.  A file whose stated root has been
    edited therefore fails even though its internal path is consistent.

    Returns a dict with ``valid`` (bool), ``reason`` (str) and ``checks``
    (ordered list of {name, passed, detail}).
    """
    checks: List[Dict[str, Any]] = []

    def add(name: str, passed: Optional[bool], detail: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    # ── Structure ─────────────────────────────────────────────────────────
    required = ["reading", "leaf_hash", "proof_path", "merkle_root", "batch"]
    missing = [k for k in required if k not in payload]
    if missing:
        add("File structure", False, f"Missing field(s): {', '.join(missing)}")
        return {
            "valid": False,
            "reason": f"Malformed proof file - missing: {', '.join(missing)}",
            "checks": checks,
        }
    add("File structure", True, "All required fields present.")

    reading = payload["reading"]
    claimed_leaf = payload["leaf_hash"]
    proof_path = payload["proof_path"]
    claimed_root = payload["merkle_root"].get("recomputed_from_proof")

    # ── 1. Leaf hash must match the reading ───────────────────────────────
    actual_leaf = hash_telemetry_record(reading)
    leaf_ok = actual_leaf == claimed_leaf
    add(
        "Reading matches its leaf hash",
        leaf_ok,
        "Recomputed leaf hash equals the one in the file."
        if leaf_ok
        else f"Reading hashes to {actual_leaf[:16]}... but the file claims "
             f"{str(claimed_leaf)[:16]}... - the reading was altered.",
    )

    # ── 2. Proof path must reconstruct the claimed root ───────────────────
    actual_root = recompute_root_from_proof(actual_leaf, proof_path)
    root_ok = actual_root == claimed_root
    add(
        "Proof path reconstructs the stated root",
        root_ok,
        "The sibling path carries the leaf up to the stated Merkle root."
        if root_ok
        else f"Path produces {actual_root[:16]}... but the file states "
             f"{str(claimed_root)[:16]}... - the root in this file is wrong.",
    )

    # ── 3. Root must reproduce the sealed batch header hash ───────────────
    # This is the check that makes an uploaded file self-policing. The batch
    # header hash committed at seal time binds the Merkle root to the batch, so
    # a file built around an altered reading reconstructs a root that cannot
    # reproduce it -- detectable with no database and no network access.
    claimed_batch_hash = payload["batch"].get("batch_hash")
    if claimed_batch_hash:
        derived_header = derive_batch_hash(
            batch_index=payload["batch"]["batch_index"],
            timestamp=payload["batch"]["timestamp"],
            prev_batch_hash=payload["batch"]["prev_batch_hash"],
            merkle_root=actual_root,
            record_count=payload["batch"]["record_count"],
            event_count=payload["batch"]["event_count"],
        )
        header_ok = derived_header == claimed_batch_hash
        add(
            "Root reproduces the sealed batch hash",
            header_ok,
            "The root rebuilds the batch hash that was sealed for this batch."
            if header_ok
            else "The root does NOT rebuild the sealed batch hash - this reading "
                 "is not the one that was originally committed.",
        )
    else:
        add(
            "Root reproduces the sealed batch hash",
            None,
            "File does not carry a batch hash - offline binding check skipped.",
        )

    # ── 4. Root must match the sealed root recorded in the file ───────────
    stated_sealed_root = payload["merkle_root"].get("stored_in_sqlite")
    if stated_sealed_root:
        sealed_ok = stated_sealed_root == actual_root
        add(
            "Root matches the sealed root in the file",
            sealed_ok,
            "The reconstructed root equals the sealed root recorded in the file."
            if sealed_ok
            else "The reconstructed root differs from the sealed root recorded "
                 "in the file itself.",
        )

    # ── 5. Root must match the sealed root in SQLite (when available) ─────
    if sqlite_batch is not None:
        db_ok = sqlite_batch["merkle_root"] == claimed_root
        add(
            "Root matches the sealed root in SQLite",
            db_ok,
            "The stated root equals the root sealed in the local database."
            if db_ok
            else "The stated root differs from the root sealed in the local database.",
        )
    else:
        db_ok = None
        add(
            "Root matches the sealed root in SQLite",
            None,
            "Batch not present in this database - local comparison skipped.",
        )

    # ── 6. On-chain derivation check ──────────────────────────────────────
    batch_meta = {
        "batch_index":     payload["batch"]["batch_index"],
        "timestamp":       payload["batch"]["timestamp"],
        "prev_batch_hash": payload["batch"]["prev_batch_hash"],
        "record_count":    payload["batch"]["record_count"],
        "event_count":     payload["batch"]["event_count"],
    }
    chain = check_onchain_root(batch_meta, actual_root, anchor_client=anchor_client)
    chain_status = chain["status"]
    if chain_status == CHAIN_VERIFIED:
        chain_ok: Optional[bool] = True
    elif chain_status == CHAIN_MISMATCH:
        chain_ok = False
    else:
        chain_ok = None
    add("Root confirmed on-chain", chain_ok, chain["detail"])

    # ── Verdict ───────────────────────────────────────────────────────────
    hard_failures = [c for c in checks if c["passed"] is False]
    valid = not hard_failures

    if valid:
        reason = (
            "The reading, its leaf hash and its proof path are internally "
            "consistent and reproduce the sealed Merkle root."
        )
        if chain_ok is None:
            reason += " The on-chain confirmation was not available."
    else:
        reason = hard_failures[0]["detail"]

    return {"valid": valid, "reason": reason, "checks": checks, "chain": chain}


def proof_json_bytes(payload: Dict[str, Any]) -> bytes:
    """Serialises a proof payload as a downloadable UTF-8 JSON file."""
    return json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")


# ── PDF ───────────────────────────────────────────────────────────────────────

# fpdf2's built-in fonts are latin-1 only, so a stray em-dash or check mark
# raises at render time.  Everything written into the PDF goes through _ascii().
_ASCII_MAP = {
    "—": "-", "–": "-", "…": "...", "‘": "'",
    "’": "'", "“": '"', "”": '"', "→": "->",
    "✓": "OK", "✅": "OK", "❌": "X", "·": "-",
}


def _ascii(value: Any) -> str:
    """Renders any value as PDF-safe ASCII."""
    text = str(value)
    for bad, good in _ASCII_MAP.items():
        text = text.replace(bad, good)
    return text.encode("ascii", "replace").decode("ascii")


def proof_pdf_bytes(payload: Dict[str, Any]) -> bytes:
    """
    Renders the Audit Proof Report as a PDF using fpdf2.

    Raises ImportError with an actionable message if fpdf2 is not installed.
    """
    try:
        from fpdf import FPDF
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "fpdf2 is required for PDF reports. Install it with: pip install fpdf2"
        ) from exc

    valid = payload.get("result") == "PROOF VALID"
    chain = payload.get("chain", {}) or {}

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ── Title ─────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 17)
    pdf.cell(0, 10, _ascii("SentinelTwin Audit Proof Report"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(
        0, 5,
        _ascii(f"Report ID {payload.get('report_id')}  |  Generated {payload.get('generated_at')}"),
        new_x="LMARGIN", new_y="NEXT",
    )
    user = payload.get("generated_by", {}) or {}
    pdf.cell(
        0, 5,
        _ascii(f"Generated by {user.get('username', 'unknown')} ({user.get('role', 'unknown')})"),
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # ── Result banner ─────────────────────────────────────────────────────
    if valid:
        pdf.set_fill_color(214, 245, 225)
        pdf.set_text_color(14, 100, 55)
        banner = "PROOF VALID: this reading is exactly as recorded"
    else:
        pdf.set_fill_color(250, 218, 218)
        pdf.set_text_color(140, 25, 25)
        banner = "PROOF FAILED: this reading was changed"
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 11, _ascii(banner), border=0, align="C", fill=True,
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # ── Section helpers ───────────────────────────────────────────────────
    def section(title: str) -> None:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_fill_color(235, 238, 242)
        pdf.cell(0, 7, _ascii(title), fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    def row(label: str, value: Any) -> None:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(46, 5.5, _ascii(label), new_x="RIGHT", new_y="TOP")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5.5, _ascii(value), new_x="LMARGIN", new_y="NEXT")

    def mono(label: str, value: Any) -> None:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(46, 5.5, _ascii(label), new_x="RIGHT", new_y="TOP")
        pdf.set_font("Courier", "", 8)
        pdf.multi_cell(0, 5.5, _ascii(value), new_x="LMARGIN", new_y="NEXT")

    # ── Reading ───────────────────────────────────────────────────────────
    section("1. Reading under proof")
    row("Machine", payload.get("machine_id"))
    row("Position in batch", f"leaf index {payload.get('leaf_index')}")
    for key, val in sorted((payload.get("reading") or {}).items()):
        row(f"  {key}", val)
    pdf.ln(2)

    # ── Hashes ────────────────────────────────────────────────────────────
    section("2. Cryptographic commitment")
    mono("Leaf hash", payload.get("leaf_hash"))
    roots = payload.get("merkle_root", {}) or {}
    mono("Recomputed root", roots.get("recomputed_from_proof"))
    mono("Root in SQLite", roots.get("stored_in_sqlite"))
    row("Roots match", "YES" if roots.get("match") else "NO")
    pdf.ln(2)

    # ── Proof path ────────────────────────────────────────────────────────
    section("3. Merkle proof path")
    path = payload.get("proof_path") or []
    if not path:
        row("Path", "Empty - this batch contains a single leaf, which is itself the root.")
    for i, step in enumerate(path):
        mono(f"Step {i + 1} ({step.get('position')})", step.get("sibling"))
    pdf.ln(2)

    # ── Batch + chain ─────────────────────────────────────────────────────
    section("4. Batch and blockchain anchor")
    batch = payload.get("batch", {}) or {}
    row("Batch number", batch.get("batch_index"))
    row("Records / events", f"{batch.get('record_count')} / {batch.get('event_count')}")
    mono("Batch header hash", batch.get("batch_hash"))
    row("Network", chain.get("network") or "not connected")
    row("Contract address", chain.get("contract_address") or "n/a")
    row("Transaction hash", chain.get("tx_hash") or "not anchored")
    row("Block number", chain.get("block_number") if chain.get("block_number") is not None else "n/a")
    row("Explorer link", chain.get("explorer_url") or "Local chain (no public explorer)")
    row("On-chain status", chain.get("status"))
    row("On-chain detail", chain.get("detail"))
    pdf.ln(2)

    # ── Plain English ─────────────────────────────────────────────────────
    section("5. What this means")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, _ascii(payload.get("explanation", PLAIN_ENGLISH_SUMMARY)),
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    closing = (
        "Because the proof path rebuilds the same Merkle root that was sealed for "
        "this batch, the reading above is byte-for-byte the one originally recorded."
        if valid else
        "The proof path does not rebuild the sealed Merkle root for this batch, so "
        "the reading above is not the one originally recorded."
    )
    pdf.multi_cell(0, 5, _ascii(closing), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
