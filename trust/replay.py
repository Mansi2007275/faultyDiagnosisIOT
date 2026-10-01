import time
from typing import Dict, Any, Tuple

class ReplayDetector:
    """
    Guards against Replay Attacks and Out-of-Order message injection.
    Tracks highest received sequence numbers and verifies timestamp freshness windows.
    """
    def __init__(self, max_allowed_clock_skew_sec: float = 30.0):
        self.max_allowed_clock_skew_sec = max_allowed_clock_skew_sec
        # Maps machine_id -> highest verified sequence_id
        self.last_sequence_ids: Dict[str, int] = {}
        # Maps machine_id -> highest verified timestamp
        self.last_timestamps: Dict[str, float] = {}

    def verify(self, telemetry: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Verifies that sequence number is strictly strictly increasing (> last_seen)
        and packet timestamp is within freshness window.
        """
        machine_id = telemetry.get("machine_id", "UNKNOWN")
        seq_id = telemetry.get("sequence_id")
        ts = telemetry.get("timestamp")
        
        if seq_id is None or ts is None:
            return False, "Packet missing sequence_id or timestamp"

        now = time.time()
        
        # 1. Timestamp Freshness Check
        if abs(now - ts) > self.max_allowed_clock_skew_sec:
            diff = now - ts
            if diff > 0:
                return False, f"Timestamp Expired: packet is {diff:.1f}s stale (> {self.max_allowed_clock_skew_sec}s threshold)"
            else:
                return False, f"Future Timestamp: packet clock is {-diff:.1f}s in future"

        # 2. Monotonic Sequence Check
        if machine_id in self.last_sequence_ids:
            last_seq = self.last_sequence_ids[machine_id]
            if seq_id <= last_seq:
                return False, f"Replay Detected: Sequence #{seq_id} <= last processed Sequence #{last_seq}"
            
            # Check for sudden massive sequence jump (possible spoofing)
            if (seq_id - last_seq) > 1000:
                return False, f"Sequence Gap Anomaly: Jumped from #{last_seq} to #{seq_id}"

        # 3. Monotonic Timestamp Check
        if machine_id in self.last_timestamps:
            last_ts = self.last_timestamps[machine_id]
            if ts <= last_ts:
                return False, f"Timestamp Regression: {ts:.3f} <= previous {last_ts:.3f}"

        # Update state on pass
        self.last_sequence_ids[machine_id] = seq_id
        self.last_timestamps[machine_id] = ts
        return True, f"Sequence #{seq_id} verified (Monotonic & Fresh)"

    def reset_machine(self, machine_id: str):
        self.last_sequence_ids.pop(machine_id, None)
        self.last_timestamps.pop(machine_id, None)

    def reset_all(self):
        self.last_sequence_ids.clear()
        self.last_timestamps.clear()
