"""
Role-Based Access Control (RBAC) configuration dictionary and permission checkers.
Supported roles: Operator, Engineer, Safety Officer, Admin, Auditor.
"""
from typing import Dict, List, Set

ROLES = ["Operator", "Engineer", "Safety Officer", "Admin", "Auditor"]

PERMISSIONS: Dict[str, Set[str]] = {
    "Project, Dataset": {"Operator", "Engineer", "Safety Officer", "Admin", "Auditor"},
    "Plant overview, Live": {"Operator", "Engineer", "Safety Officer", "Admin", "Auditor"},
    "Attack Lab": {"Engineer", "Admin"},
    "Models (view)": {"Engineer", "Admin", "Auditor"},
    "Retrain models": {"Engineer", "Admin"},
    "Ledger / Blockchain audit": {"Engineer", "Safety Officer", "Admin", "Auditor"},
    # Merkle Proof Explorer: everyone with ledger access except Operator may
    # inspect proofs and download Audit Proof Reports.
    "Merkle proof: view/download": {"Admin", "Engineer", "Safety Officer", "Auditor"},
    # Uploading a third-party proof file for independent verification is an
    # audit function, restricted to Auditor and Admin.
    "Merkle proof: upload": {"Auditor", "Admin"},
    "Maintenance: request job": {"Engineer", "Admin"},
    "Maintenance: sign": {"Engineer", "Safety Officer"},
    "Database page": {"Engineer", "Admin", "Auditor"},
    "Reset demo data": {"Admin"},
    "Users page": {"Admin"},
    "Audit log page": {"Safety Officer", "Admin", "Auditor"},
    "Security Center": {"Engineer", "Safety Officer", "Admin", "Auditor"},
    "Security Center: admin actions": {"Admin"},
}

# Navigation mapping from menu items to permission keys
PAGE_PERMISSION_MAP = {
    "📊 Project Overview": "Project, Dataset",
    "📁 Dataset Analytics": "Project, Dataset",
    "⚡ Live Digital Twin Monitor": "Plant overview, Live",
    "🛡️ Trust & Security Engine": "Plant overview, Live",  # Main view open to all; Attack Lab component checked separately
    "🩺 Predictive Health & Faults": "Plant overview, Live",
    "🤖 AI Anomaly Models": "Models (view)",
    "🔩 Bearing Vibration (CWRU)": "Project, Dataset",
    "⛓️ Tamper-Evident Ledger": "Ledger / Blockchain audit",
    "🔒 Security Center": "Security Center",
    "👥 User Management": "Users page",
    "📋 Audit Log": "Audit log page"
}


def has_permission(role: str, action_or_page: str) -> bool:
    """Check if a given role has permission for an action or page."""
    perm_key = PAGE_PERMISSION_MAP.get(action_or_page, action_or_page)
    allowed_roles = PERMISSIONS.get(perm_key, set())
    return role in allowed_roles


def get_allowed_pages(role: str) -> List[str]:
    """Return list of navigation page titles visible to the given role."""
    allowed = []
    for page_title, perm_key in PAGE_PERMISSION_MAP.items():
        if role in PERMISSIONS.get(perm_key, set()):
            allowed.append(page_title)
    return allowed
