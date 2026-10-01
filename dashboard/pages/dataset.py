import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dashboard.components import render_page_header, render_metric_card
from simulator.data_loader import DataLoader

def render_dataset_page(data_loader: DataLoader):
    """
    Renders Page: Dataset Analytics and Exploration for AI4I 2020 Predictive Maintenance.
    """
    stats = data_loader.get_summary_statistics()
    df = data_loader.df

    badge_label = "REAL DATASET" if stats["is_real"] else "DEMO BENCHMARK"

    render_page_header(
        title="AI4I 2020 Industrial Dataset Analytics",
        subtitle=f"Source: {stats['source_label']} • Exploratory Data Analysis & Failure Mode Distributions",
        badge_text=badge_label
    )

    # Missing columns warning (if any)
    if stats.get("missing_columns"):
        st.error(f"⚠️ Warning: The CSV is missing the following expected columns: {', '.join(stats['missing_columns'])}")

    # Top Metric Cards Row
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        render_metric_card(
            "Total Dataset Rows",
            f"{stats['total_rows']:,}",
            f"Source: {stats['source_label']}",
            "nominal"
        )
    with m2:
        render_metric_card(
            "Total Machine Failures",
            f"{stats['total_failures']:,}",
            "Positive failure incidents",
            "rejected" if stats['total_failures'] > 0 else "trusted"
        )
    with m3:
        render_metric_card(
            "Overall Failure Rate",
            f"{stats['failure_rate']:.2f}%",
            "Class imbalance ratio",
            "suspicious"
        )
    with m4:
        tc = stats["type_counts"]
        render_metric_card(
            "Product Type Split",
            f"L:{tc['L']:,} | M:{tc['M']:,} | H:{tc['H']:,}",
            f"L ({(tc['L']/stats['total_rows'])*100:.1f}%), M ({(tc['M']/stats['total_rows'])*100:.1f}%), H ({(tc['H']/stats['total_rows'])*100:.1f}%)",
            "purple"
        )

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # 1. Failure Counts by Type Bar Chart
    st.markdown("### 1. Canonical Failure Mode Distribution")
    
    failure_data = pd.DataFrame([
        {"Failure Code": "TWF", "Full Name": "TWF = Tool wear failure", "Count": stats["failure_counts"]["TWF (Tool wear failure)"], "Color": "#38BDF8"},
        {"Failure Code": "HDF", "Full Name": "HDF = Heat dissipation failure", "Count": stats["failure_counts"]["HDF (Heat dissipation failure)"], "Color": "#F59E0B"},
        {"Failure Code": "PWF", "Full Name": "PWF = Power failure", "Count": stats["failure_counts"]["PWF (Power failure)"], "Color": "#EF4444"},
        {"Failure Code": "OSF", "Full Name": "OSF = Overstrain failure", "Count": stats["failure_counts"]["OSF (Overstrain failure)"], "Color": "#A855F7"},
        {"Failure Code": "RNF", "Full Name": "RNF = Random failure", "Count": stats["failure_counts"]["RNF (Random failure)"], "Color": "#EC4899"}
    ])

    fig_bar = px.bar(
        failure_data,
        x="Full Name",
        y="Count",
        text="Count",
        color="Full Name",
        color_discrete_sequence=["#38BDF8", "#F59E0B", "#EF4444", "#A855F7", "#EC4899"],
        labels={"Full Name": "Failure Mode", "Count": "Incident Count"}
    )
    fig_bar.update_traces(textposition="outside", textfont=dict(color="#CBD5E1", size=13))
    fig_bar.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#CBD5E1",
        showlegend=False,
        height=320,
        margin=dict(l=20, r=20, t=20, b=30),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#334155")
    )
    st.plotly_chart(fig_bar, use_container_width=True)
    st.caption("This bar chart displays the frequency of each physical failure type across the entire machine dataset.")

    # Important Note
    st.info("ℹ️ **Note:** Failure type counts add up to more than total failures because some machines had two failures at the same time.")

    st.markdown("---")

    # 2. Histograms Section
    st.markdown("### 2. Sensor Feature Distributions (Failure vs. Nominal)")
    
    # Prepare DataFrame with readable failure label for plots
    df_plot = df.copy()
    df_plot["Failure Status"] = df_plot["failure"].map({0: "Nominal (0)", 1: "Failure (1)"})
    color_discrete_map = {"Nominal (0)": "#38BDF8", "Failure (1)": "#EF4444"}

    h_col1, h_col2 = st.columns(2)
    with h_col1:
        # Histogram 1: Process Temperature
        fig_h1 = px.histogram(
            df_plot,
            x="proc_c",
            color="Failure Status",
            barmode="overlay",
            nbins=40,
            color_discrete_map=color_discrete_map,
            labels={"proc_c": "Process Temperature (°C)"}
        )
        fig_h1.update_layout(
            title="Process Temperature (°C) Distribution",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#CBD5E1",
            height=280,
            margin=dict(l=20, r=20, t=40, b=20),
            yaxis=dict(showgrid=True, gridcolor="#334155")
        )
        st.plotly_chart(fig_h1, use_container_width=True)
        st.caption("Higher process contact temperatures elevate thermal strain, correlating with Heat Dissipation Failures (HDF).")

        # Histogram 2: Torque
        fig_h2 = px.histogram(
            df_plot,
            x="torque",
            color="Failure Status",
            barmode="overlay",
            nbins=40,
            color_discrete_map=color_discrete_map,
            labels={"torque": "Torque (Nm)"}
        )
        fig_h2.update_layout(
            title="Torque (Nm) Distribution",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#CBD5E1",
            height=280,
            margin=dict(l=20, r=20, t=40, b=20),
            yaxis=dict(showgrid=True, gridcolor="#334155")
        )
        st.plotly_chart(fig_h2, use_container_width=True)
        st.caption("Extreme torque loads (> 60 Nm) increase mechanical overstrain and lead to Power Failures (PWF).")

    with h_col2:
        # Histogram 3: Rotational Speed
        fig_h3 = px.histogram(
            df_plot,
            x="rpm",
            color="Failure Status",
            barmode="overlay",
            nbins=40,
            color_discrete_map=color_discrete_map,
            labels={"rpm": "Rotational Speed (RPM)"}
        )
        fig_h3.update_layout(
            title="Rotational Speed (RPM) Distribution",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#CBD5E1",
            height=280,
            margin=dict(l=20, r=20, t=40, b=20),
            yaxis=dict(showgrid=True, gridcolor="#334155")
        )
        st.plotly_chart(fig_h3, use_container_width=True)
        st.caption("Sub-1380 RPM operations under continuous cutting torque trigger Heat Dissipation Failures.")

        # Histogram 4: Tool Wear
        fig_h4 = px.histogram(
            df_plot,
            x="wear",
            color="Failure Status",
            barmode="overlay",
            nbins=40,
            color_discrete_map=color_discrete_map,
            labels={"wear": "Tool Wear (min)"}
        )
        fig_h4.update_layout(
            title="Tool Wear (min) Distribution",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#CBD5E1",
            height=280,
            margin=dict(l=20, r=20, t=40, b=20),
            yaxis=dict(showgrid=True, gridcolor="#334155")
        )
        st.plotly_chart(fig_h4, use_container_width=True)
        st.caption("Accumulated tool wear beyond 200 minutes drastically increases risk of Tool Wear Failure (TWF) and Overstrain (OSF).")

    st.markdown("---")

    # 3. Torque vs Speed Scatter Plot
    st.markdown("### 3. Torque vs. Rotational Speed Operating Envelope")
    
    fig_scatter = px.scatter(
        df_plot,
        x="rpm",
        y="torque",
        color="Failure Status",
        color_discrete_map=color_discrete_map,
        hover_data=["udi", "product_id", "type", "power_w", "wear"],
        opacity=0.75,
        labels={"rpm": "Rotational Speed (RPM)", "torque": "Torque (Nm)"}
    )
    fig_scatter.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#CBD5E1",
        height=400,
        margin=dict(l=20, r=20, t=20, b=20),
        xaxis=dict(showgrid=True, gridcolor="#334155"),
        yaxis=dict(showgrid=True, gridcolor="#334155"),
        legend=dict(orientation="h", y=1.08, x=0.3)
    )
    st.plotly_chart(fig_scatter, use_container_width=True)
    st.caption("This scatter plot illustrates the inverse hyperbolic relationship between torque and RPM, highlighting abnormal power failure zones.")

    st.markdown("---")

    # 4. Raw Data Table
    st.markdown("### 4. Raw Telemetry Records (First 20 Rows)")
    st.dataframe(df.head(20), use_container_width=True, hide_index=True)

    # 5. Dataset Credit Line
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #94A3B8; font-size: 0.85rem; padding: 1rem 0;'>"
        "<strong>Dataset Attribution:</strong> AI4I 2020 Predictive Maintenance Dataset, UCI Machine Learning Repository, CC BY 4.0."
        "</div>",
        unsafe_allow_html=True
    )
