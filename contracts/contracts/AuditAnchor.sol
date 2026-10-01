// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title AuditAnchor
 * @notice Append-only audit record store for SentinelTwin.
 *         Only the contract owner (deployer) may add records.
 *         Records can never be updated or deleted.
 * @dev Each record stores a SHA-256 hash (bytes32), a record type string,
 *      a batch number, a Unix timestamp, and the submitter address.
 */
contract AuditAnchor {
    // ─────────────────────────────────────────────
    //  Storage
    // ─────────────────────────────────────────────

    /// @notice Deployer address — the only account allowed to add records.
    address public immutable owner;

    struct Record {
        bytes32 hash;         // SHA-256 batch hash from the Python ledger
        string  recordType;   // e.g. "TELEMETRY_BATCH", "SECURITY_EVENT"
        uint256 batchNo;      // Matches AuditLedger.batch_index
        uint256 timestamp;    // Unix epoch (seconds)
        address submitter;    // msg.sender at time of submission
    }

    /// @dev Internal ordered list of all records (index = record id, 0-based)
    Record[] private _records;

    // ─────────────────────────────────────────────
    //  Events
    // ─────────────────────────────────────────────

    /**
     * @notice Emitted every time a new record is anchored on-chain.
     * @param id          Zero-based index of the new record.
     * @param hash        SHA-256 digest anchored.
     * @param recordType  Human-readable record category.
     * @param batchNo     Batch number from the Python ledger.
     * @param timestamp   Unix timestamp of the record.
     * @param submitter   Ethereum address that submitted the record.
     */
    event RecordAdded(
        uint256 indexed id,
        bytes32 indexed hash,
        string          recordType,
        uint256         batchNo,
        uint256         timestamp,
        address indexed submitter
    );

    // ─────────────────────────────────────────────
    //  Errors
    // ─────────────────────────────────────────────

    error NotOwner();
    error EmptyHash();
    error EmptyRecordType();

    // ─────────────────────────────────────────────
    //  Constructor
    // ─────────────────────────────────────────────

    constructor() {
        owner = msg.sender;
    }

    // ─────────────────────────────────────────────
    //  Modifiers
    // ─────────────────────────────────────────────

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    // ─────────────────────────────────────────────
    //  Write — owner only
    // ─────────────────────────────────────────────

    /**
     * @notice Anchors a new audit record on-chain.
     * @param hash       SHA-256 batch/event hash produced by the Python ledger.
     * @param recordType Category label (e.g. "TELEMETRY_BATCH").
     * @param batchNo    Batch index from the Python AuditLedger.
     * @param timestamp  Unix timestamp (seconds).  Pass block.timestamp if live.
     */
    function addRecord(
        bytes32 hash,
        string calldata recordType,
        uint256 batchNo,
        uint256 timestamp
    ) external onlyOwner {
        if (hash == bytes32(0))                     revert EmptyHash();
        if (bytes(recordType).length == 0)          revert EmptyRecordType();

        uint256 id = _records.length;
        _records.push(Record({
            hash:       hash,
            recordType: recordType,
            batchNo:    batchNo,
            timestamp:  timestamp,
            submitter:  msg.sender
        }));

        emit RecordAdded(id, hash, recordType, batchNo, timestamp, msg.sender);
    }

    // ─────────────────────────────────────────────
    //  Read
    // ─────────────────────────────────────────────

    /**
     * @notice Returns the total number of anchored records.
     */
    function recordCount() external view returns (uint256) {
        return _records.length;
    }

    /**
     * @notice Returns a single record by its zero-based id.
     * @param id  Index of the record (0 … recordCount-1).
     */
    function getRecord(uint256 id)
        external
        view
        returns (
            bytes32 hash,
            string memory recordType,
            uint256 batchNo,
            uint256 timestamp,
            address submitter
        )
    {
        require(id < _records.length, "AuditAnchor: id out of range");
        Record storage r = _records[id];
        return (r.hash, r.recordType, r.batchNo, r.timestamp, r.submitter);
    }
}
