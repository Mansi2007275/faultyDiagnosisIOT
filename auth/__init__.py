"""
Auth package for SentinelTwin.
Provides user management, password hashing, RBAC permissions, and audit logging.
"""

from auth.security import hash_password, verify_password, validate_password_strength
from auth.permissions import PERMISSIONS, has_permission, get_allowed_pages
from auth.service import AuthService, get_auth_service

__all__ = [
    "hash_password",
    "verify_password",
    "validate_password_strength",
    "PERMISSIONS",
    "has_permission",
    "get_allowed_pages",
    "AuthService",
    "get_auth_service"
]
