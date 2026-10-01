"""
ledger/hasher.py
────────────────
Deterministic SHA-256 hashing for telemetry records and Merkle trees.

Key design decisions
────────────────────
• CANONICAL_FIELDS defines the exact, ordered list of fields that are part of
  the hash commitment.  Any field not in this list (e.g. internal ``_*`` keys
  added by the trust/ML layers) is excluded so they cannot cause spurious
  mismatches.
• All float values are rounded to FLOAT_DECIMALS decimal places before
  serialisation so that floating-point arithmetic noise (e.g. 0.3000000000004)
  is always normalised to the same string (``0.3``).
• Timestamps that travel through the record dict are stored and hashed as the
  same fixed-precision string they were written with (4 d.p.).
• json.dumps uses sort_keys=True and no extra whitespace so the byte sequence
  is identical regardless of Python version or dict insertion order.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

# ── Constants ─────────────────────────────────────────────────────────────────

FLOAT_DECIMALS: int = 4          # decimal places for every numeric value

# Fixed canonical field list – ONLY these fields are committed to the hash.
# Add new sensor fields here in alphabetical order if the schema grows.
CANONICAL_FIELDS: List[str] = [
    "air_temperature_k",
    "machine_id",
    "process_temperature_k",
    "rotational_speed_rpm",
    "timestamp",
    "tool_wear_min",
    "torque_nm",
    "type",
]


# ── Public helpers ─────────────────────────────────────────────────────────────

def sha256_digest(data_str: str) -> str:
    """Returns the SHA-256 hex digest of a UTF-8 string."""
    return hashlib.sha256(data_str.encode("utf-8")).hexdigest()


def _normalise_value(v: Any) -> Any:
    """
    Normalise a single field value so its JSON representation is deterministic:
    • float / int → round to FLOAT_DECIMALS decimal places, returned as float
    • str          → unchanged
    • everything else → str() so it never silently breaks serialisation
    """
    if isinstance(v, float):
        return round(v, FLOAT_DECIMALS)
    if isinstance(v, int):
        # Keep integers as integers – they serialise deterministically already.
        return v
    if isinstance(v, str):
        return v
    return str(v)


def canonical_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a new dict containing only the CANONICAL_FIELDS in sorted-key order,
    with every value normalised.  Missing fields are represented as ``None``.

    This is the *exact* dict that is serialised and hashed.  Storing it (or
    re-deriving it from the same source dict) guarantees identical output on
    every call.
    """
    return {field: _normalise_value(record.get(field)) for field in sorted(CANONICAL_FIELDS)}


def hash_telemetry_record(record: Dict[str, Any]) -> str:
    """
    Computes the canonical SHA-256 leaf hash for one telemetry reading.

    The hash is derived from a deterministic JSON string:
      • Fixed field set  (CANONICAL_FIELDS)
      • Sorted keys
      • Floats rounded to FLOAT_DECIMALS decimal places
      • No extra whitespace
    """
    canon = canonical_record(record)
    serialised = json.dumps(canon, sort_keys=True, separators=(",", ":"))
    return sha256_digest(serialised)


def compute_merkle_root(leaf_hashes: List[str]) -> str:
    """
    Computes a standard binary Merkle root from a list of SHA-256 leaf hashes.
    Odd-length levels duplicate the last node (standard Bitcoin-style Merkle).
    """
    if not leaf_hashes:
        return sha256_digest("EMPTY_MERKLE_TREE_SENTINELTWIN_2026")

    current_level = list(leaf_hashes)

    while len(current_level) > 1:
        if len(current_level) % 2 != 0:
            current_level.append(current_level[-1])
        next_level = []
        for i in range(0, len(current_level), 2):
            parent = sha256_digest(current_level[i] + current_level[i + 1])
            next_level.append(parent)
        current_level = next_level

    return current_level[0]
