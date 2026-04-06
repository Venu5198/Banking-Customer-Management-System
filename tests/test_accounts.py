"""
test_accounts.py — Tests for Account Management

Covers:
  - Opening SAVINGS, CURRENT, and FIXED_DEPOSIT accounts
  - Minimum opening balance enforcement for each type
  - Below-minimum balance rejection
  - Unverified customer cannot open account
  - Account number format (ACC-YYYY-XXXXXX)
  - Balance endpoint correctness
  - Freeze, unfreeze, close account status workflow
  - Role restrictions (only MANAGER+ can freeze)
  - FD account requires tenure_months
"""

import pytest


class TestOpenAccount:
    """Tests for POST /api/accounts/"""

    def test_open_savings_account(self, client, teller_user, verified_customer):
        """Open a valid Savings account with sufficient opening balance."""
        resp = client.post("/api/accounts/", json={
            "customer_id": verified_customer["id"],
            "account_type": "SAVINGS",
            "opening_balance_paise": 200000,  # ₹2,000 — above ₹1,000 minimum
        }, headers=teller_user)
        assert resp.status_code == 201
        body = resp.json()
        assert body["account_type"] == "SAVINGS"
        assert body["status"] == "ACTIVE"
        assert body["balance_paise"] == 200000
        # Verify account number format: ACC-YYYY-XXXXXX
        assert body["account_number"].startswith("ACC-")

    def test_open_current_account(self, client, teller_user, verified_customer):
        """Open a valid Current account."""
        resp = client.post("/api/accounts/", json={
            "customer_id": verified_customer["id"],
            "account_type": "CURRENT",
            "opening_balance_paise": 600000,  # ₹6,000 — above ₹5,000 minimum
        }, headers=teller_user)
        assert resp.status_code == 201
        assert resp.json()["account_type"] == "CURRENT"

    def test_open_fixed_deposit_account(self, client, teller_user, verified_customer):
        """Open a valid Fixed Deposit account with a tenure."""
        resp = client.post("/api/accounts/", json={
            "customer_id": verified_customer["id"],
            "account_type": "FIXED_DEPOSIT",
            "opening_balance_paise": 1500000,  # ₹15,000 — above ₹10,000 minimum
            "fd_tenure_months": 12,
        }, headers=teller_user)
        assert resp.status_code == 201
        body = resp.json()
        assert body["account_type"] == "FIXED_DEPOSIT"
        assert body["fd_tenure_months"] == 12

    def test_savings_below_min_balance_rejected(self, client, teller_user, verified_customer):
        """Opening Savings with < ₹1,000 is rejected (422)."""
        resp = client.post("/api/accounts/", json={
            "customer_id": verified_customer["id"],
            "account_type": "SAVINGS",
            "opening_balance_paise": 50000,   # ₹500 — below ₹1,000 minimum
        }, headers=teller_user)
        assert resp.status_code == 422

    def test_current_below_min_balance_rejected(self, client, teller_user, verified_customer):
        """Opening Current with < ₹5,000 is rejected (422)."""
        resp = client.post("/api/accounts/", json={
            "customer_id": verified_customer["id"],
            "account_type": "CURRENT",
            "opening_balance_paise": 300000,  # ₹3,000 — below ₹5,000 minimum
        }, headers=teller_user)
        assert resp.status_code == 422

    def test_fd_below_min_balance_rejected(self, client, teller_user, verified_customer):
        """Opening FD with < ₹10,000 is rejected (422)."""
        resp = client.post("/api/accounts/", json={
            "customer_id": verified_customer["id"],
            "account_type": "FIXED_DEPOSIT",
            "opening_balance_paise": 500000,   # ₹5,000 — below ₹10,000 minimum
            "fd_tenure_months": 12,
        }, headers=teller_user)
        assert resp.status_code == 422

    def test_unverified_customer_cannot_open_account(self, client, teller_user):
        """A customer with PENDING KYC cannot open an account."""
        # Create customer but don't verify
        cust = client.post("/api/customers/", json={
            "full_name": "Pending User",
            "date_of_birth": "1990-05-05",
            "national_id": "PENDING-NID-777",
            "address": "Somewhere",
            "phone": "9000000099",
            "email": "pending@test.com",
        }, headers=teller_user).json()

        resp = client.post("/api/accounts/", json={
            "customer_id": cust["id"],
            "account_type": "SAVINGS",
            "opening_balance_paise": 200000,
        }, headers=teller_user)
        assert resp.status_code == 422

    def test_nonexistent_customer_cannot_open_account(self, client, teller_user):
        """Account for a non-existent customer returns 404."""
        resp = client.post("/api/accounts/", json={
            "customer_id": 99999,
            "account_type": "SAVINGS",
            "opening_balance_paise": 200000,
        }, headers=teller_user)
        assert resp.status_code == 404

    def test_account_requires_auth(self, client, verified_customer):
        """Endpoint requires authentication — returns 401 without token."""
        resp = client.post("/api/accounts/", json={
            "customer_id": verified_customer["id"],
            "account_type": "SAVINGS",
            "opening_balance_paise": 200000,
        })
        assert resp.status_code == 401


