"""
Streamlit Dashboard Page: CWRU Bearing Vibration & Fault Analysis (Step 6).
"""
import os
import json
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

from ml.cwru_bearing import (
    load_cwru_signals,
    generate_synthetic_cwru_data,
    window_signal,
    extract_window_features,
    predict_cwru_window,
    CWRU_MODEL_PATH,
    CWRU_META_PATH,
    CWRU_CM_PATH,
    CWRU_FI_PATH,
    CLASS_LABELS,
    FEATURE_NAMES,
    SAMPLING_RATE,
    WINDOW_SIZE,
    CWRU_DIR,
    DOWNLOAD_INSTRUCTIONS
)


@st.cache_data
def get_bearing_signals():
    """Cache loaded or synthetic bearing signals."""
    signals = load_cwru_signals(CWRU_DIR)
    if not signals:
        signals = generate_synthetic_cwru_data()
    return signals


def render():
    st.markdown("## 🔩 Bearing Vibration Analysis (CWRU Data Center)")
    st.markdown(
        "Real-time signal processing and Random Forest fault classification on **12 kHz Drive-End accelerometer** signals."
    )

    # ---------------------------------------------------------------------------
    # Model Status Header
    # ---------------------------------------------------------------------------
    meta = None
    if os.path.exists(CWRU_META_PATH):
        with open(CWRU_META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)

    if meta:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Model Status", "Trained ✅")
        with col2:
            macro_f1 = meta.get("metrics", {}).get("macro_f1", 0.0)
            st.metric("Test Macro F1", f"{macro_f1:.4f}")
        with col3:
            st.metric("Test Split Strategy", meta.get("split_method", "N/A"))
        with col4:
            sha = meta.get("sha256_fingerprint", "")[:12] + "..."
            st.metric("SHA-256 Fingerprint", sha)
    else:
        st.warning("⚠️ CWRU Bearing model not trained yet. Run `python -m ml.cwru_bearing train` to train.")

    st.markdown("---")

    # ---------------------------------------------------------------------------
    # Signal Explorer Controls
    # ---------------------------------------------------------------------------
    signals = get_bearing_signals()
    if not signals:
        st.error("No vibration signals available.")
        return

    st.subheader("1. Signal Explorer & Spectral Analysis")

    c1, c2 = st.columns(2)
    with c1:
        selected_label = st.selectbox(
            "Select Bearing Condition",
            options=CLASS_LABELS,
            format_func=lambda x: {
                "normal": "🟢 Healthy Baseline (Normal)",
                "inner_race": "🔴 Inner Race Fault (0.007\")",
                "ball": "🟠 Ball Fault (0.007\")",
                "outer_race": "🟣 Outer Race Fault @ 6:00 (0.007\")"
            }[x]
        )
    with c2:
        available_loads = sorted(list(set(s["load_hp"] for s in signals if s["label"] == selected_label)))
        selected_load = st.selectbox("Select Motor Load", options=available_loads, format_func=lambda x: f"{x} HP")

    # Find matching signal record
    matching_recs = [s for s in signals if s["label"] == selected_label and s["load_hp"] == selected_load]
    if not matching_recs:
        st.warning("No signal matching selected criteria.")
        return

    rec = matching_recs[0]
    sig = rec["signal"]
    fs = SAMPLING_RATE
    time_vec = np.arange(len(sig)) / fs

    # ---------------------------------------------------------------------------
    # Plot Time-Domain Waveform & FFT Spectrum
    # ---------------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5), sharex=False)
    fig.patch.set_facecolor("#0F172A")
    ax1.set_facecolor("#1E293B")
    ax2.set_facecolor("#1E293B")

    # Time domain
    ax1.plot(time_vec, sig, color="#38BDF8", linewidth=0.8)
    ax1.set_title(f"Time-Domain Waveform — {selected_label.upper()} ({selected_load} HP)", color="white", fontsize=11, fontweight="bold")
    ax1.set_xlabel("Time (seconds)", color="#94A3B8")
    ax1.set_ylabel("Acceleration (g)", color="#94A3B8")
    ax1.tick_params(colors="#94A3B8")
    ax1.grid(True, linestyle="--", alpha=0.3, color="#475569")

    # Frequency domain (FFT)
    n = len(sig)
    fft_vals = np.abs(np.fft.rfft(sig)) ** 2
    freqs = np.fft.rfftfreq(n, d=1/fs)

    ax2.plot(freqs, fft_vals, color="#F43F5E", linewidth=0.8)
    ax2.set_title("Frequency-Domain Power Spectrum (0 to 6 kHz)", color="white", fontsize=11, fontweight="bold")
    ax2.set_xlabel("Frequency (Hz)", color="#94A3B8")
    ax2.set_ylabel("Power Density", color="#94A3B8")
    ax2.tick_params(colors="#94A3B8")
    ax2.grid(True, linestyle="--", alpha=0.3, color="#475569")

    fig.tight_layout()
    st.pyplot(fig)

    st.markdown("---")

    # ---------------------------------------------------------------------------
    # Live Window Classifier
    # ---------------------------------------------------------------------------
    st.subheader("2. Live Window Fault Diagnosis")
    windows = window_signal(sig, window_size=WINDOW_SIZE, overlap=0.5)

    if windows:
        window_idx = st.slider("Select 2048-Sample Window Offset", 0, len(windows) - 1, 0,
                               format=f"Window %d of {len(windows)}")
        selected_window = windows[window_idx]

        w_col1, w_col2 = st.columns([1.2, 1.0])

        with w_col1:
            st.markdown(f"**Extracted Features (Window #{window_idx}):**")
            feats = extract_window_features(selected_window)
            df_feats = pd.DataFrame({
                "Feature Name": FEATURE_NAMES,
                "Extracted Value": [f"{v:.4f}" for v in feats]
            })
            st.dataframe(df_feats, height=260, use_container_width=True)

        with w_col2:
            st.markdown("**Random Forest Fault Prediction:**")
            pred_class, conf, probs = predict_cwru_window(selected_window)

            if pred_class:
                status_color = "#22C55E" if pred_class == "normal" else "#EF4444"
                st.markdown(
                    f"""
                    <div style="background-color: #1E293B; border-left: 5px solid {status_color}; padding: 12px; border-radius: 6px; margin-bottom: 15px;">
                        <h4 style="margin:0; color:white;">Predicted Class: <span style="color:{status_color};">{pred_class.upper()}</span></h4>
                        <p style="margin:4px 0 0 0; color:#94A3B8;">Confidence Score: <b>{conf * 100:.2f}%</b></p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                st.markdown("**Class Probability Distribution:**")
                for cls_name, prob in probs.items():
                    st.write(f"**{cls_name}**: {prob * 100:.1f}%")
                    st.progress(prob)
            else:
                st.info("Train the CWRU model to view live window predictions.")

    st.markdown("---")

    # ---------------------------------------------------------------------------
    # Model Artifacts & Diagnostics Tab
    # ---------------------------------------------------------------------------
    st.subheader("3. Model Validation & Artifacts")
    tab1, tab2, tab3 = st.tabs(["Confusion Matrix", "Feature Importances", "Data Source & Download"])

    with tab1:
        if os.path.exists(CWRU_CM_PATH):
            st.image(CWRU_CM_PATH, caption="CWRU Bearing Fault Classifier Confusion Matrix", use_container_width=True)
        else:
            st.info("Confusion matrix plot will be generated during training.")

    with tab2:
        if os.path.exists(CWRU_FI_PATH):
            st.image(CWRU_FI_PATH, caption="CWRU Bearing Random Forest Feature Importances", use_container_width=True)
        else:
            st.info("Feature importance plot will be generated during training.")

    with tab3:
        st.code(DOWNLOAD_INSTRUCTIONS, language="text")
        st.markdown(
            "See [data/cwru/README.md](file:///c:/Users/yadav/OneDrive/Desktop/fault-diagnosis-project/data/cwru/README.md) for automated download scripts."
        )


render_bearing_analysis_page = render
