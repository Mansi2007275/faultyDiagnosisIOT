"""
dashboard/pages/merkle_explorer.py
──────────────────────────────────
Merkle Proof Explorer and Audit Proof Report, rendered inside the
Tamper-Evident Ledger page.

Sections
────────
1. Plain-English explainer.
2. Batch selector + Plotly Merkle tree + batch/anchor metadata.
3. Single-reading inclusion proof, step by step, with a three-way root
   comparison (recomputed / SQLite / on-chain) and a pass-fail badge.
4. Audit Proof Report download (PDF + JSON), written to the audit log.
5. Verify an uploaded proof file (Auditor and Admin only).

An unreachable or un-anchored chain is always reported as inconclusive and
never as a failed proof.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import plotly.graph_objects as go
import streamlit as st

from auth.db import log_audit_event
from auth.permissions import has_permission
from dashboard.components import render_page_header  # noqa: F401  (shared styling import)
from ledger import store
from ledger.hasher import hash_telemetry_record
from ledger.proof import build_merkle_tree, get_merkle_proof, recompute_root_from_proof
from ledger.report import (
    CHAIN_MISMATCH,
    CHAIN_NOT_ANCHORED,
    CHAIN_OFFLINE,
    CHAIN_VERIFIED,
    PLAIN_ENGLISH_SUMMARY,
    build_proof_payload,
    check_onchain_root,
    proof_json_bytes,
    proof_pdf_bytes,
    verify_proof_payload,
)

# Tree palette
_C_IDLE = "#475569"       # ordinary node
_C_PATH = "#FBBF24"       # node carried up the proof path
_C_SIBLING = "#F97316"    # sibling supplied by the proof
_C_ROOT = "#A855F7"       # Merkle root
_C_LEAF = "#38BDF8"       # the reading being proved


def _current_user() -> Dict[str, Any]:
    return st.session_state.get("authenticated_user") or {}


def _fmt_time(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


# ── Tree drawing ──────────────────────────────────────────────────────────────

def _node_positions(levels: List[List[str]]) -> List[List[float]]:
    """
    Computes x positions per level: leaves are evenly spaced, and every parent
    sits at the midpoint of the two children it hashes.
    """
    positions: List[List[float]] = [[float(i) for i in range(len(levels[0]))]]
    for depth in range(1, len(levels)):
        below = positions[depth - 1]
        row = [
            (below[2 * j] + below[2 * j + 1]) / 2.0
            if 2 * j + 1 < len(below)
            else below[2 * j]
            for j in range(len(levels[depth]))
        ]
        positions.append(row)
    return positions


def _proof_node_map(levels: List[List[str]], leaf_index: Optional[int]) -> Dict[tuple, str]:
    """Maps (depth, index) -> highlight colour for the proof path."""
    if leaf_index is None:
        return {}
    marks: Dict[tuple, str] = {}
    idx = leaf_index
    for depth in range(len(levels)):
        marks[(depth, idx)] = _C_LEAF if depth == 0 else _C_PATH
        if depth < len(levels) - 1:
            sibling = idx + 1 if idx % 2 == 0 else idx - 1
            if sibling < len(levels[depth]):
                marks.setdefault((depth, sibling), _C_SIBLING)
        idx //= 2
    return marks


def _render_tree(levels: List[List[str]], leaf_index: Optional[int], n_real_leaves: int) -> None:
    """Draws the Merkle tree bottom-up with the proof path highlighted."""
    positions = _node_positions(levels)
    marks = _proof_node_map(levels, leaf_index)

    edge_x: List[Optional[float]] = []
    edge_y: List[Optional[float]] = []
    for depth in range(1, len(levels)):
        for j in range(len(levels[depth])):
            for child in (2 * j, 2 * j + 1):
                if child < len(positions[depth - 1]):
                    edge_x += [positions[depth - 1][child], positions[depth][j], None]
                    edge_y += [depth - 1, depth, None]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y, mode="lines",
        line=dict(color="rgba(148,163,184,0.45)", width=1.2),
        hoverinfo="skip", showlegend=False,
    ))

    top = len(levels) - 1
    for depth, row in enumerate(levels):
        xs, ys, colours, sizes, labels, hovers = [], [], [], [], [], []
        for j, node_hash in enumerate(row):
            is_root = depth == top
            colour = _C_ROOT if is_root else marks.get((depth, j), _C_IDLE)
            if is_root and (depth, j) in marks:
                colour = _C_ROOT
            duplicated = depth == 0 and j >= n_real_leaves

            xs.append(positions[depth][j])
            ys.append(depth)
            colours.append(colour)
            sizes.append(30 if is_root else 20)
            labels.append(node_hash[:8])
            role = (
                "MERKLE ROOT" if is_root
                else "Leaf (duplicated padding)" if duplicated
                else f"Leaf #{j}" if depth == 0
                else f"Level {depth} node #{j}"
            )
            hovers.append(f"<b>{role}</b><br>{node_hash}")

        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers+text",
            marker=dict(size=sizes, color=colours,
                        line=dict(color="rgba(15,23,42,0.9)", width=1.5)),
            text=labels, textposition="middle right",
            textfont=dict(family="monospace", size=9, color="#E2E8F0"),
            hovertemplate="%{customdata}<extra></extra>", customdata=hovers,
            showlegend=False,
        ))

    fig.update_layout(
        height=max(300, 110 * len(levels)),
        margin=dict(l=20, r=20, t=30, b=20),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(
            tickmode="array",
            tickvals=list(range(len(levels))),
            ticktext=["Leaves"] + [f"Level {d}" for d in range(1, top)] + ["Root"]
            if len(levels) > 1 else ["Root (single leaf)"],
            tickfont=dict(size=10, color="#94A3B8"),
            showgrid=False, zeroline=False,
        ),
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Chain status presentation ─────────────────────────────────────────────────

def _render_chain_status(chain: Dict[str, Any], anchor_client: Any) -> None:
    """Renders on-chain status without ever framing 'unknown' as a failure."""
    status = chain.get("status")
    network = chain.get("network") or "not connected"

    if status == CHAIN_VERIFIED:
        st.success(f"⛓️ **Confirmed on-chain** ({network}) — {chain.get('detail')}")
    elif status == CHAIN_MISMATCH:
        st.error(f"⛓️ **On-chain mismatch** ({network}) — {chain.get('detail')}")
    elif status == CHAIN_NOT_ANCHORED:
        st.info(f"⛓️ **Not anchored** — {chain.get('detail')} This does not invalidate the proof.")
    else:
        st.info(
            "⛓️ **Chain offline** — the blockchain is unavailable, so the on-chain "
            "confirmation could not be performed. This does not invalidate the proof."
        )

    tx_hash = chain.get("tx_hash")
    if tx_hash:
        url = chain.get("explorer_url")
        if not url and anchor_client is not None:
            url = anchor_client.explorer_tx_url(tx_hash)
        if url:
            st.markdown(f"**Transaction:** [{tx_hash[:24]}…]({url}) (Etherscan)")
        else:
            st.markdown(f"**Transaction:** `{tx_hash[:24]}…` — Local chain")
        if chain.get("block_number") is not None:
            st.caption(f"Block {chain['block_number']} · contract {chain.get('contract_address')}")


# ── Main renderer ─────────────────────────────────────────────────────────────

def render_merkle_explorer(ledger, session_state, anchor_client=None) -> None:
    """Renders the Merkle Proof Explorer and Audit Proof Report section."""
    user = _current_user()
    role = user.get("role", "Operator")

    st.markdown("---")
    st.subheader("🌳 Merkle Proof Explorer & Audit Proof Report")

    if not has_permission(role, "Merkle proof: view/download"):
        st.warning(
            "🔒 Your role does not have access to Merkle proofs or Audit Proof "
            "Reports. Required: Admin, Engineer, Safety Officer or Auditor."
        )
        return

    # 6. Plain-English explainer
    st.info(f"**How this works.** {PLAIN_ENGLISH_SUMMARY}")

    # Persist sealed batches so proofs can be checked against the database.
    try:
        store.sync_ledger(ledger)
    except Exception as exc:  # pragma: no cover - defensive
        st.warning(f"Could not persist batches to SQLite: {exc}")

    if not ledger.sealed_batches:
        st.info("No sealed batches yet. Seal a batch above to explore its Merkle tree.")
        _render_upload_section(role, anchor_client)
        return

    # ── 1. Batch selector ─────────────────────────────────────────────────
    batch_indices = [b.batch_index for b in ledger.sealed_batches]
    selected_idx = st.selectbox(
        "Select a sealed batch:",
        options=batch_indices,
        format_func=lambda i: (
            f"Batch #{i} — {len(ledger.sealed_batches[batch_indices.index(i)].records)} readings"
        ),
        key="merkle_batch_select",
    )
    batch = ledger.sealed_batches[batch_indices.index(selected_idx)]

    batch_meta = store.get_batch(batch.batch_index)
    if batch_meta is None:
        st.error("This batch is not in the ledger database yet — try reloading the page.")
        return

    stored_anchor = store.get_anchor(batch.batch_index)

    m1, m2, m3 = st.columns(3)
    m1.metric("Batch number", f"#{batch.batch_index}")
    m2.metric("Readings in batch", f"{len(batch.ledger_records)}")
    m3.metric("Leaves (incl. events)", f"{len(batch.leaf_hashes)}")
    st.caption(f"Sealed at {_fmt_time(batch.timestamp)}")

    st.markdown("**Merkle root** (click the copy icon to copy the full value):")
    st.code(batch.merkle_root, language=None)

    root_chain = check_onchain_root(
        batch_meta, batch.merkle_root,
        anchor_client=anchor_client, stored_anchor=stored_anchor,
    )
    _render_chain_status(root_chain, anchor_client)

    # ── 2. Reading selector + proof ───────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🔎 Prove a single reading")

    records = batch.records
    if not records:
        st.info("This batch contains no telemetry readings (events only).")
        _render_upload_section(role, anchor_client)
        return

    def _label(i: int) -> str:
        r = records[i]
        return (
            f"#{i} · {r.get('machine_id', '?')} · {_fmt_time(float(r.get('timestamp', 0)))} · "
            f"{r.get('rotational_speed_rpm', '?')} rpm / {r.get('torque_nm', '?')} Nm"
        )

    leaf_index = st.selectbox(
        "Select a reading:", options=list(range(len(records))),
        format_func=_label, key="merkle_reading_select",
    )

    reading = records[leaf_index]
    leaf_hash = hash_telemetry_record(reading)
    sealed_leaf = batch.leaf_hashes[leaf_index]
    proof_path = get_merkle_proof(batch.leaf_hashes, leaf_index)
    recomputed_root = recompute_root_from_proof(leaf_hash, proof_path)

    proof_chain = check_onchain_root(
        batch_meta, recomputed_root,
        anchor_client=anchor_client, stored_anchor=stored_anchor,
    )

    payload = build_proof_payload(
        batch_meta=batch_meta,
        leaf_index=leaf_index,
        reading=reading,
        leaf_hash=leaf_hash,
        proof_path=proof_path,
        recomputed_root=recomputed_root,
        chain_check=proof_chain,
        generated_by=user.get("username", "unknown"),
        generated_by_role=role,
    )
    is_valid = payload["result"] == "PROOF VALID"

    # Big verdict badge
    if is_valid:
        st.success("### ✅ PROOF VALID: this reading is exactly as recorded")
    else:
        st.error("### 🚨 PROOF FAILED: this reading was changed")

    # Step-by-step walk
    st.markdown("#### Step by step")
    with st.expander("Step 1 — The reading as stored", expanded=True):
        st.json(payload["reading"])

    with st.expander("Step 2 — Its leaf hash (SHA-256 of the canonical reading)", expanded=True):
        st.code(leaf_hash, language=None)
        if leaf_hash != sealed_leaf:
            st.error(
                "This does **not** match the leaf hash sealed at the time: "
                f"`{sealed_leaf}`. The reading has been altered since sealing."
            )
        else:
            st.caption("Matches the leaf hash sealed with the batch.")

    with st.expander(
        f"Step 3 — Proof path ({len(proof_path)} sibling"
        f"{'s' if len(proof_path) != 1 else ''} needed)", expanded=True
    ):
        if not proof_path:
            st.write("This batch has a single leaf, so the leaf *is* the Merkle root.")
        for i, step in enumerate(proof_path):
            side = step["position"]
            arrow = "hash(current + sibling)" if side == "right" else "hash(sibling + current)"
            st.markdown(
                f"**{i + 1}. Sibling on the {side.upper()}** → `{arrow}`"
            )
            st.code(step["sibling"], language=None)

    with st.expander("Step 4 — Recomputed Merkle root", expanded=True):
        st.code(recomputed_root, language=None)

    # Three-way comparison
    st.markdown("#### Root comparison")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**(a) Root stored in SQLite**")
        st.code(batch_meta["merkle_root"], language=None)
        if recomputed_root == batch_meta["merkle_root"]:
            st.success("Matches the recomputed root.")
        else:
            st.error("Does NOT match the recomputed root.")
    with c2:
        st.markdown("**(b) Root committed on-chain**")
        st.caption(
            "AuditAnchor stores the batch header hash, which commits to the root. "
            "The recomputed root is used to rebuild that hash and compare."
        )
        _render_chain_status(proof_chain, anchor_client)

    # Highlighted tree
    st.markdown("#### Merkle tree (proof path highlighted)")
    st.caption(
        "🔵 the reading · 🟠 siblings supplied by the proof · "
        "🟡 hashes recomputed on the way up · 🟣 Merkle root"
    )
    _render_tree(build_merkle_tree(batch.leaf_hashes), leaf_index, len(batch.leaf_hashes))

    # ── 3. Downloads ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📄 Audit Proof Report")
    _render_downloads(payload, user, role, batch.batch_index, leaf_index)

    # ── 4. Upload & verify ────────────────────────────────────────────────
    _render_upload_section(role, anchor_client)


def _log_download(fmt: str, batch_index: int, leaf_index: int,
                  report_id: str, result: str) -> None:
    """Writes an audit-log entry for a proof report download."""
    user = _current_user()
    try:
        log_audit_event(
            username=user.get("username", "system"),
            role=user.get("role", "unknown"),
            action="audit proof report download",
            target=f"batch_{batch_index}_leaf_{leaf_index}",
            result=result,
            details=f"{fmt} report {report_id} downloaded",
        )
    except Exception:  # pragma: no cover - logging must never break the download
        pass


def _render_downloads(payload: Dict[str, Any], user: Dict[str, Any], role: str,
                      batch_index: int, leaf_index: int) -> None:
    """Renders the PDF and JSON download buttons."""
    report_id = payload["report_id"]
    result = payload["result"]
    stem = f"SentinelTwin_Proof_B{batch_index}_L{leaf_index}_{report_id}"

    st.caption(
        f"Report **{report_id}** · generated by {user.get('username', 'unknown')} ({role})"
    )

    d1, d2 = st.columns(2)
    with d1:
        try:
            pdf_bytes = proof_pdf_bytes(payload)
            st.download_button(
                "⬇️ Download PDF report", data=pdf_bytes,
                file_name=f"{stem}.pdf", mime="application/pdf",
                use_container_width=True, type="primary",
                on_click=_log_download, args=("PDF", batch_index, leaf_index, report_id, result),
                key=f"dl_pdf_{batch_index}_{leaf_index}",
            )
        except ImportError as exc:
            st.error(str(exc))
    with d2:
        st.download_button(
            "⬇️ Download JSON proof", data=proof_json_bytes(payload),
            file_name=f"{stem}.json", mime="application/json",
            use_container_width=True,
            on_click=_log_download, args=("JSON", batch_index, leaf_index, report_id, result),
            key=f"dl_json_{batch_index}_{leaf_index}",
        )


def _render_upload_section(role: str, anchor_client: Any) -> None:
    """Section 4: verify a proof file supplied by a third party."""
    st.markdown("---")
    st.markdown("### 🔐 Verify a proof file")

    if not has_permission(role, "Merkle proof: upload"):
        st.caption(
            "🔒 Uploading proof files for verification is restricted to the "
            "Auditor and Admin roles."
        )
        return

    st.caption(
        "Upload a JSON proof file. Its root is recomputed from the reading and "
        "the proof path, then compared with the sealed batch hash, the local "
        "database and the blockchain."
    )
    uploaded = st.file_uploader(
        "Proof file (.json)", type=["json"], key="merkle_proof_upload"
    )
    if uploaded is None:
        return

    try:
        payload = json.loads(uploaded.getvalue().decode("utf-8"))
    except Exception as exc:
        st.error(f"**INVALID** — the file could not be parsed as JSON: {exc}")
        return

    sqlite_batch = None
    try:
        idx = payload.get("batch", {}).get("batch_index")
        if idx is not None:
            sqlite_batch = store.get_batch(int(idx))
    except Exception:
        sqlite_batch = None

    outcome = verify_proof_payload(
        payload, anchor_client=anchor_client, sqlite_batch=sqlite_batch
    )

    if outcome["valid"]:
        st.success(f"### ✅ VALID — {outcome['reason']}")
    else:
        st.error(f"### 🚨 INVALID — {outcome['reason']}")

    st.markdown("#### Checks performed")
    for check in outcome["checks"]:
        passed = check["passed"]
        icon = "✅" if passed is True else ("🚨" if passed is False else "➖")
        st.markdown(f"{icon} **{check['name']}** — {check['detail']}")

    try:
        user = _current_user()
        log_audit_event(
            username=user.get("username", "system"),
            role=user.get("role", role),
            action="proof file verification",
            target=f"proof_{payload.get('report_id', 'unknown')}",
            result="VALID" if outcome["valid"] else "INVALID",
            details=outcome["reason"][:400],
        )
    except Exception:  # pragma: no cover
        pass
