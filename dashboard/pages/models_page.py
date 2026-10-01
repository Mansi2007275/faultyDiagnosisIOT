import os
import json
import streamlit as st
import pandas as pd
import plotly.express as px
from dashboard.components import render_page_header, render_metric_card
from ml.anomaly import train_anomaly_model, load_model
from ml.fault_classifier import train_fault_classifier, FAULT_META_PATH
from auth.permissions import has_permission
from auth.db import log_audit_event


def render_models_page():
    """
    Renders the AI & ML Models page with model architecture, performance metrics,
    cryptographic SHA-256 binary fingerprint, on-demand retraining controls, RBAC & audit logging.
    """
    user = st.session_state.get("authenticated_user")
    user_role = user.get("role", "Operator") if user else "Operator"
    user_name = user.get("username", "system") if user else "system"

    render_page_header(
        title="AI & ML Anomaly Detection & Fault Classifier Models",
        subtitle="Unsupervised Isolation Forest & Supervised Random Forest Fault Classifier",
        badge_text="MODELS ACTIVE"
    )

    can_retrain = has_permission(user_role, "Retrain models")

    tab_anom, tab_clf = st.tabs(["🌲 Unsupervised Isolation Forest (Anomaly)", "🏷️ Supervised Random Forest (Fault Classifier)"])

    # TAB 1: Isolation Forest Anomaly Detection
    with tab_anom:
        loaded = load_model()

        if loaded is None:
            st.warning("⚠️ Anomaly model not trained yet. Click the button below to train from the dataset.")
            if st.button("🚀 Train Isolation Forest Model Now", type="primary", disabled=not can_retrain):
                with st.spinner("Training Isolation Forest on healthy baseline..."):
                    meta = train_anomaly_model()
                    st.cache_resource.clear()
                    log_audit_event(user_name, user_role, "model retrained", "IsolationForest", "SUCCESS", "Initial training of Isolation Forest")
                    st.success("Model trained successfully!")
                    st.rerun()
        else:
            pipeline, meta = loaded
            metrics = meta.get("metrics", {})
            flagged = metrics.get("flagged_per_failure_type", {})

            # Top KPI Metrics Row
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                render_metric_card("Model ROC AUC", f"{metrics.get('roc_auc', 0.0):.4f}", "Anomaly discrimination power", "trusted")
            with m2:
                render_metric_card("F1 Score", f"{metrics.get('f1_score', 0.0):.4f}", "Harmonic Precision-Recall", "nominal")
            with m3:
                render_metric_card("Anomaly Threshold", f"{meta.get('threshold', 0.0):.4f}", "97th percentile healthy cutoff", "purple")
            with m4:
                render_metric_card("Training Population", f"{meta.get('training_rows', 0):,} rows", "80/20 Healthy baseline", "nominal")

            st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

            # Model Metadata & Cryptographic Fingerprint
            col_meta, col_retrain = st.columns([2, 1])
            with col_meta:
                st.markdown("### 🏷️ Model Governance & Integrity")
                st.markdown(f"**Model Identifier:** `{meta.get('model_name')}`")
                st.markdown(f"**Version:** `{meta.get('version')}` | **Trained:** `{meta.get('trained_at')}`")
                fp = meta.get('sha256_fingerprint', '')
                st.markdown(f"**SHA-256 Binary Fingerprint (Anchor):**")
                st.markdown(f"<div class='hash-pill'>{fp}</div>", unsafe_allow_html=True)
                st.caption(f"Fingerprint prefix (Audit): `{fp[:16]}`")

            with col_retrain:
                st.markdown("### 🔄 Model Retraining")
                if not can_retrain:
                    st.info("🔒 Model retraining disabled for your role (Requires Engineer or Admin).")
                st.write("Retrain the Isolation Forest on the latest dataset baseline.")
                if st.button("⚡ Retrain Anomaly Model", type="primary", use_container_width=True, key="btn_retrain_anom", disabled=not can_retrain):
                    with st.spinner("Retraining Isolation Forest model..."):
                        train_anomaly_model()
                        st.cache_resource.clear()
                        log_audit_event(user_name, user_role, "model retrained", "IsolationForest", "SUCCESS", "Retrained Isolation Forest model")
                        st.success("Model retrained and reloaded successfully!")
                        st.rerun()

            st.info("💡 **How it works:** The model learned only from healthy readings. It flags anything that looks different from healthy, even faults it has never seen.")

            st.markdown("---")

            # Flagged Anomaly Rate per Failure Type Bar Chart
            st.markdown("### 📊 Detection Sensitivity Across Canonical Failure Modes")

            chart_data = []
            if flagged:
                for ftype, data in flagged.items():
                    full_names = {
                        "TWF": "TWF (Tool Wear)",
                        "HDF": "HDF (Heat Dissipation)",
                        "PWF": "PWF (Power Failure)",
                        "OSF": "OSF (Overstrain)",
                        "RNF": "RNF (Random Failure)"
                    }
                    chart_data.append({
                        "Failure Mode": full_names.get(ftype, ftype),
                        "Flagged (%)": data.get("percentage", 0.0),
                        "Flagged Count": f"{data.get('flagged', 0)} / {data.get('total', 0)}"
                    })

            if chart_data:
                df_chart = pd.DataFrame(chart_data)
                fig_bar = px.bar(
                    df_chart,
                    x="Failure Mode",
                    y="Flagged (%)",
                    text="Flagged (%)",
                    color="Failure Mode",
                    color_discrete_sequence=["#38BDF8", "#F59E0B", "#EF4444", "#A855F7", "#EC4899"],
                    labels={"Flagged (%)": "Detection Rate (%)", "Failure Mode": "Failure Mode"}
                )
                fig_bar.update_traces(texttemplate='%{text:.1f}%', textposition='outside', textfont=dict(color='#CBD5E1', size=13))
                fig_bar.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#CBD5E1",
                    showlegend=False,
                    height=320,
                    yaxis=dict(range=[0, 110], showgrid=True, gridcolor="#334155"),
                    margin=dict(l=20, r=20, t=20, b=30)
                )
                st.plotly_chart(fig_bar, use_container_width=True)
                st.caption("Power and Overstrain failures produce massive multi-dimensional physical deviations, resulting in high unsupervised detection rates.")

            with st.expander("🔍 Anomaly Model Feature Engineering & Baseline Stats"):
                st.write("Features used for multivariate physical distance estimation:")
                st.json(meta.get("features", []))
                st.write("Baseline Healthy Statistics:")
                st.json({
                    "means": meta.get("feature_means", {}),
                    "stds": meta.get("feature_stds", {})
                })

    # TAB 2: Supervised Random Forest Fault Classifier
    with tab_clf:
        if not os.path.exists(FAULT_META_PATH):
            st.warning("⚠️ Fault Classifier model not trained yet.")
            if st.button("🚀 Train Fault Classifier Model Now", type="primary", key="btn_train_rf_init", disabled=not can_retrain):
                with st.spinner("Training Random Forest Fault Classifier..."):
                    train_fault_classifier()
                    st.cache_resource.clear()
                    log_audit_event(user_name, user_role, "model retrained", "RandomForest", "SUCCESS", "Initial training of Random Forest Classifier")
                    st.success("Fault Classifier trained successfully!")
                    st.rerun()
        else:
            with open(FAULT_META_PATH, "r", encoding="utf-8") as f:
                clf_meta = json.load(f)

            clf_metrics = clf_meta.get("metrics", {})
            cv_mean = clf_meta.get("cross_validation_5fold", {}).get("mean_macro_f1", 0.0)
            cv_std = clf_meta.get("cross_validation_5fold", {}).get("std_macro_f1", 0.0)

            # Top KPI Cards for Fault Classifier
            cm1, cm2, cm3, cm4 = st.columns(4)
            with cm1:
                render_metric_card("Macro F1 Score", f"{clf_metrics.get('macro_f1', 0.0):.4f}", "Unweighted mean across all 5 classes", "trusted")
            with cm2:
                render_metric_card("Weighted F1 Score", f"{clf_metrics.get('weighted_f1', 0.0):.4f}", "Weighted by class frequency", "nominal")
            with cm3:
                render_metric_card("5-Fold CV Macro F1", f"{cv_mean:.4f}", f"± {cv_std:.4f} cross-validation", "purple")
            with cm4:
                render_metric_card("Clean Samples", f"{clf_meta.get('clean_rows', 0):,} rows", f"Dropped {clf_meta.get('dropped_rows', 0)} noise/RNF rows", "nominal")

            st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

            # Metadata & Retrain section
            c_meta, c_retrain = st.columns([2, 1])
            with c_meta:
                st.markdown("### 🏷️ Fault Classifier Model Governance")
                st.markdown(f"**Model Identifier:** `{clf_meta.get('model_name')}`")
                st.markdown(f"**Algorithm:** `RandomForestClassifier (n_estimators=300, class_weight=balanced)`")
                st.markdown(f"**Trained:** `{clf_meta.get('trained_at')}`")
                fp_rf = clf_meta.get('sha256_fingerprint', '')
                st.markdown(f"**SHA-256 Binary Fingerprint:**")
                st.markdown(f"<div class='hash-pill'>{fp_rf}</div>", unsafe_allow_html=True)

            with c_retrain:
                st.markdown("### 🔄 Model Retraining")
                if not can_retrain:
                    st.info("🔒 Model retraining disabled for your role.")
                st.write("Retrain Random Forest on latest dataset labels and multi-label priorities.")
                if st.button("⚡ Retrain Fault Classifier", type="primary", use_container_width=True, key="btn_retrain_rf", disabled=not can_retrain):
                    with st.spinner("Retraining Random Forest Classifier..."):
                        train_fault_classifier()
                        st.cache_resource.clear()
                        log_audit_event(user_name, user_role, "model retrained", "RandomForest", "SUCCESS", "Retrained Random Forest Classifier")
                        st.success("Fault Classifier retrained successfully!")
                        st.rerun()

            st.markdown("---")

            # Per-Class Metrics Table
            st.markdown("### 📋 Test Set Per-Class Classification Performance")
            pc_dict = clf_metrics.get("per_class", {})
            if pc_dict:
                table_rows = []
                labels_desc = {
                    "none": "Nominal Baseline (No Failure)",
                    "TWF": "Tool Wear Failure",
                    "HDF": "Heat Dissipation Failure",
                    "PWF": "Power Failure",
                    "OSF": "Overstrain Failure"
                }
                for c_name, vals in pc_dict.items():
                    table_rows.append({
                        "Class": c_name,
                        "Description": labels_desc.get(c_name, c_name),
                        "Precision": f"{vals.get('precision', 0.0):.4f}",
                        "Recall": f"{vals.get('recall', 0.0):.4f}",
                        "F1-Score": f"{vals.get('f1', 0.0):.4f}",
                        "Test Support": vals.get('support', 0)
                    })
                st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

            st.markdown("---")

            # Display Plots Side by Side
            st.markdown("### 📈 Visual Model Diagnostic Reports")
            p_col1, p_col2 = st.columns(2)

            cm_img = "docs/confusion_matrix.png"
            fi_img = "docs/feature_importance.png"

            with p_col1:
                st.markdown("#### Normalized Confusion Matrix")
                if os.path.exists(cm_img):
                    st.image(cm_img, caption="Test Set Confusion Matrix (Normalized by True Class Rows)", use_container_width=True)
                else:
                    st.info("Confusion matrix image pending model evaluation plot export.")

            with p_col2:
                st.markdown("#### Gini Feature Importance")
                if os.path.exists(fi_img):
                    st.image(fi_img, caption="Gini Importance across Physical Features", use_container_width=True)
                else:
                    st.info("Feature importance image pending model evaluation plot export.")

            with st.expander("🔍 Fault Classifier Feature Schema & Multi-Failure Resolution Rules"):
                st.write("Features (strictly ordered):")
                st.json(clf_meta.get("features", []))
                st.markdown("""
                **Multi-label Priority Resolution:** `HDF` > `PWF` > `OSF` > `TWF`.
                **Noise Filtering:** Pure `RNF` (Random Failure) rows dropped as non-systematic thermal/mechanical noise.
                """)
