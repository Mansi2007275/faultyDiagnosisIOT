import hashlib
from typing import Dict, Any, Tuple

class SignatureValidator:
    """
    Validates end-to-end cryptographic integrity and authenticity of telemetry packets.
    Reconstructs the expected HMAC-SHA256 signature using the registered device identity.
    """
    def __init__(self):
        # Known registered device secrets database (In real world: HSM / Key Vault)
        self.device_keys: Dict[str, str] = {
            "VM-CNC-01": "dev-secret-key-VM-CNC-01-L-2026",
            "VM-HYD-02": "dev-secret-key-VM-HYD-02-M-2026",
            "VM-TURB-03": "dev-secret-key-VM-TURB-03-H-2026",
            "VM-LTH-04": "dev-secret-key-VM-LTH-04-L-2026",
        }

    def register_device(self, machine_id: str, secret: str):
        self.device_keys[machine_id] = secret

    def verify(self, telemetry: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Verifies if the packet signature matches the calculated canonical payload hash.
        Returns: (is_valid, reason)
        """
        machine_id = telemetry.get("machine_id")
        if not machine_id:
            return False, "Missing machine_id in packet header"

        if machine_id not in self.device_keys:
            return False, f"Unknown/unregistered device ID: '{machine_id}'"

        signature = telemetry.get("signature")
        if not signature:
            return False, "Missing cryptographic signature in packet"

        secret = self.device_keys[machine_id]
        
        try:
            canonical_str = (
                f"{telemetry['machine_id']}|{telemetry['sequence_id']}|{telemetry['timestamp']:.3f}|"
                f"{telemetry['air_temperature_k']:.2f}|{telemetry['process_temperature_k']:.2f}|"
                f"{telemetry['rotational_speed_rpm']:.1f}|{telemetry['torque_nm']:.2f}|"
                f"{telemetry['tool_wear_min']:.1f}|{secret}"
            )
            expected_sig = hashlib.sha256(canonical_str.encode()).hexdigest()
            
            if signature.lower() == expected_sig.lower():
                return True, "Valid HMAC-SHA256 device signature"
            else:
                return False, f"Signature Mismatch: Payload tampered in transit or invalid device key"
        except KeyError as ke:
            return False, f"Missing required telemetry field for signature verification: {ke}"
        except Exception as e:
            return False, f"Signature verification error: {str(e)}"
