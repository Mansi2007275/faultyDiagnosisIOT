"""
Zero-Trust Verification Engine for Industrial Telemetry.
Validates cryptographic signatures, detects replay attacks, 
verifies thermodynamic/mechanical physical laws, and detects stuck sensors.
"""
from trust.signature import SignatureValidator
from trust.replay import ReplayDetector
from trust.physics import PhysicsValidator
from trust.stuck_sensor import StuckSensorDetector
from trust.reputation import ReputationEngine

__all__ = [
    "SignatureValidator",
    "ReplayDetector",
    "PhysicsValidator",
    "StuckSensorDetector",
    "TrustEngine",
    "TrustVerdict",
    "TrustReport",
    "ReputationEngine"
]
