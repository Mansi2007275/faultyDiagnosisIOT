"""
Authentication and User Management Service (Step 9).
Handles login, lockout after 5 failures, password change, user CRUD, and audit logging.
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
import sqlite3

from auth.security import hash_password, verify_password, validate_password_strength
from auth.db import get_auth_db_connection, init_auth_db, log_audit_event, AUTH_DB_PATH
from auth.permissions import ROLES


class AuthService:
    def __init__(self, db_path: str = AUTH_DB_PATH):
        self.db_path = db_path
        init_auth_db(self.db_path)

    def _get_conn(self) -> sqlite3.Connection:
        return get_auth_db_connection(self.db_path)

    def login(self, username: str, password: str, current_time: Optional[datetime] = None) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Authenticate a user.
        - Check active status
        - Check lockout status (15 min lock after 5 failed attempts)
        - Verify bcrypt password
        - Update failed_logins, locked_until, last_login
        - Record audit log for login success, failure, or lockout
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        now_str = current_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),))
        row = cursor.fetchone()

        if not row:
            log_audit_event(
                username=username, role="Unknown", action="login failure",
                target="auth", result="FAILED", details="User does not exist",
                db_path=self.db_path
            )
            conn.close()
            return False, None, "Invalid username or password"

        user = dict(row)

        if not user["is_active"]:
            log_audit_event(
                username=user["username"], role=user["role"], action="login failure",
                target="auth", result="FAILED", details="Account is deactivated",
                db_path=self.db_path
            )
            conn.close()
            return False, None, "Invalid username or password"

        # Check if account is currently locked
        if user["locked_until"]:
            try:
                locked_until_dt = datetime.fromisoformat(user["locked_until"].replace("Z", "+00:00"))
            except ValueError:
                locked_until_dt = current_time

            if current_time < locked_until_dt:
                remaining = int((locked_until_dt - current_time).total_seconds())
                mins = remaining // 60
                secs = remaining % 60
                msg = f"Account locked due to 5 failed attempts. Please try again in {mins}m {secs}s."
                log_audit_event(
                    username=user["username"], role=user["role"], action="login failure",
                    target="auth", result="BLOCKED", details=f"Account locked until {user['locked_until']}",
                    db_path=self.db_path
                )
                conn.close()
                return False, None, msg

        # Verify password
        if verify_password(password, user["password_hash"]):
            # Reset failures & clear lock
            cursor.execute("""
            UPDATE users
            SET failed_logins = 0, locked_until = NULL, last_login = ?
            WHERE id = ?
            """, (now_str, user["id"]))
            conn.commit()

            user["failed_logins"] = 0
            user["locked_until"] = None
            user["last_login"] = now_str

            log_audit_event(
                username=user["username"], role=user["role"], action="login success",
                target="auth", result="SUCCESS", details="Successful login",
                db_path=self.db_path
            )
            conn.close()
            return True, user, "Login successful"

        else:
            # Failed attempt
            new_failed = user["failed_logins"] + 1
            locked_until_str = None

            if new_failed >= 5:
                lock_time = current_time + timedelta(minutes=15)
                locked_until_str = lock_time.strftime("%Y-%m-%dT%H:%M:%SZ")

                cursor.execute("""
                UPDATE users
                SET failed_logins = ?, locked_until = ?
                WHERE id = ?
                """, (new_failed, locked_until_str, user["id"]))
                conn.commit()

                log_audit_event(
                    username=user["username"], role=user["role"], action="lockout",
                    target="auth", result="LOCKED", details=f"Account locked for 15 minutes after {new_failed} failed attempts",
                    db_path=self.db_path
                )
                conn.close()
                return False, None, "Account locked due to 5 failed attempts. Please try again in 15 minutes."

            else:
                cursor.execute("""
                UPDATE users
                SET failed_logins = ?
                WHERE id = ?
                """, (new_failed, user["id"]))
                conn.commit()

                log_audit_event(
                    username=user["username"], role=user["role"], action="login failure",
                    target="auth", result="FAILED", details=f"Invalid password (attempt {new_failed}/5)",
                    db_path=self.db_path
                )
                conn.close()
                return False, None, "Invalid username or password"

    def logout(self, username: str, role: str) -> None:
        """Log user logout event."""
        log_audit_event(
            username=username, role=role, action="logout",
            target="auth", result="SUCCESS", details="User logged out",
            db_path=self.db_path
        )

    def change_password(self, username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
        """User self-service password change."""
        valid, msg = validate_password_strength(new_password)
        if not valid:
            return False, msg

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return False, "User not found"

        user = dict(row)
        if not verify_password(old_password, user["password_hash"]):
            conn.close()
            return False, "Current password is incorrect"

        new_hash = hash_password(new_password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (new_hash, username))
        conn.commit()
        conn.close()

        log_audit_event(
            username=username, role=user["role"], action="password change",
            target="auth", result="SUCCESS", details="User changed password",
            db_path=self.db_path
        )
        return True, "Password changed successfully"

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Retrieve all user accounts."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, display_name, role, wallet_address, is_active, failed_logins, locked_until, created_at, last_login FROM users ORDER BY id ASC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def create_user(self, admin_username: str, username: str, display_name: str, role: str, password: str, wallet_address: Optional[str] = None) -> Tuple[bool, str]:
        """Admin creates a new user account."""
        valid, msg = validate_password_strength(password)
        if not valid:
            return False, msg

        if role not in ROLES:
            return False, f"Invalid role. Must be one of {ROLES}"

        conn = self._get_conn()
        cursor = conn.cursor()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            hashed = hash_password(password)
            cursor.execute("""
            INSERT INTO users (username, display_name, role, password_hash, wallet_address, is_active, failed_logins, locked_until, created_at)
            VALUES (?, ?, ?, ?, ?, 1, 0, NULL, ?)
            """, (username.strip().lower(), display_name.strip(), role, hashed, wallet_address, now_str))
            conn.commit()
            conn.close()

            log_audit_event(
                username=admin_username, role="Admin", action="user created/changed",
                target=username, result="SUCCESS", details=f"Created user {username} with role {role}",
                db_path=self.db_path
            )
            return True, f"User '{username}' created successfully."
        except sqlite3.IntegrityError:
            conn.close()
            return False, f"Username '{username}' already exists."

    def update_user_role(self, admin_username: str, target_username: str, new_role: str) -> Tuple[bool, str]:
        """Admin updates target user's role. Admin cannot demote self."""
        if admin_username.lower() == target_username.lower():
            return False, "Admin cannot change or demote their own account role."

        if new_role not in ROLES:
            return False, f"Invalid role. Must be one of {ROLES}"

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = ? WHERE username = ?", (new_role, target_username))
        if cursor.rowcount == 0:
            conn.close()
            return False, "User not found."

        conn.commit()
        conn.close()

        log_audit_event(
            username=admin_username, role="Admin", action="user created/changed",
            target=target_username, result="SUCCESS", details=f"Updated role to {new_role}",
            db_path=self.db_path
        )
        return True, f"Role for '{target_username}' updated to {new_role}."

    def admin_reset_password(self, admin_username: str, target_username: str, new_password: str) -> Tuple[bool, str]:
        """Admin resets target user's password."""
        valid, msg = validate_password_strength(new_password)
        if not valid:
            return False, msg

        conn = self._get_conn()
        cursor = conn.cursor()
        new_hash = hash_password(new_password)
        cursor.execute("UPDATE users SET password_hash = ?, failed_logins = 0, locked_until = NULL WHERE username = ?", (new_hash, target_username))
        if cursor.rowcount == 0:
            conn.close()
            return False, "User not found."

        conn.commit()
        conn.close()

        log_audit_event(
            username=admin_username, role="Admin", action="user created/changed",
            target=target_username, result="SUCCESS", details="Admin reset user password",
            db_path=self.db_path
        )
        return True, f"Password for '{target_username}' reset successfully."

    def unlock_user(self, admin_username: str, target_username: str) -> Tuple[bool, str]:
        """Admin unlocks a locked user account."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET failed_logins = 0, locked_until = NULL WHERE username = ?", (target_username,))
        if cursor.rowcount == 0:
            conn.close()
            return False, "User not found."

        conn.commit()
        conn.close()

        log_audit_event(
            username=admin_username, role="Admin", action="user created/changed",
            target=target_username, result="SUCCESS", details="Admin unlocked user account",
            db_path=self.db_path
        )
        return True, f"User '{target_username}' account unlocked."

    def deactivate_user(self, admin_username: str, target_username: str) -> Tuple[bool, str]:
        """Admin deactivates a user account. Admin cannot deactivate self."""
        if admin_username.lower() == target_username.lower():
            return False, "Admin cannot deactivate their own account."

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = 0 WHERE username = ?", (target_username,))
        if cursor.rowcount == 0:
            conn.close()
            return False, "User not found."

        conn.commit()
        conn.close()

        log_audit_event(
            username=admin_username, role="Admin", action="user created/changed",
            target=target_username, result="SUCCESS", details="Admin deactivated user account",
            db_path=self.db_path
        )
        return True, f"User '{target_username}' deactivated."


def get_auth_service(db_path: str = AUTH_DB_PATH) -> AuthService:
    """Singleton getter for AuthService."""
    return AuthService(db_path=db_path)
