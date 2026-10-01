import time
import streamlit as st

# 1. Page Configuration
st.set_page_config(
    page_title="SentinelTwin | Industrial Digital Twin",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Imports from Modular Architecture
from simulator.data_loader import DataLoader
from simulator.virtual_machine import MachineFleet
from simulator.attacks import AttackEngine
from trust.engine import TrustEngine
from trust.reputation import ReputationEngine
from health.diagnostics import DiagnosticsEngine
from ledger.batch import AuditLedger
from ledger.chain import AnchorClient
from auth.service import get_auth_service
from auth.permissions import get_allowed_pages, has_permission
from dashboard.components import inject_custom_css
from dashboard.pages import (
    render_overview_page,
    render_dataset_page,
    render_live_monitor_page,
    render_trust_security_page,
    render_health_diagnostics_page,
    render_models_page,
    render_audit_ledger_page,
    render_bearing_analysis_page,
    render_security_center_page,
    render_users_page,
    render_audit_log_page
)

# 3. Inject Glassmorphism Design System CSS
inject_custom_css()

# 4. Initialize Global Session State Singletons
def init_session_state():
    if "auth_service" not in st.session_state:
        st.session_state.auth_service = get_auth_service()

    if "reputation_engine" not in st.session_state:
        st.session_state.reputation_engine = ReputationEngine()

    if "data_loader" not in st.session_state:
        st.session_state.data_loader = DataLoader()

    if "fleet" not in st.session_state:
        st.session_state.fleet = MachineFleet(dataset_df=st.session_state.data_loader.df)

    if "attack_engine" not in st.session_state:
        st.session_state.attack_engine = AttackEngine()

    if "trust_engine" not in st.session_state:
        st.session_state.trust_engine = TrustEngine(rep_engine=st.session_state.reputation_engine)

    if "diag_engine" not in st.session_state:
        st.session_state.diag_engine = DiagnosticsEngine()

    if "ledger" not in st.session_state:
        st.session_state.ledger = AuditLedger(batch_size_limit=10)

    if "anchor_client" not in st.session_state:
        st.session_state.anchor_client = AnchorClient()

    if "telemetry_history" not in st.session_state:
        st.session_state.telemetry_history = {}

    if "authenticated_user" not in st.session_state:
        st.session_state.authenticated_user = None

    if "last_activity_time" not in st.session_state:
        st.session_state.last_activity_time = time.time()

init_session_state()

# 5. Session Timeout Check (30 minutes inactivity)
if st.session_state.authenticated_user is not None:
    now = time.time()
    if now - st.session_state.last_activity_time > 1800:  # 30 mins = 1800 sec
        user = st.session_state.authenticated_user
        st.session_state.auth_service.logout(user["username"], user["role"])
        st.session_state.authenticated_user = None
        st.session_state.login_error = "Session timed out after 30 minutes of inactivity. Please log in again."
        st.rerun()
    else:
        st.session_state.last_activity_time = now

# 6. Login Screen Gatekeeper
if st.session_state.authenticated_user is None:
    st.markdown("""
    <div style="max-width: 450px; margin: 40px auto; padding: 2.5rem; background: rgba(15, 23, 42, 0.85); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 16px; backdrop-filter: blur(16px); box-shadow: 0 20px 40px rgba(0,0,0,0.5);">
        <div style="text-align: center; margin-bottom: 1.5rem;">
            <div style="font-size: 3rem; margin-bottom: 0.5rem;">⚙️</div>
            <h2 style="margin: 0; font-size: 1.8rem; font-weight: 700; color: #F8FAFC;">SentinelTwin</h2>
            <div style="font-size: 0.85rem; color: #38BDF8; font-family: monospace; margin-top: 0.25rem;">ZERO-TRUST INDUSTRIAL DIGITAL TWIN</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_l, col_m, col_r = st.columns([1, 1.2, 1])
    with col_m:
        st.subheader("🔐 Platform Sign-In")
        if "login_error" in st.session_state and st.session_state.login_error:
            st.error(st.session_state.login_error)

        with st.form("login_form"):
            username = st.text_input("Username").strip()
            password = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("Sign In", type="primary", use_container_width=True)

            if submit_login:
                if not username or not password:
                    st.error("Please enter both username and password.")
                else:
                    success, user, msg = st.session_state.auth_service.login(username, password)
                    if success:
                        st.session_state.authenticated_user = user
                        st.session_state.last_activity_time = time.time()
                        st.session_state.login_error = None
                        st.success(f"Welcome back, {user['display_name']}!")
                        st.rerun()
                    else:
                        st.session_state.login_error = msg
                        st.error(msg)

        with st.expander("💡 Demo Accounts & Credentials"):
            st.markdown("""
            - **Admin:** `admin` / `Admin@123`
            - **Engineer:** `engineer` / `Engineer@123`
            - **Safety Officer:** `safety` / `Safety@123`
            - **Operator:** `operator` / `Operator@123`
            - **Auditor:** `auditor` / `Auditor@123`
            """)

    st.stop()  # Stop execution here if not logged in!

# 7. Logged-in Session Profile & Sidebar Setup
user = st.session_state.authenticated_user
user_role = user["role"]
user_name = user["username"]

# Brand header
st.sidebar.markdown("""
<div class="nav-brand-card">
    <div style="font-size: 1.8rem; margin-bottom: 0.2rem;">⚙️</div>
    <h2 class="nav-brand-title">SentinelTwin</h2>
    <div style="font-size: 0.78rem; color: #94A3B8; margin-top: 0.15rem;">Zero-Trust Industrial Twin</div>
    <div class="nav-brand-tag"><span class="pulse-dot"></span>Active Telemetry</div>
</div>
""", unsafe_allow_html=True)

# User Profile Card in Sidebar
role_colors = {
    "Admin": "#EF4444",
    "Engineer": "#38BDF8",
    "Safety Officer": "#F59E0B",
    "Operator": "#10B981",
    "Auditor": "#A855F7"
}
r_color = role_colors.get(user_role, "#38BDF8")

st.sidebar.markdown(f"""
<div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 0.75rem 1rem; margin-bottom: 1rem;">
    <div style="font-size: 0.72rem; color: #64748B; font-weight: 700; text-transform: uppercase;">LOGGED IN USER</div>
    <div style="font-size: 0.95rem; font-weight: 700; color: #F8FAFC; margin-top: 0.2rem;">{user['display_name']}</div>
    <div style="display: inline-block; background: {r_color}22; border: 1px solid {r_color}; color: {r_color}; border-radius: 4px; padding: 0.15rem 0.5rem; font-size: 0.72rem; font-weight: 700; margin-top: 0.35rem;">
        {user_role}
    </div>
</div>
""", unsafe_allow_html=True)

# Sidebar Change Password Expander
with st.sidebar.expander("🔑 Change My Password"):
    with st.form("sidebar_change_pwd_form"):
        old_pwd = st.text_input("Current Password", type="password")
        new_pwd = st.text_input("New Password (min 8 chars, 1 digit)", type="password")
        sub_chg = st.form_submit_button("Update Password")
        if sub_chg:
            if not old_pwd or not new_pwd:
                st.error("Please fill in both password fields.")
            else:
                ok, chg_msg = st.session_state.auth_service.change_password(user_name, old_pwd, new_pwd)
                if ok:
                    st.success(chg_msg)
                else:
                    st.error(chg_msg)

# Logout Button
if st.sidebar.button("🚪 Log Out", use_container_width=True):
    st.session_state.auth_service.logout(user_name, user_role)
    st.session_state.authenticated_user = None
    st.rerun()

st.sidebar.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

# Filter navigation menu according to role permissions
allowed_pages = get_allowed_pages(user_role)

nav_selection = st.sidebar.radio(
    "Navigation Menu",
    allowed_pages,
    index=0
)

st.sidebar.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

# Dataset Status indicator pill
stats = st.session_state.data_loader.get_summary_statistics()
if not stats["is_real"]:
    st.sidebar.warning("⚠️ Real dataset not found (`data/ai4i2020.csv`).")
else:
    st.sidebar.markdown(f"""
    <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; padding: 0.5rem 0.75rem; font-size: 0.76rem; color: #34D399;">
        <strong>Dataset:</strong> AI4I 2020 ({stats['total_rows']:,} rows)
    </div>
    """, unsafe_allow_html=True)

st.sidebar.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

# Connected Fleet Cards
st.sidebar.markdown("<div style='font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; color: #64748B; font-weight: 700; margin-bottom: 0.4rem;'>Connected Fleet</div>", unsafe_allow_html=True)
for vm in st.session_state.fleet.get_all_machines():
    rep = st.session_state.reputation_engine.get_reputation(vm.machine_id)
    rep_st = rep["state"]
    st_color = "#34D399" if rep_st == "Trusted" else ("#F59E0B" if rep_st == "Watched" else "#EF4444")
    st.sidebar.markdown(f"""
    <div class="sidebar-mach-card">
        <div>
            <div class="sidebar-mach-id">{vm.machine_id}</div>
            <div class="sidebar-mach-name">{vm.name}</div>
        </div>
        <div style="font-size: 0.7rem; color: {st_color}; font-weight: 600;">● {rep_st}</div>
    </div>
    """, unsafe_allow_html=True)

# Sidebar Footer
st.sidebar.markdown("""
<div class="sidebar-footer-card">
    <div style="font-size: 0.72rem; color: #64748B; font-weight: 600;">PLATFORM SPECIFICATION</div>
    <div style="font-size: 0.75rem; color: #94A3B8; margin-top: 0.15rem;">Zero-Trust Architecture v2.0</div>
    <div style="font-size: 0.7rem; color: #38BDF8; font-family: monospace; margin-top: 0.2rem;">SHA-256 • AI4I 2020</div>
</div>
""", unsafe_allow_html=True)

# 8. Page Routing with Direct Access Guard
if nav_selection == "📊 Project Overview":
    render_overview_page(
        data_loader=st.session_state.data_loader,
        fleet=st.session_state.fleet,
        ledger=st.session_state.ledger,
        trust_engine=st.session_state.trust_engine,
        diag_engine=st.session_state.diag_engine,
        rep_engine=st.session_state.reputation_engine
    )

elif nav_selection == "📁 Dataset Analytics":
    render_dataset_page(data_loader=st.session_state.data_loader)

elif nav_selection == "⚡ Live Digital Twin Monitor":
    render_live_monitor_page(
        fleet=st.session_state.fleet,
        attack_engine=st.session_state.attack_engine,
        trust_engine=st.session_state.trust_engine,
        diag_engine=st.session_state.diag_engine,
        ledger=st.session_state.ledger,
        session_state=st.session_state
    )

elif nav_selection == "🛡️ Trust & Security Engine":
    render_trust_security_page(
        fleet=st.session_state.fleet,
        attack_engine=st.session_state.attack_engine,
        trust_engine=st.session_state.trust_engine,
        ledger=st.session_state.ledger,
        session_state=st.session_state
    )

elif nav_selection == "🩺 Predictive Health & Faults":
    render_health_diagnostics_page(
        fleet=st.session_state.fleet,
        diag_engine=st.session_state.diag_engine,
        ledger=st.session_state.ledger,
        session_state=st.session_state
    )

elif nav_selection == "🤖 AI Anomaly Models":
    render_models_page()

elif nav_selection == "🔩 Bearing Vibration (CWRU)":
    render_bearing_analysis_page()

elif nav_selection == "⛓️ Tamper-Evident Ledger":
    render_audit_ledger_page(
        ledger=st.session_state.ledger,
        session_state=st.session_state,
        anchor_client=st.session_state.anchor_client
    )

elif nav_selection == "🔒 Security Center":
    render_security_center_page(
        rep_engine=st.session_state.reputation_engine,
        session_state=st.session_state
    )

elif nav_selection == "👥 User Management":
    render_users_page()

elif nav_selection == "📋 Audit Log":
    render_audit_log_page()
