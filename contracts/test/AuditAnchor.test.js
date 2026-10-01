const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AuditAnchor", function () {
  let anchor;
  let owner;
  let nonOwner;

  // SHA-256 style bytes32 hashes for tests
  const HASH_1 = ethers.encodeBytes32String("batchhash0001");
  const HASH_2 = ethers.encodeBytes32String("batchhash0002");
  const TYPE_TELEMETRY = "TELEMETRY_BATCH";
  const TYPE_EVENT     = "SECURITY_EVENT";

  beforeEach(async function () {
    [owner, nonOwner] = await ethers.getSigners();
    const AuditAnchor = await ethers.getContractFactory("AuditAnchor");
    anchor = await AuditAnchor.deploy();
  });

  // ── 1. Owner can add a record ──────────────────────────────────────────
  it("owner can add a record and count increases", async function () {
    expect(await anchor.recordCount()).to.equal(0);

    await anchor.connect(owner).addRecord(HASH_1, TYPE_TELEMETRY, 0, 1700000000);

    expect(await anchor.recordCount()).to.equal(1);
  });

  // ── 2. Non-owner is rejected ───────────────────────────────────────────
  it("non-owner is rejected with NotOwner error", async function () {
    await expect(
      anchor.connect(nonOwner).addRecord(HASH_1, TYPE_TELEMETRY, 0, 1700000000)
    ).to.be.revertedWithCustomError(anchor, "NotOwner");
  });

  // ── 3. Records cannot change after insertion ───────────────────────────
  it("stored record data matches what was submitted", async function () {
    const ts = 1700000042;
    await anchor.connect(owner).addRecord(HASH_1, TYPE_TELEMETRY, 7, ts);

    const [hash, recordType, batchNo, timestamp, submitter] =
      await anchor.getRecord(0);

    expect(hash).to.equal(HASH_1);
    expect(recordType).to.equal(TYPE_TELEMETRY);
    expect(batchNo).to.equal(7n);
    expect(timestamp).to.equal(BigInt(ts));
    expect(submitter).to.equal(owner.address);
  });

  // ── 4. Count increases with multiple records ───────────────────────────
  it("count increases correctly with multiple records", async function () {
    await anchor.addRecord(HASH_1, TYPE_TELEMETRY, 0, 1700000001);
    await anchor.addRecord(HASH_2, TYPE_EVENT,     1, 1700000002);
    await anchor.addRecord(HASH_1, TYPE_TELEMETRY, 2, 1700000003);

    expect(await anchor.recordCount()).to.equal(3);
  });

  // ── 5. Event is emitted on every new record ────────────────────────────
  it("emits RecordAdded event with correct fields", async function () {
    const ts = 1700000099;
    await expect(anchor.connect(owner).addRecord(HASH_2, TYPE_EVENT, 3, ts))
      .to.emit(anchor, "RecordAdded")
      .withArgs(0, HASH_2, TYPE_EVENT, 3n, BigInt(ts), owner.address);
  });

  // ── 6. Zero hash is rejected ───────────────────────────────────────────
  it("reverts when hash is zero bytes32", async function () {
    const ZERO_HASH = ethers.ZeroHash;
    await expect(
      anchor.addRecord(ZERO_HASH, TYPE_TELEMETRY, 0, 1700000000)
    ).to.be.revertedWithCustomError(anchor, "EmptyHash");
  });

  // ── 7. Empty record type is rejected ──────────────────────────────────
  it("reverts when recordType is empty string", async function () {
    await expect(
      anchor.addRecord(HASH_1, "", 0, 1700000000)
    ).to.be.revertedWithCustomError(anchor, "EmptyRecordType");
  });

  // ── 8. getRecord reverts on out-of-range id ───────────────────────────
  it("getRecord reverts for out-of-range id", async function () {
    await expect(anchor.getRecord(0)).to.be.revertedWith(
      "AuditAnchor: id out of range"
    );
  });

  // ── 9. Owner address is set correctly ─────────────────────────────────
  it("owner() returns deployer address", async function () {
    expect(await anchor.owner()).to.equal(owner.address);
  });
});
