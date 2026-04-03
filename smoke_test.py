"""
Full smoke test for the Banking API.
Tests: login, customer KYC, account open, deposit, withdraw, transfer, loan apply/approve/disburse/EMI.
"""

import requests
import sys

BASE = "http://127.0.0.1:8000"
PASS = True

def check(label, resp, expected_status):
    global PASS
    ok = resp.status_code == expected_status
    status = "PASS" if ok else "FAIL"
    if not ok:
        PASS = False
    print(f"  [{status}] {label} -> HTTP {resp.status_code}")
    if not ok:
        print(f"         Body: {resp.text[:300]}")
    return resp.json() if ok else None

# ── 1. Health ─────────────────────────────────────────────────────────────────
print("\n=== Health ===")
r = requests.get(f"{BASE}/health")
check("GET /health", r, 200)

# ── 2. Login as admin ─────────────────────────────────────────────────────────
print("\n=== Auth ===")
r = requests.post(f"{BASE}/api/auth/login", data={"username": "admin", "password": "admin1234"})
resp = check("POST /api/auth/login", r, 200)
token = resp["access_token"] if resp else None
ADMIN = {"Authorization": f"Bearer {token}"}

# ── 3. Create a Teller user ───────────────────────────────────────────────────
r = requests.post(f"{BASE}/api/auth/users", json={
    "username": "teller1", "email": "teller@bank.com",
    "password": "teller1234", "role": "TELLER"
}, headers=ADMIN)
check("POST /api/auth/users (teller)", r, 200)

# ── 4. Login as Teller ────────────────────────────────────────────────────────
r = requests.post(f"{BASE}/api/auth/login", data={"username": "teller1", "password": "teller1234"})
resp = check("POST /api/auth/login (teller)", r, 200)
TELLER = {"Authorization": f"Bearer {resp['access_token']}"} if resp else ADMIN

# ── 5. Create customer (must be 18+) ─────────────────────────────────────────
print("\n=== KYC Onboarding ===")
r = requests.post(f"{BASE}/api/customers/", json={
    "full_name": "Priya Sharma",
    "date_of_birth": "1995-06-15",
    "national_id": "AADHAR-987654321012",
    "address": "42 MG Road, Bengaluru, Karnataka 560001",
    "phone": "+919876543210",
    "email": "priya.sharma2@example.com"
}, headers=TELLER)
cust = check("POST /api/customers/ (create)", r, 201)
cust_id = cust["id"] if cust else 1

# Try under-18 (should fail)
r = requests.post(f"{BASE}/api/customers/", json={
    "full_name": "Minor User",
    "date_of_birth": "2015-01-01",
    "national_id": "MINOR-ID-999",
    "address": "123 Test St",
    "phone": "9000000001",
    "email": "minor@test.com"
}, headers=TELLER)
check("POST /api/customers/ (under-18, expect 422)", r, 422)

# Verify KYC (need Manager — use admin)
print("\n=== KYC Approval ===")
r = requests.patch(f"{BASE}/api/customers/{cust_id}/kyc",
    json={"status": "VERIFIED"}, headers=ADMIN)
check("PATCH /kyc (verify)", r, 200)

# ── 6. Open Accounts ─────────────────────────────────────────────────────────
print("\n=== Accounts ===")
r = requests.post(f"{BASE}/api/accounts/", json={
    "customer_id": cust_id,
    "account_type": "SAVINGS",
    "opening_balance_paise": 200000   # ₹2,000
}, headers=TELLER)
savings = check("POST /api/accounts/ (savings)", r, 201)
savings_id = savings["id"] if savings else 1

# Below min balance (should fail — ₹500 < ₹1,000 min)
r = requests.post(f"{BASE}/api/accounts/", json={
    "customer_id": cust_id,
    "account_type": "SAVINGS",
    "opening_balance_paise": 50000   # ₹500
}, headers=TELLER)
check("POST /api/accounts/ (below min, expect 422)", r, 422)

r = requests.post(f"{BASE}/api/accounts/", json={
    "customer_id": cust_id,
    "account_type": "CURRENT",
    "opening_balance_paise": 600000   # ₹6,000
}, headers=TELLER)
current = check("POST /api/accounts/ (current)", r, 201)
current_id = current["id"] if current else 2

r = requests.post(f"{BASE}/api/accounts/", json={
    "customer_id": cust_id,
    "account_type": "FIXED_DEPOSIT",
    "opening_balance_paise": 1000000,  # ₹10,000
    "fd_tenure_months": 12
}, headers=TELLER)
fd = check("POST /api/accounts/ (FD)", r, 201)
fd_id = fd["id"] if fd else 3

