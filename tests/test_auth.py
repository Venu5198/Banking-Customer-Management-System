"""
test_auth.py — Tests for Authentication & Security

Covers:
  - Successful login
  - Wrong password rejection
  - Non-existent user rejection
  - Brute-force lockout after 3 failures
  - Creating users (admin-only)
  - Role-based endpoint protection
  - /me endpoint returns correct user
  - Duplicate username/email rejection
"""

import pytest


class TestLogin:
    """Tests for POST /api/auth/login"""

    def test_login_success(self, client, admin_user):
        """Admin can log in successfully and receive a JWT token."""
        resp = client.post("/api/auth/login",
                           data={"username": "admin_test", "password": "Admin@123"})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["username"] == "admin_test"
        assert body["role"] == "ADMIN"

    def test_login_wrong_password(self, client, admin_user):
        """Login with wrong password returns 401."""
        resp = client.post("/api/auth/login",
                           data={"username": "admin_test", "password": "WrongPass!"})
        assert resp.status_code == 401
        assert "Invalid username or password" in resp.json()["detail"]

    def test_login_nonexistent_user(self, client):
        """Login with a username that does not exist returns 401."""
        resp = client.post("/api/auth/login",
                           data={"username": "ghost_user", "password": "anything"})
        assert resp.status_code == 401

    def test_brute_force_lockout(self, client, admin_user):
        """
        3 consecutive wrong passwords lock the account.
        4th attempt returns 403 even with an unrelated message.
        """
        for _ in range(3):
            client.post("/api/auth/login",
                        data={"username": "admin_test", "password": "BadPass!"})

        # 4th attempt — should be locked
        resp = client.post("/api/auth/login",
                           data={"username": "admin_test", "password": "Admin@123"})
        assert resp.status_code == 403
        assert "locked" in resp.json()["detail"].lower()

    def test_login_with_correct_password_after_one_failure(self, client, admin_user):
        """One failed attempt followed by correct password should still work."""
        client.post("/api/auth/login",
                    data={"username": "admin_test", "password": "Wrong!"})
        resp = client.post("/api/auth/login",
                           data={"username": "admin_test", "password": "Admin@123"})
        assert resp.status_code == 200


class TestUserCreation:
    """Tests for POST /api/auth/users"""

    def test_admin_can_create_teller(self, client, admin_user):
        """Admin creates a Teller user successfully."""
        resp = client.post("/api/auth/users", json={
            "username": "new_teller",
            "email": "newteller@bank.com",
            "password": "Teller@pass1",
            "role": "TELLER",
        }, headers=admin_user)
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "new_teller"
        assert body["role"] == "TELLER"

    def test_admin_can_create_manager(self, client, admin_user):
        """Admin creates a Manager user successfully."""
        resp = client.post("/api/auth/users", json={
            "username": "new_manager",
            "email": "newmanager@bank.com",
            "password": "Manager@pass1",
            "role": "MANAGER",
        }, headers=admin_user)
        assert resp.status_code == 200
        assert resp.json()["role"] == "MANAGER"

    def test_teller_cannot_create_users(self, client, teller_user):
        """Teller does not have permission to create system users — expects 403."""
        resp = client.post("/api/auth/users", json={
            "username": "sneaky_user",
            "email": "sneaky@bank.com",
            "password": "Sneaky@123",
            "role": "TELLER",
        }, headers=teller_user)
        assert resp.status_code == 403

    def test_duplicate_username_rejected(self, client, admin_user):
        """Creating two users with the same username returns 409."""
        payload = {
            "username": "unique_user",
            "email": "unique1@bank.com",
            "password": "Pass@123",
            "role": "TELLER",
        }
        client.post("/api/auth/users", json=payload, headers=admin_user)

        payload["email"] = "unique2@bank.com"  # different email, same username
        resp = client.post("/api/auth/users", json=payload, headers=admin_user)
        assert resp.status_code == 409
        assert "Username already exists" in resp.json()["detail"]

    def test_duplicate_email_rejected(self, client, admin_user):
        """Creating two users with the same email returns 409."""
        client.post("/api/auth/users", json={
            "username": "user_one",
            "email": "shared@bank.com",
            "password": "Pass@123",
            "role": "TELLER",
        }, headers=admin_user)

        resp = client.post("/api/auth/users", json={
            "username": "user_two",
            "email": "shared@bank.com",
            "password": "Pass@123",
            "role": "TELLER",
        }, headers=admin_user)
        assert resp.status_code == 409

    def test_unauthenticated_cannot_create_users(self, client):
        """/api/auth/users requires authentication — expects 401."""
        resp = client.post("/api/auth/users", json={
            "username": "hacker",
            "email": "hacker@evil.com",
            "password": "hack123",
            "role": "ADMIN",
        })
        assert resp.status_code == 401


class TestGetMe:
    """Tests for GET /api/auth/me"""

    def test_get_me_returns_own_profile(self, client, admin_user):
        """/me returns the current user's profile."""
        resp = client.get("/api/auth/me", headers=admin_user)
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "admin_test"
        assert body["role"] == "ADMIN"

    def test_get_me_unauthenticated(self, client):
        """/me without a token returns 401."""
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_get_me_invalid_token(self, client):
        """/me with a garbage token returns 401."""
        resp = client.get("/api/auth/me",
                          headers={"Authorization": "Bearer this.is.garbage"})
        assert resp.status_code == 401


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_root_endpoint(self, client):
        """Root endpoint is publicly accessible and returns service info."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "operational"

    def test_health_endpoint(self, client):
        """Health endpoint returns ok."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
