"""
SQLite Database interface for Users and Audit Logs (Step 9).
"""
import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from auth.security import hash_password

DB_DIR = "data"
AUTH_DB_PATH = os.path.join(DB_DIR, "sentinel_auth.db")


def get_auth_db_connection(db_path: str = AUTH_DB_PATH) -> sqlite3.Connection:
    """Get SQLite database connection with Row factory."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db(db_path: str = AUTH_DB_PATH) -> None:
    """Initialize users and audit_log tables, and seed demo users if empty."""
    conn = get_auth_db_connection(db_path)
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL,
        role TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        wallet_address TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        failed_logins INTEGER NOT NULL DEFAULT 0,
        locked_until TEXT,
        created_at TEXT NOT NULL,
        last_login TEXT
    )
    """)

    # Audit log table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT NOT NULL,
        username TEXT NOT NULL,
        role TEXT NOT NULL,
        action TEXT NOT NULL,
        target TEXT NOT NULL,
        result TEXT NOT NULL,
        details TEXT NOT NULL
    )
    """)

    conn.commit()

    # Check if users table is empty; if so, seed demo users
    cursor.execute("SELECT COUNT(*) as count FROM users")
    count = cursor.fetchone()["count"]

    if count == 0:
        demo_users = [
            ("admin", "Admin User", "Admin", "Admin@123"),
            ("engineer", "Lead Engineer", "Engineer", "Engineer@123"),
            ("safety", "Safety Officer", "Safety Officer", "Safety@123"),
            ("operator", "Plant Operator", "Operator", "Operator@123"),
            ("auditor", "External Auditor", "Auditor", "Auditor@123"),
        ]
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        for username, display_name, role, plain_pwd in demo_users:
            hashed = hash_password(plain_pwd)
            cursor.execute("""
            INSERT INTO users (username, display_name, role, password_hash, wallet_address, is_active, failed_logins, locked_until, created_at)
            VALUES (?, ?, ?, ?, ?, 1, 0, NULL, ?)
            """, (username, display_name, role, hashed, None, now_str))

        conn.commit()

    conn.close()


def log_audit_event(username: str, role: str, action: str, target: str, result: str, details: str, db_path: str = AUTH_DB_PATH) -> int:
    """Record an entry in audit_log."""
    init_auth_db(db_path)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = get_auth_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO audit_log (time, username, role, action, target, result, details)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (now_str, username, role, action, target, result, details))
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id


def get_audit_logs(user_filter: Optional[str] = None, action_filter: Optional[str] = None,
                   date_filter: Optional[str] = None, limit: int = 100, db_path: str = AUTH_DB_PATH) -> List[Dict[str, Any]]:
    """Fetch audit logs with optional filters."""
    init_auth_db(db_path)
    conn = get_auth_db_connection(db_path)
    cursor = conn.cursor()

    query = "SELECT id, time, username, role, action, target, result, details FROM audit_log WHERE 1=1"
    params = []

    if user_filter and user_filter.strip():
        query += " AND username LIKE ?"
        params.append(f"%{user_filter.strip()}%")

    if action_filter and action_filter.strip():
        query += " AND action LIKE ?"
        params.append(f"%{action_filter.strip()}%")

    if date_filter and date_filter.strip():
        query += " AND time LIKE ?"
        params.append(f"{date_filter.strip()}%")

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(r) for r in rows]
