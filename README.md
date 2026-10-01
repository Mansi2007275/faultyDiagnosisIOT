# SentinelTwin — Zero-Trust Industrial Digital Twin & Fault Diagnosis

An end-to-end industrial digital twin platform implementing **Zero-Trust Telemetry Verification**, **Device Reputation & Honeypot Defense**, **AI4I 2020 Multi-Physics Fault Diagnostics**, **Role-Based Access Control (RBAC)**, and **Tamper-Evident SHA-256 Merkle Ledger**.

---

## 🔑 Demo users (change before any real use)

The platform includes 5 default role-based demo accounts seeded automatically on first run:

| Username | Password | Role | Permissions Overview |
| :--- | :--- | :--- | :--- |
| `admin` | `Admin@123` | **Admin** | Full system control, User Management, Device Quarantine Release/Revoke/Restore, Retrain ML models, Reset Demo Data |
| `engineer` | `Engineer@123` | **Engineer** | Attack Lab, Model Retraining, Maintenance job requesting & signing, Security Center inspection |
| `safety` | `Safety@123` | **Safety Officer** | Maintenance dual-signing (Safety), Audit Log inspection, Security Center inspection |
| `operator` | `Operator@123` | **Operator** | Live telemetry monitoring, Plant Overview, Dataset Analytics |
| `auditor` | `Auditor@123` | **Auditor** | Read-only access to Audit Logs, Security Center, Models, Ledger & Datasets |

---

## 🔒 Security & Authentication Architecture Notes

- **Password Storage:** Passwords are hashed using `bcrypt` with unique salts. Plaintext passwords are **never** logged or stored in database tables.
- **Account Lockout:** After 5 failed authentication attempts, the target user account is locked for 15 minutes.
- **Inactivity Timeout:** Sessions automatically expire after 30 minutes of inactivity.
- **Audit Logging:** Every login success, login failure, lockout, password change, user creation/deactivation, attack injection, model retrain, and maintenance signature is recorded in the SQLite `audit_log` table.
- **Production Deployment Note:** This is application-level login intended for evaluation and demo purposes. A real-world plant installation should connect to corporate Single Sign-On (SSO / OIDC / SAML 2.0) and enforce TLS/HTTPS encryption across all edge nodes.

---

## 📁 Modular Architecture

```text
fault-diagnosis-project/
├── app.py                          # Master Streamlit entry point, RBAC router & login gatekeeper
├── PROJECT_RULES.md                # Engineering constraints and conventions
│
├── auth/                           # Authentication & RBAC module (Step 9)
│   ├── __init__.py
│   ├── db.py                       # SQLite users & audit_log tables
│   ├── security.py                 # Bcrypt hashing & password validation
│   ├── permissions.py              # Centralized permission matrix & RBAC checkers
│   └── service.py                  # Login, lockouts, user CRUD & audit logging
│
├── simulator/                      # Machine simulation & attack injection
│   ├── __init__.py
│   ├── data_loader.py              # AI4I 2020 dataset loader + synthetic benchmark
│   ├── virtual_machine.py          # Physics-based virtual machine fleet
│   └── attacks.py                  # MITM, replay, physics, stuck sensor, honeypot & flood attacks
│
├── trust/                          # Zero-Trust verification engine & reputation (Step 8)
│   ├── __init__.py
│   ├── signature.py                # HMAC-SHA256 device signature validator
│   ├── replay.py                   # Anti-replay sequence and timestamp freshness check
│   ├── physics.py                  # Thermodynamic gradient and power law validator
│   ├── stuck_sensor.py             # Rolling variance and frozen transducer detector
│   ├── reputation.py               # Device reputation score history, flood detector & Security Score
│   └── engine.py                   # Composite trust scoring and verdict aggregator
│
├── health/                         # Predictive maintenance & fault diagnostics
│   ├── __init__.py
│   ├── fault_rules.py              # AI4I standard failure rules (TWF, HDF, PWF, OSF, RNF)
│   └── diagnostics.py              # Severity grading, health index & response ladder
│
├── ledger/                         # Cryptographic audit log
│   ├── __init__.py
│   ├── hasher.py                   # Canonical record hashing & Merkle tree roots
│   └── batch.py                    # Batch management, hash chaining & tamper proofs
│
└── dashboard/                      # UI components & pages
    ├── __init__.py
    ├── components.py               # Glassmorphism dark theme CSS, cards & badges
    └── pages/
        ├── __init__.py
        ├── overview.py             # Page 1: System Overview & Fleet Analytics
        ├── live_monitor.py         # Page 2: Real-time Telemetry & Digital Twin
        ├── trust_security.py       # Page 3: Zero-Trust Engine & Attack Simulator
        ├── health_diagnostics.py   # Page 4: Predictive Health & Response Ladder
        ├── audit_ledger.py         # Page 5: Merkle Ledger & Tamper Verification
        ├── security_center.py      # Page 6: Security Center & Reputation Posture (Step 8)
        ├── users_page.py           # Page 7: Admin User Management (Step 9)
        └── audit_log_page.py       # Page 8: Audit Log & Compliance Traceability (Step 9)
```

---

## 🚀 Running the Application

To run the dashboard:

```bash
python -m streamlit run app.py
```

Then open `http://localhost:8501` in your browser.

---

## 🧪 Running Unit Tests

To run the complete test suite (including authentication, device reputation, anomaly detection, fault classification, and verdict engine):

```bash
pytest
```
