import time
import math
import hashlib
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional

class VirtualMachine:
    """
    Simulates an individual physical asset / machine sensor node.
    Can replay historical dataset records (AI4I 2020) or generate synthetic physics telemetry.
    Signs all data packets with device cryptographic keys.
    """
    def __init__(
        self,
        machine_id: str,
        name: str,
        machine_type: str = "M",
        base_air_temp: float = 300.0,
        base_rpm: float = 1500.0,
        base_torque: float = 40.0,
        wear_rate: float = 0.05,
        dataset_df: Optional[pd.DataFrame] = None
    ):
        self.machine_id = machine_id
        self.name = name
        self.machine_type = machine_type  # 'L', 'M', or 'H'
        
        # Operational baseline parameters
        self.base_air_temp = base_air_temp
        self.base_rpm = base_rpm
        self.base_torque = base_torque
        self.wear_rate = wear_rate
        
        # Dataset replay buffer (subset matching machine_type if available)
        self.dataset_df = dataset_df
        self.dataset_cursor: int = 0
        self._type_subset: Optional[pd.DataFrame] = None
        if dataset_df is not None and not dataset_df.empty:
            match = dataset_df[dataset_df["type"] == machine_type]
            self._type_subset = match if not match.empty else dataset_df

        # Dynamic state
        self.sequence_id: int = 0
        self.tool_wear: float = float(np.random.uniform(10.0, 50.0))
        self.current_rpm: float = base_rpm
        self.current_torque: float = base_torque
        self.current_air_temp: float = base_air_temp
        self.current_process_temp: float = base_air_temp + 10.0
        self.current_vibration_rms: float = 1.2 # mm/s
        
        # Cryptographic key (simulated device key for HMAC/SHA256 signature)
        self.device_secret = f"dev-secret-key-{machine_id}-{machine_type}-2026"
        self.public_key_id = f"PK-DEV-{hashlib.md5(machine_id.encode()).hexdigest()[:8].upper()}"
        
        # Fault injection overrides (if manually forced)
        self.forced_fault_mode: Optional[str] = None

    def set_dataset(self, df: pd.DataFrame):
        """Sets or updates the real dataset for replay."""
        self.dataset_df = df
        match = df[df["type"] == self.machine_type]
        self._type_subset = match if not match.empty else df
        self.dataset_cursor = 0

    def tick(self, dt_seconds: float = 1.0) -> Dict[str, Any]:
        """
        Advances the virtual machine by one simulation step.
        If real dataset rows are present, steps through dataset rows and signs the packet.
        """
        self.sequence_id += 1
        now = time.time()
        
        if self._type_subset is not None and len(self._type_subset) > 0:
            # Replay from real dataset
            row = self._type_subset.iloc[self.dataset_cursor % len(self._type_subset)]
            self.dataset_cursor += 1
            
            self.current_air_temp = float(row.get("air_k", 300.0))
            self.current_process_temp = float(row.get("proc_k", 310.0))
            self.current_rpm = float(row.get("rpm", 1500.0))
            self.current_torque = float(row.get("torque", 40.0))
            self.tool_wear = float(row.get("wear", 0.0))
            self.current_vibration_rms = float(1.2 + (self.tool_wear / 200.0) * 1.5)
            calc_power = float(row.get("power_w", self.current_torque * (2 * math.pi * self.current_rpm / 60)))
        else:
            # Synthetic continuous generation
            self.current_air_temp = self.base_air_temp + 1.2 * math.sin(self.sequence_id * 0.05) + float(np.random.normal(0, 0.2))
            rpm_fluctuation = float(np.random.normal(0, 15.0))
            self.current_rpm = float(np.clip(self.base_rpm + rpm_fluctuation, 1100.0, 2800.0))
            
            target_power = 6500.0 + 300.0 * math.sin(self.sequence_id * 0.03)
            rad_s = (2.0 * math.pi * self.current_rpm) / 60.0
            self.current_torque = float(np.clip((target_power / rad_s) + np.random.normal(0, 1.2), 10.0, 75.0))
            
            self.tool_wear += self.wear_rate * dt_seconds
            thermal_dissipation = 9.5 + (self.tool_wear * 0.015) + float(np.random.normal(0, 0.25))
            self.current_process_temp = float(self.current_air_temp + thermal_dissipation)
            self.current_vibration_rms = float(1.2 + (self.tool_wear / 200.0) * 2.5 + np.random.normal(0, 0.1))
            calc_power = self.current_torque * rad_s

        # Handle forced fault modes if manually set
        if self.forced_fault_mode == "TWF":
            self.tool_wear = max(self.tool_wear, 245.0)
        elif self.forced_fault_mode == "HDF":
            self.current_process_temp = self.current_air_temp + 5.0
            self.current_rpm = 1250.0
        elif self.forced_fault_mode == "PWF":
            self.current_torque = 78.0
            self.current_rpm = 2500.0
        elif self.forced_fault_mode == "OSF":
            self.tool_wear = 220.0
            self.current_torque = 65.0

        rad_s_actual = (2.0 * math.pi * self.current_rpm) / 60.0
        calc_power_actual = self.current_torque * rad_s_actual

        payload = {
            "machine_id": self.machine_id,
            "machine_type": self.machine_type,
            "sequence_id": self.sequence_id,
            "timestamp": now,
            "air_temperature_k": round(self.current_air_temp, 2),
            "process_temperature_k": round(self.current_process_temp, 2),
            "rotational_speed_rpm": round(self.current_rpm, 1),
            "torque_nm": round(self.current_torque, 2),
            "tool_wear_min": round(self.tool_wear, 1),
            "vibration_rms_mms": round(self.current_vibration_rms, 3),
            "calculated_power_w": round(calc_power_actual, 2)
        }
        
        # Generate cryptographic signature
        payload["signature"] = self._sign_payload(payload)
        payload["public_key_id"] = self.public_key_id
        
        return payload

    def _sign_payload(self, payload: Dict[str, Any]) -> str:
        """Signs telemetry payload with device secret via HMAC-SHA256."""
        canonical_str = (
            f"{payload['machine_id']}|{payload['sequence_id']}|{payload['timestamp']:.3f}|"
            f"{payload['air_temperature_k']:.2f}|{payload['process_temperature_k']:.2f}|"
            f"{payload['rotational_speed_rpm']:.1f}|{payload['torque_nm']:.2f}|"
            f"{payload['tool_wear_min']:.1f}|{self.device_secret}"
        )
        return hashlib.sha256(canonical_str.encode()).hexdigest()

    def reset(self):
        """Resets the virtual machine state."""
        self.sequence_id = 0
        self.dataset_cursor = 0
        self.tool_wear = float(np.random.uniform(5.0, 25.0))
        self.forced_fault_mode = None


