# AuditAnchor Smart Contract

Solidity contract for SentinelTwin's on-chain audit anchoring. Uses **Hardhat** — no Docker or WSL required on Windows.

## Quick Start (Windows PowerShell)

```powershell
# 1. Enter the contracts folder
cd contracts

# 2. Install dependencies (first time only)
npm install

# 3. Compile the contract
npx hardhat compile

# 4. Run tests (uses in-process Hardhat network — fast)
npx hardhat test

# 5a. LOCAL: Start the Hardhat node (keep this terminal open)
npx hardhat node

# 5b. LOCAL: In a NEW terminal, deploy the contract
npm run deploy:localhost
#   → saves contracts/deployments/local.json (Python reads this file)

# 6. Restart the Streamlit app — the Ledger page will show "🟢 Blockchain connected"
```

## Sepolia Testnet

> You need an Alchemy (or Infura) account and a wallet with Sepolia ETH.
> Get free testnet ETH from https://sepoliafaucet.com/

```powershell
# 1. Edit the ROOT .env file (not inside contracts/)
#    Fill in your actual values:
SEPOLIA_RPC_URL=https://eth-sepolia.g.alchemy.com/v2/<your-key>
PRIVATE_KEY=0x<your-wallet-private-key>
ETHERSCAN_API_KEY=<your-etherscan-key>
CHAIN=sepolia

# 2. Deploy to Sepolia
npm run deploy:sepolia
#   → saves contracts/deployments/local.json with Sepolia address

# 3. Restart Streamlit — anchoring now goes to the real Sepolia testnet
```

## Files

| File | Purpose |
|---|---|
| `contracts/AuditAnchor.sol` | Solidity contract — append-only record store |
| `scripts/deploy.js` | Deploy script (localhost + Sepolia) |
| `test/AuditAnchor.test.js` | Hardhat test suite (9 tests) |
| `hardhat.config.js` | Network config (reads `../.env`) |
| `deployments/local.json` | Auto-generated after deploy — read by Python |

## Contract ABI Summary

| Function | Access | Description |
|---|---|---|
| `addRecord(hash, recordType, batchNo, timestamp)` | owner only | Anchors a new record on-chain |
| `getRecord(id)` | public | Returns a record by index |
| `recordCount()` | public | Total number of records |
| `owner()` | public | Deployer address |

Event emitted on every new record:
```solidity
event RecordAdded(uint256 indexed id, bytes32 indexed hash, string recordType,
                  uint256 batchNo, uint256 timestamp, address indexed submitter);
```
