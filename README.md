# 🏦 Banking Customer Management System

> A production-grade Python banking backend that enforces real-world banking regulations, KYC compliance, AML/CTR monitoring, and role-based security — built with **FastAPI**, **SQLAlchemy**, **PostgreSQL**, and fully **Dockerized**.

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue)](https://docker.com)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL%2016-blue)](https://postgresql.org)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 📌 Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technical Stack & Libraries](#2-technical-stack--libraries)
3. [Core Modules & Business Logic](#3-core-modules--business-logic)
4. [Project Structure](#4-project-structure)
5. [Running with Docker (Recommended)](#5-running-with-docker-recommended)
6. [Running Locally (Without Docker)](#6-running-locally-without-docker)
7. [Testing via Swagger UI](#7-testing-via-swagger-ui)
8. [API Endpoints Reference](#8-api-endpoints-reference)
9. [Inspecting the Database](#9-inspecting-the-database)
10. [Banking Rules Quick Reference](#10-banking-rules-quick-reference)
11. [Unit Tests (pytest)](#11-unit-tests-pytest)
    - [Auto-Run Tests on File Save](#auto-run-tests-on-file-save)
    - [GitHub Actions CI](#github-actions-ci)
    - [Run Tests Inside Docker](#run-tests-inside-docker)

---

## 1. Project Overview

The **Banking Customer Management System** is a fully functional, compliance-aware Python backend that simulates real-world bank core operations. Every module mirrors the actual standards used by financial institutions.

### What the system does

| Domain | Capability |
|:---|:---|
| **Identity & KYC** | Onboard customers with encrypted PII, enforce KYC workflow |
| **Accounts** | SAVINGS, CURRENT, FIXED DEPOSIT with enforced balance rules |
| **Transactions** | Deposits, withdrawals, and transfers with daily limits |
| **Loans** | Apply, approve, disburse, and repay with auto-generated EMI schedules |
| **Compliance** | Auto-generate AML flags and CTR reports for suspicious transactions |
| **Audit** | Immutable audit trail for every state change |
| **Security** | JWT auth, Bcrypt, Fernet encryption, brute-force lockouts, RBAC |

---

## 2. Technical Stack & Libraries

| Library | Role & Why It Was Chosen |
|:---|:---|
| **FastAPI** | Web framework — chosen for automatic Swagger UI, async support, and dependency injection (used heavily for RBAC) |
| **SQLAlchemy** | ORM — abstracts raw SQL; seamlessly switches between SQLite (dev) and PostgreSQL (Docker/prod) |
| **Pydantic v2** | All request/response data is validated through typed schemas — invalid data never reaches business logic |
| **Passlib + Bcrypt 4.x** | Password hashing — Bcrypt is computationally slow by design, resisting brute-force attacks |
| **Cryptography (Fernet)** | AES-128 symmetric encryption for National IDs — stolen databases cannot reveal raw IDs |
| **python-jose (JWT)** | Stateless session management — user identity and role embedded in a signed token |
| **psycopg2-binary** | PostgreSQL driver — required when running with Docker/PostgreSQL |
| **python-dotenv** | Loads `.env` secrets without hardcoding them in source code |
| **python-dateutil** | Reliable date math for age verification (18+ check) |

---

## 3. Core Modules & Business Logic

### A. Authentication & Security (`models/auth.py`)
- **Role-Based Access Control (RBAC):** Four roles — `CUSTOMER < TELLER < MANAGER < ADMIN`. A Teller can open accounts but cannot approve loans or delete customers.
- **Brute-Force Lockout:** 3 failed login attempts → account locked for 15 minutes automatically.
- **JWT Tokens:** Issued on successful login, expire in 30 minutes. Every protected endpoint verifies the token and extracts the user role.

### B. Customer KYC Onboarding (`models/customer.py`)
- **Age Verification:** `(today - date_of_birth).days // 365 >= 18` — customers under 18 are strictly rejected.
- **Duplicate Detection:** SHA-256 hash of National ID stored separately — instant duplicate check without decrypting sensitive data.
- **Encrypted Storage:** The actual National ID is Fernet-encrypted at rest (looks like `gAAAAABpz5Ox...`). Plain text is never stored.
- **KYC Lifecycle:** `PENDING → VERIFIED` (or `REJECTED`). No banking activity until a Manager verifies.
- **Delete Guard:** Cannot delete a customer who has active accounts or loans.

### C. Account Management (`models/account.py`)
- **Paise-Based Arithmetic (Critical):** All money stored as integers in Paise (100 paise = ₹1). Floats cause rounding errors (`0.1 + 0.2 = 0.30000000000000004`) — unacceptable in banking.
- **Minimum Balances:** Savings ₹1,000 | Current ₹5,000 | FD ₹10,000. Withdrawals that breach these floors are rejected.
- **Daily Withdrawal Limits:** Savings ₹50,000 | Current ₹2,00,000. Resets at midnight automatically.
- **Account Status Enforcement:** `FROZEN` or `CLOSED` accounts block all transactions.

### D. Transaction Engine (`models/transaction.py`)
- **Atomic Transfers:** Fund transfers debit source and credit destination in a single database transaction — no partial failures.
- **Failed Transaction Logging:** Even rejected transactions are recorded with machine-readable `FailureReason` codes for fraud detection.
- **Immutable Audit Logs:** Every state change (KYC approval, account freeze, user creation) is permanently written to `audit_logs`. Zero delete/update capability.

### E. Loan Processing (`models/loan.py`)
- **Eligibility Gates:** KYC must be `VERIFIED`, account must be `ACTIVE` and at least **6 months old**, credit score must be **≥ 650**.
- **EMI Amortization Formula:** `EMI = P × r × (1+r)^n / ((1+r)^n - 1)` — standard banking formula auto-generates a full repayment schedule.
- **Loan Rates by Type:** Personal 12% | Home 8.5% | Vehicle 10% | Education 9%

### F. Compliance Middleware (AML & CTR)
- **AML Flag:** Any single transaction > ₹10,00,000 is automatically flagged and must be reviewed by a Manager.
- **CTR Report:** Any cash transaction > ₹50,000 auto-generates a Currency Transaction Report for regulatory submission.

---

## 4. Project Structure

```
banking_app/
│
├── Dockerfile               ← Multi-stage Docker build (non-root, lean final image)
├── docker-compose.yml       ← Orchestrates PostgreSQL + FastAPI app + optional pgAdmin
├── .dockerignore            ← Excludes venv, .env, __pycache__ from the Docker image
├── main.py                  ← App entry point — registers routes, runs startup lifecycle
├── database.py              ← SQLAlchemy engine (auto-switches SQLite ↔ PostgreSQL)
├── requirements.txt         ← All pinned Python dependencies
├── generate_env.py          ← Auto-generates SECRET_KEY, FERNET_KEY, and .env file
├── .env                     ← Secret keys (never committed to git)
├── .env.example             ← Template showing all required environment variables
│
├── models/                  ← SQLAlchemy table definitions
│   ├── auth.py              ← Users, roles, login_attempts
│   ├── customer.py          ← Customer KYC data
│   ├── account.py           ← Bank account model
│   ├── transaction.py       ← Transactions, audit_logs, CTR reports, AML flags
│   └── loan.py              ← Loans and EMI schedule
│
├── schemas/                 ← Pydantic request/response validation
├── services/                ← All banking business logic and rules
├── routes/                  ← HTTP API endpoint definitions
├── middleware/              ← JWT auth, RBAC, AML checker, audit logger
└── utils/                   ← ID generators, encryption helpers, interest math
```

---

## 5. Running with Docker (Recommended)

Docker is the **easiest and most production-like** way to run this project. It automatically starts a **PostgreSQL database** and the **FastAPI application** together with a single command.

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop) installed and running

### Step 1 — Clone the Repository
```bash
git clone https://github.com/Venu5198/Banking-Customer-Management-System.git
cd Banking-Customer-Management-System
```

### Step 2 — Generate Secrets
```bash
python generate_env.py
```
This creates a `.env` file with a secure `SECRET_KEY` and `FERNET_KEY`.

### Step 3 — Start Everything
```bash
# If your Docker version uses the hyphenated command:
docker-compose up --build

# If your Docker Desktop is newer (v2+):
docker compose up --build
```

On first run, Docker will:
1. Pull the **PostgreSQL 16** image
2. Build the **FastAPI app** image (multi-stage, ~16 steps)
3. Start PostgreSQL with a healthcheck
4. Wait for the DB to be ready, then start the app
5. Auto-seed the admin user

You will see:
```
banking_app  | INFO: 🏦 Banking App starting up...
banking_app  | INFO: ✅ Database tables initialized
banking_app  | INFO: ✅ Default admin user seeded.
banking_app  | INFO: Uvicorn running on http://0.0.0.0:8000
```

### Step 4 — Access the App

| Service | URL |
|:---|:---|
| **Swagger UI** | http://localhost:8000/docs |
| **Health Check** | http://localhost:8000/health |
| **PostgreSQL** | `localhost:5432` (user: `banking_user`, pass: `banking_pass`) |
| **pgAdmin** (optional) | http://localhost:5050 (see below) |

### Docker Commands Reference

```bash
# Start in background (detached mode)
docker-compose up --build -d

# View live logs
docker-compose logs -f

# Stop containers (database data is preserved)
docker-compose down

# Stop and wipe the database volume (full reset)
docker-compose down -v

# Launch with pgAdmin GUI (visual database browser)
docker-compose --profile tools up --build
# Then visit http://localhost:5050 → login: admin@bank.local / admin1234

# Rebuild only the app image (after code changes)
docker-compose up --build app
```

### Docker Architecture

```
┌─────────────────────────────────────────────┐
│              banking_network                 │
│                                             │
│  ┌──────────────┐     ┌───────────────────┐  │
│  │  banking_db  │────▶│   banking_app     │  │
│  │ PostgreSQL:  │     │  FastAPI + Uvicorn │  │
│  │  Port 5432   │     │    Port 8000       │  │
│  └──────────────┘     └───────────────────┘  │
│         │                                    │
│  ┌──────▼──────┐                             │
│  │postgres_data│ ← Named Volume (persistent) │
│  └─────────────┘                             │
└─────────────────────────────────────────────┘
```

> **Why `depends_on: condition: service_healthy`?**  
> The app waits for PostgreSQL to fully pass its health check before starting — preventing connection errors on cold boot.

---

## 6. Running Locally (Without Docker)

Use this method if you want to run with SQLite for quick local development.

### Step 1 — Create Virtual Environment
```bash
python -m venv venv

# Windows:
venv\Scripts\activate

# Mac/Linux:
source venv/bin/activate
```

### Step 2 — Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3 — Generate Keys & .env
```bash
python generate_env.py
```

### Step 4 — Start the Server
```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Visit: **http://127.0.0.1:8000/docs**

---

## 7. Testing via Swagger UI

FastAPI generates a fully interactive API explorer at **http://localhost:8000/docs**.

### Authenticate First
1. Click the green **Authorize** button (top right)
2. Enter **Username:** `admin` | **Password:** `admin1234`
3. Click **Authorize → Close**

### End-to-End Test Flow

| Step | Endpoint | Payload / Action | Expected Result |
|:---|:---|:---|:---|
| 1 | `POST /api/customers/` | DOB: 2015-01-01 | `422` — Under 18 rejected |
| 2 | `POST /api/customers/` | Valid adult DOB | `201` — Customer created (note the `id`) |
| 3 | `POST /api/customers/` | Same `national_id` | `409` — Duplicate blocked |
| 4 | `PATCH /api/customers/1/kyc` | `{"status": "VERIFIED"}` | `200` — KYC approved |
| 5 | `POST /api/accounts/` | SAVINGS, `50000` paise (₹500) | `422` — Below ₹1,000 minimum |
| 6 | `POST /api/accounts/` | SAVINGS, `500000` paise (₹5,000) | `201` — Account opened |
| 7 | `GET /api/accounts/1/balance` | — | `200` — Shows balance |
| 8 | `POST /api/transactions/deposit` | `200000` paise (₹2,000) | `201` — Deposited |
| 9 | `POST /api/transactions/withdraw` | Amount that breaches min balance | `422` — Minimum balance protection |
| 10 | `POST /api/transactions/transfer` | From account 1 → account 2 | `201` — Both balances updated atomically |
| 11 | `POST /api/transactions/deposit` | `150000000` paise (₹15,00,000) | `201` — `is_aml_flagged: true` |
| 12 | `GET /api/transactions/compliance/aml-flags` | — | `200` — Lists all AML flags |
| 13 | `PATCH /api/accounts/1/status` | `{"status": "FROZEN"}` | `200` — Account frozen |
| 14 | `POST /api/transactions/deposit` | Any amount to frozen account | `422` — Frozen account blocked |
| 15 | `DELETE /api/customers/1` | Customer has accounts | `400` — Delete guard blocks it |

---

## 8. API Endpoints Reference

### Authentication (`/api/auth`)
| Method | Endpoint | Role | Description |
|:---|:---|:---|:---|
| `POST` | `/api/auth/login` | Public | Login — returns JWT token |
| `POST` | `/api/auth/users` | ADMIN | Create bank staff user |
| `GET` | `/api/auth/me` | Any | Get current user profile |

### Customers (`/api/customers`)
| Method | Endpoint | Role | Description |
|:---|:---|:---|:---|
| `POST` | `/api/customers/` | TELLER+ | Onboard new customer |
| `GET` | `/api/customers/` | TELLER+ | List all customers |
| `GET` | `/api/customers/{id}` | Any | Get customer by ID |
| `PUT` | `/api/customers/{id}` | TELLER+ | Update customer details |
| `PATCH` | `/api/customers/{id}/kyc` | MANAGER+ | Approve or reject KYC |
| `DELETE` | `/api/customers/{id}` | MANAGER+ | Delete customer (blocked if accounts exist) |

### Accounts (`/api/accounts`)
| Method | Endpoint | Role | Description |
|:---|:---|:---|:---|
| `POST` | `/api/accounts/` | TELLER+ | Open new account |
| `GET` | `/api/accounts/{id}` | Any | Get account details |
| `GET` | `/api/accounts/{id}/balance` | Any | Get current balance |
| `PATCH` | `/api/accounts/{id}/status` | MANAGER+ | Freeze / unfreeze / close |

### Transactions (`/api/transactions`)
| Method | Endpoint | Role | Description |
|:---|:---|:---|:---|
| `POST` | `/api/transactions/deposit` | TELLER+ | Deposit money |
| `POST` | `/api/transactions/withdraw` | TELLER+ | Withdraw money |
| `POST` | `/api/transactions/transfer` | TELLER+ | Transfer between accounts |
| `GET` | `/api/transactions/account/{id}` | Any | List account transactions |
| `GET` | `/api/transactions/compliance/aml-flags` | ADMIN | View all AML flags |
| `GET` | `/api/transactions/compliance/ctr-reports` | ADMIN | View all CTR reports |

### Loans (`/api/loans`)
| Method | Endpoint | Role | Description |
|:---|:---|:---|:---|
| `POST` | `/api/loans/` | TELLER+ | Apply for a loan |
| `GET` | `/api/loans/{id}` | Any | Get loan details |
| `PATCH` | `/api/loans/{id}/approve` | MANAGER+ | Approve loan |
| `PATCH` | `/api/loans/{id}/disburse` | MANAGER+ | Disburse loan to account |
| `POST` | `/api/loans/{id}/repay` | TELLER+ | Pay EMI installment |

---

## 9. Inspecting the Database

### Docker — Connect via pgAdmin
1. Run `docker-compose --profile tools up --build`
2. Visit **http://localhost:5050**
3. Login: `admin@bank.local` / `admin1234`
4. Add a server: host=`db`, port=`5432`, user=`banking_user`, pass=`banking_pass`

### Local SQLite — VS Code Viewer
1. Install the **SQLite Viewer** extension
2. Open `banking.db` from the file explorer

### What to look for in each table

| Table | Key Things to Observe |
|:---|:---|
| `users` | `hashed_password` shows `$2b$12$...` — Bcrypt in action |
| `customers` | `national_id_encrypted` shows `gAAAAABpz5Ox...` — Fernet encryption in action |
| `accounts` | `balance_paise` stores integers (e.g. `500000` = ₹5,000) — no floats ever |
| `transactions` | `FAILED` rows with `failure_reason` codes alongside `SUCCESS` rows |
| `audit_logs` | Permanent record of every action: who did what, old value, new value |
| `aml_flags` | Triggered for transactions over ₹10,00,000 — `is_reviewed: false` until cleared |
| `ctr_reports` | Auto-generated for cash movements over ₹50,000 |

---

## 10. Banking Rules Quick Reference

| Rule | Value | Where Enforced |
|:---|:---|:---|
| Minimum customer age | 18 years | `customer_service.py` |
| Savings minimum balance | ₹1,000 | `transaction_service.py` |
| Current minimum balance | ₹5,000 | `transaction_service.py` |
| FD minimum balance | ₹10,000 | `account_service.py` |
| Savings daily withdrawal limit | ₹50,000 | `transaction_service.py` |
| Current daily withdrawal limit | ₹2,00,000 | `transaction_service.py` |
| Failed login lockout threshold | 3 attempts | `auth_middleware.py` |
| Account lockout duration | 15 minutes | `auth_middleware.py` |
| Loan min credit score | 650 | `loan_service.py` |
| Loan min account age | 6 months | `loan_service.py` |
| AML threshold | ₹10,00,000 | `aml_checker.py` |
| CTR threshold | ₹50,000 | `aml_checker.py` |

---

## 11. Unit Tests (pytest)

### Why Unit Tests?

Banking software is exception-intolerant. A single regression — an unchecked withdrawal breaching minimum balance, a KYC bypass, a loan approved for an unverified customer — could cause real financial and legal damage at scale.

Unit tests act as an **automated safety net** that:
- Verifies every business rule is enforced correctly, every time
- Catches breaking changes introduced during new feature development
- Documents exactly what the system is supposed to do (tests are living specifications)
- Enables confident refactoring without fear of silent regressions

---

### Why pytest?

| Choice | Reason |
|:---|:---|
| **pytest** | Python's most widely used testing framework — clean syntax, powerful fixtures, rich plugin ecosystem |
| **FastAPI TestClient** | Runs the full application stack against a real HTTP client without needing a live server |
| **In-memory SQLite** | Each test run uses a fresh, isolated database — no leftover data from previous tests |
| **Dependency Override** | FastAPI's `app.dependency_overrides` replaces the production DB with the test DB without changing any app code |
| **pytest-cov** | Measures which lines of code are covered by tests, identifying untested paths |

---

### How Tests Are Isolated (The Key Mechanism)

This is the most critical design decision in the test suite:

```python
# conftest.py

# 1. Create a separate in-memory SQLite engine — never touches banking.db
engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)

# 2. Override FastAPI's DB dependency for all tests
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# 3. Wipe all table data automatically between every single test
@pytest.fixture(autouse=True)
def clean_tables():
    yield
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
```

**Result:** Every test starts with a perfectly empty database. Test A's data can never bleed into Test B.

---

### Test File Structure

```
tests/
├── __init__.py              ← Makes tests/ a Python package
├── conftest.py              ← Shared fixtures (DB setup, tokens, verified customer, accounts)
├── test_auth.py             ← 16 tests — login, lockout, RBAC, user creation
├── test_customers.py        ← 21 tests — KYC workflow, age gate, duplicate detection
├── test_accounts.py         ← 15 tests — account types, min balance, freeze/close
├── test_transactions.py     ← 25 tests — deposit, withdrawal, transfers, AML/CTR
└── test_loans.py            ← 12 tests — eligibility, approval workflow, EMI math
```

**Total: 89 tests — all passing ✅**

---

### What Each Test Module Covers

#### `test_auth.py` — Authentication & Security
| Test | What It Proves |
|:---|:---|
| `test_login_success` | Valid credentials return a JWT token |
| `test_login_wrong_password` | Wrong password returns 401 |
| `test_brute_force_lockout` | 3 failed attempts locks the account (403) |
| `test_teller_cannot_create_users` | RBAC blocks Tellers from admin endpoints |
| `test_get_me_invalid_token` | Garbage JWT tokens are rejected |

#### `test_customers.py` — KYC Onboarding
| Test | What It Proves |
|:---|:---|
| `test_under_18_rejected` | Age < 18 is blocked at the service layer |
| `test_duplicate_national_id_rejected` | SHA-256 hash comparison catches duplicates |
| `test_manager_can_verify_kyc` | Only MANAGER+ can approve KYC status |
| `test_cannot_revert_verified_to_pending` | KYC state machine is unidirectional |
| `test_delete_customer_with_accounts_blocked` | Guard prevents deleting active customers |

#### `test_accounts.py` — Account Management
| Test | What It Proves |
|:---|:---|
| `test_savings_below_min_balance_rejected` | ₹1,000 floor enforced on Savings |
| `test_fd_below_min_balance_rejected` | ₹10,000 floor enforced on Fixed Deposits |
| `test_unverified_customer_cannot_open_account` | PENDING KYC blocks account opening |
| `test_manager_can_freeze_account` | Only MANAGER+ can change account status |

#### `test_transactions.py` — Transaction Engine
| Test | What It Proves |
|:---|:---|
| `test_withdrawal_below_min_balance_rejected` | Minimum balance floor prevents overdraft |
| `test_withdrawal_exact_minimum_balance_allowed` | Withdrawing to exactly ₹1,000 is permitted |
| `test_transfer_between_accounts` | Source decreases and destination increases atomically |
| `test_self_transfer_rejected` | Cannot transfer to the same account |
| `test_large_deposit_triggers_aml_flag` | Deposits > ₹10,00,000 auto-flag AML |
| `test_large_deposit_triggers_ctr_report` | Deposits > ₹50,000 auto-generate CTR |
| `test_deposit_on_frozen_account_blocked` | FROZEN accounts cannot transact |

#### `test_loans.py` — Loan Lifecycle
| Test | What It Proves |
|:---|:---|
| `test_loan_rejected_account_too_new` | Accounts < 6 months old cannot back a loan |
| `test_manager_can_approve_loan` | Only MANAGER+ approves loan applications |
| `test_emi_is_positive_and_reasonable` | EMI formula outputs match expected ₹8,885 range |
| `test_emi_schedule_sum_covers_principal_plus_interest` | Total payable > principal (interest is applied) |

---

### How to Run the Tests

#### Prerequisites
Ensure dependencies are installed:
```bash
pip install -r requirements.txt
```

#### Run All Tests
```bash
python -m pytest tests/ -v
```

#### Run a Specific File
```bash
python -m pytest tests/test_transactions.py -v
python -m pytest tests/test_auth.py -v
python -m pytest tests/test_customers.py -v
```

#### Run a Specific Test Class
```bash
python -m pytest tests/test_customers.py::TestKYCWorkflow -v
python -m pytest tests/test_transactions.py::TestAMLAndCTR -v
python -m pytest tests/test_loans.py::TestEMICalculation -v
```

#### Run a Single Test
```bash
python -m pytest tests/test_auth.py::TestLogin::test_brute_force_lockout -v
python -m pytest tests/test_transactions.py::TestWithdrawal::test_withdrawal_below_min_balance_rejected -v
```

#### Run with Coverage Report
```bash
python -m pytest tests/ --cov=. --cov-report=term-missing
```
This shows exactly which lines of your services and routes are covered by tests.

#### Run with Short Summary (fast output)
```bash
python -m pytest tests/ -q
```

---

### Expected Output

A successful run produces:
```
tests/test_accounts.py::TestOpenAccount::test_open_savings_account PASSED     [  1%]
tests/test_accounts.py::TestOpenAccount::test_open_current_account PASSED     [  2%]
...
tests/test_transactions.py::TestAMLAndCTR::test_large_deposit_triggers_aml_flag PASSED  [ 93%]
tests/test_transactions.py::TestAMLAndCTR::test_large_deposit_triggers_ctr_report PASSED [ 94%]
...
=================== 89 passed in 105.64s (0:01:45) ===================
```

> 💡 **Tests run against an in-memory SQLite database and never touch your real `banking.db` or PostgreSQL database.** They are completely safe to run at any time.

---

### Auto-Run Tests on File Save

**What it is:** Instead of manually running `pytest` after every code change, `pytest-watch` monitors your project folder for saved changes and re-runs the full test suite automatically in the background.

**Why it matters:** This creates an instant feedback loop — a red failure appears within seconds of you writing a bug, rather than discovering it later during a manual run.

**How it works:**
`pytest-watch` (installed via `requirements.txt`) uses filesystem event listeners to detect when any `.py` file changes. The moment you hit **Save** in your editor, it triggers a fresh `pytest` run and prints the results directly in the terminal.

**How to run it:**
```bash
# Start the file watcher — it runs until you press Ctrl+C
python -m pytest_watch tests/ -- --tb=short -q
```

**What you will see in the terminal:**
```
[pytest-watch] Starting...
[pytest-watch] Running: pytest tests/ --tb=short -q

89 passed in 102.54s

[pytest-watch] Watching for changes in: tests/, models/, services/, routes/
# ...Save any file...
[pytest-watch] Change detected! Re-running tests...

89 passed in 104.12s
```

> ⚠️ On Windows, use `python -m pytest_watch` instead of just `ptw` if the `ptw` command is not found on your system PATH.

---

### GitHub Actions CI

**What it is:** A cloud pipeline that automatically runs all 89 tests on GitHub's servers every time you push code to the repository or open a Pull Request — without you doing anything manually.

**Why it matters:** It prevents broken code from being merged into `main`. If you push a change that breaks a business rule (e.g., removes the minimum balance check), the pipeline goes red before anyone merges it. It is the standard practice in professional software teams.

**How it works:**
The file `.github/workflows/tests.yml` defines the pipeline. GitHub reads this file on every `git push` and executes the steps automatically on its cloud servers:

```
push to main branch
       ↓
GitHub Actions triggers
       ↓
  Checkout code
       ↓
  Set up Python 3.11 & 3.12 (matrix — runs in parallel)
       ↓
  pip install -r requirements.txt
       ↓
  python generate_env.py  ← generates fresh crypto keys for CI
       ↓
  pytest tests/ --cov=. --cov-report=xml
       ↓
  ✅ All 89 passed → Green checkmark on GitHub
  ❌ Any failure  → Red X, email notification, PR blocked
```

**Triggers:**
- Every `git push` to `main` or `develop`
- Every Pull Request targeting `main` or `develop`

**How to view the results:**
1. Go to your repository on GitHub
2. Click the **Actions** tab
3. Click the latest workflow run to see per-job logs and test output

**Current CI status:** ✅ **Run Tests #1 — Passed (2m 28s)** on Python 3.11 and 3.12

**To re-trigger manually:**
```bash
git commit --allow-empty -m "trigger CI"
git push
```

---

### Run Tests Inside Docker

**What it is:** Running the entire pytest suite inside a Docker container, isolated from your local machine's Python environment — exactly as it would run on a production server or in CI.

**Why it matters:** It guarantees that the tests pass in a clean, reproducible environment regardless of what Python packages you have installed locally. It answers the common question *"works on my machine but fails in CI"*.

**How it works:**
The `docker-compose.yml` defines a dedicated `test` service that:
1. Builds the same Docker image used for the app
2. Mounts the source code so you don't need to rebuild the image on every code change
3. Generates fresh `.env` secrets at runtime
4. Runs `pytest` against an **in-memory SQLite** database — no PostgreSQL dependency required
5. Removes the container automatically after the run (`--rm` flag)

```yaml
# What the test service does inside Docker:
sh -c "python generate_env.py && python -m pytest tests/ --tb=short -v"
```

**How to run it:**
```bash
# Run the full test suite inside Docker (exits when done)
docker-compose --profile test run --rm test
```

**What you will see:**
```
[+] Building 2.3s (complete)
Creating banking_test ... done
SUCCESS: .env created

tests/test_accounts.py::TestOpenAccount::test_open_savings_account PASSED [  1%]
tests/test_accounts.py::TestOpenAccount::test_open_current_account PASSED [  2%]
...
=================== 89 passed in 108.41s ===================
```

> ⚠️ **Note:** The Docker test service uses `DATABASE_URL=sqlite:///./banking_test.db` so it **never connects to your PostgreSQL container**. It is completely self-contained and will not affect any live data.

**Comparison table:**

| Method | When to Use | DB Used | Speed |
|:---|:---|:---|:---|
| `pytest tests/ -v` | During active development | In-memory SQLite | Fastest |
| `python -m pytest_watch` | Continuous development feedback | In-memory SQLite | Auto on save |
| `docker-compose --profile test run --rm test` | Before pushing / environment validation | SQLite in container | Moderate |
| GitHub Actions | Automatic on every push/PR | In-memory SQLite (CI) | Cloud (parallel) |

---

## 🔗 Repository

**GitHub:** [https://github.com/Venu5198/Banking-Customer-Management-System](https://github.com/Venu5198/Banking-Customer-Management-System)

---

*Developed as a production-grade blueprint demonstrating real-world banking backend development using Python, FastAPI, PostgreSQL, and Docker.*
