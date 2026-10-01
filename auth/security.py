"""
Security helper functions: password hashing with bcrypt and complexity checks.
"""
import re
import bcrypt
from typing import Tuple


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Validate password complexity:
    - Minimum 8 characters
    - At least one digit (0-9)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number."
    return True, "Password is valid."
