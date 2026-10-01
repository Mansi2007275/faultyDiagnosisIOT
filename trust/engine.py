from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from trust.signature import SignatureValidator
from trust.replay import ReplayDetector
from trust.physics import PhysicsValidator
from trust.stuck_sensor import StuckSensorDetector
from trust.reputation import ReputationEngine

class TrustVerdict(str, Enum):
    TRUSTED = "TRUSTED"
    SUSPICIOUS = "SUSPICIOUS"
    REJECTED = "REJECTED"
    HELD = "HELD"  # For Quarantined devices

@dataclass
class TrustReport:
    is_trusted: bool
    verdict: TrustVerdict
    trust_score: float # 0.0 to 100.0
    signature_valid: bool
    replay_valid: bool
    physics_valid: bool
    sensor_healthy: bool
    signature_msg: str
    replay_msg: str
    physics_findings: List[str] = field(default_factory=list)
    sensor_findings: List[str] = field(default_factory=list)
    failure_reasons: List[str] = field(default_factory=list)
    reputation_score: int = 100
    reputation_state: str = "Trusted"
    is_held: bool = False

class TrustEngine:
    """
    Central Zero-Trust evaluation orchestrator for industrial edge telemetry.
    Aggregates Cryptographic, Anti-Replay, Physical Laws, Sensor Variance, and Device Reputation checks.
    """
    def __init__(self, rep_engine: Optional[ReputationEngine] = None):
        self.signature_val = SignatureValidator()
        self.replay_det = ReplayDetector()
        self.physics_val = PhysicsValidator()
        self.stuck_det = StuckSensorDetector()
        self.rep_engine = rep_engine or ReputationEngine()

    def evaluate(self, telemetry: Dict[str, Any]) -> TrustReport:
        """
        Executes all trust checks, updates device reputation, and produces an aggregated TrustReport.
        """
        machine_id = str(telemetry.get("machine_id", "M_001"))

        # 0. Reputation check - Revoked device check
        rep = self.rep_engine.get_reputation(machine_id)
        if rep["state"] == "Revoked":
            return TrustReport(
                is_trusted=False,
                verdict=TrustVerdict.REJECTED,
                trust_score=0.0,
                signature_valid=False,
                replay_valid=False,
                physics_valid=False,
                sensor_healthy=False,
                signature_msg="Device REVOKED",
                replay_msg="Device REVOKED",
                failure_reasons=["[Reputation] Device is REVOKED by Admin - all telemetry rejected"],
                reputation_score=0,
                reputation_state="Revoked",
                is_held=False
            )

        # 0.1 Flood check
        is_flood, msg_rate = self.rep_engine.check_flood(machine_id)

        # 1. Cryptographic Signature (Weight: 30 pts)
        sig_ok, sig_msg = self.signature_val.verify(telemetry)

        # 2. Anti-Replay & Sequence (Weight: 25 pts)
        rep_ok, rep_msg = self.replay_det.verify(telemetry)

        # 3. Thermodynamics & Physics Consistency (Weight: 25 pts)
        phy_ok, phy_findings = self.physics_val.verify(telemetry)

        # 4. Stuck Sensor / Variance (Weight: 20 pts)
        stuck_ok, stuck_findings = self.stuck_det.verify(telemetry)

        # Record reputation events/penalties
        if not sig_ok:
            rep = self.rep_engine.record_security_event(machine_id, "tampered signature", severity="HIGH", reason=sig_msg)
        if not rep_ok:
            rep = self.rep_engine.record_security_event(machine_id, "replay", severity="HIGH", reason=rep_msg)
        if not phy_ok:
            rep = self.rep_engine.record_security_event(machine_id, "physics broken", severity="MEDIUM", reason="; ".join(phy_findings))
        if not stuck_ok:
            rep = self.rep_engine.record_security_event(machine_id, "stuck/silent sensor", severity="LOW", reason="; ".join(stuck_findings))

        if sig_ok and rep_ok and phy_ok and stuck_ok and not is_flood:
            rep = self.rep_engine.record_clean_reading(machine_id)

        # Calculate composite score
        score = 0.0
        if sig_ok:
            score += 30.0
        if rep_ok:
            score += 25.0
        if phy_ok:
            score += 25.0
        if stuck_ok:
            score += 20.0

        failure_reasons = []
        if is_flood:
            failure_reasons.append(f"[Flood] Message rate {msg_rate}/min exceeds threshold")
        if not sig_ok:
            failure_reasons.append(f"[Crypto] {sig_msg}")
        if not rep_ok:
            failure_reasons.append(f"[Replay] {rep_msg}")
        if not phy_ok:
            for pf in phy_findings:
                failure_reasons.append(f"[Physics] {pf}")
        if not stuck_ok:
            for sf in stuck_findings:
                failure_reasons.append(f"[Sensor] {sf}")

        is_quarantined = (rep["state"] == "Quarantined")

        # Determine verdict
        if is_quarantined:
            verdict = TrustVerdict.HELD
            is_trusted = False
            failure_reasons.append("[Reputation] Device is QUARANTINED - readings held")
        elif score >= 90.0 and sig_ok and rep_ok and phy_ok and not is_flood:
            verdict = TrustVerdict.TRUSTED
            is_trusted = True
        elif score >= 50.0:
            verdict = TrustVerdict.SUSPICIOUS
            is_trusted = False
        else:
            verdict = TrustVerdict.REJECTED
            is_trusted = False

        return TrustReport(
            is_trusted=is_trusted,
            verdict=verdict,
            trust_score=score,
            signature_valid=sig_ok,
            replay_valid=rep_ok,
            physics_valid=phy_ok,
            sensor_healthy=stuck_ok,
            signature_msg=sig_msg,
            replay_msg=rep_msg,
            physics_findings=phy_findings,
            sensor_findings=stuck_findings,
            failure_reasons=failure_reasons,
            reputation_score=rep["score"],
            reputation_state=rep["state"],
            is_held=is_quarantined
        )

    def reset_all(self):
        self.replay_det.reset_all()
        self.stuck_det.reset_all()
