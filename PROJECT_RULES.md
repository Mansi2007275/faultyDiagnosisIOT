# SentinelTwin Project Rules & Architecture Standards

## 1. Modular Organization
- `simulator/`: Telemetry data loading (AI4I 2020), Virtual Machine simulation instances, and Attack/Fault injection.
- `trust/`: Zero-Trust verification engine (HMAC signatures, anti-replay sequence checks, thermodynamics & power physical invariants, stuck sensor rolling variance).
- `health/`: Domain-specific predictive maintenance rules (TWF, HDF, PWF, OSF, RNF) and response ladder actions.
- `ledger/`: Cryptographic SHA-256 Merkle tree batching, immutable hash chaining, and tamper verification proofs.
- `dashboard/pages/`: Modular page components (one dedicated file per page).
- `app.py`: Clean entry point responsible for routing, session management, and layout.

## 2. Non-Negotiable Engineering Constraints
- No breaking changes between modules.
- Strict typing and docstrings across core verification methods.
- Cryptographic canonical serialization before hashing.
