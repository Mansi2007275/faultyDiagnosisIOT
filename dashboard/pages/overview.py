import streamlit as st
import pandas as pd
import plotly.express as px
from dashboard.components import render_page_header, render_metric_card
from simulator.data_loader import DataLoader
from ml.anomaly import score_reading
from auth.permissions import has_permission
from auth.db import log_audit_event


def render_overview_page(data_loader: DataLoader, fleet, ledger, trust_engine, diag_engine, rep_engine=None):
    """
    Renders Page 1: System Overview, Fleet Topology, Dataset Status, and Anomaly Health.
    Includes Device Reputation badges and Admin Demo Data Reset action.
    """
    user = st.session_state.get("authenticated_user")
    user_role = user.get("role", "Operator") if user else "Operator"
    user_name = user.get("username", "system") if user else "system"

    stats = data_loader.get_summary_statistics()

    render_page_header(
        title="SentinelTwin Industrial Intelligence",
        subtitle="Zero-Trust Digital Twin, Multi-Physics Fault Diagnostics & Cryptographic Audit Ledger",
        badge_text="OPERATIONAL"
    )

    # Top Fallback/Status Banner
    if not stats["is_real"]:
        st.warning(
            "⚠️ Real dataset not found. Download it from "
            "[https://archive.ics.uci.edu/dataset/601](https://archive.ics.uci.edu/dataset/601), "
            "unzip it, and put `ai4i2020.csv` in the `data` folder."
        )
    else:
        st.success(f"✅ Real dataset loaded from `data/ai4i2020.csv` ({stats['total_rows']:,} rows). Check the **📁 Dataset Analytics** page for deep EDA.")

    # Top KPI Metrics Row
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_metric_card("Connected Machines", f"{len(fleet.get_all_machines())} Units", "Active edge nodes", "nominal")
    with c2:
        render_metric_card("Trust Verification", "Zero-Trust Active", "4-tier continuous check", "trusted")
    with c3:
        sealed_count = len(ledger.sealed_batches)
        render_metric_card("Immutable Batches", f"{sealed_count} Batches", f"{len(ledger.open_batch.records)} in open buffer", "purple")
    with c4:
        render_metric_card("Diagnostics Engine", "AI4I Standard", "TWF, HDF, PWF, OSF, RNF", "trusted")

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # Architecture & Data Flow Overview
    st.subheader("System Architecture & Data Pipeline")
    st.markdown("""
    ```mermaid
    graph LR
        subgraph Machine Fleet
            VM1[CNC Center] -->|Signed Telemetry| TE[Zero-Trust Engine]
            VM2[Hydraulic Press] -->|Signed Telemetry| TE
            VM3[Gas Turbine] -->|Signed Telemetry| TE
            VM4[Lathe Cell] -->|Signed Telemetry| TE
        end

        subgraph Trust & Security
            TE -->|1. HMAC Signature| V1[Crypto Valid]
            TE -->|2. Anti-Replay| V2[Monotonic Seq]
            TE -->|3. Physics Laws| V3[Thermodynamics]
            TE -->|4. Sensor Noise| V4[Variance Check]
        end

        subgraph AI & Diagnostics
            V1 & V2 & V3 & V4 -->|Verified Stream| ML[Isolation Forest]
            ML -->|Anomaly Score| HD[AI4I Fault Engine]
            HD -->|Response Ladder| ACT[Watch / Warn / Derate / Stop]
            HD -->|Sealed Telemetry| AL[SHA-256 Merkle Ledger]
        end
    ```
    """)

    st.markdown("---")

    # Dataset & Training Baseline Summary
    st.subheader("Industrial Telemetry Baseline (AI4I 2020 Summary)")

    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.markdown("#### Dataset Status")
        st.write(f"**Data Source:** `{stats['source_label']}`")
        st.write(f"**Total Records Analyzed:** `{stats['total_rows']:,}` rows")
        st.write(f"**Total Machine Failures:** `{stats['total_failures']:,}` ({stats['failure_rate']:.2f}%)")

        # Display failure counts table
        fail_df = pd.DataFrame(
            list(stats["failure_counts"].items()),
            columns=["Failure Mode", "Observed Incidents"]
        )
        st.dataframe(fail_df, use_container_width=True, hide_index=True)

    with col_b:
        st.markdown("#### Failure Distribution Breakdown")
        df_plot = pd.DataFrame({
            "Mode": ["TWF", "HDF", "PWF", "OSF", "RNF"],
            "Count": [
                stats["failure_counts"]["TWF (Tool wear failure)"],
                stats["failure_counts"]["HDF (Heat dissipation failure)"],
                stats["failure_counts"]["PWF (Power failure)"],
                stats["failure_counts"]["OSF (Overstrain failure)"],
                stats["failure_counts"]["RNF (Random failure)"]
            ]
        })
        fig = px.bar(
            df_plot,
            x="Mode",
            y="Count",
            color="Mode",
            color_discrete_sequence=["#38BDF8", "#F59E0B", "#EF4444", "#A855F7", "#EC4899"],
            labels={"Count": "Failures", "Mode": "Failure Mode"}
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#CBD5E1",
            margin=dict(l=20, r=20, t=20, b=20),
            height=280
        )
        st.plotly_chart(fig, use_container_width=True)

    # Active Fleet Grid with Anomaly Score & Reputation Badges
    st.markdown("---")
    st.subheader("Active Industrial Assets & Live Reputation Badges")

    fleet_rows = []
    for vm in fleet.get_all_machines():
        # Read current telemetry snapshot
        raw_telemetry = {
            "air_temperature_k": vm.current_air_temp,
            "process_temperature_k": vm.current_process_temp,
            "rotational_speed_rpm": vm.current_rpm,
            "torque_nm": vm.current_torque,
            "tool_wear_min": vm.tool_wear,
            "calculated_power_w": vm.current_torque * (2 * 3.14159 * vm.current_rpm / 60)
        }
        anom_score, is_unusual, _ = score_reading(raw_telemetry)
        anom_str = f"{anom_score:.2f} (🔴 Unusual)" if is_unusual else (f"{anom_score:.2f} (🟢 Normal)" if anom_score is not None else "N/A")

        # Reputation badge
        rep_state = "Trusted"
        rep_score = 100
        if rep_engine:
            r = rep_engine.get_reputation(vm.machine_id)
            rep_state = r["state"]
            rep_score = r["score"]

        state_badge_map = {
            "Trusted": "🛡️ Trusted (80-100)",
            "Watched": "👁️ Watched (50-79)",
            "Quarantined": "⚠️ Quarantined (<50)",
            "Revoked": "🚫 Revoked (Admin)"
        }
        badge_str = state_badge_map.get(rep_state, "🛡️ Trusted")

        fleet_rows.append({
            "Machine ID": vm.machine_id,
            "Asset Name": vm.name,
            "Reputation State": f"{badge_str} [{rep_score} pts]",
            "Operating Speed": f"{vm.current_rpm:.0f} RPM",
            "Torque": f"{vm.current_torque:.1f} Nm",
            "Tool Wear": f"{vm.tool_wear:.1f} min",
            "ML Anomaly Score": anom_str,
            "Device Key ID": vm.public_key_id
        })
    st.dataframe(pd.DataFrame(fleet_rows), use_container_width=True, hide_index=True)

    # Admin Reset Demo Data Section
    if has_permission(user_role, "Reset demo data"):
        st.markdown("---")
        st.subheader("⚠️ Admin System Controls")
        if st.button("Reset Demo Data"):
            trust_engine.reset_all()
            log_audit_event(
                username=user_name, role=user_role, action="demo data reset",
                target="system", result="SUCCESS", details="Admin reset all demo simulation state"
            )
            st.success("Demo data state reset successfully.")
            st.rerun()
