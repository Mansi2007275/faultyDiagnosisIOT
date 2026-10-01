import streamlit as st

def inject_custom_css():
    """Injects high-end modern dark-mode industrial CSS with premium sidebar styling."""
    st.markdown("""
    <style>
    /* SentinelTwin Modern Industrial Glassmorphism Theme */
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }

    code, pre, .mono-font {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Main Container */
    .block-container {
        padding-top: 1.6rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }

    /* ========================================================= */
    /* 🌟 PREMIUM SIDEBAR / NAVBAR STYLING                      */
    /* ========================================================= */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0B1120 0%, #070B14 100%) !important;
        border-right: 1px solid rgba(56, 189, 248, 0.12) !important;
        box-shadow: 4px 0 24px -2px rgba(0, 0, 0, 0.6) !important;
    }

    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.2rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }

    /* Sidebar Brand Card */
    .nav-brand-card {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.9) 0%, rgba(30, 41, 59, 0.6) 100%);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 14px;
        padding: 1.1rem 1rem;
        margin-bottom: 1.2rem;
        text-align: center;
        box-shadow: 0 8px 20px -4px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(12px);
    }

    .nav-brand-title {
        font-size: 1.35rem;
        font-weight: 800;
        background: linear-gradient(135deg, #38BDF8 0%, #818CF8 50%, #C084FC 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.5px;
        margin: 0;
        line-height: 1.2;
    }

    .nav-brand-tag {
        display: inline-flex;
        align-items: center;
        margin-top: 0.45rem;
        padding: 0.2rem 0.6rem;
        background: rgba(56, 189, 248, 0.1);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 9999px;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.8px;
        color: #38BDF8;
        text-transform: uppercase;
    }

    /* Custom Radio Navigation Buttons */
    div[data-testid="stRadio"] > div {
        gap: 0.4rem;
    }

    div[data-testid="stRadio"] label {
        background: rgba(15, 23, 42, 0.55) !important;
        border: 1px solid rgba(56, 189, 248, 0.08) !important;
        border-radius: 10px !important;
        padding: 0.65rem 0.9rem !important;
        margin-bottom: 0.2rem !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
        cursor: pointer !important;
        color: #94A3B8 !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
    }

    div[data-testid="stRadio"] label:hover {
        background: rgba(56, 189, 248, 0.12) !important;
        border-color: rgba(56, 189, 248, 0.35) !important;
        color: #F8FAFC !important;
        transform: translateX(4px) !important;
    }

    /* Active / Checked Item */
    div[data-testid="stRadio"] label[data-checked="true"],
    div[data-testid="stRadio"] label:has(input:checked) {
        background: linear-gradient(90deg, rgba(14, 165, 233, 0.22) 0%, rgba(15, 23, 42, 0.8) 100%) !important;
        border-left: 3.5px solid #38BDF8 !important;
        border-top: 1px solid rgba(56, 189, 248, 0.3) !important;
        border-right: 1px solid rgba(56, 189, 248, 0.2) !important;
        border-bottom: 1px solid rgba(56, 189, 248, 0.2) !important;
        color: #38BDF8 !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 14px -2px rgba(14, 165, 233, 0.25) !important;
    }

    /* Hide standard radio circle for modern tab look */
    div[data-testid="stRadio"] div[role="radiogroup"] input {
        display: none !important;
    }

    /* Mini Fleet Machine Status Cards in Sidebar */
    .sidebar-mach-card {
        background: rgba(15, 23, 42, 0.65);
        border: 1px solid rgba(56, 189, 248, 0.1);
        border-radius: 9px;
        padding: 0.55rem 0.75rem;
        margin-bottom: 0.35rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        transition: border-color 0.2s ease, background 0.2s ease;
    }
    .sidebar-mach-card:hover {
        border-color: rgba(56, 189, 248, 0.3);
        background: rgba(15, 23, 42, 0.85);
    }
    .sidebar-mach-id {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.78rem;
        font-weight: 700;
        color: #38BDF8;
    }
    .sidebar-mach-name {
        font-size: 0.72rem;
        color: #94A3B8;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 140px;
    }

    /* Sidebar Footer Info Card */
    .sidebar-footer-card {
        background: rgba(15, 23, 42, 0.45);
        border: 1px dashed rgba(100, 116, 139, 0.3);
        border-radius: 10px;
        padding: 0.7rem 0.8rem;
        text-align: center;
        margin-top: 1rem;
    }

    /* Pulsing Green Indicator */
    .pulse-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        background-color: #10B981;
        border-radius: 50%;
        margin-right: 6px;
        box-shadow: 0 0 8px #10B981;
        animation: pulse-green 2s infinite;
    }

    @keyframes pulse-green {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    /* ========================================================= */
    /* 📄 GENERAL PAGE COMPONENTS                               */
    /* ========================================================= */
    /* Gradient Headers */
    .st-hero-title {
        font-size: 2.1rem;
        font-weight: 800;
        background: linear-gradient(135deg, #00F2FE 0%, #4FACFE 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
        letter-spacing: -0.5px;
    }
    
    .st-hero-sub {
        font-size: 1.0rem;
        color: #94A3B8;
        margin-bottom: 1.4rem;
        font-weight: 400;
    }

    /* Glass Cards */
    .sentinel-card {
        background: rgba(15, 23, 42, 0.75);
        border: 1px solid rgba(56, 189, 248, 0.18);
        border-radius: 12px;
        padding: 1.25rem 1.4rem;
        margin-bottom: 1rem;
        box-shadow: 0 8px 24px -4px rgba(0, 0, 0, 0.35);
        backdrop-filter: blur(12px);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .sentinel-card:hover {
        border-color: rgba(56, 189, 248, 0.4);
    }

    .sentinel-card-title {
        font-size: 0.82rem;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        color: #64748B;
        font-weight: 700;
        margin-bottom: 0.45rem;
    }

    .sentinel-card-value {
        font-size: 1.75rem;
        font-weight: 800;
        color: #F8FAFC;
    }

    /* Status Badges */
    .badge {
        display: inline-flex;
        align-items: center;
        padding: 0.3rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }
    .badge-trusted {
        background: rgba(16, 185, 129, 0.15);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.4);
    }
    .badge-suspicious {
        background: rgba(245, 158, 11, 0.15);
        color: #FBBF24;
        border: 1px solid rgba(245, 158, 11, 0.4);
    }
    .badge-rejected {
        background: rgba(239, 68, 68, 0.15);
        color: #F87171;
        border: 1px solid rgba(239, 68, 68, 0.4);
    }
    .badge-nominal {
        background: rgba(14, 165, 233, 0.15);
        color: #38BDF8;
        border: 1px solid rgba(14, 165, 233, 0.4);
    }

    /* Hash Pill */
    .hash-pill {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.78rem;
        background: rgba(30, 41, 59, 0.8);
        padding: 0.25rem 0.55rem;
        border-radius: 6px;
        color: #38BDF8;
        border: 1px solid rgba(56, 189, 248, 0.2);
        word-break: break-all;
    }
    </style>
    """, unsafe_allow_html=True)

def render_page_header(title: str, subtitle: str, badge_text: str = "LIVE SYSTEM"):
    """Renders standardized styled page header."""
    st.markdown(f"""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.2rem;">
        <div>
            <div class="st-hero-title">{title}</div>
            <div class="st-hero-sub">{subtitle}</div>
        </div>
        <div>
            <span class="badge badge-trusted"><span class="pulse-dot"></span>{badge_text}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_metric_card(title: str, value: str, subtext: str = "", status: str = "nominal"):
    """Renders a metric card."""
    color_map = {
        "trusted": "#10B981",
        "suspicious": "#F59E0B",
        "rejected": "#EF4444",
        "nominal": "#38BDF8",
        "purple": "#A855F7"
    }
    c = color_map.get(status, "#38BDF8")
    st.markdown(f"""
    <div class="sentinel-card" style="border-left: 4px solid {c};">
        <div class="sentinel-card-title">{title}</div>
        <div class="sentinel-card-value" style="color: {c};">{value}</div>
        <div style="font-size: 0.8rem; color: #94A3B8; margin-top: 0.35rem;">{subtext}</div>
    </div>
    """, unsafe_allow_html=True)
