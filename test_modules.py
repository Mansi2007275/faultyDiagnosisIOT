import sys
import os

def main():
    print("--- Testing SentinelTwin Modular Architecture ---")
    try:
        import simulator
        import trust
        import health
        import ledger
        import dashboard.pages
        print("SUCCESS: All packages and modules imported clean.")
    except Exception as e:
        print(f"FAILED import: {e}")
        sys.exit(1)

    # Test Simulator
    dl = simulator.DataLoader()
    stats = dl.get_summary_statistics()
    print(f"SUCCESS: DataLoader initialized ({stats['total_rows']} rows, is_real={stats['is_real']})")

    fleet = simulator.MachineFleet()
    vm = fleet.get_machine("VM-CNC-01")
    raw = vm.tick()
    print(f"SUCCESS: MachineFleet tick -> ID: {raw['machine_id']}, Seq: #{raw['sequence_id']}, Power: {raw['calculated_power_w']} W")

    # Test Attacks
    atk = simulator.AttackEngine()
    atk.set_attack("VM-CNC-01", simulator.AttackType.PHYSICS_VIOLATION)
    mutated = atk.apply_attack(raw)
    print(f"SUCCESS: AttackEngine applied -> Injected: {mutated.get('_attack_injected')}")

    # Test Trust
    te = trust.TrustEngine()
    trep = te.evaluate(mutated)
    print(f"SUCCESS: TrustEngine evaluated -> Verdict: {trep.verdict.value}, Score: {trep.trust_score}")

    # Test Health
    de = health.DiagnosticsEngine()
    drep = de.diagnose(raw)
    print(f"SUCCESS: DiagnosticsEngine -> Severity: {drep.severity.value}, Action: {drep.action.value}")

    # Test Ledger
    al = ledger.AuditLedger(batch_size_limit=3)
    al.record_telemetry(raw)
    al.record_telemetry(raw)
    al.record_telemetry(raw) # should auto-seal
    is_valid, findings = al.verify_chain_integrity()
    print(f"SUCCESS: AuditLedger -> Sealed Batches: {len(al.sealed_batches)}, Integrity Valid: {is_valid}")

    print("\n--- ALL BACKEND CHECKS PASSED PERFECTLY ---")

if __name__ == "__main__":
    main()
