import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from dashboard.components import render_page_header, render_metric_card
from ml.anomaly import score_reading, load_model
from ml.fault_classifier import predict_fault

def render_live_monitor_page(fleet, attack_engine, trust_engine, diag_engine, ledger, session_state):
    """
    Renders Page: Real-time Digital Twin telemetry stream, live sensor plots, 
    Zero-Trust Gate, ML Anomaly Scoring, Fault Classifier & Dual Verdict cards.
    """
    render_page_header(
        title="Live Digital Twin & Telemetry Monitor",
        subtitle="Real-time sensor streaming, Zero-Trust verification, ML Anomaly & Fault Classification",
        badge_text="STREAMING"
    )

    machines = fleet.get_all_machines()
    machine_ids = [m.machine_id for m in machines]

    # Model metadata for threshold
    loaded_model = load_model()
    anomaly_threshold = loaded_model[1].get("threshold", 0.75) if loaded_model else 0.75

    # Top selector & controls
    top_col1, top_col2, top_col3 = st.columns([2, 1, 1])
    with top_col1:
        selected_id = st.selectbox(
            "Select Industrial Asset:",
            options=machine_ids,
            format_func=lambda mid: f"{mid} - {fleet.get_machine(mid).name}"
        )
    with top_col2:
        st.write("")
        st.write("")
        if st.button("⚡ Generate Telemetry Tick", use_container_width=True, type="primary"):
            vm = fleet.get_machine(selected_id)
            raw = vm.tick()
            mutated = attack_engine.apply_attack(raw)
            
            # 1. Zero-Trust Gate
            trust_rep = trust_engine.evaluate(mutated)
            
            # Check if device is quarantined (held)
            if trust_rep.is_held:
                anom_score, is_unusual, anom_exp = None, None, "Readings held: device quarantined"
                ml_fault, ml_conf, ml_probs = "quarantined", 0.0, {}
                diag_rep = diag_engine.diagnose(mutated)
            elif trust_rep.is_trusted:
                anom_score, is_unusual, anom_exp = score_reading(mutated)
                ml_fault, ml_conf, ml_probs = predict_fault(mutated)
                diag_rep = diag_engine.diagnose(mutated)
            else:
                anom_score, is_unusual, anom_exp = None, None, "Untrusted telemetry skipped by Zero-Trust gate"
                ml_fault, ml_conf, ml_probs = "untrusted", 0.0, {}
                diag_rep = diag_engine.diagnose(mutated)
            
            # 4. Ledger record (Quarantined held readings are NOT written to ledger)
            if not trust_rep.is_held:
                ledger.record_telemetry(mutated)
                if not trust_rep.is_trusted:
                    ledger.record_event(selected_id, "TRUST_VIOLATION", f"Score {trust_rep.trust_score}%: {'; '.join(trust_rep.failure_reasons)}")
                if diag_rep.fault_report.has_fault:
                    ledger.record_event(selected_id, "FAULT_DETECTED", f"Faults: {diag_rep.primary_fault}")

            # Append to session history
            if "telemetry_history" not in session_state:
                session_state.telemetry_history = {}
            if selected_id not in session_state.telemetry_history:
                session_state.telemetry_history[selected_id] = []
            
            record_entry = {
                **mutated,
                "_trust_score": trust_rep.trust_score,
                "_trust_verdict": trust_rep.verdict.value,
                "_anomaly_score": anom_score,
                "_is_unusual": is_unusual,
                "_anomaly_exp": anom_exp,
                "_health_index": diag_rep.fault_report.health_index,
                "_severity": diag_rep.severity.value,
                "_action": diag_rep.action.value,
                "_primary_fault": diag_rep.primary_fault,
                "_ml_fault": ml_fault,
                "_ml_conf": ml_conf,
                "_ml_probs": ml_probs
            }
            session_state.telemetry_history[selected_id].append(record_entry)
            st.rerun()

    with top_col3:
        st.write("")
        st.write("")
        if st.button("🔄 Reset Asset State", use_container_width=True):
            vm = fleet.get_machine(selected_id)
            vm.reset()
            trust_engine.stuck_det.reset_machine(selected_id)
            trust_engine.replay_det.reset_machine(selected_id)
            attack_engine.clear_attack(selected_id)
            if "telemetry_history" in session_state and selected_id in session_state.telemetry_history:
                session_state.telemetry_history[selected_id].clear()
            st.success(f"Reset {selected_id} state successfully.")
            st.rerun()

    # Get active machine telemetry history
    hist = session_state.get("telemetry_history", {}).get(selected_id, [])
    
    # If no history yet, generate initial tick
    if not hist:
        vm = fleet.get_machine(selected_id)
        raw = vm.tick()
        mutated = attack_engine.apply_attack(raw)
        trust_rep = trust_engine.evaluate(mutated)
        
        if trust_rep.is_trusted:
            anom_score, is_unusual, anom_exp = score_reading(mutated)
            ml_fault, ml_conf, ml_probs = predict_fault(mutated)
        else:
            anom_score, is_unusual, anom_exp = None, None, "Untrusted telemetry skipped"
            ml_fault, ml_conf, ml_probs = "untrusted", 0.0, {}
            
        diag_rep = diag_engine.diagnose(mutated)
        ledger.record_telemetry(mutated)
        
        record_entry = {
            **mutated,
            "_trust_score": trust_rep.trust_score,
            "_trust_verdict": trust_rep.verdict.value,
            "_anomaly_score": anom_score,
            "_is_unusual": is_unusual,
            "_anomaly_exp": anom_exp,
            "_health_index": diag_rep.fault_report.health_index,
            "_severity": diag_rep.severity.value,
            "_action": diag_rep.action.value,
            "_primary_fault": diag_rep.primary_fault,
            "_ml_fault": ml_fault,
            "_ml_conf": ml_conf,
            "_ml_probs": ml_probs
        }
        if "telemetry_history" not in session_state:
            session_state.telemetry_history = {}
        session_state.telemetry_history[selected_id] = [record_entry]
        hist = session_state.telemetry_history[selected_id]

    latest = hist[-1]

    if latest.get("_trust_verdict") == "HELD":
        st.warning("⚠️ **Readings held: device quarantined.** Readings are stored but suppressed from diagnosis, ML, and audit ledger until an Admin releases the device.")

    # Dual Verdict + ML Anomaly Status Banner
    st.markdown("### Operational Intelligence Verdict")
    v_col1, v_col2, v_col3, v_col4 = st.columns(4)
    
    trust_verdict = latest.get("_trust_verdict", "TRUSTED")
    trust_status = "trusted" if trust_verdict == "TRUSTED" else ("suspicious" if trust_verdict == "SUSPICIOUS" else "rejected")
    
    severity = latest.get("_severity", "NOMINAL")
    sev_status = "trusted" if severity == "NOMINAL" else ("suspicious" if severity == "WARNING" else "rejected")
    
    anom_val = latest.get("_anomaly_score")
    is_unusual = latest.get("_is_unusual")
    if anom_val is not None:
        anom_txt = f"{anom_val:.2f}"
        anom_sub = "🔴 Unusual Behavior" if is_unusual else "🟢 Normal Baseline"
        anom_status = "rejected" if is_unusual else "trusted"
    else:
        anom_txt = "N/A"
        anom_sub = "Skipped (Untrusted)"
        anom_status = "suspicious"

    with v_col1:
        render_metric_card(
            "1. Zero-Trust Gate",
            f"{trust_verdict} ({latest.get('_trust_score', 100):.0f}%)",
            "Signature • Sequence • Physics • Variance",
            trust_status
        )
    with v_col2:
        render_metric_card(
            "2. ML Anomaly Score",
            anom_txt,
            anom_sub,
            anom_status
        )
    with v_col3:
        render_metric_card(
            "3. Rule Health Severity",
            f"{severity} ({latest.get('_health_index', 100):.0f}%)",
            f"Fault: {latest.get('_primary_fault', 'None')}",
            sev_status
        )
    with v_col4:
        render_metric_card(
            "4. Response Ladder",
            latest.get("_action", "Watch"),
            "Automated action dispatch",
            "purple"
        )

    # ML Anomaly Time-Series Line Chart (Last 60 readings)
    st.markdown("### 📈 Real-Time ML Anomaly Tracking (Last 60 Readings)")
    df_60 = pd.DataFrame(hist[-60:])
    
    # Extract anomaly scores (replacing None with NaN for plotting)
    scores_series = [r.get("_anomaly_score") for r in hist[-60:]]
    valid_scores = [s if s is not None else None for s in scores_series]

    fig_anom = go.Figure()
    fig_anom.add_trace(go.Scatter(
        y=valid_scores,
        mode="lines+markers",
        name="Anomaly Score",
        line=dict(color="#38BDF8", width=2.5),
        marker=dict(size=6, color=["#EF4444" if s is not None and s >= anomaly_threshold else "#38BDF8" for s in valid_scores])
    ))
    # Add horizontal threshold line
    fig_anom.add_hline(
        y=anomaly_threshold,
        line_dash="dash",
        line_color="#EF4444",
        line_width=2,
        annotation_text=f"Unusual above this ({anomaly_threshold:.3f})",
        annotation_position="top right",
        annotation_font_color="#EF4444"
    )
    fig_anom.update_layout(
        title="Isolation Forest Multivariate Physical Anomaly Score (0 = Normal, 1 = Very Unusual)",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#CBD5E1",
        yaxis=dict(range=[0.0, 1.05], showgrid=True, gridcolor="#334155", title="Anomaly Score"),
        xaxis=dict(showgrid=True, gridcolor="#334155", title="Cycle Index"),
        margin=dict(l=20, r=20, t=40, b=20),
        height=280
    )
    st.plotly_chart(fig_anom, use_container_width=True)
    
    # Explanation text below anomaly chart
    latest_exp = latest.get("_anomaly_exp", "")
    if is_unusual:
        st.error(f"⚠️ **{latest_exp}**")
    elif anom_val is not None:
        st.success(f"✅ **{latest_exp}**")
    else:
        st.info("ℹ️ Telemetry rejected by Zero-Trust gate; anomaly inference withheld.")

    st.markdown("---")

    # Dual Diagnostics Section: Rule-based vs ML Random Forest Classifier
    st.markdown("### 🔬 Dual Diagnostic Comparison (Rule Engine vs ML Classifier)")
    diag_c1, diag_c2 = st.columns(2)
    
    rule_fault = latest.get("_primary_fault", "None")
    ml_fault = latest.get("_ml_fault", "none")
    ml_conf = latest.get("_ml_conf", 0.0)
    ml_probs = latest.get("_ml_probs", {})
    
    # Normalize fault names for comparison
    rule_norm = "none" if str(rule_fault).lower() in ["none", "nominal", "no fault"] else str(rule_fault)
    ml_norm = ml_fault
    
    with diag_c1:
        st.markdown("#### 📜 Rule-Based Engine")
        render_metric_card(
            "Rule Engine Verdict",
            f"Fault: {rule_fault}",
            f"Health Index: {latest.get('_health_index', 100):.0f}% | Severity: {latest.get('_severity', 'NOMINAL')}",
            "trusted" if rule_norm == "none" else "rejected"
        )
    with diag_c2:
        st.markdown("#### 🌲 ML Random Forest Classifier")
        render_metric_card(
            "ML RF Verdict",
            f"Class: {ml_fault} ({ml_conf*100:.1f}%)",
            "Multi-class Supervised Physics Model",
            "trusted" if ml_norm == "none" else "rejected"
        )

    # Agreement and Confidence Alerts
    if ml_fault == "untrusted":
        st.info("ℹ️ Telemetry untrusted. ML fault classifier skipped.")
    else:
        if rule_norm == ml_norm:
            st.success(f"🟢 **Rules and ML agree:** Both engines diagnosed **{rule_fault if rule_norm != 'none' else 'Nominal Operation (No Failure)'}**.")
        else:
            st.warning(f"⚠️ **Rules and ML disagree, check manually:** Rule engine diagnosed **{rule_fault}** while ML Random Forest predicted **{ml_fault}** ({ml_conf*100:.1f}% confidence).")

        if ml_conf < 0.60:
            st.warning(f"⚠️ **Low Confidence Warning:** Top predicted class confidence is {ml_conf*100:.1f}% (< 60%). Human expert inspection recommended.")

    # Class Probabilities Horizontal Bar Chart
    if ml_probs:
        classes = list(ml_probs.keys())
        probs_pct = [ml_probs[c] * 100 for c in classes]
        
        fig_prob = go.Figure(go.Bar(
            x=probs_pct,
            y=classes,
            orientation='h',
            marker=dict(
                color=["#34D399" if c == "none" else ("#EF4444" if c == ml_fault else "#38BDF8") for c in classes]
            ),
            text=[f"{p:.1f}%" for p in probs_pct],
            textposition="auto"
        ))
        fig_prob.update_layout(
            title="Random Forest Fault Type Class Probabilities (%)",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#CBD5E1",
            xaxis=dict(range=[0, 100], title="Probability (%)", showgrid=True, gridcolor="#334155"),
            margin=dict(l=20, r=20, t=35, b=20),
            height=220
        )
        st.plotly_chart(fig_prob, use_container_width=True)

    st.markdown("---")

    # Real-time Telemetry Metrics Grid
    st.markdown("### Physical Telemetry Sensors")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    with m1:
        st.metric("Air Temp", f"{latest.get('air_temperature_k', 0):.1f} K")
    with m2:
        st.metric("Process Temp", f"{latest.get('process_temperature_k', 0):.1f} K")
    with m3:
        st.metric("Speed (RPM)", f"{latest.get('rotational_speed_rpm', 0):.0f} RPM")
    with m4:
        st.metric("Torque", f"{latest.get('torque_nm', 0):.1f} Nm")
    with m5:
        st.metric("Power", f"{latest.get('calculated_power_w', 0):.0f} W")
    with m6:
        st.metric("Tool Wear", f"{latest.get('tool_wear_min', 0):.1f} min")

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # Time-Series Telemetry Charts
    st.markdown("### Telemetry Stream History")
    df_hist = pd.DataFrame(hist[-30:])

    chart_c1, chart_c2 = st.columns(2)
    with chart_c1:
        fig_speed = go.Figure()
        fig_speed.add_trace(go.Scatter(y=df_hist["rotational_speed_rpm"], mode="lines+markers", name="RPM", line=dict(color="#38BDF8", width=2)))
        fig_speed.add_trace(go.Scatter(y=df_hist["torque_nm"], mode="lines+markers", name="Torque (Nm)", yaxis="y2", line=dict(color="#F59E0B", width=2)))
        fig_speed.update_layout(
            title="Rotational Speed vs Torque",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#CBD5E1",
            margin=dict(l=20, r=20, t=40, b=20),
            height=250,
            yaxis=dict(title="Speed (RPM)", showgrid=True, gridcolor="#334155"),
            yaxis2=dict(title="Torque (Nm)", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.1, x=0.2)
        )
        st.plotly_chart(fig_speed, use_container_width=True)

    with chart_c2:
        fig_temp = go.Figure()
        fig_temp.add_trace(go.Scatter(y=df_hist["process_temperature_k"], mode="lines+markers", name="Process Temp", line=dict(color="#EF4444", width=2)))
        fig_temp.add_trace(go.Scatter(y=df_hist["air_temperature_k"], mode="lines+markers", name="Air Temp", line=dict(color="#34D399", width=2)))
        fig_temp.update_layout(
            title="Thermal Gradient (K)",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#CBD5E1",
            margin=dict(l=20, r=20, t=40, b=20),
            height=250,
            yaxis=dict(title="Temp (K)", showgrid=True, gridcolor="#334155"),
            legend=dict(orientation="h", y=1.1, x=0.2)
        )
        st.plotly_chart(fig_temp, use_container_width=True)
