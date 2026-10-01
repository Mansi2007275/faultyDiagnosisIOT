"""
ledger/proof.py
───────────────
Merkle tree construction and single-leaf inclusion proofs.

Design contract
───────────────
`build_merkle_tree()` reproduces ``ledger.hasher.compute_merkle_root()`` exactly,
including its odd-level rule (duplicate the last node).  This is asserted by the
test-suite for every leaf count: the root returned by ``merkle_root_from_tree()``
is always bit-identical to ``compute_merkle_root()`` for the same input.

A proof is a list of steps, ordered bottom-up (leaf level first).  Each step is::

    {"sibling": "<64-hex>", "position": "left" | "right"}

where ``position`` describes where the SIBLING sits relative to the hash being
carried up.  Recomputation therefore concatenates in that order:

    position == "right"  →  parent = H(carried + sibling)
    position == "left"   →  parent = H(sibling + carried)
"""

from __future__ import annotations

from typing import Any, Dict, List

from ledger.hasher import compute_merkle_root, sha256_digest

__all__ = [
    "build_merkle_tree",
    "merkle_root_from_tree",
    "get_merkle_proof",
    "recompute_root_from_proof",
    "verify_merkle_proof",
]


def build_merkle_tree(leaf_hashes: List[str]) -> List[List[str]]:
    """
    Builds the full Merkle tree and returns it as a list of levels.

    ``levels[0]`` is the leaf level, ``levels[-1]`` is ``[root]``.  Every level
    except the last is padded to an even length by duplicating its final node,
    mirroring ``compute_merkle_root()``.  The padding is visible in the returned
    structure so the UI can draw exactly the tree that was hashed.

    An empty input yields the single-node sentinel tree used by
    ``compute_merkle_root([])``.
    """
    if not leaf_hashes:
        return [[compute_merkle_root([])]]

    levels: List[List[str]] = []
    current: List[str] = list(leaf_hashes)

    while True:
        if len(current) == 1:
            levels.append(list(current))
            break

        if len(current) % 2 != 0:
            current = current + [current[-1]]

        levels.append(list(current))
        current = [
            sha256_digest(current[i] + current[i + 1])
            for i in range(0, len(current), 2)
        ]

    return levels


def merkle_root_from_tree(levels: List[List[str]]) -> str:
    """Returns the root of a tree produced by ``build_merkle_tree()``."""
    if not levels or not levels[-1]:
        return compute_merkle_root([])
    return levels[-1][0]


def get_merkle_proof(leaf_hashes: List[str], index: int) -> List[Dict[str, str]]:
    """
    Returns the inclusion proof (sibling path) for the leaf at ``index``.

    Raises
    ------
    IndexError
        If ``index`` does not address a real leaf (padding duplicates are not
        addressable — they are not independent readings).
    """
    if not leaf_hashes:
        raise IndexError("Cannot build a proof for an empty leaf set.")
    if not 0 <= index < len(leaf_hashes):
        raise IndexError(
            f"Leaf index {index} out of range (0..{len(leaf_hashes) - 1})."
        )

    levels = build_merkle_tree(leaf_hashes)
    proof: List[Dict[str, str]] = []
    idx = index

    # Every level except the root level contributes exactly one sibling.
    for level in levels[:-1]:
        if idx % 2 == 0:
            sibling_idx, position = idx + 1, "right"
        else:
            sibling_idx, position = idx - 1, "left"
        proof.append({"sibling": level[sibling_idx], "position": position})
        idx //= 2

    return proof


def recompute_root_from_proof(leaf_hash: str, proof: List[Dict[str, str]]) -> str:
    """
    Walks a proof path upwards from ``leaf_hash`` and returns the resulting root.

    This is the only function an external auditor needs: given a reading's leaf
    hash and its proof path, it reconstructs the root independently of the
    original tree.
    """
    carried = leaf_hash
    for step in proof:
        sibling = step["sibling"]
        if step.get("position") == "left":
            carried = sha256_digest(sibling + carried)
        else:
            carried = sha256_digest(carried + sibling)
    return carried


def verify_merkle_proof(
    leaf_hash: str, proof: List[Dict[str, str]], expected_root: str
) -> bool:
    """True iff the proof path carries ``leaf_hash`` up to ``expected_root``."""
    return recompute_root_from_proof(leaf_hash, proof) == expected_root
