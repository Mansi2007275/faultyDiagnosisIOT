import streamlit as st
import pandas as pd
from dashboard.components import render_page_header, render_metric_card
from simulator.attacks import AttackType
from auth.permissions import has_permission
from auth.db import log_audit_event


def render_trust_security_page(fleet, attack_engine, trust_engine, ledger, session_state):
    """
    Renders Page 3: Trust & Security Engine verification dashboard and Attack Simulation Center.
    Includes Honeypot, Flood detection triggers, RBAC access check, and audit logging.
    """
    user = st.session_state.get("authenticated_user")
    user_role = user.get("role", "Operator") if user else "Operator"
    user_name = user.get("username", "system") if user else "system"

    render_page_header(
        title="Zero-Trust & Cyber-Physical Security Engine",
        subtitle="Cryptographic proof, replay defense, thermodynamic invariants & anomaly detection",
        badge_text="ZERO-TRUST"
    )

    machines = fleet.get_all_machines()
    machine_ids = [m.machine_id for m in machines]

    st.markdown("### 🛡️ Interactive Cyber Attack & Fault Injection Simulator")
    st.markdown("Simulate adversarial MITM attacks, replay injections, sensor spoofing, flood traffic, or honeypot triggers.")

    # Check permission for Attack Lab
    can_use_attack_lab = has_permission(user_role, "Attack Lab")

    if not can_use_attack_lab:
        st.warning("🔒 Attack Lab controls are disabled for your current role (Requires Engineer or Admin permission).")

    col1, col2, col3 = st.columns([1.5, 2, 1])

    with col1:
        target_machine = st.selectbox("Target Asset:", options=machine_ids, key="trust_target_mach", disabled=not can_use_attack_lab)
        selected_attack = st.selectbox(
            "Attack / Anomaly Mode:",
            options=[
                AttackType.NONE,
                AttackType.SIGNATURE_TAMPERING,
                AttackType.REPLAY_ATTACK,
                AttackType.PHYSICS_VIOLATION,
                AttackType.STUCK_SENSOR,
                AttackType.DRIFT_BIAS,
                AttackType.HONEYPOT,
                AttackType.FLOOD
            ],
            format_func=lambda a: {
                AttackType.NONE: "🟢 Nominal (No Attack)",
                AttackType.SIGNATURE_TAMPERING: "🔴 Cryptographic Payload Tampering",
                AttackType.REPLAY_ATTACK: "🟠 Replay Attack (Stale Sequence & Timestamp)",
                AttackType.PHYSICS_VIOLATION: "🟣 Thermodynamic / Power Physics Violation",
                AttackType.STUCK_SENSOR: "🟡 Stuck / Frozen Analog Transducer",
                AttackType.DRIFT_BIAS: "🔵 Stealthy Sensor Drift Bias",
                AttackType.HONEYPOT: "🍯 Publish to Honeypot (sentineltwin/plant1/admin/config)",
                AttackType.FLOOD: "🌊 Message Flood Traffic (500 msgs/min)"
            }.get(a, a.value),
            disabled=not can_use_attack_lab
        )

    with col2:
        st.markdown("#### Attack Parameters")
        attack_params = {}
        if selected_attack == AttackType.SIGNATURE_TAMPERING:
            mode = st.radio("Tamper Target:", ["payload_tampering", "corrupt_signature_hash"], horizontal=True)
            attack_params["mode"] = mode
            st.caption("Alters telemetry payload after cryptographic signing to simulate man-in-the-middle packet forgery.")
        elif selected_attack == AttackType.PHYSICS_VIOLATION:
            violation = st.radio("Violation Type:", ["thermal_inversion", "power_torque_mismatch"], horizontal=True)
            attack_params["violation"] = violation
            st.caption("Forces process temperature below ambient air temperature or breaks rotational power law P = Tau * Omega.")
        elif selected_attack == AttackType.STUCK_SENSOR:
            sensor = st.selectbox("Frozen Sensor:", ["process_temperature_k", "air_temperature_k", "rotational_speed_rpm", "all"])
            attack_params["sensor"] = sensor
            st.caption("Pins sensor value to constant across cycles with zero analog variance.")
        elif selected_attack == AttackType.REPLAY_ATTACK:
            lag = st.slider("Replay Lag (steps back):", min_value=3, max_value=20, value=8)
            attack_params["lag_steps"] = lag
            st.caption("Transmits authentic past packet with expired timestamp and non-monotonic sequence ID.")
        elif selected_attack == AttackType.DRIFT_BIAS:
            rate = st.slider("Drift Rate (K / step):", min_value=0.2, max_value=2.0, value=0.8, step=0.1)
            attack_params["drift_rate"] = rate
            st.caption("Gradually biases process temperature upward to trigger false thermal alarms.")
        elif selected_attack == AttackType.HONEYPOT:
            st.warning("🍯 Honeypot channel: Transmits unauthorized packet to fake config topic. Device will be QUARANTINED immediately.")
        elif selected_attack == AttackType.FLOOD:
            st.warning("🌊 Message flood: Simulates 500 requests/min flood traffic to trigger rate limiting & drop extra packets.")
        else:
            st.success("Target asset running in clean operational mode.")

    with col3:
        st.write("")
        st.write("")
        if st.button("🚀 Fire Attack Payload", type="primary", use_container_width=True, disabled=not can_use_attack_lab):
            if selected_attack == AttackType.HONEYPOT:
                # Honeypot action
                rep_res = trust_engine.rep_engine.trigger_honeypot(target_machine)
                log_audit_event(
                    username=user_name, role=user_role, action="Attack Lab attack sent",
                    target=target_machine, result="SUCCESS", details="Honeypot payload published to fake topic"
                )
                st.error(f"🍯 Honeypot triggered for {target_machine}! Device QUARANTINED.")
            elif selected_attack == AttackType.FLOOD:
                # Flood action: simulate 500 messages
                for _ in range(500):
                    trust_engine.rep_engine.check_flood(target_machine)
                log_audit_event(
                    username=user_name, role=user_role, action="Attack Lab attack sent",
                    target=target_machine, result="SUCCESS", details="Simulated 500 msgs flood traffic"
                )
                st.warning(f"🌊 Message flood simulated for {target_machine}. Rate limit applied.")
            else:
                attack_engine.set_attack(target_machine, selected_attack, attack_params)
                log_audit_event(
                    username=user_name, role=user_role, action="Attack Lab attack sent",
                    target=target_machine, result="SUCCESS", details=f"Attack payload '{selected_attack.value}' sent"
                )

            # Step machine
            vm = fleet.get_machine(target_machine)
            raw = vm.tick()
            mutated = attack_engine.apply_attack(raw)
            trust_rep = trust_engine.evaluate(mutated)

            ledger.record_telemetry(mutated)
            if not trust_rep.is_trusted:
                ledger.record_event(
                    target_machine,
                    "SECURITY_ALERT",
                    f"Attack '{selected_attack.value}' detected. Trust Score: {trust_rep.trust_score}% | Reasons: {'; '.join(trust_rep.failure_reasons)}"
                )

            if "last_attack_result" not in session_state:
                session_state.last_attack_result = {}
            session_state.last_attack_result[target_machine] = {
                "telemetry": mutated,
                "report": trust_rep,
                "attack_type": selected_attack
            }
            st.rerun()

        if st.button("🧹 Clear All Active Attacks", use_container_width=True, disabled=not can_use_attack_lab):
            attack_engine.clear_all()
            st.success("All attacks cleared. Fleet operating under nominal baseline.")
            st.rerun()

    st.markdown("---")

    # Evaluation Dashboard for Target Machine
    last_res = session_state.get("last_attack_result", {}).get(target_machine)
    if not last_res:
        vm = fleet.get_machine(target_machine)
        raw = vm.tick()
        mutated = attack_engine.apply_attack(raw)
        trust_rep = trust_engine.evaluate(mutated)
        last_res = {
            "telemetry": mutated,
            "report": trust_rep,
            "attack_type": AttackType.NONE
        }

    rep = last_res["report"]
    tel = last_res["telemetry"]

    st.subheader(f"Verification Results for {target_machine}")

    # 4 Pillar Status Cards
    p1, p2, p3, p4 = st.columns(4)
    with p1:
        st_color = "trusted" if rep.signature_valid else "rejected"
        render_metric_card("1. Cryptographic Signature", "PASS (30/30)" if rep.signature_valid else "FAIL (0/30)", rep.signature_msg, st_color)
    with p2:
        st_color = "trusted" if rep.replay_valid else "rejected"
        render_metric_card("2. Anti-Replay / Seq", "PASS (25/25)" if rep.replay_valid else "FAIL (0/25)", rep.replay_msg, st_color)
    with p3:
        st_color = "trusted" if rep.physics_valid else "rejected"
        render_metric_card("3. Physics Invariants", "PASS (25/25)" if rep.physics_valid else "FAIL (0/25)", "Thermodynamics & Power", st_color)
    with p4:
        st_color = "trusted" if rep.sensor_healthy else "rejected"
        render_metric_card("4. Sensor Variance", "PASS (20/20)" if rep.sensor_healthy else "FAIL (0/20)", "Dynamic analog noise", st_color)

    # Detailed Findings Box
    if rep.is_trusted:
        st.success(f"**TRUST VERDICT: {rep.verdict.value} (Score: {rep.trust_score:.0f}/100)** — Telemetry packet is cryptographically authentic, timely, physically consistent, and valid.")
    else:
        st.error(f"**TRUST VERDICT: {rep.verdict.value} (Score: {rep.trust_score:.0f}/100)** — Security Engine flagged packet anomalies:")
        for reason in rep.failure_reasons:
            st.markdown(f"- ⚠️ **{reason}**")

    # Deep-dive tabs
    st.markdown("### Verification Breakdown & Proof Details")
    tab_crypto, tab_seq, tab_phys, tab_var = st.tabs([
        "🔐 Cryptographic HMAC", "⏱️ Anti-Replay & Sequence", "⚛️ Physics Invariants", "📊 Sensor Variance"
    ])

    with tab_crypto:
        st.markdown(f"**Device Public Key ID:** `{tel.get('public_key_id')}`")
        st.markdown(f"**Packet HMAC-SHA256 Signature:**")
        st.markdown(f"<div class='hash-pill'>{tel.get('signature')}</div>", unsafe_allow_html=True)
        st.write(f"**Status:** {rep.signature_msg}")

    with tab_seq:
        st.write(f"**Sequence ID:** `#{tel.get('sequence_id')}`")
        st.write(f"**Timestamp (UNIX):** `{tel.get('timestamp'):.3f}`")
        st.write(f"**Anti-Replay Status:** {rep.replay_msg}")

    with tab_phys:
        st.write(f"**Thermodynamic Differential (Process - Air):** `{tel.get('process_temperature_k', 0) - tel.get('air_temperature_k', 0):.2f} K`")
        st.write(f"**Reported Mechanical Power:** `{tel.get('calculated_power_w', 0):.1f} W`")
        for f in rep.physics_findings:
            st.info(f)

    with tab_var:
        for sf in rep.sensor_findings:
            st.info(sf)
