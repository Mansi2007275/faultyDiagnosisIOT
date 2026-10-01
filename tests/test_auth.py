"""
Unit tests for Authentication, Lockouts, Passwords, RBAC, Admin self-protection, and Audit Logging (Step 9).
"""
import pytest
import os
import tempfile
from datetime import datetime, timezone, timedelta

from auth.service import AuthService
from auth.security import verify_password, hash_password
from auth.permissions import has_permission
from auth.db import get_audit_logs


@pytest.fixture
def temp_auth_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def auth_service(temp_auth_db):
    return AuthService(db_path=temp_auth_db)


def test_correct_password_logs_in_wrong_password_fails(auth_service):
    """Test 1: Correct password succeeds, wrong password fails."""
    # Demo admin login
    success, user, msg = auth_service.login("admin", "Admin@123")
    assert success is True
    assert user["username"] == "admin"
    assert user["role"] == "Admin"

    # Wrong password
    success, user, msg = auth_service.login("admin", "WrongPass123")
    assert success is False
    assert user is None
    assert msg == "Invalid username or password"


def test_password_is_stored_hashed_not_plain_text(auth_service):
    """Test 2: Password stored hashed using bcrypt, not plain text."""
    users = auth_service.get_all_users()
    admin_user = next(u for u in users if u["username"] == "admin")

    # DB user query does not return plain text 'Admin@123'
    conn = auth_service._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE username = 'admin'")
    pwd_hash = cursor.fetchone()["password_hash"]
    conn.close()

    assert pwd_hash != "Admin@123"
    assert pwd_hash.startswith("$2b$") or pwd_hash.startswith("$2a$")
    assert verify_password("Admin@123", pwd_hash) is True


def test_five_wrong_attempts_lock_account(auth_service):
    """Test 3: 5 wrong attempts lock the account; correct password refused while locked."""
    # 4 wrong attempts
    for i in range(4):
        ok, user, msg = auth_service.login("engineer", "WrongPass")
        assert ok is False
        assert "Invalid username or password" in msg

    # 5th wrong attempt triggers lockout
    ok, user, msg = auth_service.login("engineer", "WrongPass")
    assert ok is False
    assert "locked" in msg.lower()

    # Subsequent correct password is STILL refused while locked
    ok, user, msg = auth_service.login("engineer", "Engineer@123")
    assert ok is False
    assert "locked" in msg.lower()


def test_lock_expires_after_15_minutes(auth_service):
    """Test 4: Lock expires after 15 minutes (simulate time)."""
    now = datetime.now(timezone.utc)

    # Fail 5 times to trigger lockout
    for _ in range(5):
        auth_service.login("safety", "WrongPass", current_time=now)

    # Refused at now + 5 minutes
    five_min_later = now + timedelta(minutes=5)
    ok, user, msg = auth_service.login("safety", "Safety@123", current_time=five_min_later)
    assert ok is False

    # Allowed after 16 minutes (lock expired)
    sixteen_min_later = now + timedelta(minutes=16)
    ok, user, msg = auth_service.login("safety", "Safety@123", current_time=sixteen_min_later)
    assert ok is True
    assert user["username"] == "safety"


def test_operator_permissions_restricted():
    """Test 5: Operator cannot access Attack Lab, Users page, or Reset demo data."""
    role = "Operator"
    assert has_permission(role, "Project, Dataset") is True
    assert has_permission(role, "Plant overview, Live") is True
    assert has_permission(role, "Attack Lab") is False
    assert has_permission(role, "Users page") is False
    assert has_permission(role, "Reset demo data") is False


def test_auditor_permissions_restricted():
    """Test 6: Auditor can view Audit log but cannot retrain or reset demo data."""
    role = "Auditor"
    assert has_permission(role, "Audit log page") is True
    assert has_permission(role, "Models (view)") is True
    assert has_permission(role, "Retrain models") is False
    assert has_permission(role, "Reset demo data") is False


def test_admin_cannot_deactivate_own_account(auth_service):
    """Test 7: Admin cannot deactivate their own account or demote self."""
    ok, msg = auth_service.deactivate_user(admin_username="admin", target_username="admin")
    assert ok is False
    assert "cannot deactivate their own account" in msg

    ok, msg = auth_service.update_user_role(admin_username="admin", target_username="admin", new_role="Operator")
    assert ok is False
    assert "cannot change or demote" in msg


def test_login_success_and_failure_written_to_audit_log(auth_service, temp_auth_db):
    """Test 8: Every login success and failure is written to audit_log."""
    # Successful login
    auth_service.login("operator", "Operator@123")

    # Failed login
    auth_service.login("operator", "BadPassword")

    logs = get_audit_logs(db_path=temp_auth_db)

    actions = [l["action"] for l in logs]
    assert "login success" in actions
    assert "login failure" in actions