class MachineFleet:
    """
    Manages a fleet of virtual machines in the industrial plant.
    """
    def __init__(self, dataset_df: Optional[pd.DataFrame] = None):
        self.machines: Dict[str, VirtualMachine] = {}
        self.dataset_df = dataset_df
        self._initialize_default_fleet()

    def _initialize_default_fleet(self):
        fleet_configs = [
            ("VM-CNC-01", "High-Precision CNC Milling Center", "L", 298.5, 1540.0, 39.5, 0.04),
            ("VM-HYD-02", "Heavy Hydraulic Stamping Press", "M", 300.2, 1380.0, 48.0, 0.06),
            ("VM-TURB-03", "Gas Cogeneration Turbine Gen-3", "H", 301.8, 2100.0, 32.0, 0.03),
            ("VM-LTH-04", "Automated Multi-Axis Lathe Cell", "L", 299.0, 1620.0, 36.5, 0.05),
        ]
        for mid, name, mtype, air_t, rpm, torque, wear in fleet_configs:
            self.machines[mid] = VirtualMachine(
                machine_id=mid,
                name=name,
                machine_type=mtype,
                base_air_temp=air_t,
                base_rpm=rpm,
                base_torque=torque,
                wear_rate=wear,
                dataset_df=self.dataset_df
            )

    def set_fleet_dataset(self, df: pd.DataFrame):
        self.dataset_df = df
        for vm in self.machines.values():
            vm.set_dataset(df)

    def get_machine(self, machine_id: str) -> Optional[VirtualMachine]:
        return self.machines.get(machine_id)

    def get_all_machines(self) -> List[VirtualMachine]:
        return list(self.machines.values())

    def tick_all(self) -> Dict[str, Dict[str, Any]]:
        return {mid: vm.tick() for mid, vm in self.machines.items()}
