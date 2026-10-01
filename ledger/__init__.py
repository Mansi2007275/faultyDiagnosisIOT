"""
Tamper-Evident Cryptographic Ledger module for SentinelTwin.
Provides SHA-256 Merkle tree hashing, batch sealing, immutable hash chaining,
cryptographic audit proof verification, and optional on-chain anchoring via
the AuditAnchor Solidity contract.
"""
from ledger.hasher import hash_telemetry_record, compute_merkle_root, sha256_digest
from ledger.batch import Batch, AuditLedger, AuditEvent
from ledger.chain import AnchorClient
from ledger.proof import (
    build_merkle_tree,
    merkle_root_from_tree,
    get_merkle_proof,
    recompute_root_from_proof,
    verify_merkle_proof,
)
from ledger.report import (
    build_proof_payload,
    check_onchain_root,
    derive_batch_hash,
    proof_json_bytes,
    proof_pdf_bytes,
    verify_proof_payload,
)

__all__ = [
    "hash_telemetry_record",
    "compute_merkle_root",
    "sha256_digest",
    "Batch",
    "AuditLedger",
    "AuditEvent",
    "AnchorClient",
    # Merkle proofs
    "build_merkle_tree",
    "merkle_root_from_tree",
    "get_merkle_proof",
    "recompute_root_from_proof",
    "verify_merkle_proof",
    # Audit proof reports
    "build_proof_payload",
    "check_onchain_root",
    "derive_batch_hash",
    "proof_json_bytes",
    "proof_pdf_bytes",
    "verify_proof_payload",
]
