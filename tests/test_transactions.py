"""
test_transactions.py — Tests for the Transaction Engine

Covers:
  - Deposit (success, zero amount rejection)
  - Withdrawal (success, below minimum balance, insufficient funds)
  - Transfer (success, self-transfer rejection, frozen target)
  - AML flagging for transactions > ₹10,00,000
  - CTR report generation for cash > ₹50,000
  - Transactions on FROZEN accounts are blocked
  - Transactions on CLOSED accounts are blocked
  - Transaction list per account
  - Compliance reports (AML flags, CTR reports) — Admin only
"""

import pytest


class TestDeposit:
    """Tests for POST /api/transactions/deposit"""

    def test_deposit_increases_balance(self, client, teller_user, savings_account):
        """A valid deposit increases the account balance correctly."""
        acct_id = savings_account["id"]
        initial_balance = savings_account["balance_paise"]

        resp = client.post("/api/transactions/deposit", json={
            "account_id": acct_id,
            "txn_type": "DEPOSIT",
            "amount_paise": 100000,  # ₹1,000
            "description": "Test deposit",
        }, headers=teller_user)
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "SUCCESS"
        assert body["balance_after_paise"] == initial_balance + 100000

    def test_deposit_zero_amount_rejected(self, client, teller_user, savings_account):
        """Deposit of zero paise is rejected by Pydantic validation."""
        resp = client.post("/api/transactions/deposit", json={
            "account_id": savings_account["id"],
            "txn_type": "DEPOSIT",
            "amount_paise": 0,
        }, headers=teller_user)
        assert resp.status_code == 422

    def test_deposit_negative_amount_rejected(self, client, teller_user, savings_account):
        """Negative deposit amount is rejected."""
        resp = client.post("/api/transactions/deposit", json={
            "account_id": savings_account["id"],
            "txn_type": "DEPOSIT",
            "amount_paise": -50000,
        }, headers=teller_user)
        assert resp.status_code == 422

    def test_deposit_on_frozen_account_blocked(self, client, teller_user,
                                               manager_user, savings_account):
        """Deposit on a FROZEN account is rejected with 422."""
        acct_id = savings_account["id"]
        # Freeze the account
        client.patch(f"/api/accounts/{acct_id}/status",
                     json={"status": "FROZEN", "reason": "Test"},
                     headers=manager_user)
        resp = client.post("/api/transactions/deposit", json={
            "account_id": acct_id,
            "txn_type": "DEPOSIT",
            "amount_paise": 100000,
        }, headers=teller_user)
        assert resp.status_code == 422

    def test_deposit_on_closed_account_blocked(self, client, teller_user,
                                               manager_user, savings_account):
        """Deposit on a CLOSED account is rejected with 422."""
        acct_id = savings_account["id"]
        client.patch(f"/api/accounts/{acct_id}/status",
                     json={"status": "CLOSED"}, headers=manager_user)
        resp = client.post("/api/transactions/deposit", json={
            "account_id": acct_id,
            "txn_type": "DEPOSIT",
            "amount_paise": 100000,
        }, headers=teller_user)
        assert resp.status_code == 422

    def test_deposit_on_nonexistent_account(self, client, teller_user):
        """Deposit to a non-existent account returns 404."""
        resp = client.post("/api/transactions/deposit", json={
            "account_id": 99999,
            "txn_type": "DEPOSIT",
            "amount_paise": 100000,
        }, headers=teller_user)
        assert resp.status_code == 404


