"""
ledger/store.py
───────────────
SQLite persistence for sealed ledger batches and their on-chain anchors.

Why this exists
───────────────
``AuditLedger`` lives in Streamlit session state and is therefore in-memory
only.  An audit proof needs a durable, independent copy of what was committed
at seal time, so a proof can be checked against the database of record rather
than against the process that produced it.

Append-only discipline
──────────────────────
The cryptographic columns (``merkle_root``, ``batch_hash``, ``prev_batch_hash``,
``leaf_hashes_json``) are written exactly once, when the batch is first seen,
and are never updated afterwards.  Re-syncing a batch refreshes only
``records_json`` — the mutable payload.  That is deliberate: it models an
adversary who edits database rows but cannot alter the sealed commitment, which
is precisely the condition a Merkle proof is designed to expose.

This module never imports Streamlit and is safe to use from tests and scripts.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ledger.batch import AuditLedger, Batch

DB_DIR = "data"
LEDGER_DB_PATH = os.path.join(DB_DIR, "sentinel_ledger.db")

__all__ = [
    "LEDGER_DB_PATH",
    "init_ledger_db",
    "save_batch",
    "sync_ledger",
    "get_batch",
    "list_batches",
    "save_anchor",
    "get_anchor",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect(db_path: str = LEDGER_DB_PATH) -> sqlite3.Connection:
    """Opens the ledger database, creating its directory if needed."""
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_ledger_db(db_path: str = LEDGER_DB_PATH) -> None:
    """Creates the sealed_batches and batch_anchors tables if absent."""
    conn = _connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sealed_batches (
        batch_index      INTEGER PRIMARY KEY,
        timestamp        REAL NOT NULL,
        merkle_root      TEXT NOT NULL,
        batch_hash       TEXT NOT NULL,
        prev_batch_hash  TEXT NOT NULL,
        record_count     INTEGER NOT NULL,
        event_count      INTEGER NOT NULL,
        leaf_hashes_json TEXT NOT NULL,
        records_json     TEXT NOT NULL,
        sealed_at        TEXT NOT NULL,
        updated_at       TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS batch_anchors (
        batch_index      INTEGER PRIMARY KEY,
        network          TEXT NOT NULL,
        contract_address TEXT NOT NULL,
        tx_hash          TEXT NOT NULL,
        block_number     INTEGER,
        record_id        INTEGER,
        record_type      TEXT NOT NULL,
        anchored_at      TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def save_batch(batch: "Batch", db_path: str = LEDGER_DB_PATH) -> bool:
    """
    Persists one sealed batch.

    Returns True if the batch was inserted for the first time, False if it was
    already present (in which case only ``records_json`` is refreshed — the
    sealed commitment columns are left untouched).  Unsealed batches are
    ignored.
    """
    if not batch.is_sealed:
        return False

    init_ledger_db(db_path)
    conn = _connect(db_path)
    cur = conn.cursor()

    cur.execute(
        "SELECT batch_index FROM sealed_batches WHERE batch_index = ?",
        (batch.batch_index,),
    )
    exists = cur.fetchone() is not None
    now = _utc_now()
    records_json = json.dumps(batch.records, sort_keys=True, default=str)

    if exists:
        cur.execute(
            "UPDATE sealed_batches SET records_json = ?, updated_at = ? "
            "WHERE batch_index = ?",
            (records_json, now, batch.batch_index),
        )
    else:
        cur.execute(
            """
            INSERT INTO sealed_batches (
                batch_index, timestamp, merkle_root, batch_hash, prev_batch_hash,
                record_count, event_count, leaf_hashes_json, records_json,
                sealed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch.batch_index,
                batch.timestamp,
                batch.merkle_root,
                batch.current_batch_hash,
                batch.prev_batch_hash,
                len(batch.ledger_records),
                len(batch.events),
                json.dumps(batch.leaf_hashes),
                records_json,
                now,
                now,
            ),
        )

    conn.commit()
    conn.close()
    return not exists


def sync_ledger(ledger: "AuditLedger", db_path: str = LEDGER_DB_PATH) -> int:
    """Persists every sealed batch. Returns the number newly inserted."""
    return sum(save_batch(b, db_path) for b in ledger.sealed_batches)


def get_batch(batch_index: int, db_path: str = LEDGER_DB_PATH) -> Optional[Dict[str, Any]]:
    """Returns one persisted batch as a dict, with JSON columns decoded."""
    init_ledger_db(db_path)
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM sealed_batches WHERE batch_index = ?", (batch_index,))
    row = cur.fetchone()
    conn.close()

    if row is None:
        return None

    data = dict(row)
    data["leaf_hashes"] = json.loads(data.pop("leaf_hashes_json"))
    data["records"] = json.loads(data.pop("records_json"))
    return data


def list_batches(db_path: str = LEDGER_DB_PATH) -> List[Dict[str, Any]]:
    """Returns batch summaries (no payloads), newest first."""
    init_ledger_db(db_path)
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT batch_index, timestamp, merkle_root, batch_hash, record_count, "
        "event_count, sealed_at FROM sealed_batches ORDER BY batch_index DESC"
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def save_anchor(
    batch_index: int,
    network: str,
    contract_address: str,
    tx_hash: str,
    block_number: Optional[int] = None,
    record_id: Optional[int] = None,
    record_type: str = "TELEMETRY_BATCH",
    db_path: str = LEDGER_DB_PATH,
) -> None:
    """Records (or replaces) the on-chain anchor metadata for a batch."""
    init_ledger_db(db_path)
    conn = _connect(db_path)
    conn.execute(
        """
        INSERT INTO batch_anchors (
            batch_index, network, contract_address, tx_hash, block_number,
            record_id, record_type, anchored_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(batch_index) DO UPDATE SET
            network          = excluded.network,
            contract_address = excluded.contract_address,
            tx_hash          = excluded.tx_hash,
            block_number     = excluded.block_number,
            record_id        = excluded.record_id,
            record_type      = excluded.record_type,
            anchored_at      = excluded.anchored_at
        """,
        (
            batch_index, network, contract_address, tx_hash,
            block_number, record_id, record_type, _utc_now(),
        ),
    )
    conn.commit()
    conn.close()


def get_anchor(batch_index: int, db_path: str = LEDGER_DB_PATH) -> Optional[Dict[str, Any]]:
    """Returns stored anchor metadata for a batch, or None if never anchored."""
    init_ledger_db(db_path)
    conn = _connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM batch_anchors WHERE batch_index = ?", (batch_index,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None
