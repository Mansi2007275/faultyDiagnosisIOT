"""
SQLite Database Storage for Verdict Engine & Audit Timeline (Step 7).
"""
import os
import json
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

DB_DIR = "data"
DEFAULT_DB_PATH = os.path.join(DB_DIR, "sentinel_verdicts.db")


def get_db_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Get SQLite database connection with row factory."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialize SQLite database tables for verdicts, changes, and machine state."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Verdicts table for every telemetry reading
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS verdicts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        machine_id TEXT NOT NULL,
        verdict TEXT NOT NULL,
        response TEXT NOT NULL,
        severity TEXT NOT NULL,
        reasons_json TEXT NOT NULL,
        inputs_json TEXT NOT NULL
    )
    """)

    # Verdict changes table for timeline audit log
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS verdict_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        machine_id TEXT NOT NULL,
        from_verdict TEXT,
        to_verdict TEXT NOT NULL,
        from_response TEXT,
        to_response TEXT NOT NULL,
        reasons_json TEXT NOT NULL
    )
    """)

    # Persistent machine hysteresis state
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS machine_state (
        machine_id TEXT PRIMARY KEY,
        current_verdict TEXT NOT NULL,
        current_response TEXT NOT NULL,
        pending_response TEXT,
        consecutive_count INTEGER NOT NULL DEFAULT 0,
        high_fault_consecutive INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def save_verdict(machine_id: str, verdict: str, response: str, severity: str,
                 reasons: List[str], inputs_used: Dict[str, Any],
                 timestamp: Optional[str] = None, db_path: str = DEFAULT_DB_PATH) -> int:
    """Save a reading verdict to SQLite database."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO verdicts (timestamp, machine_id, verdict, response, severity, reasons_json, inputs_json)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        timestamp,
        machine_id,
        verdict,
        response,
        severity,
        json.dumps(reasons),
        json.dumps(inputs_used)
    ))
    verdict_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return verdict_id


def save_verdict_change(machine_id: str, from_verdict: Optional[str], to_verdict: str,
                        from_response: Optional[str], to_response: str,
                        reasons: List[str], timestamp: Optional[str] = None,
                        db_path: str = DEFAULT_DB_PATH) -> int:
    """Save a verdict/response change to verdict_changes audit log."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO verdict_changes (timestamp, machine_id, from_verdict, to_verdict, from_response, to_response, reasons_json)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        timestamp,
        machine_id,
        from_verdict or "Initial",
        to_verdict,
        from_response or "Initial",
        to_response,
        json.dumps(reasons)
    ))
    change_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return change_id


def get_recent_verdict_changes(machine_id: Optional[str] = None, limit: int = 20,
                               db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Retrieve recent verdict changes from SQLite audit log."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    if machine_id:
        cursor.execute("""
        SELECT id, timestamp, machine_id, from_verdict, to_verdict, from_response, to_response, reasons_json
        FROM verdict_changes
        WHERE machine_id = ?
        ORDER BY id DESC
        LIMIT ?
        """, (machine_id, limit))
    else:
        cursor.execute("""
        SELECT id, timestamp, machine_id, from_verdict, to_verdict, from_response, to_response, reasons_json
        FROM verdict_changes
        ORDER BY id DESC
        LIMIT ?
        """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "timestamp": r["timestamp"],
            "machine_id": r["machine_id"],
            "from_verdict": r["from_verdict"],
            "to_verdict": r["to_verdict"],
            "from_response": r["from_response"],
            "to_response": r["to_response"],
            "reasons": json.loads(r["reasons_json"])
        })
    return result


def get_machine_state(machine_id: str, db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Retrieve persisted machine state (or default if uninitialized)."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT current_verdict, current_response, pending_response, consecutive_count, high_fault_consecutive
    FROM machine_state
    WHERE machine_id = ?
    """, (machine_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "current_verdict": row["current_verdict"],
            "current_response": row["current_response"],
            "pending_response": row["pending_response"],
            "consecutive_count": row["consecutive_count"],
            "high_fault_consecutive": row["high_fault_consecutive"]
        }
    else:
        return {
            "current_verdict": "Normal",
            "current_response": "OK",
            "pending_response": None,
            "consecutive_count": 0,
            "high_fault_consecutive": 0
        }


def set_machine_state(machine_id: str, state: Dict[str, Any],
                      db_path: str = DEFAULT_DB_PATH) -> None:
    """Save/update machine state in SQLite database."""
    init_db(db_path)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO machine_state (machine_id, current_verdict, current_response, pending_response, consecutive_count, high_fault_consecutive, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(machine_id) DO UPDATE SET
        current_verdict = excluded.current_verdict,
        current_response = excluded.current_response,
        pending_response = excluded.pending_response,
        consecutive_count = excluded.consecutive_count,
        high_fault_consecutive = excluded.high_fault_consecutive,
        updated_at = excluded.updated_at
    """, (
        machine_id,
        state["current_verdict"],
        state["current_response"],
        state["pending_response"],
        state["consecutive_count"],
        state["high_fault_consecutive"],
        timestamp
    ))

    conn.commit()
    conn.close()


# Ensure tables are initialized when module is imported
init_db()