class TestWithdrawal:
    """Tests for POST /api/transactions/withdraw"""

    def test_withdrawal_decreases_balance(self, client, teller_user, savings_account):
        """A valid withdrawal decreases the account balance."""
        acct_id = savings_account["id"]
        initial_balance = savings_account["balance_paise"]

        resp = client.post("/api/transactions/withdraw", json={
            "account_id": acct_id,
            "txn_type": "WITHDRAWAL",
            "amount_paise": 100000,  # ₹1,000 — safe amount
        }, headers=teller_user)
        assert resp.status_code == 201
        assert resp.json()["balance_after_paise"] == initial_balance - 100000

    def test_withdrawal_below_min_balance_rejected(self, client, teller_user,
                                                    savings_account):
        """
        Savings minimum balance is ₹1,000 (100000 paise).
        Account has ₹5,000. Withdrawing ₹4,500 would leave ₹500 — rejected.
        """
        resp = client.post("/api/transactions/withdraw", json={
            "account_id": savings_account["id"],
            "txn_type": "WITHDRAWAL",
            "amount_paise": 450000,  # Would leave ₹500 — below ₹1,000 minimum
        }, headers=teller_user)
        assert resp.status_code == 422

    def test_withdrawal_exact_minimum_balance_allowed(self, client, teller_user,
                                                       savings_account):
        """
        Withdrawing exactly down to the minimum balance is allowed.
        Account ₹5,000, min ₹1,000 → withdraw ₹4,000 leaves exactly ₹1,000.
        """
        resp = client.post("/api/transactions/withdraw", json={
            "account_id": savings_account["id"],
            "txn_type": "WITHDRAWAL",
            "amount_paise": 400000,  # ₹4,000 — leaves exactly ₹1,000
        }, headers=teller_user)
        assert resp.status_code == 201
        assert resp.json()["balance_after_paise"] == 100000  # exactly ₹1,000

    def test_withdrawal_insufficient_funds(self, client, teller_user, savings_account):
        """Withdrawing more than available balance is rejected."""
        resp = client.post("/api/transactions/withdraw", json={
            "account_id": savings_account["id"],
            "txn_type": "WITHDRAWAL",
            "amount_paise": 99999999,  # Way more than balance
        }, headers=teller_user)
        assert resp.status_code == 422

    def test_withdrawal_on_frozen_account_blocked(self, client, teller_user,
                                                   manager_user, savings_account):
        """Withdrawal on a FROZEN account is rejected."""
        acct_id = savings_account["id"]
        client.patch(f"/api/accounts/{acct_id}/status",
                     json={"status": "FROZEN", "reason": "Test"},
                     headers=manager_user)
        resp = client.post("/api/transactions/withdraw", json={
            "account_id": acct_id,
            "txn_type": "WITHDRAWAL",
            "amount_paise": 100000,
        }, headers=teller_user)
        assert resp.status_code == 422


class TestTransfer:
    """Tests for POST /api/transactions/transfer"""

    def test_transfer_between_accounts(self, client, teller_user,
                                        savings_account, current_account):
        """A valid transfer moves funds from source to destination correctly."""
        src_id = savings_account["id"]
        dst_id = current_account["id"]
        src_initial = savings_account["balance_paise"]
        dst_initial = current_account["balance_paise"]
        amount = 100000  # ₹1,000

        resp = client.post("/api/transactions/transfer", json={
            "from_account_id": src_id,
            "to_account_id": dst_id,
            "amount_paise": amount,
            "description": "Internal transfer",
        }, headers=teller_user)
        assert resp.status_code == 201

        # Verify source balance decreased
        src_balance = client.get(f"/api/accounts/{src_id}/balance",
                                  headers=teller_user).json()["balance_paise"]
        assert src_balance == src_initial - amount

        # Verify destination balance increased
        dst_balance = client.get(f"/api/accounts/{dst_id}/balance",
                                  headers=teller_user).json()["balance_paise"]
        assert dst_balance == dst_initial + amount

    def test_self_transfer_rejected(self, client, teller_user, savings_account):
        """Transfer from an account to itself is rejected."""
        acct_id = savings_account["id"]
        resp = client.post("/api/transactions/transfer", json={
            "from_account_id": acct_id,
            "to_account_id": acct_id,
            "amount_paise": 50000,
        }, headers=teller_user)
        assert resp.status_code == 422

    def test_transfer_to_frozen_account_blocked(self, client, teller_user,
                                                manager_user, savings_account,
                                                current_account):
        """Transfer to a FROZEN destination account is blocked."""
        dst_id = current_account["id"]
        client.patch(f"/api/accounts/{dst_id}/status",
                     json={"status": "FROZEN", "reason": "Compliance"},
                     headers=manager_user)
        resp = client.post("/api/transactions/transfer", json={
            "from_account_id": savings_account["id"],
            "to_account_id": dst_id,
            "amount_paise": 50000,
        }, headers=teller_user)
        assert resp.status_code == 422

    def test_transfer_from_frozen_account_blocked(self, client, teller_user,
                                                   manager_user, savings_account,
                                                   current_account):
        """Transfer from a FROZEN source account is blocked."""
        src_id = savings_account["id"]
        client.patch(f"/api/accounts/{src_id}/status",
                     json={"status": "FROZEN", "reason": "Compliance"},
                     headers=manager_user)
        resp = client.post("/api/transactions/transfer", json={
            "from_account_id": src_id,
            "to_account_id": current_account["id"],
            "amount_paise": 50000,
        }, headers=teller_user)
        assert resp.status_code == 422

    def test_transfer_zero_amount_rejected(self, client, teller_user,
                                            savings_account, current_account):
        """Transfer of zero amount is rejected."""
        resp = client.post("/api/transactions/transfer", json={
            "from_account_id": savings_account["id"],
            "to_account_id": current_account["id"],
            "amount_paise": 0,
        }, headers=teller_user)
        assert resp.status_code == 422


