"""
conftest.py — Shared fixtures for the entire test suite.

Strategy:
  - Use an in-memory SQLite database isolated per test session.
  - Override FastAPI's get_db dependency so tests never touch the real DB.
  - Provide ready-made fixtures: admin token, teller token, a verified customer,
    open accounts, etc., so individual test files stay concise.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── Use an in-memory SQLite DB for tests ──────────────────────────────────────
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,    # single shared connection — required for in-memory SQLite
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Import models to register them with SQLAlchemy Base ──────────────────────
from database import Base, get_db
import models.auth        # noqa: F401
import models.customer    # noqa: F401
import models.account     # noqa: F401
import models.transaction # noqa: F401
import models.loan        # noqa: F401

from main import app
from middleware.auth_middleware import hash_password
from models.auth import User, UserRole


def override_get_db():
    """Dependency override — yields a test DB session instead of the real one."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create all tables once per test session, then drop them after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def clean_tables():
    """
    Wipe all data between every test so each test starts with a fresh state.
    Runs automatically for every test function.
    """
    yield
    db = TestingSessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="session")
def client():
    """TestClient with the get_db dependency overridden to use the test database."""
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ── Seed helpers ──────────────────────────────────────────────────────────────

def _create_user(role: UserRole, username: str, password: str, email: str) -> User:
    """Directly insert a user into the test database."""
    db = TestingSessionLocal()
    try:
        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def _get_token(client: TestClient, username: str, password: str) -> str:
    """Login and return the bearer token string."""
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


# ── Role fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def admin_user(client):
    _create_user(UserRole.ADMIN, "admin_test", "Admin@123", "admin@test.com")
    token = _get_token(client, "admin_test", "Admin@123")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def teller_user(admin_user, client):
    resp = client.post(
        "/api/auth/users",
        json={"username": "teller_test", "email": "teller@test.com",
              "password": "Teller@123", "role": "TELLER"},
        headers=admin_user,
    )
    assert resp.status_code == 200
    token = _get_token(client, "teller_test", "Teller@123")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def manager_user(admin_user, client):
    resp = client.post(
        "/api/auth/users",
        json={"username": "manager_test", "email": "manager@test.com",
              "password": "Manager@123", "role": "MANAGER"},
        headers=admin_user,
    )
    assert resp.status_code == 200
    token = _get_token(client, "manager_test", "Manager@123")
    return {"Authorization": f"Bearer {token}"}


# ── Domain object fixtures ────────────────────────────────────────────────────

@pytest.fixture
def verified_customer(client, teller_user, manager_user):
    """A fully KYC-verified customer ready to open accounts."""
    resp = client.post("/api/customers/", json={
        "full_name": "Test Customer",
        "date_of_birth": "1990-01-01",
        "national_id": "TEST-NID-001",
        "address": "123 Test Street, Bengaluru",
        "phone": "9876543210",
        "email": "customer@test.com",
    }, headers=teller_user)
    assert resp.status_code == 201
    customer_id = resp.json()["id"]

    # Verify KYC
    resp = client.patch(f"/api/customers/{customer_id}/kyc",
                        json={"status": "VERIFIED"}, headers=manager_user)
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture
def savings_account(client, teller_user, verified_customer):
    """An active Savings account with ₹5,000 balance."""
    resp = client.post("/api/accounts/", json={
        "customer_id": verified_customer["id"],
        "account_type": "SAVINGS",
        "opening_balance_paise": 500000,   # ₹5,000
    }, headers=teller_user)
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def current_account(client, teller_user, verified_customer):
    """An active Current account with ₹10,000 balance."""
    resp = client.post("/api/accounts/", json={
        "customer_id": verified_customer["id"],
        "account_type": "CURRENT",
        "opening_balance_paise": 1000000,  # ₹10,000
    }, headers=teller_user)
    assert resp.status_code == 201
    return resp.json()
