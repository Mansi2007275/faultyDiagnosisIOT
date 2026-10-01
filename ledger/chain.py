"""
ledger/chain.py
───────────────
Connects the Python AuditLedger to the AuditAnchor Solidity contract.

Supports two networks (chosen by CHAIN env var):
  - "localhost"  →  local Hardhat node  (default)
  - "sepolia"    →  Ethereum Sepolia testnet

Usage
-----
    from ledger.chain import AnchorClient
    client = AnchorClient()          # reads .env automatically
    tx_hash = client.anchor_batch(batch)   # returns None if chain disabled
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from ledger.batch import Batch

logger = logging.getLogger(__name__)

# ── Load root .env (../  relative to this file) ──────────────────────────────
_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

# ── Deployment manifest location ─────────────────────────────────────────────
_DEPLOYMENTS_DIR = Path(__file__).resolve().parents[1] / "contracts" / "deployments"

# Kept for backward compatibility with any caller that imported this constant.
_DEPLOYMENTS_PATH = _DEPLOYMENTS_DIR / "local.json"

# ── RPC endpoints ─────────────────────────────────────────────────────────────
_RPC_URLS = {
    "localhost": "http://127.0.0.1:8545",
    "sepolia":   os.getenv("SEPOLIA_RPC_URL", ""),
}

# ── Block explorers (tx URL prefix per network) ──────────────────────────────
_EXPLORERS = {
    "sepolia": "https://sepolia.etherscan.io/tx/",
    "mainnet": "https://etherscan.io/tx/",
}


def _deployment_path(chain: str) -> Path:
    """
    Resolves the deployment manifest for a network.

    Prefers ``deployments/<network>.json`` and falls back to the historical
    ``deployments/local.json`` so existing localhost deployments keep working
    without being redeployed.
    """
    named = _DEPLOYMENTS_DIR / f"{chain}.json"
    if named.exists():
        return named
    return _DEPLOYMENTS_DIR / "local.json"


def _ensure_0x(hex_str: str) -> str:
    """
    Normalises a hex string to a 0x-prefixed form.

    Necessary because ``HexBytes.hex()`` returns an unprefixed string from
    hexbytes 1.0 onwards, which would otherwise produce broken explorer URLs.
    """
    if not hex_str:
        return ""
    s = str(hex_str)
    return s if s.startswith("0x") else "0x" + s


def _hex_to_bytes32(hex_str: str) -> bytes:
    """Convert a 64-char hex string to 32-byte bytes32 for the contract."""
    return bytes.fromhex(hex_str.lstrip("0x").zfill(64))[:32]


class AnchorClient:
    """
    Thin wrapper around the AuditAnchor contract.

    If the deployment manifest does not exist, or web3 is unavailable,
    every method is a silent no-op (returns None) so the app still works
    without a running blockchain.
    """

    def __init__(self) -> None:
        self._w3 = None
        self._contract = None
        self._account = None
        self._enabled = False
        self._network = os.getenv("CHAIN", "localhost").strip().lower()
        self._contract_address = ""

        try:
            self._setup()
        except Exception as exc:  # pragma: no cover
            logger.warning("AnchorClient disabled: %s", exc)

    # ── Setup ─────────────────────────────────────────────────────────────

    def _setup(self) -> None:
        from web3 import Web3

        chain = os.getenv("CHAIN", "localhost").strip().lower()
        self._network = chain

        manifest = _deployment_path(chain)
        if not manifest.exists():
            logger.info(
                "contracts/deployments/%s.json not found — "
                "blockchain anchoring disabled. "
                "Run: cd contracts && npm install && npx hardhat node "
                "&& npm run deploy:localhost",
                chain,
            )
            return

        deployment = json.loads(manifest.read_text())
        contract_address: str = deployment["contractAddress"]
        abi: list = deployment["abi"]
        self._contract_address = contract_address

        rpc_url = _RPC_URLS.get(chain, _RPC_URLS["localhost"])
        if not rpc_url:
            logger.warning("CHAIN=%s but no RPC URL configured.", chain)
            return

        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))
        if not w3.is_connected():
            logger.warning(
                "Cannot connect to %s (%s) — anchoring disabled.", chain, rpc_url
            )
            return

        self._w3 = w3
        self._contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address), abi=abi
        )

        # Choose the signing account.
        #
        # On a local Hardhat node the node's own unlocked account[0] is both
        # funded and the contract owner (AuditAnchor is onlyOwner), so it is
        # always preferred there.  A PRIVATE_KEY in .env is a public-testnet
        # wallet: using it against localhost produces an unfunded, non-owner
        # sender and every anchoring transaction fails.
        private_key = os.getenv("PRIVATE_KEY", "")
        local_accounts = []
        if chain == "localhost":
            try:
                local_accounts = w3.eth.accounts
            except Exception:
                local_accounts = []

        if local_accounts:
            self._account = None  # use the node's unlocked default account
            self._default_account = local_accounts[0]
            w3.eth.default_account = local_accounts[0]
            logger.info("AnchorClient ready on %s — using Hardhat account[0]", chain)
        elif private_key and private_key != "0x" + "0" * 64:
            self._account = w3.eth.account.from_key(private_key)
            logger.info(
                "AnchorClient ready on %s — wallet %s",
                chain,
                self._account.address[:10] + "...",
            )
        else:
            logger.warning("No accounts available on %s.", chain)
            return

        self._enabled = True

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def is_enabled(self) -> bool:
        """True only if connected and ready to submit transactions."""
        return self._enabled

    @property
    def network(self) -> str:
        """The configured chain name, e.g. 'localhost' or 'sepolia'."""
        return self._network

    @property
    def contract_address(self) -> str:
        """Deployed AuditAnchor address, or '' when anchoring is disabled."""
        return self._contract_address

    def explorer_tx_url(self, tx_hash: str) -> Optional[str]:
        """
        Returns a block-explorer URL for a transaction, or None on a local
        chain (which has no public explorer).
        """
        prefix = _EXPLORERS.get(self._network)
        if not prefix or not tx_hash:
            return None
        return prefix + _ensure_0x(tx_hash)

    def anchor_batch(self, batch: "Batch") -> Optional[str]:
        """
        Anchors a sealed batch's hash on-chain.

        Parameters
        ----------
        batch : Batch
            A sealed AuditLedger batch.

        Returns
        -------
        str | None
            Transaction hash (hex) if successful, None otherwise.
        """
        if not self._enabled:
            return None
        if not batch.is_sealed:
            logger.warning("anchor_batch called on an unsealed batch — skipped.")
            return None

        try:
            hash_bytes = _hex_to_bytes32(batch.current_batch_hash)
            record_type = "TELEMETRY_BATCH"
            batch_no = batch.batch_index
            timestamp = int(batch.timestamp)

            return self._send_tx(hash_bytes, record_type, batch_no, timestamp)
        except Exception as exc:
            logger.error("anchor_batch failed: %s", exc)
            return None

    def anchor_batch_detailed(self, batch: "Batch") -> Optional[dict]:
        """
        Anchors a sealed batch and returns full transaction metadata.

        Unlike :meth:`anchor_batch` (which returns only a tx hash), this returns
        the data an audit report needs:

            {"tx_hash", "block_number", "record_id", "network",
             "contract_address", "record_type", "explorer_url"}

        Returns None if anchoring is disabled or the batch is not sealed.
        """
        if not self._enabled or not batch.is_sealed:
            return None

        try:
            hash_bytes = _hex_to_bytes32(batch.current_batch_hash)
            receipt = self._send_tx_receipt(
                hash_bytes, "TELEMETRY_BATCH", batch.batch_index, int(batch.timestamp)
            )
        except Exception as exc:
            logger.error("anchor_batch_detailed failed: %s", exc)
            return None

        tx_hash = _ensure_0x(receipt.transactionHash.hex())
        # The new record is the last one appended by this transaction.
        count = self.get_record_count() or 0
        return {
            "tx_hash":          tx_hash,
            "block_number":     int(receipt.blockNumber),
            "record_id":        count - 1 if count else None,
            "network":          self._network,
            "contract_address": self._contract_address,
            "record_type":      "TELEMETRY_BATCH",
            "explorer_url":     self.explorer_tx_url(tx_hash),
        }

    def find_batch_anchor(self, batch_no: int) -> Optional[dict]:
        """
        Searches the contract for the most recent TELEMETRY_BATCH record
        anchored for ``batch_no``.

        Returns the record dict (plus its ``record_id``) or None if that batch
        was never anchored.  Returns None when the chain is unavailable — the
        caller must treat that as "unknown", never as a proof failure.
        """
        if not self._enabled:
            return None
        try:
            count = self.get_record_count() or 0
            for rid in range(count - 1, -1, -1):
                rec = self.get_record(rid)
                if (
                    rec
                    and rec["batchNo"] == batch_no
                    and rec["recordType"] == "TELEMETRY_BATCH"
                ):
                    rec["record_id"] = rid
                    return rec
        except Exception as exc:
            logger.error("find_batch_anchor(%d) failed: %s", batch_no, exc)
        return None

    def anchor_event(
        self, event_hash: str, event_type: str, batch_no: int, timestamp: float
    ) -> Optional[str]:
        """
        Anchors a single security/audit event hash on-chain.

        Returns
        -------
        str | None
            Transaction hash (hex) if successful, None otherwise.
        """
        if not self._enabled:
            return None
        try:
            hash_bytes = _hex_to_bytes32(event_hash)
            return self._send_tx(hash_bytes, event_type, batch_no, int(timestamp))
        except Exception as exc:
            logger.error("anchor_event failed: %s", exc)
            return None

    def get_record_count(self) -> Optional[int]:
        """Returns the number of records stored on-chain."""
        if not self._enabled:
            return None
        try:
            return self._contract.functions.recordCount().call()
        except Exception as exc:
            logger.error("get_record_count failed: %s", exc)
            return None

    def get_record(self, record_id: int) -> Optional[dict]:
        """
        Returns a single on-chain record as a dict.

        Keys: hash (hex), recordType, batchNo, timestamp, submitter
        """
        if not self._enabled:
            return None
        try:
            result = self._contract.functions.getRecord(record_id).call()
            return {
                "hash":       result[0].hex(),
                "recordType": result[1],
                "batchNo":    result[2],
                "timestamp":  result[3],
                "submitter":  result[4],
            }
        except Exception as exc:
            logger.error("get_record(%d) failed: %s", record_id, exc)
            return None

    # ── Internal ───────────────────────────────────────────────────────────

    def _send_tx(
        self,
        hash_bytes: bytes,
        record_type: str,
        batch_no: int,
        timestamp: int,
    ) -> str:
        """Builds, signs (if key present), and sends the addRecord transaction."""
        receipt = self._send_tx_receipt(hash_bytes, record_type, batch_no, timestamp)
        tx_hex = receipt.transactionHash.hex()
        logger.info(
            "✅ Anchored on-chain | type=%s batchNo=%d tx=%s...",
            record_type,
            batch_no,
            tx_hex[:18],
        )
        return tx_hex

    def _send_tx_receipt(
        self,
        hash_bytes: bytes,
        record_type: str,
        batch_no: int,
        timestamp: int,
    ):
        """
        Same as :meth:`_send_tx` but returns the full transaction receipt, so
        callers can read the block number alongside the hash.
        """
        w3 = self._w3
        fn = self._contract.functions.addRecord(
            hash_bytes, record_type, batch_no, timestamp
        )

        if self._account is not None:
            # Signed transaction (Sepolia or localhost with explicit key)
            nonce = w3.eth.get_transaction_count(self._account.address)
            gas_price = w3.eth.gas_price
            tx = fn.build_transaction(
                {
                    "from":     self._account.address,
                    "nonce":    nonce,
                    "gasPrice": gas_price,
                    "gas":      200_000,
                }
            )
            signed = w3.eth.account.sign_transaction(tx, private_key=self._account.key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        else:
            # Unlocked Hardhat account (localhost only)
            tx_hash = fn.transact()

        return w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