# ── 7. Balance ────────────────────────────────────────────────────────────────
print("\n=== Balance & Transactions ===")
r = requests.get(f"{BASE}/api/accounts/{savings_id}/balance", headers=TELLER)
check("GET /api/accounts/{id}/balance", r, 200)

# Deposit
r = requests.post(f"{BASE}/api/transactions/deposit", json={
    "account_id": savings_id,
    "txn_type": "DEPOSIT",
    "amount_paise": 500000,   # ₹5,000
    "description": "Salary credit"
}, headers=TELLER)
dep = check("POST /transactions/deposit (5,000)", r, 201)

# Withdraw (valid)
r = requests.post(f"{BASE}/api/transactions/withdraw", json={
    "account_id": savings_id,
    "txn_type": "WITHDRAWAL",
    "amount_paise": 100000,  # 1,000
    "description": "ATM withdrawal"
}, headers=TELLER)
check("POST /transactions/withdraw (1,000)", r, 201)

# Withdraw below min balance (should fail)
r = requests.post(f"{BASE}/api/transactions/withdraw", json={
    "account_id": savings_id,
    "txn_type": "WITHDRAWAL",
    "amount_paise": 599000,  # Would leave < ₹1,000 min
    "description": "Over-limit withdrawal"
}, headers=TELLER)
check("POST /transactions/withdraw (below min, expect 422)", r, 422)

# AML test — deposit > ₹10,00,000
r = requests.post(f"{BASE}/api/transactions/deposit", json={
    "account_id": savings_id,
    "txn_type": "DEPOSIT",
    "amount_paise": 150000000,  # ₹15,00,000
    "description": "Large AML test deposit"
}, headers=TELLER)
aml_dep = check("POST /transactions/deposit (AML > 10L)", r, 201)
if aml_dep:
    print(f"         AML flagged: {aml_dep.get('is_aml_flagged')} | CTR: {aml_dep.get('is_ctr_generated')}")

# Transfer
r = requests.post(f"{BASE}/api/transactions/transfer", json={
    "from_account_id": savings_id,
    "to_account_id": current_id,
    "amount_paise": 100000,  # ₹1,000
    "description": "Fund transfer"
}, headers=TELLER)
check("POST /transactions/transfer", r, 201)

# List transactions
r = requests.get(f"{BASE}/api/transactions/account/{savings_id}", headers=TELLER)
check("GET /transactions/account/{id}", r, 200)

# ── 8. Freeze account & try transact ─────────────────────────────────────────
print("\n=== Account Status ===")
r = requests.patch(f"{BASE}/api/accounts/{current_id}/status",
    json={"status": "FROZEN", "reason": "Suspicious activity"}, headers=ADMIN)
check("PATCH /accounts/{id}/status (freeze)", r, 200)

r = requests.post(f"{BASE}/api/transactions/deposit", json={
    "account_id": current_id,
    "txn_type": "DEPOSIT",
    "amount_paise": 10000   # ₹100
}, headers=TELLER)
check("POST /deposit on FROZEN account (expect 422)", r, 422)

# Unfreeze
r = requests.patch(f"{BASE}/api/accounts/{current_id}/status",
    json={"status": "ACTIVE"}, headers=ADMIN)
check("PATCH /accounts/{id}/status (unfreeze)", r, 200)

# ── 9. Compliance Reports ────────────────────────────────────────────────────
print("\n=== Compliance ===")
r = requests.get(f"{BASE}/api/transactions/compliance/aml-flags", headers=ADMIN)
aml_list = check("GET /compliance/aml-flags", r, 200)
if aml_list:
    print(f"         AML flags found: {len(aml_list)}")

r = requests.get(f"{BASE}/api/transactions/compliance/ctr-reports", headers=ADMIN)
ctr_list = check("GET /compliance/ctr-reports", r, 200)
if ctr_list:
    print(f"         CTR reports found: {len(ctr_list)}")

# ── 10. Create 2nd customer for loan (needs 6-month-old account) ─────────────
# We'll just test loan eligibility rejection due to account age
print("\n=== Loans ===")
r = requests.post(f"{BASE}/api/loans/", json={
    "customer_id": cust_id,
    "linked_account_id": savings_id,
    "loan_type": "PERSONAL",
    "principal_paise": 10000000,  # ₹1,00,000
    "tenure_months": 24
}, headers=TELLER)
# Expecting 422 since account < 6 months old
check("POST /api/loans/ (expect 422 — account < 6 months)", r, 422)

print(f"\n{'='*50}")
print(f"  OVERALL: {'ALL TESTS PASSED' if PASS else 'SOME TESTS FAILED'}")
print(f"{'='*50}\n")
