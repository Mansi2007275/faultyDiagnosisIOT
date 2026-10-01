"""
Security Center Page (Step 8).
Provides fleet-wide security posture analysis, device reputation tracking, security score breakdown,
interactive event charts, and Admin-only quarantine release & revocation controls.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as gg
from datetime import datetime, timezone
from typing import Any

from trust.reputation import ReputationEngine
from auth.permissions import has_permission
from auth.db import log_audit_event


def render_security_center_page(rep_engine: ReputationEngine, session_state: Any = None):
    user = st.session_state.get("authenticated_user")
    user_role = user.get("role", "Operator") if user else "Operator"
    user_name = user.get("username", "system") if user else "system"

    # Permission check
    if not has_permission(user_role, "Security Center"):
        st.error("🔒 You do not have access to this page.")
        return

    st.markdown("""
    <div style="margin-bottom: 1.2rem;">
        <h1 style="margin: 0; font-size: 2.0rem; font-weight: 700; color: #F8FAFC;">
            🔒 Security Center & Device Reputation
        </h1>
        <p style="margin: 0.2rem 0 0 0; color: #94A3B8; font-size: 0.95rem;">
            Continuous device reputation history, honeypot alerts, message flood analytics, and security posture breakdown.
        </p>
    </div>
    """, unsafe_allow_html=True)

    reps = rep_engine.get_all_reputations()
    events = rep_engine.get_recent_security_events(limit=100)

    # 1. Top KPI Summary Cards
    total_events_today = len(events)
    honeypot_triggers = len([e for e in events if e.get("event_type") == "honeypot"])

    trusted_cnt = len([r for r in reps if r["state"] == "Trusted"])
    watched_cnt = len([r for r in reps if r["state"] == "Watched"])
    quarantined_cnt = len([r for r in reps if r["state"] == "Quarantined"])
    revoked_cnt = len([r for r in reps if r["state"] == "Revoked"])

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Total Events", total_events_today)
    with c2:
        st.metric("🟢 Trusted Devices", trusted_cnt)
    with c3:
        st.metric("🟡 Watched Devices", watched_cnt)
    with c4:
        st.metric("🔴 Quarantined", quarantined_cnt)
    with c5:
        st.metric("🍯 Honeypot Hits", honeypot_triggers)

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # 2. Fleet Machine Reputation & Security Score Table
    st.subheader("🖥️ Connected Machine Reputation & Security Posture")

    machine_rows = []
    for r in reps:
        m_id = r["machine_id"]
        sec_score_info = rep_engine.calculate_security_score(m_id)

        # Get last event
        m_events = [e for e in events if e["machine_id"] == m_id]
        last_evt = m_events[0]["event_type"] if m_events else "None"

        # Rate
        rate = len(rep_engine._message_timestamps.get(m_id, []))

        machine_rows.append({
            "Machine ID": m_id,
            "Reputation Score": r["score"],
            "Reputation State": r["state"],
            "Security Score": f"{sec_score_info['total_score']} / 100",
            "Last Event": last_evt,
            "Traffic (msgs/min)": rate
        })

    if machine_rows:
        df_rep = pd.DataFrame(machine_rows)
        st.dataframe(df_rep, use_container_width=True)

    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

    # 3. Machine Selection for Timeline & Breakdown & Admin Controls
    machine_ids = [r["machine_id"] for r in reps] if reps else ["M_001"]
    selected_machine = st.selectbox("Select Machine for Detailed Security Breakdown & Timeline:", machine_ids)

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("### 📈 Reputation Score Timeline")
        hist = rep_engine.get_reputation_history(selected_machine, limit=50)

        if hist:
            df_hist = pd.DataFrame(hist)
            fig_line = px.line(
                df_hist, x="timestamp", y="new_score",
                labels={"new_score": "Reputation Score", "timestamp": "Time"},
                title=f"Reputation History for {selected_machine}",
                markers=True
            )
            # Add state boundary lines
            fig_line.add_hline(y=80, line_dash="dash", line_color="#10B981", annotation_text="Trusted (80+)")
            fig_line.add_hline(y=50, line_dash="dash", line_color="#F59E0B", annotation_text="Watched (50+)")
            fig_line.update_layout(template="plotly_dark", yaxis=dict(range=[0, 105]))
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info(f"No reputation history recorded yet for {selected_machine}.")

    with col_right:
        st.markdown("### 📊 Security Score Breakdown")
        sec_info = rep_engine.calculate_security_score(selected_machine)
        st.markdown(f"**Total Security Score:** `{sec_info['total_score']} / 100`")

        breakdown_rows = []
        for component, (gained, max_pts) in sec_info["components"].items():
            breakdown_rows.append({
                "Component": component,
                "Score Gained": f"+{gained} pts",
                "Max Available": f"{max_pts} pts"
            })
        st.table(pd.DataFrame(breakdown_rows))

    # 4. Admin Management Controls (Release / Revoke / Restore)
    if has_permission(user_role, "Security Center: admin actions"):
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        st.markdown(f"### ⚙️ Admin Actions for {selected_machine}")

        curr_rep = rep_engine.get_reputation(selected_machine)
        curr_state = curr_rep["state"]

        c_act1, c_act2, c_act3 = st.columns(3)

        with c_act1:
            if curr_state == "Quarantined":
                if st.button(f"🔓 Release {selected_machine} to Watched", key="btn_release"):
                    res = rep_engine.release_quarantine(selected_machine, admin_username=user_name)
                    log_audit_event(user_name, "Admin", "release quarantine", selected_machine, "SUCCESS", f"Released {selected_machine} to Watched (Score 50)")
                    st.success(f"Released {selected_machine} to Watched state!")
                    st.rerun()
            else:
                st.button(f"🔓 Release {selected_machine} to Watched", disabled=True, key="btn_release_dis", help="Only available when machine is Quarantined")

        with c_act2:
            if curr_state != "Revoked":
                confirm_revoke = st.checkbox(f"Confirm Revoke {selected_machine}", key="chk_revoke")
                if st.button(f"🚫 Revoke {selected_machine}", key="btn_revoke", disabled=not confirm_revoke):
                    res = rep_engine.revoke_device(selected_machine, admin_username=user_name)
                    log_audit_event(user_name, "Admin", "revoke device", selected_machine, "SUCCESS", f"Revoked device {selected_machine}")
                    st.error(f"Device {selected_machine} REVOKED.")
                    st.rerun()
            else:
                st.button(f"🚫 Revoke {selected_machine}", disabled=True, key="btn_revoke_dis")

        with c_act3:
            if curr_state == "Revoked":
                confirm_restore = st.checkbox(f"Confirm Restore {selected_machine}", key="chk_restore")
                if st.button(f"🔄 Restore {selected_machine}", key="btn_restore", disabled=not confirm_restore):
                    res = rep_engine.restore_device(selected_machine, admin_username=user_name)
                    log_audit_event(user_name, "Admin", "restore device", selected_machine, "SUCCESS", f"Restored device {selected_machine} to Watched")
                    st.success(f"Device {selected_machine} restored to Watched state.")
                    st.rerun()
            else:
                st.button(f"🔄 Restore {selected_machine}", disabled=True, key="btn_restore_dis", help="Only available when device is Revoked")

    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

    # 5. Events by Type Bar Chart & Recent Events Log Table
    st.subheader("📊 Security Events by Event Type")
    if events:
        df_events = pd.DataFrame(events)
        fig_bar = px.histogram(
            df_events, x="event_type", color="machine_id",
            barmode="group", title="Security Events Breakdown by Type & Machine",
            labels={"event_type": "Event Type", "count": "Event Count"}
        )
        fig_bar.update_layout(template="plotly_dark")
        st.plotly_chart(fig_bar, use_container_width=True)

        st.subheader("📋 Last 30 Security Events Stream")
        st.dataframe(df_events[['timestamp', 'machine_id', 'event_type', 'severity', 'reason']].head(30), use_container_width=True)
    else:
        st.info("No security events recorded yet.")
