const { ethers, network } = require("hardhat");
const fs   = require("fs");
const path = require("path");

async function main() {
  const [deployer] = await ethers.getSigners();
  const networkName = network.name;

  console.log(`\n🚀 Deploying AuditAnchor to network: ${networkName}`);
  console.log(`   Deployer: ${deployer.address}`);

  const balance = await ethers.provider.getBalance(deployer.address);
  console.log(`   Balance:  ${ethers.formatEther(balance)} ETH\n`);

  // ── Deploy ───────────────────────────────────────────────────────────
  const AuditAnchor = await ethers.getContractFactory("AuditAnchor");
  const anchor      = await AuditAnchor.deploy();
  await anchor.waitForDeployment();

  const contractAddress = await anchor.getAddress();
  console.log(`✅ AuditAnchor deployed at: ${contractAddress}`);

  // ── Save address + ABI to deployments/local.json ────────────────────
  const deploymentsDir = path.join(__dirname, "..", "deployments");
  if (!fs.existsSync(deploymentsDir)) {
    fs.mkdirSync(deploymentsDir, { recursive: true });
  }

  // Read compiled ABI from Hardhat artifacts
  const artifactPath = path.join(
    __dirname,
    "..",
    "artifacts",
    "contracts",
    "AuditAnchor.sol",
    "AuditAnchor.json"
  );
  const artifact = JSON.parse(fs.readFileSync(artifactPath, "utf8"));

  const deployment = {
    network:         networkName,
    contractAddress: contractAddress,
    deployer:        deployer.address,
    deployedAt:      new Date().toISOString(),
    abi:             artifact.abi
  };

  const outFile = path.join(deploymentsDir, "local.json");
  fs.writeFileSync(outFile, JSON.stringify(deployment, null, 2));
  console.log(`📄 Deployment info saved to: contracts/deployments/local.json`);
  console.log(`\n   Set in your .env:`);
  console.log(`   CHAIN=localhost`);
  console.log(`   (already the default)\n`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
