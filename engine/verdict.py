"""
SentinelTwin Verdict Engine & Response Ladder (Step 7).
Combines Zero-Trust Security Gate, Domain Rule Engine, Isolation Forest Anomaly Score,
and ML Fault Predictions into one unified, hysteresis-filtered verdict.
"""

from typing import Dict, Any, List, Optional, Tuple
from engine.config import (
    CONFIRM_FAULT_CONFIDENCE_THRESHOLD,
    WATCH_FAULT_CONFIDENCE_THRESHOLD,
    HYSTERESIS_ESCALATE_COUNT,
    HYSTERESIS_STEPDOWN_COUNT,
    SAFE_STOP_HIGH_FAULTS_CONSECUTIVE,
    SAFE_STOP_SIMULTANEOUS_HIGH_FAULTS,
    RESPONSE_LEVELS,
    STATUS_BADGES
)
from engine.db import (
    get_machine_state,
    set_machine_state,
    save_verdict,
    save_verdict_change,
    DEFAULT_DB_PATH
)


def _extract_anomaly_score_and_flag(anomaly: Any) -> Tuple[float, bool]:
    """Extract float anomaly score and boolean flag from dict or float."""
    if isinstance(anomaly, dict):
        score = float(anomaly.get("anomaly_score", 0.0))
        is_anom = bool(anomaly.get("is_anomaly", False))
        return score, is_anom
    elif isinstance(anomaly, (int, float)):
        score = float(anomaly)
        return score, score > 0.65
    return 0.0, False


def _extract_ml_prediction(ml_prediction: Any) -> Tuple[str, float]:
    """Extract (predicted_class, confidence) from ml_prediction dict or tuple."""
    if isinstance(ml_prediction, dict):
        pred_cls = str(ml_prediction.get("predicted_class", "none"))
        conf = float(ml_prediction.get("confidence", 0.0))
        return pred_cls, conf
    elif isinstance(ml_prediction, (tuple, list)) and len(ml_prediction) >= 2:
        return str(ml_prediction[0]), float(ml_prediction[1])
    return "none", 0.0


