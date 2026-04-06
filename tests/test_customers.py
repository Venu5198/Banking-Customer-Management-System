"""
test_customers.py — Tests for Customer KYC Onboarding

Covers:
  - Creating a customer (success)
  - Age < 18 rejection
  - Duplicate National ID rejection
  - KYC status workflow (PENDING → VERIFIED / REJECTED)
  - Cannot revert VERIFIED to PENDING
  - Rejection requires a reason
  - Fetching a customer
  - Updating customer details
  - Deleting a customer (with and without accounts)
  - Role restrictions on every endpoint
"""

import pytest


# ── Helpers ─────────────────────────────────────────────────────────────────

VALID_CUSTOMER = {
    "full_name": "Priya Sharma",
    "date_of_birth": "1992-03-10",
    "national_id": "AADHAR-111122223333",
    "address": "42 MG Road, Bengaluru - 560001",
    "phone": "9876543210",
    "email": "priya.sharma@example.com",
}


class TestCreateCustomer:
    """Tests for POST /api/customers/"""

    def test_create_customer_success(self, client, teller_user):
        """Valid adult customer is created with PENDING KYC status."""
        resp = client.post("/api/customers/", json=VALID_CUSTOMER,
                           headers=teller_user)
        assert resp.status_code == 201
        body = resp.json()
        assert body["full_name"] == "Priya Sharma"
        assert body["kyc_status"] == "PENDING"
        assert "national_id" not in body  # must never be returned in response

    def test_under_18_rejected(self, client, teller_user):
        """Applicant under 18 years old is rejected with 422."""
        payload = {**VALID_CUSTOMER, "date_of_birth": "2015-06-01",
                   "national_id": "MINOR-001", "email": "minor@test.com"}
        resp = client.post("/api/customers/", json=payload, headers=teller_user)
        assert resp.status_code == 422
        assert "18" in resp.text

    def test_exactly_18_accepted(self, client, teller_user):
        """Applicant who is exactly 18 today is accepted."""
        from datetime import date, timedelta
        dob = (date.today().replace(year=date.today().year - 18)).isoformat()
        payload = {**VALID_CUSTOMER, "date_of_birth": dob,
                   "national_id": "EXACT-18", "email": "exact18@test.com"}
        resp = client.post("/api/customers/", json=payload, headers=teller_user)
        assert resp.status_code == 201

    def test_duplicate_national_id_rejected(self, client, teller_user):
        """Same National ID cannot be registered twice — returns 409."""
        client.post("/api/customers/", json=VALID_CUSTOMER, headers=teller_user)
        payload = {**VALID_CUSTOMER, "email": "other@test.com"}  # same national_id
        resp = client.post("/api/customers/", json=payload, headers=teller_user)
        assert resp.status_code == 409
        assert "National ID" in resp.json()["detail"]

    def test_duplicate_email_rejected(self, client, teller_user):
        """Same email cannot be registered twice — returns 409."""
        client.post("/api/customers/", json=VALID_CUSTOMER, headers=teller_user)
        payload = {**VALID_CUSTOMER, "national_id": "DIFF-NID-999"}
        resp = client.post("/api/customers/", json=payload, headers=teller_user)
        assert resp.status_code == 409

    def test_customer_requires_auth(self, client):
        """Creating a customer without a token returns 401."""
        resp = client.post("/api/customers/", json=VALID_CUSTOMER)
        assert resp.status_code == 401

    def test_customer_role_cannot_create(self, client, admin_user, teller_user):
        """
        A CUSTOMER-role user cannot onboard new customers.
        We create a customer-linked user to test this.
        """
        # First create a customer
        cust = client.post("/api/customers/", json=VALID_CUSTOMER,
                           headers=teller_user).json()
        # Create a user with CUSTOMER role linked to that customer
        client.post("/api/auth/users", json={
            "username": "cust_user",
            "email": "custuser@test.com",
            "password": "Cust@1234",
            "role": "CUSTOMER",
            "customer_id": cust["id"],
        }, headers=admin_user)

        token_resp = client.post("/api/auth/login",
                                 data={"username": "cust_user",
                                       "password": "Cust@1234"})
        cust_headers = {"Authorization": f"Bearer {token_resp.json()['access_token']}"}

        payload = {**VALID_CUSTOMER, "national_id": "CUST-NEW-111",
                   "email": "newcust@test.com"}
        resp = client.post("/api/customers/", json=payload, headers=cust_headers)
        assert resp.status_code == 403

    def test_blank_name_rejected(self, client, teller_user):
        """Empty full name is rejected by Pydantic validation."""
        payload = {**VALID_CUSTOMER, "full_name": "   ",
                   "national_id": "NID-BLANK", "email": "blank@test.com"}
        resp = client.post("/api/customers/", json=payload, headers=teller_user)
        assert resp.status_code == 422

    def test_invalid_phone_rejected(self, client, teller_user):
        """Phone with fewer than 10 digits is rejected."""
        payload = {**VALID_CUSTOMER, "phone": "123",
                   "national_id": "NID-PHONE", "email": "phone@test.com"}
        resp = client.post("/api/customers/", json=payload, headers=teller_user)
        assert resp.status_code == 422