class TestAMLAndCTR:
    """Tests for AML flag and CTR report auto-generation."""

    def test_large_deposit_triggers_aml_flag(self, client, teller_user, admin_user,
                                              savings_account):
        """
        Deposit exceeding AML threshold (₹10,00,000 = 100000000 paise)
        must set is_aml_flagged=True on the transaction.
        """
        resp = client.post("/api/transactions/deposit", json={
            "account_id": savings_account["id"],
            "txn_type": "DEPOSIT",
            "amount_paise": 150000000,  # ₹15,00,000 — above ₹10,00,000 AML threshold
        }, headers=teller_user)
        assert resp.status_code == 201
        assert resp.json()["is_aml_flagged"] is True

        # AML flag should appear in compliance endpoint
        flags = client.get("/api/transactions/compliance/aml-flags",
                           headers=admin_user).json()
        assert len(flags) >= 1

    def test_large_deposit_triggers_ctr_report(self, client, teller_user, admin_user,
                                                savings_account):
        """
        Cash deposit exceeding CTR threshold (₹50,000 = 5000000 paise)
        must set is_ctr_generated=True.
        """
        resp = client.post("/api/transactions/deposit", json={
            "account_id": savings_account["id"],
            "txn_type": "DEPOSIT",
            "amount_paise": 10000000,  # ₹1,00,000 — above ₹50,000 CTR threshold
        }, headers=teller_user)
        assert resp.status_code == 201
        assert resp.json()["is_ctr_generated"] is True

        reports = client.get("/api/transactions/compliance/ctr-reports",
                             headers=admin_user).json()
        assert len(reports) >= 1

    def test_small_deposit_no_aml_no_ctr(self, client, teller_user, savings_account):
        """Small deposit below all thresholds has no AML or CTR flags."""
        resp = client.post("/api/transactions/deposit", json={
            "account_id": savings_account["id"],
            "txn_type": "DEPOSIT",
            "amount_paise": 100000,  # ₹1,000 — well below all thresholds
        }, headers=teller_user)
        assert resp.status_code == 201
        body = resp.json()
        assert body["is_aml_flagged"] is False
        assert body["is_ctr_generated"] is False

    def test_compliance_endpoints_require_admin(self, client, teller_user):
        """Compliance endpoints are restricted to ADMIN role."""
        assert client.get("/api/transactions/compliance/aml-flags",
                          headers=teller_user).status_code == 403
        assert client.get("/api/transactions/compliance/ctr-reports",
                          headers=teller_user).status_code == 403


class TestTransactionList:
    """Tests for GET /api/transactions/account/{id}"""

    def test_transaction_list_is_empty_initially(self, client, teller_user,
                                                  savings_account):
        """Freshly opened account has no transactions."""
        resp = client.get(f"/api/transactions/account/{savings_account['id']}",
                          headers=teller_user)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_transaction_list_grows_after_deposit(self, client, teller_user,
                                                   savings_account):
        """After a deposit, the transaction list has one record."""
        acct_id = savings_account["id"]
        client.post("/api/transactions/deposit", json={
            "account_id": acct_id,
            "txn_type": "DEPOSIT",
            "amount_paise": 50000,
        }, headers=teller_user)

        resp = client.get(f"/api/transactions/account/{acct_id}",
                          headers=teller_user)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["txn_type"] == "DEPOSIT"

    def test_transaction_list_nonexistent_account(self, client, teller_user):
        """
        Transaction list for a non-existent account ID returns 200 with an empty list.
        The route returns all matching transactions (none found = empty list, not 404).
        """
        resp = client.get("/api/transactions/account/99999", headers=teller_user)
        assert resp.status_code == 200
        assert resp.json() == []
