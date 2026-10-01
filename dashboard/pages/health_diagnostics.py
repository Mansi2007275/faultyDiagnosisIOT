import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from dashboard.components import render_page_header, render_metric_card
from auth.permissions import has_permission
from auth.db import log_audit_event


def render_health_diagnostics_page(fleet, diag_engine, ledger, session_state):
    """
    Renders Page 4: Health Diagnostics, AI4I Fault Rules, Response Ladder, and Maintenance Job Workflow.
    """
    user = st.session_state.get("authenticated_user")
    user_role = user.get("role", "Operator") if user else "Operator"
    user_name = user.get("username", "system") if user else "system"

    render_page_header(
        title="Predictive Health & Fault Diagnostics",
        subtitle="AI4I 2020 multi-physics failure mode detection and automated response ladder",
        badge_text="DIAGNOSTICS"
    )

    machines = fleet.get_all_machines()
    machine_ids = [m.machine_id for m in machines]

    top1, top2 = st.columns([2, 1])
    with top1:
        selected_id = st.selectbox("Select Asset for Health Assessment:", options=machine_ids, key="diag_mach_select")
        vm = fleet.get_machine(selected_id)
    with top2:
        st.write("")
        st.write("")
        force_mode = st.selectbox(
            "Simulate Specific Failure Mode:",
            options=["None", "TWF", "HDF", "PWF", "OSF"],
            help="Forces machine physics into specific AI4I failure envelope for testing."
        )
        if force_mode != "None":
            vm.forced_fault_mode = force_mode
        else:
            vm.forced_fault_mode = None

    # Tick and evaluate current machine state
    raw = vm.tick()
    diag_verdict = diag_engine.diagnose(raw)
    report = diag_verdict.fault_report

    st.markdown("---")

    # Top Health Status & Response Ladder Cards
    c1, c2, c3 = st.columns(3)

    sev_color = "trusted" if diag_verdict.severity.value == "NOMINAL" else ("suspicious" if diag_verdict.severity.value == "WARNING" else "rejected")

    with c1:
        render_metric_card(
            "Machine Health Index",
            f"{report.health_index:.1f}%",
            "100% = Nominal / 0% = Total Failure",
            sev_color
        )
    with c2:
        render_metric_card(
            "Primary Diagnostic Verdict",
            diag_verdict.primary_fault,
            f"Severity: {diag_verdict.severity.value}",
            sev_color
        )
    with c3:
        render_metric_card(
            "Actionable Response Ladder",
            diag_verdict.action.value,
            "Automated maintenance trigger",
            "purple"
        )

    st.markdown("### AI4I Canonical Failure Mode Monitor")

    # Grid of 5 failure modes
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        st_txt = "🔴 TRIGGERED" if report.twf_triggered else "🟢 NOMINAL"
        st.metric("TWF (Tool Wear)", st_txt, f"{raw.get('tool_wear_min'):.1f} min / 235m")
    with f2:
        st_txt = "🔴 TRIGGERED" if report.hdf_triggered else "🟢 NOMINAL"
        st.metric("HDF (Heat Dissipation)", st_txt, f"dT: {report.metrics['delta_t_k']:.1f} K")
    with f3:
        st_txt = "🔴 TRIGGERED" if report.pwf_triggered else "🟢 NOMINAL"
        st.metric("PWF (Power Failure)", st_txt, f"{report.metrics['power_w']:.0f} W")
    with f4:
        st_txt = "🔴 TRIGGERED" if report.osf_triggered else "🟢 NOMINAL"
        st.metric("OSF (Overstrain)", st_txt, f"{report.metrics['overstrain_product']:.0f} min*Nm")
    with f5:
        st_txt = "🔴 TRIGGERED" if report.rnf_triggered else "🟢 NOMINAL"
        st.metric("RNF (Random Shock)", st_txt, f"Vib: {report.metrics['vibration_rms']:.2f} mm/s")

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # Health Index Gauge & Diagnostics Details
    g_col, d_col = st.columns([1, 1.2])

    with g_col:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=report.health_index,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': f"Health Score ({selected_id})", 'font': {'size': 20, 'color': '#CBD5E1'}},
            gauge={
                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#94A3B8"},
                'bar': {'color': "#38BDF8"},
                'bgcolor': "rgba(15, 23, 42, 0.8)",
                'borderwidth': 2,
                'bordercolor': "#334155",
                'steps': [
                    {'range': [0, 40], 'color': 'rgba(239, 68, 68, 0.4)'},
                    {'range': [40, 75], 'color': 'rgba(245, 158, 11, 0.4)'},
                    {'range': [75, 100], 'color': 'rgba(16, 185, 129, 0.4)'}
                ]
            }
        ))
        fig_gauge.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#CBD5E1",
            margin=dict(l=20, r=20, t=30, b=20),
            height=260
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

    with d_col:
        st.markdown("#### Diagnostic Findings & Rule Details")
        st.write(diag_verdict.summary_text)

        if report.rule_details:
            for rd in report.rule_details:
                st.warning(rd)
        else:
            st.success("No anomalous physical degradation rules violated.")

        st.markdown("#### Recommended Maintenance Procedures")
        for step in diag_verdict.recommended_steps:
            st.markdown(f"- 🛠️ {step}")

    st.markdown("---")

    # Maintenance Jobs Request & Dual-Sign Section
    st.subheader("🛠️ Maintenance Work Orders & Dual-Signature Clearance")
    if "maintenance_jobs" not in session_state:
        session_state.maintenance_jobs = {}

    can_request = has_permission(user_role, "Maintenance: request job")
    can_sign = has_permission(user_role, "Maintenance: sign")

    m_c1, m_c2 = st.columns([1.2, 1.8])

    with m_c1:
        st.markdown("##### Request Maintenance Work Order")
        if not can_request:
            st.info("🔒 Job requesting restricted to Engineer or Admin.")
        job_desc = st.text_input("Work Order Description:", placeholder="e.g. Replace spindle bearing", disabled=not can_request)
        if st.button("📝 Create Maintenance Job Request", disabled=not can_request or not job_desc):
            job_id = f"JOB-{len(session_state.maintenance_jobs)+1:03d}"
            session_state.maintenance_jobs[job_id] = {
                "job_id": job_id,
                "machine_id": selected_id,
                "description": job_desc,
                "requested_by": user_name,
                "engineer_sign": None,
                "safety_sign": None,
                "status": "Pending Signatures"
            }
            log_audit_event(
                username=user_name, role=user_role, action="maintenance requested/signed",
                target=job_id, result="SUCCESS", details=f"Requested job for {selected_id}: {job_desc}"
            )
            st.success(f"Work order {job_id} created.")
            st.rerun()

    with m_c2:
        st.markdown("##### Active Work Orders & Signature Clearance")
        if not session_state.maintenance_jobs:
            st.info("No active maintenance work orders.")
        else:
            for j_id, job in list(session_state.maintenance_jobs.items()):
                with st.expander(f"📌 {job['job_id']} — {job['machine_id']} ({job['status']})"):
                    st.write(f"**Description:** {job['description']}")
                    st.write(f"**Requested by:** {job['requested_by']}")
                    st.write(f"**Engineer Signature:** {job['engineer_sign'] or '❌ Pending'}")
                    st.write(f"**Safety Officer Signature:** {job['safety_sign'] or '❌ Pending'}")

                    if job['status'] == "Pending Signatures" and can_sign:
                        # Dual sign rule: Same user cannot sign as both Engineer and Safety Officer!
                        if user_role == "Engineer":
                            if job['requested_by'] == user_name and job['safety_sign'] == user_name:
                                st.warning("Same user cannot sign as both Engineer and Safety Officer.")
                            elif job['engineer_sign'] is None:
                                if st.button(f"✍️ Sign as Engineer ({user_name})", key=f"sign_eng_{j_id}"):
                                    job['engineer_sign'] = user_name
                                    if job['safety_sign']:
                                        job['status'] = "Cleared & Approved"
                                    log_audit_event(
                                        username=user_name, role=user_role, action="maintenance requested/signed",
                                        target=j_id, result="SUCCESS", details=f"Signed as Engineer by {user_name}"
                                    )
                                    st.success(f"Signed as Engineer!")
                                    st.rerun()

                        elif user_role == "Safety Officer":
                            if job['engineer_sign'] == user_name:
                                st.warning("Same user cannot sign as both Engineer and Safety Officer.")
                            elif job['safety_sign'] is None:
                                if st.button(f"✍️ Sign as Safety Officer ({user_name})", key=f"sign_saf_{j_id}"):
                                    job['safety_sign'] = user_name
                                    if job['engineer_sign']:
                                        job['status'] = "Cleared & Approved"
                                    log_audit_event(
                                        username=user_name, role=user_role, action="maintenance requested/signed",
                                        target=j_id, result="SUCCESS", details=f"Signed as Safety Officer by {user_name}"
                                    )
                                    st.success(f"Signed as Safety Officer!")
                                    st.rerun()

    # Standard Rule Definitions Accordion
    with st.expander("📚 Reference: AI4I 2020 Predictive Maintenance Mathematical Rules"):
        st.markdown("""
        - **TWF (Tool Wear Failure):** The tool is replaced or fails when the accumulated cutting time reaches $200 - 240$ minutes.
        - **HDF (Heat Dissipation Failure):** Occurs if the temperature difference between process contact point and ambient air is strictly less than $8.6\\text{ K}$ and the rotational speed is under $1380\\text{ RPM}$.
        - **PWF (Power Failure):** Mechanical delivered power $P = \\tau \\times \\omega$ falls outside the permissible motor operational bounds ($P < 3500\\text{ W}$ or $P > 9000\\text{ W}$).
        - **OSF (Overstrain Failure):** The product of Tool Wear and operating Torque exceeds the machine material limit:
          * Type L: $> 11,000\\text{ min}\\cdot\\text{Nm}$
          * Type M: $> 12,000\\text{ min}\\cdot\\text{Nm}$
          * Type H: $> 13,000\\text{ min}\\cdot\\text{Nm}$
        - **RNF (Random Failure):** Uncorrelated mechanical fault or bearing spike.
        """)
