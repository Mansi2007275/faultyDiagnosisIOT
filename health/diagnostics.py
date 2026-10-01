from enum import Enum
from typing import Dict, Any, List
from dataclasses import dataclass

from health.fault_rules import FaultRuleEngine, FaultReport

class HealthSeverity(str, Enum):
    NOMINAL = "NOMINAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"

class ResponseAction(str, Enum):
    WATCH = "Watch (Continuous Monitoring)"
    WARN = "Warn (Schedule Inspection)"
    REDUCE_LOAD = "Reduce Load (Derate Operating Speed by 30%)"
    SAFE_STOP = "Safe Stop (Immediate Controlled Shutdown)"

@dataclass
class DiagnosticVerdict:
    severity: HealthSeverity
    action: ResponseAction
    fault_report: FaultReport
    primary_fault: str
    summary_text: str
    recommended_steps: List[str]

class DiagnosticsEngine:
    """
    Synthesizes rule evaluation, severity grading, and response ladder triggers.
    """
    def __init__(self):
        self.rule_engine = FaultRuleEngine()

    def diagnose(self, telemetry: Dict[str, Any]) -> DiagnosticVerdict:
        """
        Runs diagnostic evaluation and produces the actionable maintenance verdict.
        """
        report = self.rule_engine.evaluate(telemetry)
        
        # Determine Severity and Response Ladder
        if not report.has_fault:
            if report.health_index >= 85.0:
                severity = HealthSeverity.NOMINAL
                action = ResponseAction.WATCH
                primary_fault = "None (System Healthy)"
                summary_text = "All physical operational parameters are within nominal safety envelopes."
                steps = ["Maintain standard continuous monitoring cycle.", "Log routine telemetry batch to ledger."]
            else:
                severity = HealthSeverity.WARNING
                action = ResponseAction.WARN
                primary_fault = "Wear / Thermal Creep"
                summary_text = f"Degradation detected: Health index at {report.health_index}%. Pre-fault operating conditions."
                steps = ["Inspect tool wear tooling on next maintenance window.", "Verify coolant flow and ambient ventilation."]
        else:
            primary_fault = ", ".join(report.fault_types)
            # Check critical failure triggers
            if "OSF" in report.fault_types or "RNF" in report.fault_types or "PWF" in report.fault_types:
                severity = HealthSeverity.EMERGENCY
                action = ResponseAction.SAFE_STOP
                summary_text = f"EMERGENCY: Catastrophic failure risk [{primary_fault}] detected. Automated safe shutdown recommended."
                steps = [
                    "Trigger automated soft-stop sequence to prevent spindle/stator destruction.",
                    "Isolate machine electrical feed and lock out tag out (LOTO).",
                    "Disclose signed audit evidence bundle to maintenance supervisor."
                ]
            elif "HDF" in report.fault_types:
                severity = HealthSeverity.CRITICAL
                action = ResponseAction.REDUCE_LOAD
                summary_text = "CRITICAL: Heat Dissipation Failure (HDF) detected. Cooling failure at active torque."
                steps = [
                    "Derate motor rotational speed by 30% immediately to shed thermal load.",
                    "Check coolant lines, heat exchanger fans, and thermal paste.",
                    "Schedule urgent inspection before next production batch."
                ]
            else: # TWF
                severity = HealthSeverity.CRITICAL
                action = ResponseAction.REDUCE_LOAD
                summary_text = "CRITICAL: Tool Wear Failure (TWF) threshold reached. Severe insert degradation."
                steps = [
                    "Reduce machining feed rate and feed pressure.",
                    "Prepare replacement cutting insert and toolholder.",
                    "Queue tool changeover sequence."
                ]

        return DiagnosticVerdict(
            severity=severity,
            action=action,
            fault_report=report,
            primary_fault=primary_fault,
            summary_text=summary_text,
            recommended_steps=steps
        )