class TestGetCustomer:
    """Tests for GET /api/customers/{id}"""

    def test_get_customer_by_id(self, client, teller_user):
        """Fetching an existing customer by ID returns correct data."""
        create_resp = client.post("/api/customers/", json=VALID_CUSTOMER,
                                  headers=teller_user)
        cust_id = create_resp.json()["id"]
        resp = client.get(f"/api/customers/{cust_id}", headers=teller_user)
        assert resp.status_code == 200
        assert resp.json()["id"] == cust_id

    def test_get_nonexistent_customer_returns_404(self, client, teller_user):
        """Fetching a customer that does not exist returns 404."""
        resp = client.get("/api/customers/99999", headers=teller_user)
        assert resp.status_code == 404

    def test_list_customers(self, client, teller_user):
        """Listing customers returns all created customers."""
        client.post("/api/customers/", json=VALID_CUSTOMER, headers=teller_user)
        resp = client.get("/api/customers/", headers=teller_user)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestKYCWorkflow:
    """Tests for PATCH /api/customers/{id}/kyc"""

    def test_manager_can_verify_kyc(self, client, teller_user, manager_user):
        """Manager successfully verifies a PENDING customer."""
        cust_id = client.post("/api/customers/", json=VALID_CUSTOMER,
                              headers=teller_user).json()["id"]
        resp = client.patch(f"/api/customers/{cust_id}/kyc",
                            json={"status": "VERIFIED"}, headers=manager_user)
        assert resp.status_code == 200
        assert resp.json()["kyc_status"] == "VERIFIED"
        assert resp.json()["kyc_verified_at"] is not None

    def test_manager_can_reject_kyc_with_reason(self, client, teller_user, manager_user):
        """Manager rejects a customer with a reason provided."""
        cust_id = client.post("/api/customers/", json=VALID_CUSTOMER,
                              headers=teller_user).json()["id"]
        resp = client.patch(f"/api/customers/{cust_id}/kyc",
                            json={"status": "REJECTED",
                                  "rejection_reason": "Documents incomplete"},
                            headers=manager_user)
        assert resp.status_code == 200
        assert resp.json()["kyc_status"] == "REJECTED"

    def test_rejection_without_reason_fails(self, client, teller_user, manager_user):
        """Rejecting KYC without providing a reason returns 422."""
        cust_id = client.post("/api/customers/", json=VALID_CUSTOMER,
                              headers=teller_user).json()["id"]
        resp = client.patch(f"/api/customers/{cust_id}/kyc",
                            json={"status": "REJECTED"}, headers=manager_user)
        assert resp.status_code == 422

    def test_teller_cannot_verify_kyc(self, client, teller_user):
        """Teller cannot approve KYC — requires at least Manager role."""
        cust_id = client.post("/api/customers/", json=VALID_CUSTOMER,
                              headers=teller_user).json()["id"]
        resp = client.patch(f"/api/customers/{cust_id}/kyc",
                            json={"status": "VERIFIED"}, headers=teller_user)
        assert resp.status_code == 403

    def test_cannot_revert_verified_to_pending(self, client, teller_user, manager_user):
        """Once VERIFIED, a customer's KYC cannot be moved back to PENDING."""
        cust_id = client.post("/api/customers/", json=VALID_CUSTOMER,
                              headers=teller_user).json()["id"]
        client.patch(f"/api/customers/{cust_id}/kyc",
                     json={"status": "VERIFIED"}, headers=manager_user)
        resp = client.patch(f"/api/customers/{cust_id}/kyc",
                            json={"status": "PENDING"}, headers=manager_user)
        assert resp.status_code == 422


class TestUpdateCustomer:
    """Tests for PUT /api/customers/{id}"""

    def test_update_address(self, client, teller_user):
        """Teller can update a customer's address."""
        cust_id = client.post("/api/customers/", json=VALID_CUSTOMER,
                              headers=teller_user).json()["id"]
        resp = client.put(f"/api/customers/{cust_id}",
                          json={"address": "100 New Street, Mumbai"},
                          headers=teller_user)
        assert resp.status_code == 200
        assert resp.json()["address"] == "100 New Street, Mumbai"


class TestDeleteCustomer:
    """Tests for DELETE /api/customers/{id}"""

    def test_delete_customer_with_no_accounts(self, client, teller_user, manager_user):
        """Manager can delete a customer who has no linked accounts."""
        cust_id = client.post("/api/customers/", json=VALID_CUSTOMER,
                              headers=teller_user).json()["id"]
        resp = client.delete(f"/api/customers/{cust_id}", headers=manager_user)
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

    def test_delete_customer_with_accounts_blocked(self, client, teller_user,
                                                    manager_user, verified_customer):
        """Cannot delete a customer who has an open account — returns 400."""
        cust_id = verified_customer["id"]
        # Open an account for them
        client.post("/api/accounts/", json={
            "customer_id": cust_id,
            "account_type": "SAVINGS",
            "opening_balance_paise": 200000,
        }, headers=teller_user)

        resp = client.delete(f"/api/customers/{cust_id}", headers=manager_user)
        assert resp.status_code == 400
        assert "accounts" in resp.json()["detail"].lower()

    def test_teller_cannot_delete_customer(self, client, teller_user):
        """Teller does not have permission to delete customers — returns 403."""
        cust_id = client.post("/api/customers/", json=VALID_CUSTOMER,
                              headers=teller_user).json()["id"]
        resp = client.delete(f"/api/customers/{cust_id}", headers=teller_user)
        assert resp.status_code == 403
