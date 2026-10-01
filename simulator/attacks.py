import copy
import time
from enum import Enum
from typing import Dict, Any, Optional, List

class AttackType(str, Enum):
    NONE = "NONE"
    SIGNATURE_TAMPERING = "SIGNATURE_TAMPERING"
    REPLAY_ATTACK = "REPLAY_ATTACK"
    PHYSICS_VIOLATION = "PHYSICS_VIOLATION"
    STUCK_SENSOR = "STUCK_SENSOR"
    DRIFT_BIAS = "DRIFT_BIAS"
    HONEYPOT = "HONEYPOT"
    FLOOD = "FLOOD"

class AttackEngine:
    """
    Simulates malicious cyber attacks, MITM tampering, replay injections,
    and sensor hardware faults for testing the Zero-Trust verification engine.
    """
    def __init__(self):
        self.active_attacks: Dict[str, AttackType] = {}
        self.attack_parameters: Dict[str, Dict[str, Any]] = {}
        self.stuck_cache: Dict[str, Dict[str, Any]] = {}
        self.replay_cache: Dict[str, List[Dict[str, Any]]] = {}
        self.drift_accumulators: Dict[str, float] = {}

    def set_attack(self, machine_id: str, attack_type: AttackType, params: Optional[Dict[str, Any]] = None):
        """Activates an attack mode for a specific machine."""
        self.active_attacks[machine_id] = attack_type
        self.attack_parameters[machine_id] = params or {}
        if attack_type != AttackType.DRIFT_BIAS:
            self.drift_accumulators[machine_id] = 0.0

    def clear_attack(self, machine_id: str):
        """Clears any active attack on a machine."""
        self.active_attacks.pop(machine_id, None)
        self.attack_parameters.pop(machine_id, None)
        self.drift_accumulators.pop(machine_id, None)

    def clear_all(self):
        """Clears all active attacks across the fleet."""
        self.active_attacks.clear()
        self.attack_parameters.clear()
        self.drift_accumulators.clear()
        self.stuck_cache.clear()

    def apply_attack(self, raw_telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Intercepts raw telemetry packet and mutates it if an attack is active.
        Returns the (possibly mutated) telemetry packet with attack metadata attached.
        """
        machine_id = raw_telemetry.get("machine_id", "UNKNOWN")
        attack_type = self.active_attacks.get(machine_id, AttackType.NONE)
        params = self.attack_parameters.get(machine_id, {})
        
        telemetry = copy.deepcopy(raw_telemetry)
        telemetry["_attack_injected"] = attack_type.value
        
        # Maintain replay buffer for replay attacks
        if machine_id not in self.replay_cache:
            self.replay_cache[machine_id] = []
        self.replay_cache[machine_id].append(copy.deepcopy(raw_telemetry))
        if len(self.replay_cache[machine_id]) > 50:
            self.replay_cache[machine_id].pop(0)

        if attack_type == AttackType.NONE:
            return telemetry

        elif attack_type == AttackType.SIGNATURE_TAMPERING:
            # Modify sensor reading after signature was generated OR corrupt the signature
            tamper_mode = params.get("mode", "payload_tampering")
            if tamper_mode == "payload_tampering":
                # Stealthily change temperature by +20 K without updating the signature
                telemetry["process_temperature_k"] = round(telemetry["process_temperature_k"] + 25.0, 2)
            else:
                # Invert signature hash
                sig = telemetry.get("signature", "")
                telemetry["signature"] = sig[::-1] if sig else "000000000000000000000000000000000000000000000000000000000000dead"
            telemetry["_attack_details"] = "Data packet payload was modified without valid cryptographic re-signing."

        elif attack_type == AttackType.REPLAY_ATTACK:
            # Resend a packet captured 15-30 cycles ago
            buf = self.replay_cache.get(machine_id, [])
            if len(buf) >= 5:
                idx = max(0, len(buf) - params.get("lag_steps", 10))
                stale_packet = copy.deepcopy(buf[idx])
                # Keep current transport wrapper but stale content / sequence
                stale_packet["_attack_injected"] = attack_type.value
                stale_packet["_attack_details"] = f"Stale telemetry packet (Seq #{stale_packet.get('sequence_id')}) replayed."
                return stale_packet
            else:
                # If buffer too small, rewind sequence_id
                telemetry["sequence_id"] = max(1, telemetry["sequence_id"] - 12)
                telemetry["timestamp"] = time.time() - 3600.0
                telemetry["_attack_details"] = "Stale sequence number and expired timestamp replayed."

        elif attack_type == AttackType.PHYSICS_VIOLATION:
            # Violate 2nd Law of Thermodynamics: Process temp colder than ambient air temp,
            # or power violation: high torque & rpm with zero power
            violation_type = params.get("violation", "thermal_inversion")
            if violation_type == "thermal_inversion":
                # Process Temp < Air Temp (Impossible in running motor)
                telemetry["air_temperature_k"] = 305.0
                telemetry["process_temperature_k"] = 285.0 # -20 K below ambient
                telemetry["_attack_details"] = "Thermodynamic Inversion: Process Temp (285K) < Air Temp (305K)."
            elif violation_type == "power_torque_mismatch":
                # Report high torque and high rpm but zero calculated power
                telemetry["rotational_speed_rpm"] = 2400.0
                telemetry["torque_nm"] = 65.0
                telemetry["calculated_power_w"] = 150.0 # Physics law dictates ~16,336 W
                telemetry["_attack_details"] = "Mechanical Power Violation: Reported power (150W) contradicts (Torque x Speed) (16.3kW)."

        elif attack_type == AttackType.STUCK_SENSOR:
            # Freeze sensor readings across consecutive packets
            if machine_id not in self.stuck_cache:
                self.stuck_cache[machine_id] = copy.deepcopy(raw_telemetry)
            
            cached = self.stuck_cache[machine_id]
            frozen_sensor = params.get("sensor", "process_temperature_k")
            if frozen_sensor == "all":
                for k in ["air_temperature_k", "process_temperature_k", "rotational_speed_rpm", "torque_nm", "vibration_rms_mms"]:
                    telemetry[k] = cached[k]
            else:
                telemetry[frozen_sensor] = cached[frozen_sensor]
            
            telemetry["_attack_details"] = f"Sensor frozen/stuck: '{frozen_sensor}' has zero variance across frames."

        elif attack_type == AttackType.DRIFT_BIAS:
            # Gradual stealthy sensor drift
            drift = self.drift_accumulators.get(machine_id, 0.0) + params.get("drift_rate", 0.8)
            self.drift_accumulators[machine_id] = drift
            telemetry["process_temperature_k"] = round(telemetry["process_temperature_k"] + drift, 2)
            telemetry["_attack_details"] = f"Stealthy bias drift: +{drift:.2f}K accumulated offset."

        return telemetry