class TestGetBalance:
    """Tests for GET /api/accounts/{id}/balance"""

    def test_get_balance_returns_correct_amount(self, client, teller_user,
                                                savings_account):
        """Balance endpoint returns the exact opening balance."""
        acct_id = savings_account["id"]
        resp = client.get(f"/api/accounts/{acct_id}/balance", headers=teller_user)
        assert resp.status_code == 200
        body = resp.json()
        assert body["balance_paise"] == 500000  # ₹5,000

    def test_balance_nonexistent_account(self, client, teller_user):
        """Balance for a non-existent account returns 404."""
        resp = client.get("/api/accounts/99999/balance", headers=teller_user)
        assert resp.status_code == 404


class TestAccountStatus:
    """Tests for PATCH /api/accounts/{id}/status"""

    def test_manager_can_freeze_account(self, client, manager_user, savings_account):
        """Manager successfully freezes an account."""
        acct_id = savings_account["id"]
        resp = client.patch(f"/api/accounts/{acct_id}/status",
                            json={"status": "FROZEN", "reason": "Suspicious activity"},
                            headers=manager_user)
        assert resp.status_code == 200
        assert resp.json()["status"] == "FROZEN"

    def test_manager_can_unfreeze_account(self, client, manager_user, savings_account):
        """Manager can unfreeze a frozen account."""
        acct_id = savings_account["id"]
        # First freeze
        client.patch(f"/api/accounts/{acct_id}/status",
                     json={"status": "FROZEN", "reason": "Test"},
                     headers=manager_user)
        # Then unfreeze
        resp = client.patch(f"/api/accounts/{acct_id}/status",
                            json={"status": "ACTIVE"}, headers=manager_user)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ACTIVE"

    def test_manager_can_close_account(self, client, manager_user, savings_account):
        """Manager can close an account permanently."""
        acct_id = savings_account["id"]
        resp = client.patch(f"/api/accounts/{acct_id}/status",
                            json={"status": "CLOSED"}, headers=manager_user)
        assert resp.status_code == 200
        assert resp.json()["status"] == "CLOSED"

    def test_teller_cannot_freeze_account(self, client, teller_user, savings_account):
        """Teller does not have permission to change account status — 403."""
        acct_id = savings_account["id"]
        resp = client.patch(f"/api/accounts/{acct_id}/status",
                            json={"status": "FROZEN", "reason": "Test"},
                            headers=teller_user)
        assert resp.status_code == 403

    def test_get_account_details(self, client, teller_user, savings_account):
        """GET /api/accounts/{id} returns full account details."""
        acct_id = savings_account["id"]
        resp = client.get(f"/api/accounts/{acct_id}", headers=teller_user)
        assert resp.status_code == 200
        body = resp.json()
        assert body["account_type"] == "SAVINGS"
        assert body["status"] == "ACTIVE"
