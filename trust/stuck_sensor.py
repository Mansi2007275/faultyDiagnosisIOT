import numpy as np
from typing import Dict, Any, List, Tuple

class StuckSensorDetector:
    """
    Detects frozen, pinned, or stuck analog sensors by analyzing rolling variance 
    and repeated identical floating point readings across consecutive sampling cycles.
    """
    def __init__(self, window_size: int = 8, min_variance_threshold: float = 1e-4):
        self.window_size = window_size
        self.min_variance_threshold = min_variance_threshold
        # Maps machine_id -> list of historical telemetry dicts
        self.history: Dict[str, List[Dict[str, Any]]] = {}

    def verify(self, telemetry: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Appends current telemetry to rolling window and tests for frozen variance.
        Returns: (is_healthy, findings)
        """
        machine_id = telemetry.get("machine_id", "UNKNOWN")
        if machine_id not in self.history:
            self.history[machine_id] = []

        # Store a lightweight copy
        self.history[machine_id].append({
            "air_t": telemetry.get("air_temperature_k", 0.0),
            "proc_t": telemetry.get("process_temperature_k", 0.0),
            "rpm": telemetry.get("rotational_speed_rpm", 0.0),
            "torque": telemetry.get("torque_nm", 0.0),
            "vib": telemetry.get("vibration_rms_mms", 0.0)
        })

        if len(self.history[machine_id]) > self.window_size:
            self.history[machine_id].pop(0)

        # Need at least 4 readings to assess stuck sensor
        if len(self.history[machine_id]) < 4:
            return True, ["Calibrating rolling sensor variance buffer..."]

        findings = []
        samples = self.history[machine_id]
        
        sensor_keys = {
            "air_t": "Ambient Air Temperature",
            "proc_t": "Process Temperature",
            "rpm": "Rotational Speed (RPM)",
            "torque": "Torque Sensor",
            "vib": "Vibration Transducer"
        }

        for key, name in sensor_keys.items():
            vals = [s[key] for s in samples]
            std = float(np.std(vals))
            # If all values in window are bitwise identical or standard deviation is zero
            all_identical = len(set(vals)) == 1
            
            if all_identical or (std < self.min_variance_threshold and len(samples) >= self.window_size):
                findings.append(f"Stuck Sensor Detected: '{name}' reading is completely frozen across {len(samples)} consecutive frames (val={vals[-1]}, std={std:.6f}).")

        if len(findings) == 0:
            return True, ["Sensor variance nominal: Dynamic physical analog noise detected"]
        else:
            return False, findings

    def reset_machine(self, machine_id: str):
        self.history.pop(machine_id, None)

    def reset_all(self):
        self.history.clear()
