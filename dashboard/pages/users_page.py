"""
Admin Users Management Page (Step 9).
Allows Admin to inspect accounts, add users, modify roles, reset passwords, unlock, and deactivate users.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from typing import Any

from auth.service import get_auth_service
from auth.permissions import has_permission, ROLES


def render_users_page():
    user = st.session_state.get("authenticated_user")
    user_role = user.get("role", "Operator") if user else "Operator"
    user_name = user.get("username", "admin") if user else "admin"

    # Permission Guard
    if not has_permission(user_role, "Users page"):
        st.error("🔒 You do not have access to this page.")
        return

    auth_service = get_auth_service()

    st.markdown("""
    <div style="margin-bottom: 1.2rem;">
        <h1 style="margin: 0; font-size: 2.0rem; font-weight: 700; color: #F8FAFC;">
            👥 User Management & Access Control
        </h1>
        <p style="margin: 0.2rem 0 0 0; color: #94A3B8; font-size: 0.95rem;">
            Admin administration portal for platform accounts, RBAC roles, password resets, and account unlocking.
        </p>
    </div>
    """, unsafe_allow_html=True)

    users = auth_service.get_all_users()

    # 1. User Table
    st.subheader("📋 Registered Users Overview")
    display_data = []
    for u in users:
        is_locked = bool(u["locked_until"])
        display_data.append({
            "Username": u["username"],
            "Display Name": u["display_name"],
            "Role": u["role"],
            "Status": "Active" if u["is_active"] else "Inactive (Deactivated)",
            "Locked": f"🔒 Locked until {u['locked_until']}" if is_locked else "🟢 Unlocked",
            "Failed Logins": u["failed_logins"],
            "Last Login": u["last_login"] or "Never",
            "Created At": u["created_at"]
        })

    st.dataframe(pd.DataFrame(display_data), use_container_width=True)
    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # 2. Add New User Section
    with st.expander("➕ Add New User", expanded=False):
        with st.form("add_user_form"):
            new_user = st.text_input("Username").strip().lower()
            new_disp = st.text_input("Display Name")
            new_role = st.selectbox("Role", ROLES, index=0)
            new_pwd = st.text_input("Password (min 8 chars, at least 1 number)", type="password")
            new_wallet = st.text_input("Wallet Address (Optional)").strip()

            submit_add = st.form_submit_button("Create User")
            if submit_add:
                if not new_user or not new_disp or not new_pwd:
                    st.error("Please fill in all required fields.")
                else:
                    success, msg = auth_service.create_user(
                        admin_username=user_name,
                        username=new_user,
                        display_name=new_disp,
                        role=new_role,
                        password=new_pwd,
                        wallet_address=new_wallet if new_wallet else None
                    )
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    # 3. Manage Existing Users Controls
    st.subheader("⚙️ Account Management Actions")
    user_list = [u["username"] for u in users]
    selected_target = st.selectbox("Select Target User:", user_list)

    target_user_dict = next((u for u in users if u["username"] == selected_target), None)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("##### 🔄 Change Role")
        current_role = target_user_dict["role"] if target_user_dict else "Operator"
        role_idx = ROLES.index(current_role) if current_role in ROLES else 0
        updated_role = st.selectbox("New Role", ROLES, index=role_idx, key="sel_new_role")

        if st.button("Update Role", key="btn_update_role"):
            success, msg = auth_service.update_user_role(
                admin_username=user_name,
                target_username=selected_target,
                new_role=updated_role
            )
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    with col2:
        st.markdown("##### 🔑 Reset Password")
        reset_pwd = st.text_input("New Password", type="password", key="txt_reset_pwd")
        if st.button("Reset Password", key="btn_reset_pwd"):
            if not reset_pwd:
                st.error("Please enter a new password.")
            else:
                success, msg = auth_service.admin_reset_password(
                    admin_username=user_name,
                    target_username=selected_target,
                    new_password=reset_pwd
                )
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    with col3:
        st.markdown("##### 🔓 Lock & Status Actions")
        if target_user_dict and target_user_dict["locked_until"]:
            if st.button(f"Unlock Account '{selected_target}'", key="btn_unlock_usr"):
                success, msg = auth_service.unlock_user(user_name, selected_target)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        else:
            st.button(f"Unlock Account '{selected_target}'", disabled=True, key="btn_unlock_dis", help="Account is not locked")

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        if target_user_dict and target_user_dict["is_active"]:
            if st.button(f"Deactivate Account '{selected_target}'", key="btn_deact_usr"):
                success, msg = auth_service.deactivate_user(user_name, selected_target)
                if success:
                    st.warning(msg)
                    st.rerun()
                else:
                    st.error(msg)
        else:
            st.info("Account is already deactivated.")
