import math
from typing import Dict, Any, Tuple, List

class PhysicsValidator:
    """
    Applies fundamental physical laws (thermodynamics and mechanics) to detect
    sensor spoofing, impossible readings, and data integrity violations.
    """
    def __init__(self):
        # Physics bounds
        self.MIN_AIR_TEMP_K = 273.15  # 0 C
        self.MAX_AIR_TEMP_K = 340.0   # 66.85 C
        self.MIN_RPM = 500.0
        self.MAX_RPM = 3500.0
        self.MIN_TORQUE = 0.0
        self.MAX_TORQUE = 150.0

    def verify(self, telemetry: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Runs comprehensive thermodynamic and mechanical consistency checks.
        Returns: (all_passed, list_of_findings)
        """
        findings: List[str] = []
        air_t = telemetry.get("air_temperature_k")
        proc_t = telemetry.get("process_temperature_k")
        rpm = telemetry.get("rotational_speed_rpm")
        torque = telemetry.get("torque_nm")
        calc_power = telemetry.get("calculated_power_w")

        if any(v is None for v in [air_t, proc_t, rpm, torque]):
            return False, ["Missing core physical dimensions in telemetry packet"]

        # 1. 2nd Law of Thermodynamics: In an operational machine dissipated work creates heat.
        # Process Temperature cannot fall below Ambient Air Temperature when running.
        if proc_t < air_t:
            findings.append(
                f"Thermodynamic Violation: Process Temp ({proc_t:.1f} K) < Ambient Air Temp ({air_t:.1f} K). "
                f"Negative thermal gradient is physically impossible for operating machinery."
            )
        
        # Check for absurd thermal difference (> 45 K without extreme failure)
        delta_t = proc_t - air_t
        if delta_t > 45.0:
            findings.append(f"Abnormal Thermal Disparity: Delta T = {delta_t:.1f} K exceeds physical dissipation limits.")

        # 2. Operating Envelope Boundary Checks
        if not (self.MIN_AIR_TEMP_K <= air_t <= self.MAX_AIR_TEMP_K):
            findings.append(f"Air Temperature {air_t:.1f} K out of physical atmospheric bounds [{self.MIN_AIR_TEMP_K}, {self.MAX_AIR_TEMP_K}]")

        if not (self.MIN_RPM <= rpm <= self.MAX_RPM):
            findings.append(f"Rotational Speed {rpm:.1f} RPM out of physical drive limits [{self.MIN_RPM}, {self.MAX_RPM}]")

        if not (self.MIN_TORQUE <= torque <= self.MAX_TORQUE):
            findings.append(f"Torque {torque:.1f} Nm out of transducer range [{self.MIN_TORQUE}, {self.MAX_TORQUE}]")

        # 3. Mechanical Power Law: Power = Torque * Omega = Torque * (2 * pi * RPM / 60)
        omega = (2.0 * math.pi * rpm) / 60.0
        expected_power = torque * omega
        
        if calc_power is not None:
            power_diff = abs(calc_power - expected_power)
            # Allow max 10% tolerance for numerical rounding/efficiency
            allowed_tol = max(50.0, 0.10 * expected_power)
            if power_diff > allowed_tol:
                findings.append(
                    f"Mechanical Power Law Violation: Reported Power ({calc_power:.1f} W) deviates from "
                    f"Torque x Angular Speed ({expected_power:.1f} W) by {power_diff:.1f} W."
                )

        if len(findings) == 0:
            return True, ["Physical laws verified: Thermodynamic gradient and power laws conformant"]
        else:
            return False, findings
