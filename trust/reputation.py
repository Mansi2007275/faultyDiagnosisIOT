"""
Device Reputation Engine, Honeypot Detector, Flood Detector, and Security Score Breakdown (Step 8).
"""
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

DB_DIR = "data"
DEFAULT_DB_PATH = os.path.join(DB_DIR, "sentinel_verdicts.db")
HONEYPOT_TOPIC = "sentineltwin/plant1/admin/config"

PENALTIES = {
    "replay": 25,
    "tampered signature": 30,
    "physics broken": 35,
    "flood": 20,
    "stuck/silent sensor": 10,
    "honeypot": 100,  # Honeypot sets score to 0
}

CLEAN_READINGS_RECOVERY_INTERVAL = 20  # +1 point every 20 clean readings
NORMAL_MSG_RATE = 60  # msgs per minute
FLOOD_THRESHOLD = 180  # > 3x normal rate per minute


def get_db_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_reputation_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialize SQLite database tables for device reputation and security events."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS device_reputation (
        machine_id TEXT PRIMARY KEY,
        score INTEGER NOT NULL DEFAULT 100,
        state TEXT NOT NULL DEFAULT 'Trusted',
        clean_count INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reputation_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        machine_id TEXT NOT NULL,
        old_score INTEGER NOT NULL,
        new_score INTEGER NOT NULL,
        old_state TEXT NOT NULL,
        new_state TEXT NOT NULL,
        reason TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS security_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        machine_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        reason TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


