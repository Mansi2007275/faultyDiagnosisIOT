import sys
import streamlit as st
from simulator.data_loader import DataLoader
from simulator.virtual_machine import MachineFleet
from simulator.attacks import AttackEngine
from trust.engine import TrustEngine
from health.diagnostics import DiagnosticsEngine
from ledger.batch import AuditLedger
from dashboard.pages import (
    render_overview_page,
    render_dataset_page,
    render_live_monitor_page,
    render_trust_security_page,
    render_health_diagnostics_page,
    render_audit_ledger_page
)

def main():
    print("=== 1. VERIFYING DATASET STATISTICS ===")
    dl = DataLoader()
    stats = dl.get_summary_statistics()

    print("Source Label:", stats["source_label"])
    print("Total Rows:", stats["total_rows"])
    print("Total Failures:", stats["total_failures"])
    print(f"Failure Rate: {stats['failure_rate']:.2f}%")
    print("Failure Counts:", stats["failure_counts"])
    print("Type Counts:", stats["type_counts"])

    # Assert exact required figures
    assert stats["total_rows"] == 10000, f"Expected 10000 rows, got {stats['total_rows']}"
    assert stats["total_failures"] == 339, f"Expected 339 failures, got {stats['total_failures']}"
    assert stats["failure_counts"]["TWF (Tool wear failure)"] == 46, "TWF mismatch"
    assert stats["failure_counts"]["HDF (Heat dissipation failure)"] == 115, "HDF mismatch"
    assert stats["failure_counts"]["PWF (Power failure)"] == 95, "PWF mismatch"
    assert stats["failure_counts"]["OSF (Overstrain failure)"] == 98, "OSF mismatch"
    assert stats["failure_counts"]["RNF (Random failure)"] == 19, "RNF mismatch"
    assert stats["type_counts"]["L"] == 6000, "Type L count mismatch"
    assert stats["type_counts"]["M"] == 2997, "Type M count mismatch"
    assert stats["type_counts"]["H"] == 1003, "Type H count mismatch"

    print(">>> ALL STATISTICAL ASSERTIONS CONFIRMED! <<<")

    print("\n=== 2. VERIFYING DERIVED COLUMNS ===")
    df = dl.df
    required_derived = ["air_c", "proc_c", "temp_gap_c", "power_w", "strain"]
    for col in required_derived:
        assert col in df.columns, f"Missing derived column {col}"
        print(f"Derived column '{col}' verified (sample={df[col].iloc[0]})")

    print("\n=== 3. EXECUTING ALL PAGES ===")
    class FakeSession(dict):
        def __getattr__(self, k): return self.get(k)
        def __setattr__(self, k, v): self[k] = v

    session = FakeSession()
    fleet = MachineFleet(dataset_df=dl.df)
    atk = AttackEngine()
    te = TrustEngine()
    de = DiagnosticsEngine()
    ledger = AuditLedger()

    print("-> Page 1: Overview")
    render_overview_page(dl, fleet, ledger, te, de)

    print("-> Page 2: Dataset Analytics")
    render_dataset_page(dl)

    print("-> Page 3: Live Monitor")
    render_live_monitor_page(fleet, atk, te, de, ledger, session)

    print("-> Page 4: Trust & Security")
    render_trust_security_page(fleet, atk, te, ledger, session)

    print("-> Page 5: Health Diagnostics")
    render_health_diagnostics_page(fleet, de, ledger, session)

    print("-> Page 6: Audit Ledger")
    render_audit_ledger_page(ledger, session)

    print("\n>>> ALL PAGES EXECUTED SUCCESSFULLY WITHOUT EXCEPTIONS! <<<")

if __name__ == "__main__":
    main()
