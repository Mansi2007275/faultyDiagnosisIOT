import math
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

@dataclass
class FaultReport:
    has_fault: bool
    fault_types: List[str] # List of triggered faults e.g. ['TWF', 'HDF']
    twf_triggered: bool
    hdf_triggered: bool
    pwf_triggered: bool
    osf_triggered: bool
    rnf_triggered: bool
    health_index: float # 0.0 to 100.0 (100 = Brand New / Perfect)
    metrics: Dict[str, Any] = field(default_factory=dict)
    rule_details: List[str] = field(default_factory=list)

class FaultRuleEngine:
    """
    Expert Rule-Based Diagnostics Engine based on the AI4I 2020 Predictive Maintenance standard.
    Detects 5 canonical physical failure modes:
    1. Tool Wear Failure (TWF)
    2. Heat Dissipation Failure (HDF)
    3. Power Failure (PWF)
    4. Overstrain Failure (OSF)
    5. Random Failures (RNF)
    """
    def __init__(self):
        # AI4I standard thresholds
        self.TWF_WARN_THRESHOLD = 180.0 # minutes
        self.TWF_FAIL_THRESHOLD = 235.0 # minutes
        self.HDF_DELTA_T_LIMIT = 8.6    # Kelvin
        self.HDF_RPM_LIMIT = 1380.0     # RPM
        self.PWF_MIN_POWER = 3500.0     # Watts
        self.PWF_MAX_POWER = 9000.0     # Watts
        self.OSF_THRESHOLDS = {
            "L": 11000.0, # min * Nm
            "M": 12000.0,
            "H": 13000.0
        }

    def evaluate(self, telemetry: Dict[str, Any]) -> FaultReport:
        """
        Evaluates incoming telemetry against predictive maintenance physics rules.
        """
        air_t = telemetry.get("air_temperature_k", 300.0)
        proc_t = telemetry.get("process_temperature_k", 310.0)
        rpm = telemetry.get("rotational_speed_rpm", 1500.0)
        torque = telemetry.get("torque_nm", 40.0)
        tool_wear = telemetry.get("tool_wear_min", 0.0)
        mtype = telemetry.get("machine_type", "M").upper()
        vibration = telemetry.get("vibration_rms_mms", 1.2)

        # 1. Calculate derived engineering features
        delta_t = proc_t - air_t
        rad_s = (2.0 * math.pi * rpm) / 60.0
        power_w = torque * rad_s
        overstrain_product = tool_wear * torque
        osf_limit = self.OSF_THRESHOLDS.get(mtype, 12000.0)

        fault_types: List[str] = []
        rule_details: List[str] = []

        # Rule 1: TWF (Tool Wear Failure)
        twf = False
        if tool_wear >= self.TWF_FAIL_THRESHOLD:
            twf = True
            fault_types.append("TWF")
            rule_details.append(f"TWF (Tool Wear Failure): Tool wear {tool_wear:.1f} min exceeds threshold of {self.TWF_FAIL_THRESHOLD} min.")
        elif tool_wear >= self.TWF_WARN_THRESHOLD:
            rule_details.append(f"TWF Warning: Tool wear {tool_wear:.1f} min approaching replacement limit ({self.TWF_FAIL_THRESHOLD} min).")

        # Rule 2: HDF (Heat Dissipation Failure)
        # Occurs when thermal gradient delta_T < 8.6 K and RPM < 1380
        hdf = False
        if delta_t < self.HDF_DELTA_T_LIMIT and rpm < self.HDF_RPM_LIMIT:
            hdf = True
            fault_types.append("HDF")
            rule_details.append(
                f"HDF (Heat Dissipation Failure): Temperature difference delta_T = {delta_t:.1f} K (< {self.HDF_DELTA_T_LIMIT} K) "
                f"at low rotational speed {rpm:.1f} RPM (< {self.HDF_RPM_LIMIT} RPM). Heat is not dissipating correctly."
            )

        # Rule 3: PWF (Power Failure)
        # Occurs when calculated power is outside safe operational envelope (< 3500W or > 9000W)
        pwf = False
        if power_w < self.PWF_MIN_POWER:
            pwf = True
            fault_types.append("PWF")
            rule_details.append(f"PWF (Power Underflow Failure): Delivered power {power_w:.1f} W is below safe operating floor of {self.PWF_MIN_POWER} W.")
        elif power_w > self.PWF_MAX_POWER:
            pwf = True
            fault_types.append("PWF")
            rule_details.append(f"PWF (Power Overload Failure): Delivered power {power_w:.1f} W exceeds maximum motor capacity of {self.PWF_MAX_POWER} W.")

        # Rule 4: OSF (Overstrain Failure)
        # Occurs when Tool Wear * Torque exceeds product rating for machine type
        osf = False
        if overstrain_product > osf_limit:
            osf = True
            fault_types.append("OSF")
            rule_details.append(
                f"OSF (Overstrain Failure): Wear x Torque product ({overstrain_product:.1f} min*Nm) "
                f"exceeds Type-{mtype} limit ({osf_limit:.1f} min*Nm)."
            )

        # Rule 5: RNF (Random Failure) - e.g. acute vibration spike or bearing seizure
        rnf = False
        if vibration > 4.5:
            rnf = True
            fault_types.append("RNF")
            rule_details.append(f"RNF (Random Failure): Extreme vibration anomaly {vibration:.2f} mm/s indicates acute mechanical imbalance/bearing shock.")

        # Calculate composite Health Index (0 - 100%)
        # Base starts at 100, degraded by tool wear, thermal strain, power deviation, vibration
        wear_penalty = min(35.0, (tool_wear / 250.0) * 35.0)
        vib_penalty = min(25.0, max(0.0, (vibration - 1.2) * 8.0))
        power_penalty = 0.0
        if power_w < self.PWF_MIN_POWER or power_w > self.PWF_MAX_POWER:
            power_penalty = 30.0
        elif power_w > 8000.0 or power_w < 4200.0:
            power_penalty = 15.0

        health_index = max(0.0, 100.0 - wear_penalty - vib_penalty - power_penalty)
        if len(fault_types) > 0:
            health_index = min(health_index, 35.0)

        metrics = {
            "delta_t_k": round(delta_t, 2),
            "power_w": round(power_w, 2),
            "overstrain_product": round(overstrain_product, 2),
            "osf_limit": osf_limit,
            "vibration_rms": round(vibration, 3)
        }

        return FaultReport(
            has_fault=len(fault_types) > 0,
            fault_types=fault_types,
            twf_triggered=twf,
            hdf_triggered=hdf,
            pwf_triggered=pwf,
            osf_triggered=osf,
            rnf_triggered=rnf,
            health_index=round(health_index, 1),
            metrics=metrics,
            rule_details=rule_details
        )
