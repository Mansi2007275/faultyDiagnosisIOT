"""
Audit Log Page (Step 9).
Provides filterable audit logs for security, authentication, model retrains, tamper tests, and maintenance actions.
"""
import streamlit as st
import pandas as pd

from auth.db import get_audit_logs
from auth.permissions import has_permission


def render_audit_log_page():
    user = st.session_state.get("authenticated_user")
    user_role = user.get("role", "Operator") if user else "Operator"

    # Permission Guard
    if not has_permission(user_role, "Audit log page"):
        st.error("🔒 You do not have access to this page.")
        return

    st.markdown("""
    <div style="margin-bottom: 1.2rem;">
        <h1 style="margin: 0; font-size: 2.0rem; font-weight: 700; color: #F8FAFC;">
            📋 System Audit Log & Compliance Traceability
        </h1>
        <p style="margin: 0.2rem 0 0 0; color: #94A3B8; font-size: 0.95rem;">
            Immutable audit record of login attempts, user updates, attack injections, model retraining, and maintenance signatures.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Filter controls
    c1, c2, c3 = st.columns(3)
    with c1:
        user_filter = st.text_input("Filter by Username:", placeholder="e.g. admin, operator")
    with c2:
        action_filter = st.text_input("Filter by Action:", placeholder="e.g. login, attack, retrain")
    with c3:
        date_filter = st.text_input("Filter by Date (YYYY-MM-DD):", placeholder="e.g. 2026-10-01")

    logs = get_audit_logs(
        user_filter=user_filter,
        action_filter=action_filter,
        date_filter=date_filter,
        limit=200
    )

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    if logs:
        df_logs = pd.DataFrame(logs)
        st.dataframe(df_logs[['time', 'username', 'role', 'action', 'target', 'result', 'details']], use_container_width=True)
    else:
        st.info("No audit log records match the selected filters.")