def decide(reading: Dict[str, Any],
           trust_result: Optional[Dict[str, Any]] = None,
           rule_faults: Optional[List[Dict[str, Any]]] = None,
           anomaly: Any = None,
           ml_prediction: Any = None,
           recent_history: Optional[List[Dict[str, Any]]] = None,
           machine_id: str = "M-001",
           db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """
    Unified Verdict Engine: Evaluates a telemetry reading through 4 priority gates,
    computes response ladder recommendation, applies anti-flicker hysteresis,
    and persists audit logs to SQLite.

    Returns:
        Dict with keys: verdict, response, severity, reasons (list of str), inputs_used
    """
    trust_result = trust_result or {"valid": True, "status": "VERIFIED", "reasons": []}
    rule_faults = rule_faults or []
    anomaly_score, is_anomaly = _extract_anomaly_score_and_flag(anomaly)
    ml_class, ml_conf = _extract_ml_prediction(ml_prediction)

    reasons: List[str] = []
    inputs_used = {
        "trust_valid": trust_result.get("valid", True),
        "rule_fault_count": len(rule_faults),
        "anomaly_score": round(anomaly_score, 4),
        "ml_class": ml_class,
        "ml_confidence": round(ml_conf, 4)
    }

    # Retrieve per-machine hysteresis state from SQLite DB
    m_state = get_machine_state(machine_id, db_path=db_path)
    prev_verdict = m_state["current_verdict"]
    prev_response = m_state["current_response"]
    pending_resp = m_state["pending_response"]
    consec_count = m_state["consecutive_count"]
    high_fault_consec = m_state["high_fault_consecutive"]

    # ---------------------------------------------------------------------------
    # Priority 1: Data Attack Check (Trust Gate Rejected Message)
    # ---------------------------------------------------------------------------
    if not trust_result.get("valid", True):
        verdict = "Data Attack"
        response = "Verify data: no machine action"
        severity = "CRITICAL"

        trust_reasons = trust_result.get("reasons", [])
        if trust_reasons:
            for tr in trust_reasons:
                reasons.append(f"Trust Gate: {tr}")
        else:
            reasons.append("Trust Gate: Message verification failed (bad signature, replay attack, or physical invariant violation)")

        reasons.append("Security Policy: Data Attack detected — data excluded from machine health diagnosis.")

        # Save verdict & update state
        new_state = {
            "current_verdict": verdict,
            "current_response": response,
            "pending_response": None,
            "consecutive_count": 0,
            "high_fault_consecutive": 0
        }
        set_machine_state(machine_id, new_state, db_path=db_path)

        if verdict != prev_verdict or response != prev_response:
            save_verdict_change(machine_id, prev_verdict, verdict, prev_response, response, reasons, db_path=db_path)

        save_verdict(machine_id, verdict, response, severity, reasons, inputs_used, db_path=db_path)
        return {
            "verdict": verdict,
            "response": response,
            "severity": severity,
            "reasons": reasons,
            "inputs_used": inputs_used
        }

    # ---------------------------------------------------------------------------
    # Priority 2: Sensor Failure Check (Stuck / Zero-Variance / Disagreeing Sensor)
    # ---------------------------------------------------------------------------
    sensor_reasons = []
    # Check trust_result for sensor anomaly flags or reading stuck flags
    if trust_result.get("sensor_failure", False) or "stuck" in str(trust_result.get("status", "")).lower():
        sensor_reasons.append("Trust Gate: Sensor failure detected (stuck signal or zero variance)")
    for tr in trust_result.get("reasons", []):
        if "sensor" in tr.lower() or "stuck" in tr.lower() or "variance" in tr.lower():
            sensor_reasons.append(f"Sensor Check: {tr}")

    if sensor_reasons:
        verdict = "Sensor Failure"
        response = "Verify data: no machine action"
        severity = "HIGH"
        reasons.extend(sensor_reasons)
        reasons.append("Maintenance Policy: Sensor Failure detected — reading excluded from machine health diagnosis.")

        new_state = {
            "current_verdict": verdict,
            "current_response": response,
            "pending_response": None,
            "consecutive_count": 0,
            "high_fault_consecutive": 0
        }
        set_machine_state(machine_id, new_state, db_path=db_path)

        if verdict != prev_verdict or response != prev_response:
            save_verdict_change(machine_id, prev_verdict, verdict, prev_response, response, reasons, db_path=db_path)

        save_verdict(machine_id, verdict, response, severity, reasons, inputs_used, db_path=db_path)
        return {
            "verdict": verdict,
            "response": response,
            "severity": severity,
            "reasons": reasons,
            "inputs_used": inputs_used
        }

    # ---------------------------------------------------------------------------
    # Priority 3 & 4: Machine Fault vs Normal Check
    # ---------------------------------------------------------------------------
    high_faults = [f for f in rule_faults if str(f.get("risk_level", "")).upper() == "HIGH"]
    med_faults = [f for f in rule_faults if str(f.get("risk_level", "")).upper() == "MEDIUM"]

    has_rule_fault = len(high_faults) > 0 or len(med_faults) > 0
    has_high_rule_fault = len(high_faults) > 0
    has_ml_confirmed_fault = (ml_class != "none" and ml_conf >= CONFIRM_FAULT_CONFIDENCE_THRESHOLD)

    if has_rule_fault or has_ml_confirmed_fault:
        verdict = "Machine Fault"
    else:
        verdict = "Normal"

    # Track consecutive HIGH faults for Safe Stop escalation
    if has_high_rule_fault:
        high_fault_consec += 1
    else:
        high_fault_consec = 0

    # Collect plain-English reasons for diagnosis
    for f in rule_faults:
        r_name = f.get("name", f.get("code", "Fault"))
        r_risk = f.get("risk_level", "MEDIUM")
        r_exp = f.get("explanation", f.get("description", ""))
        reasons.append(f"Rule: {r_name} ({r_risk}) — {r_exp}")

    if ml_class != "none":
        reasons.append(f"ML: {ml_class} predicted with {ml_conf * 100:.1f}% confidence")

    if is_anomaly:
        reasons.append(f"Anomaly: Isolation Forest score {anomaly_score:.2f} (above threshold 0.65)")

    # ---------------------------------------------------------------------------
    # Response Ladder Calculation (Candidate Response)
    # ---------------------------------------------------------------------------
    candidate_response = "OK"

    if verdict == "Machine Fault":
        # Check rule & ML agreement: rule present and ML predicts same fault or high confidence fault
        rule_fault_codes = set(f.get("code", "") for f in rule_faults)
        rules_and_ml_agree = (
            has_high_rule_fault and (ml_class in rule_fault_codes or has_ml_confirmed_fault)
        ) or (
            has_rule_fault and ml_class != "none" and ml_conf >= 0.50
        )

        if len(high_faults) >= SAFE_STOP_SIMULTANEOUS_HIGH_FAULTS or high_fault_consec >= SAFE_STOP_HIGH_FAULTS_CONSECUTIVE:
            candidate_response = "Safe stop (recommend)"
            if len(high_faults) >= SAFE_STOP_SIMULTANEOUS_HIGH_FAULTS:
                reasons.append(f"Critical Rule: {len(high_faults)} simultaneous HIGH risk faults detected!")
            if high_fault_consec >= SAFE_STOP_HIGH_FAULTS_CONSECUTIVE:
                reasons.append(f"Critical Persistence: HIGH risk fault present in {high_fault_consec} consecutive readings!")

        elif has_high_rule_fault or rules_and_ml_agree:
            candidate_response = "Reduce load (recommend)"
            if rules_and_ml_agree:
                reasons.append("Agreement: Domain rules and ML fault classifier agree on active machine fault.")

        elif len(med_faults) > 0 or (has_ml_confirmed_fault and not has_rule_fault):
            candidate_response = "Warn"
            if has_ml_confirmed_fault and not has_rule_fault:
                reasons.append("ML Alert: ML predicts high-confidence fault not yet triggered by hard domain rules.")

    else:
        # Verdict is Normal
        if is_anomaly or (ml_class != "none" and WATCH_FAULT_CONFIDENCE_THRESHOLD <= ml_conf < CONFIRM_FAULT_CONFIDENCE_THRESHOLD):
            candidate_response = "Watch"
            if ml_class != "none" and ml_conf >= WATCH_FAULT_CONFIDENCE_THRESHOLD:
                reasons.append(f"Early Watch: ML detected moderate confidence {ml_class} ({ml_conf*100:.1f}%).")
        else:
            candidate_response = "OK"
            if not reasons:
                reasons.append("Normal: All physical parameters within nominal operating bounds.")

    # ---------------------------------------------------------------------------
    # Anti-Flicker Hysteresis Filtering
    # ---------------------------------------------------------------------------
    cand_level = RESPONSE_LEVELS.get(candidate_response, 0)
    curr_level = RESPONSE_LEVELS.get(prev_response, 0)

    # Special case: 2+ simultaneous HIGH faults OR 5 consecutive HIGH faults cause immediate Safe Stop
    immediate_escalation = (
        len(high_faults) >= SAFE_STOP_SIMULTANEOUS_HIGH_FAULTS or
        high_fault_consec >= SAFE_STOP_HIGH_FAULTS_CONSECUTIVE
    )

    final_response = prev_response
    if prev_response not in RESPONSE_LEVELS or prev_response == "Verify data: no machine action":
        final_response = candidate_response
        consec_count = 0
        pending_resp = None
    elif immediate_escalation:
        final_response = "Safe stop (recommend)"
        consec_count = 0
        pending_resp = None
    elif cand_level > curr_level:
        # Escalation path: requires HYSTERESIS_ESCALATE_COUNT (3) consecutive readings
        if pending_resp == candidate_response:
            consec_count += 1
        else:
            pending_resp = candidate_response
            consec_count = 1

        if consec_count >= HYSTERESIS_ESCALATE_COUNT:
            final_response = candidate_response
            pending_resp = None
            consec_count = 0
    elif cand_level < curr_level:
        # De-escalation path: requires HYSTERESIS_STEPDOWN_COUNT (10) consecutive readings
        if pending_resp == candidate_response:
            consec_count += 1
        else:
            pending_resp = candidate_response
            consec_count = 1

        if consec_count >= HYSTERESIS_STEPDOWN_COUNT:
            final_response = candidate_response
            pending_resp = None
            consec_count = 0
    else:
        # Candidate level equals current level
        pending_resp = None
        consec_count = 0
        final_response = candidate_response

    # Map final response to severity rating
    severity_map = {
        "OK": "LOW",
        "Watch": "LOW",
        "Warn": "MEDIUM",
        "Reduce load (recommend)": "HIGH",
        "Safe stop (recommend)": "CRITICAL",
        "Verify data: no machine action": "HIGH"
    }
    severity = severity_map.get(final_response, "LOW")

    # Update persistent machine state
    new_state = {
        "current_verdict": verdict,
        "current_response": final_response,
        "pending_response": pending_resp,
        "consecutive_count": consec_count,
        "high_fault_consecutive": high_fault_consec
    }
    set_machine_state(machine_id, new_state, db_path=db_path)

    # Log verdict/response change if changed
    if verdict != prev_verdict or final_response != prev_response:
        save_verdict_change(
            machine_id, prev_verdict, verdict, prev_response, final_response, reasons, db_path=db_path
        )

    # Save to verdicts table
    save_verdict(machine_id, verdict, final_response, severity, reasons, inputs_used, db_path=db_path)

    return {
        "verdict": verdict,
        "response": final_response,
        "severity": severity,
        "reasons": reasons,
        "inputs_used": inputs_used
    }
