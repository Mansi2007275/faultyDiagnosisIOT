import streamlit as st
import pandas as pd
import time
from dashboard.components import render_page_header, render_metric_card
from dashboard.pages.merkle_explorer import render_merkle_explorer
from auth.db import log_audit_event
from ledger import store

def render_audit_ledger_page(ledger, session_state, anchor_client=None):
    """
    Renders Page 5: Tamper-Evident Cryptographic Ledger, Merkle Explorer, and Tamper Verification.
    """
    render_page_header(
        title="Tamper-Evident Cryptographic Ledger",
        subtitle="SHA-256 Merkle hash chains, batch sealing, and cryptographic audit proofs",
        badge_text="AUDIT READY"
    )

    # Top KPI Metrics
    total_sealed = len(ledger.sealed_batches)
    total_records = sum(len(b.records) for b in ledger.sealed_batches) + len(ledger.open_batch.records)
    total_events = len(ledger.all_events)

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_metric_card("Sealed Batches", f"{total_sealed}", "Immutable blocks", "purple")
    with k2:
        render_metric_card("Open Batch Buffer", f"{len(ledger.open_batch.records)} / {ledger.batch_size_limit}", "Auto-seals at limit", "nominal")
    with k3:
        render_metric_card("Total Telemetry Records", f"{total_records:,}", "Hashed & anchored", "trusted")
    with k4:
        render_metric_card("Security Audit Events", f"{total_events}", "Violations & alerts", "suspicious" if total_events > 0 else "trusted")

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # Actions Bar: Seal Batch & Run Audit
    act_c1, act_c2 = st.columns([1, 1])
    with act_c1:
        if st.button("🔒 Manually Seal Open Batch Now", use_container_width=True, type="primary"):
            sealed = ledger.seal_current_batch()
            if sealed:
                store.save_batch(sealed)
                st.success(f"Sealed Batch #{sealed.batch_index} with Merkle Root: `{sealed.merkle_root[:16]}...`")
                st.rerun()
            else:
                st.warning("Open batch is empty; nothing to seal.")

    with act_c2:
        if st.button("🛡️ Verify Full Ledger Cryptographic Integrity", use_container_width=True):
            is_valid, findings = ledger.verify_chain_integrity()
            session_state.last_audit_result = (is_valid, findings)
            user = st.session_state.get("authenticated_user", {})
            log_audit_event(
                username=user.get("username", "system"),
                role=user.get("role", "Operator"),
                action="ledger tamper test",
                target="ledger",
                result="SUCCESS" if is_valid else "FAILED",
                details="Cryptographic integrity verification check executed"
            )
            st.rerun()

    # Display Audit Result if present
    if "last_audit_result" in session_state:
        is_valid, findings = session_state.last_audit_result
        st.markdown("### 🔍 Cryptographic Audit Proof Result")
        if is_valid:
            st.success(f"**CHAIN INTEGRITY VERIFIED (VALID):** {findings[0]}")
        else:
            st.error(f"**ALERT: CRYPTOGRAPHIC TAMPERING DETECTED!**")
            for f in findings:
                st.markdown(f"- 🚨 **{f}**")

    st.markdown("---")

    # Interactive Tamper Demonstration Section
    st.subheader("🧪 Adversary Tamper Simulation")
    st.markdown("Simulate an attacker modifying a historical database record after it was sealed. The Merkle proof will detect the modification instantly.")

    if total_sealed > 0:
        t_col1, t_col2, t_col3, t_col4 = st.columns([1, 1, 1, 1])
        with t_col1:
            batch_to_tamper = st.selectbox("Select Batch Index:", options=list(range(total_sealed)))
        with t_col2:
            target_batch = ledger.sealed_batches[batch_to_tamper]
            rec_count = len(target_batch.records)
            rec_idx = st.selectbox("Record in Batch:", options=list(range(rec_count))) if rec_count > 0 else 0
        with t_col3:
            field_to_tamper = st.selectbox("Field to Alter:", ["process_temperature_k", "torque_nm", "rotational_speed_rpm"])
        with t_col4:
            st.write("")
            st.write("")
            if st.button("⚠️ Tamper Historical Record", use_container_width=True):
                # Modify record
                success = ledger.simulate_tamper(batch_to_tamper, rec_idx, field_to_tamper, 999.99)
                if success:
                    st.error(f"Adversary modified Batch #{batch_to_tamper}, Record #{rec_idx}: `{field_to_tamper}` set to 999.99.")
                    # Automatically re-verify
                    is_valid, findings = ledger.verify_chain_integrity()
                    session_state.last_audit_result = (is_valid, findings)
                    user = st.session_state.get("authenticated_user", {})
                    log_audit_event(
                        username=user.get("username", "system"),
                        role=user.get("role", "Operator"),
                        action="ledger tamper test",
                        target=f"batch_{batch_to_tamper}_rec_{rec_idx}",
                        result="TAMPERED",
                        details=f"Simulated tamper on field {field_to_tamper}"
                    )
                    st.rerun()
    else:
        st.info("Seal at least one batch above to enable the tamper simulation demo.")

    st.markdown("---")

    # Sealed Batches Explorer
    st.subheader("Immutable Merkle Hash Chain Explorer")
    if total_sealed == 0:
        st.write("No sealed batches yet. Click 'Manually Seal Open Batch Now' or stream telemetry on the Live Monitor to generate batches.")
    else:
        for b in reversed(ledger.sealed_batches):
            with st.expander(f"📦 Batch #{b.batch_index} — {len(b.records)} Telemetry Records — {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(b.timestamp))}"):
                st.markdown(f"**Current Batch Header Hash:**")
                st.markdown(f"<div class='hash-pill'>{b.current_batch_hash}</div>", unsafe_allow_html=True)
                st.markdown(f"**Previous Batch Hash (Chain Link):**")
                st.markdown(f"<div class='hash-pill'>{b.prev_batch_hash}</div>", unsafe_allow_html=True)
                st.markdown(f"**Merkle Tree Root:**")
                st.markdown(f"<div class='hash-pill'>{b.merkle_root}</div>", unsafe_allow_html=True)
                
                st.markdown("#### Records in Batch")
                st.dataframe(pd.DataFrame(b.records), use_container_width=True)

    # Security Events Audit Table
    st.markdown("---")
    st.subheader("Security & Operational Event Log")
    if ledger.all_events:
        evt_rows = [{
            "Event ID": e.event_id,
            "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.timestamp)),
            "Asset": e.machine_id,
            "Type": e.event_type,
            "Details": e.details,
            "Event Hash": e.event_hash[:16] + "..."
        } for e in reversed(ledger.all_events)]
        st.dataframe(pd.DataFrame(evt_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No security or trust violation events recorded yet.")

    # ── Blockchain Anchoring Panel ─────────────────────────────────────────
    st.markdown("---")
    st.subheader("⛓️ On-Chain Anchoring (AuditAnchor Contract)")

    chain_enabled = anchor_client is not None and anchor_client.is_enabled

    if chain_enabled:
        on_chain_count = anchor_client.get_record_count()
        st.success(
            f"🟢 **Blockchain connected** — {on_chain_count} record(s) anchored on-chain"
        )

        bc1, bc2 = st.columns(2)
        with bc1:
            if st.button("⛓️ Anchor Latest Sealed Batch On-Chain", use_container_width=True, type="primary"):
                if ledger.sealed_batches:
                    latest = ledger.sealed_batches[-1]
                    anchor_info = anchor_client.anchor_batch_detailed(latest)
                    tx = anchor_info["tx_hash"] if anchor_info else None
                    if tx:
                        store.save_batch(latest)
                        store.save_anchor(
                            batch_index=latest.batch_index,
                            network=anchor_info["network"],
                            contract_address=anchor_info["contract_address"],
                            tx_hash=tx,
                            block_number=anchor_info["block_number"],
                            record_id=anchor_info["record_id"],
                            record_type=anchor_info["record_type"],
                        )
                        st.success(f"✅ Anchored! TX: `{tx}`")
                        user = session_state.get("authenticated_user", {})
                        log_audit_event(
                            username=user.get("username", "system"),
                            role=user.get("role", "Operator"),
                            action="blockchain anchor",
                            target=f"batch_{latest.batch_index}",
                            result="SUCCESS",
                            details=f"TX hash: {tx}"
                        )
                    else:
                        st.error("Anchoring failed — check logs.")
                else:
                    st.warning("No sealed batches to anchor yet.")

        with bc2:
            if st.button("🔎 View Latest On-Chain Record", use_container_width=True):
                count = anchor_client.get_record_count()
                if count and count > 0:
                    rec = anchor_client.get_record(count - 1)
                    if rec:
                        st.json(rec)
                else:
                    st.info("No on-chain records yet.")

        # Show all anchored records
        count = anchor_client.get_record_count() or 0
        if count > 0:
            st.markdown("#### On-Chain Records")
            rows = []
            for i in range(count):
                r = anchor_client.get_record(i)
                if r:
                    rows.append({
                        "ID": i,
                        "Type": r["recordType"],
                        "Batch #": r["batchNo"],
                        "Timestamp": time.strftime(
                            "%Y-%m-%d %H:%M:%S", time.localtime(r["timestamp"])
                        ),
                        "Hash (first 16)": r["hash"][:16] + "...",
                        "Submitter": r["submitter"][:12] + "...",
                    })
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info(
            "⚪ **Blockchain anchoring is offline.** "
            "To enable it, start a local Hardhat node and deploy the contract:\n\n"
            "```powershell\n"
            "cd contracts\n"
            "npm install\n"
            "npx hardhat node          # Terminal 1 – keep running\n"
            "npm run deploy:localhost  # Terminal 2\n"
            "```\n\n"
            "Then restart the Streamlit app."
        )

    # ── Merkle Proof Explorer & Audit Proof Report ─────────────────────────
    render_merkle_explorer(ledger, session_state, anchor_client)
