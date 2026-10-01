"""
SentinelTwin Verdict Engine Configuration & Tunable Thresholds (Step 7).
"""

# ML Fault Classifier Confidence Thresholds
CONFIRM_FAULT_CONFIDENCE_THRESHOLD = 0.70  # ML fault confidence >= 70% confirms Machine Fault
WATCH_FAULT_CONFIDENCE_THRESHOLD = 0.50    # ML fault confidence 50%-70% triggers Watch state

# Response Ladder Hysteresis (Anti-Flicker) Limits
HYSTERESIS_ESCALATE_COUNT = 3               # Must see 3 consecutive higher readings before escalating
HYSTERESIS_STEPDOWN_COUNT = 10              # Must see 10 consecutive calmer readings before stepping down

# Safe Stop Escalation Rules
SAFE_STOP_HIGH_FAULTS_CONSECUTIVE = 5       # HIGH fault present in 5 consecutive readings triggers Safe Stop
SAFE_STOP_SIMULTANEOUS_HIGH_FAULTS = 2      # 2 or more simultaneous HIGH faults trigger Safe Stop

# Response Ladder Levels (ordered by severity for comparison)
RESPONSE_LEVELS = {
    "OK": 0,
    "Watch": 1,
    "Warn": 2,
    "Reduce load (recommend)": 3,
    "Safe stop (recommend)": 4,
    "Verify data: no machine action": -1  # Special response for Data Attack / Sensor Failure
}

# UI Status Badge Colors & Icons (Dual Visual Cue: Word + Icon + Color)
STATUS_BADGES = {
    "OK": {
        "text": "OK",
        "icon": "✓",
        "emoji": "🟢",
        "color": "#10B981",       # Emerald Green
        "bg": "rgba(16, 185, 129, 0.15)",
        "border": "#059669"
    },
    "Watch": {
        "text": "Watch",
        "icon": "👁",
        "emoji": "🔵",
        "color": "#3B82F6",       # Blue
        "bg": "rgba(59, 130, 246, 0.15)",
        "border": "#2563EB"
    },
    "Warn": {
        "text": "Warn",
        "icon": "⚠",
        "emoji": "🟡",
        "color": "#F59E0B",       # Amber
        "bg": "rgba(245, 158, 11, 0.15)",
        "border": "#D97706"
    },
    "Reduce load (recommend)": {
        "text": "Reduce load (recommend)",
        "icon": "⬇",
        "emoji": "🟠",
        "color": "#F97316",       # Orange
        "bg": "rgba(249, 115, 22, 0.15)",
        "border": "#EA580C"
    },
    "Safe stop (recommend)": {
        "text": "Safe stop (recommend)",
        "icon": "⛔",
        "emoji": "🔴",
        "color": "#EF4444",       # Red
        "bg": "rgba(239, 68, 68, 0.15)",
        "border": "#DC2626"
    },
    "Data Attack": {
        "text": "Data Attack",
        "icon": "🛡",
        "emoji": "🟣",
        "color": "#A855F7",       # Purple
        "bg": "rgba(168, 85, 247, 0.15)",
        "border": "#9333EA"
    },
    "Sensor Failure": {
        "text": "Sensor Failure",
        "icon": "🔧",
        "emoji": "⚪",
        "color": "#94A3B8",       # Slate Grey
        "bg": "rgba(148, 163, 184, 0.15)",
        "border": "#64748B"
    }
}