class ReputationEngine:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        init_reputation_db(self.db_path)

        # In-memory rate tracker: machine_id -> list of timestamps
        self._message_timestamps: Dict[str, List[datetime]] = {}

    def _determine_state(self, score: int, current_state: str) -> str:
        """Calculate state based on score (unless Revoked)."""
        if current_state == "Revoked":
            return "Revoked"
        if score >= 80:
            return "Trusted"
        elif score >= 50:
            return "Watched"
        else:
            return "Quarantined"

    def get_reputation(self, machine_id: str) -> Dict[str, Any]:
        """Get machine reputation record (initialize if not exists)."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT score, state, clean_count, updated_at FROM device_reputation WHERE machine_id = ?", (machine_id,))
        row = cursor.fetchone()

        if not row:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            cursor.execute("""
            INSERT INTO device_reputation (machine_id, score, state, clean_count, updated_at)
            VALUES (?, 100, 'Trusted', 0, ?)
            """, (machine_id, now_str))
            conn.commit()
            conn.close()
            return {"machine_id": machine_id, "score": 100, "state": "Trusted", "clean_count": 0, "updated_at": now_str}

        conn.close()
        return {
            "machine_id": machine_id,
            "score": row["score"],
            "state": row["state"],
            "clean_count": row["clean_count"],
            "updated_at": row["updated_at"]
        }

    def record_security_event(self, machine_id: str, event_type: str, severity: str = "HIGH", reason: str = "", current_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Log a security event and apply score penalty."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        now_str = current_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        rep = self.get_reputation(machine_id)
        old_score = rep["score"]
        old_state = rep["state"]

        # If device is revoked, state stays revoked
        if old_state == "Revoked":
            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO security_events (timestamp, machine_id, event_type, severity, reason)
            VALUES (?, ?, ?, ?, ?)
            """, (now_str, machine_id, event_type, severity, reason or f"Event on Revoked device: {event_type}"))
            conn.commit()
            conn.close()
            return rep

        # Calculate score drop
        if event_type == "honeypot":
            new_score = 0
        else:
            penalty = PENALTIES.get(event_type.lower(), 20)
            new_score = max(0, old_score - penalty)

        new_state = self._determine_state(new_score, old_state)

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()

        # Update reputation
        cursor.execute("""
        UPDATE device_reputation
        SET score = ?, state = ?, clean_count = 0, updated_at = ?
        WHERE machine_id = ?
        """, (new_score, new_state, now_str, machine_id))

        # Log history
        cursor.execute("""
        INSERT INTO reputation_history (timestamp, machine_id, old_score, new_score, old_state, new_state, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (now_str, machine_id, old_score, new_score, old_state, new_state, reason or f"Penalty for {event_type}"))

        # Log event
        cursor.execute("""
        INSERT INTO security_events (timestamp, machine_id, event_type, severity, reason)
        VALUES (?, ?, ?, ?, ?)
        """, (now_str, machine_id, event_type, severity, reason or f"Security event: {event_type}"))

        conn.commit()
        conn.close()

        return {"machine_id": machine_id, "score": new_score, "state": new_state, "clean_count": 0, "updated_at": now_str}

    def record_clean_reading(self, machine_id: str, current_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Record a clean reading. If non-quarantined/non-revoked, increment clean_count and recover +1 per 20 readings."""
        rep = self.get_reputation(machine_id)
        if rep["state"] in ("Quarantined", "Revoked"):
            # Quarantined and Revoked devices DO NOT auto-recover
            return rep

        if current_time is None:
            current_time = datetime.now(timezone.utc)
        now_str = current_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        new_count = rep["clean_count"] + 1
        new_score = rep["score"]
        old_score = rep["score"]
        old_state = rep["state"]

        if new_count >= CLEAN_READINGS_RECOVERY_INTERVAL:
            new_count = 0
            new_score = min(100, new_score + 1)

        new_state = self._determine_state(new_score, old_state)

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE device_reputation
        SET score = ?, state = ?, clean_count = ?, updated_at = ?
        WHERE machine_id = ?
        """, (new_score, new_state, new_count, now_str, machine_id))

        if new_score != old_score or new_state != old_state:
            cursor.execute("""
            INSERT INTO reputation_history (timestamp, machine_id, old_score, new_score, old_state, new_state, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (now_str, machine_id, old_score, new_score, old_state, new_state, "Clean readings recovery"))

        conn.commit()
        conn.close()

        return {"machine_id": machine_id, "score": new_score, "state": new_state, "clean_count": new_count, "updated_at": now_str}

    def check_flood(self, machine_id: str, current_time: Optional[datetime] = None) -> Tuple[bool, int]:
        """
        Track messages per minute.
        Returns (is_flood, current_msg_rate_per_min).
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        if machine_id not in self._message_timestamps:
            self._message_timestamps[machine_id] = []

        # Keep timestamps within last 60 seconds
        cutoff = current_time - timedelta(seconds=60)
        self._message_timestamps[machine_id] = [
            t for t in self._message_timestamps[machine_id] if t > cutoff
        ]
        self._message_timestamps[machine_id].append(current_time)

        rate = len(self._message_timestamps[machine_id])
        if rate > FLOOD_THRESHOLD:
            # Record security event
            self.record_security_event(machine_id, "flood", severity="HIGH", reason=f"Message rate {rate} exceeds threshold {FLOOD_THRESHOLD}/min", current_time=current_time)
            return True, rate
        return False, rate

    def trigger_honeypot(self, machine_id: str, current_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Trigger honeypot alert for a machine: instant Quarantined with score 0."""
        return self.record_security_event(machine_id, "honeypot", severity="HIGH", reason="Published to fake admin topic sentineltwin/plant1/admin/config", current_time=current_time)

    def release_quarantine(self, machine_id: str, admin_username: str = "admin", current_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Admin releases a Quarantined machine to Watched state."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        now_str = current_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        rep = self.get_reputation(machine_id)
        old_score = rep["score"]
        old_state = rep["state"]

        new_score = max(50, old_score)
        new_state = "Watched"

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE device_reputation
        SET score = ?, state = ?, clean_count = 0, updated_at = ?
        WHERE machine_id = ?
        """, (new_score, new_state, now_str, machine_id))

        cursor.execute("""
        INSERT INTO reputation_history (timestamp, machine_id, old_score, new_score, old_state, new_state, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (now_str, machine_id, old_score, new_score, old_state, new_state, f"Released from Quarantine by Admin ({admin_username})"))

        cursor.execute("""
        INSERT INTO security_events (timestamp, machine_id, event_type, severity, reason)
        VALUES (?, ?, 'admin action', 'INFO', ?)
        """, (now_str, machine_id, f"Admin {admin_username} released device from Quarantine to Watched"))

        conn.commit()
        conn.close()

        return {"machine_id": machine_id, "score": new_score, "state": new_state, "clean_count": 0, "updated_at": now_str}

    def revoke_device(self, machine_id: str, admin_username: str = "admin", current_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Admin revokes a device completely."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        now_str = current_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        rep = self.get_reputation(machine_id)
        old_score = rep["score"]
        old_state = rep["state"]

        new_score = 0
        new_state = "Revoked"

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE device_reputation
        SET score = ?, state = ?, clean_count = 0, updated_at = ?
        WHERE machine_id = ?
        """, (new_score, new_state, now_str, machine_id))

        cursor.execute("""
        INSERT INTO reputation_history (timestamp, machine_id, old_score, new_score, old_state, new_state, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (now_str, machine_id, old_score, new_score, old_state, new_state, f"Revoked by Admin ({admin_username})"))

        cursor.execute("""
        INSERT INTO security_events (timestamp, machine_id, event_type, severity, reason)
        VALUES (?, ?, 'admin action', 'HIGH', ?)
        """, (now_str, machine_id, f"Admin {admin_username} revoked device"))

        conn.commit()
        conn.close()

        return {"machine_id": machine_id, "score": new_score, "state": new_state, "clean_count": 0, "updated_at": now_str}

    def restore_device(self, machine_id: str, admin_username: str = "admin", current_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Admin restores a Revoked device back to Watched state."""
        if current_time is None:
            current_time = datetime.now(timezone.utc)
        now_str = current_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        rep = self.get_reputation(machine_id)
        old_score = rep["score"]
        old_state = rep["state"]

        new_score = 50
        new_state = "Watched"

        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE device_reputation
        SET score = ?, state = ?, clean_count = 0, updated_at = ?
        WHERE machine_id = ?
        """, (new_score, new_state, now_str, machine_id))

        cursor.execute("""
        INSERT INTO reputation_history (timestamp, machine_id, old_score, new_score, old_state, new_state, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (now_str, machine_id, old_score, new_score, old_state, new_state, f"Restored from Revoked by Admin ({admin_username})"))

        cursor.execute("""
        INSERT INTO security_events (timestamp, machine_id, event_type, severity, reason)
        VALUES (?, ?, 'admin action', 'INFO', ?)
        """, (now_str, machine_id, f"Admin {admin_username} restored device to Watched"))

        conn.commit()
        conn.close()

        return {"machine_id": machine_id, "score": new_score, "state": new_state, "clean_count": 0, "updated_at": now_str}

    def calculate_security_score(self, machine_id: str, is_signed_valid: bool = True, current_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Calculate device Security Score (0–100) with detailed component breakdown:
        - Signed & verified: +20
        - Device registered & not revoked: +20
        - Reputation state: Trusted (+20), Watched (+10), Quarantined/Revoked (0)
        - Traffic rate normal in last 10 min: +20
        - No security events in last 1 hour: +20
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        rep = self.get_reputation(machine_id)
        state = rep["state"]

        # Component 1: Signed & verified
        comp_signed = 20 if is_signed_valid else 0

        # Component 2: Registered & not revoked
        comp_reg = 20 if state != "Revoked" else 0

        # Component 3: Reputation state
        if state == "Trusted":
            comp_state = 20
        elif state == "Watched":
            comp_state = 10
        else:
            comp_state = 0

        # Component 4: Traffic rate normal in last 10 min
        rate = len(self._message_timestamps.get(machine_id, []))
        comp_traffic = 20 if rate <= FLOOD_THRESHOLD else 0

        # Component 5: No security events in last 1 hour
        one_hour_ago = (current_time - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
        SELECT COUNT(*) as cnt FROM security_events
        WHERE machine_id = ? AND timestamp >= ? AND event_type != 'admin action'
        """, (machine_id, one_hour_ago))
        event_cnt = cursor.fetchone()["cnt"]
        conn.close()

        comp_events = 20 if event_cnt == 0 else 0

        total_score = comp_signed + comp_reg + comp_state + comp_traffic + comp_events

        return {
            "total_score": total_score,
            "components": {
                "Signed & Verified": (comp_signed, 20),
                "Registered & Active": (comp_reg, 20),
                "Reputation State": (comp_state, 20),
                "Traffic Rate Normal": (comp_traffic, 20),
                "Zero Events (Last Hour)": (comp_events, 20)
            },
            "state": state,
            "reputation_score": rep["score"]
        }

    def get_all_reputations(self) -> List[Dict[str, Any]]:
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT machine_id, score, state, clean_count, updated_at FROM device_reputation ORDER BY machine_id ASC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_recent_security_events(self, limit: int = 30) -> List[Dict[str, Any]]:
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, timestamp, machine_id, event_type, severity, reason
        FROM security_events
        ORDER BY id DESC LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_reputation_history(self, machine_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, timestamp, machine_id, old_score, new_score, old_state, new_state, reason
        FROM reputation_history
        WHERE machine_id = ?
        ORDER BY id ASC LIMIT ?
        """, (machine_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]
