require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config({ path: "../.env" }); // read root .env

const SEPOLIA_RPC_URL = process.env.SEPOLIA_RPC_URL || "";
const PRIVATE_KEY     = process.env.PRIVATE_KEY     || "0x" + "0".repeat(64);
const ETHERSCAN_KEY   = process.env.ETHERSCAN_API_KEY || "";

// Safety guard: never print PRIVATE_KEY
if (PRIVATE_KEY && PRIVATE_KEY !== "0x" + "0".repeat(64)) {
  console.log("✅ Sepolia wallet loaded (key hidden)");
}

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.20",
    settings: {
      optimizer: { enabled: true, runs: 200 }
    }
  },
  networks: {
    hardhat: {},
    localhost: {
      url: "http://127.0.0.1:8545"
    },
    sepolia: {
      url: SEPOLIA_RPC_URL,
      accounts: PRIVATE_KEY !== "0x" + "0".repeat(64) ? [PRIVATE_KEY] : [],
      chainId: 11155111
    }
  },
  etherscan: {
    apiKey: ETHERSCAN_KEY
  }
};
