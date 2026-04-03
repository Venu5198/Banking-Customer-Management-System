"""
Banking Customer Management System
====================================
FastAPI backend with full banking compliance:
- KYC onboarding (age verification, duplicate detection)
- Account management (SAVINGS, CURRENT, FIXED_DEPOSIT)
- Transactions with full rule enforcement
- Loan lifecycle management with EMI amortization
- AML & CTR compliance
- JWT authentication with role-based access control
- Immutable audit logging

Run with: uvicorn main:app --reload
Docs at:  http://127.0.0.1:8000/docs
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import logging

load_dotenv()

# ── Logging Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("banking_app")

# ── DB + Models Import (must come before create_all) ─────────────────────────
from database import engine, Base

# Import all models to register them with SQLAlchemy metadata
import models.auth        # noqa: F401
import models.customer    # noqa: F401
import models.account     # noqa: F401
import models.transaction # noqa: F401
import models.loan        # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create all DB tables on startup. In production use Alembic migrations."""
    logger.info("🏦 Banking App starting up...")
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Database tables initialized")

    # Seed a default ADMIN user if none exist
    _seed_admin_user()

    yield
    logger.info("🏦 Banking App shutting down...")


def _seed_admin_user():
    """
    On first run, create a default ADMIN user.
    Credentials: admin / admin1234 — CHANGE IMMEDIATELY IN PRODUCTION.
    """
    from database import SessionLocal
    from models.auth import User, UserRole
    from middleware.auth_middleware import hash_password

    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "admin").first():
            admin = User(
                username="admin",
                email="admin@bank.local",
                hashed_password=hash_password("admin1234"),
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            logger.warning(
                "⚠️  Default ADMIN user created: username='admin' password='admin1234' "
                "— CHANGE THIS IMMEDIATELY IN PRODUCTION!"
            )
    finally:
        db.close()


# ── App Initialization ────────────────────────────────────────────────────────
app = FastAPI(
    title="🏦 Banking Customer Management System",
    description="""
## Banking API with full compliance

### Modules
- **Authentication** — JWT login, RBAC, account lockout
- **Customers (KYC)** — Onboarding, age verification, duplicate detection
- **Accounts** — SAVINGS, CURRENT, FIXED_DEPOSIT with minimum balance rules
- **Transactions** — Deposits, withdrawals, transfers with daily limits
- **Loans** — Application, approval, disbursement, EMI payment
- **Compliance** — AML flags, CTR reports, audit logs, interest engine

### Roles
| Role | Permissions |
|------|-------------|
| `CUSTOMER` | View own accounts/transactions/loans |
| `TELLER` | Create customers, open accounts, process transactions |
| `MANAGER` | Approve KYC/loans, freeze accounts |
| `ADMIN` | Full access including user management |

### Default Admin
- Username: `admin` | Password: `admin1234` *(change immediately)*
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global Exception Handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# ── Routes ───────────────────────────────────────────────────────────────────
from routes.auth import router as auth_router
from routes.customers import router as customers_router
from routes.accounts import router as accounts_router
from routes.transactions import router as transactions_router
from routes.loans import router as loans_router

app.include_router(auth_router)
app.include_router(customers_router)
app.include_router(accounts_router)
app.include_router(transactions_router)
app.include_router(loans_router)


@app.get("/", tags=["Health"])
def root():
    return {
        "service": "Banking Customer Management System",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
