"""
Account model.
- Account numbers follow format: ACC-YYYY-XXXXXX
- All balance values stored in PAISE (integer). 1 INR = 100 paise.
- Minimum balances enforced at transaction level, not DB level.
"""

import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, Enum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from database import Base


class AccountType(str, enum.Enum):
    SAVINGS = "SAVINGS"           # Min balance ₹1,000 | Daily withdrawal ₹50,000
    CURRENT = "CURRENT"           # Min balance ₹5,000 | Daily withdrawal ₹2,00,000
    FIXED_DEPOSIT = "FIXED_DEPOSIT"  # Min balance ₹10,000 | No daily withdrawals


class AccountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"      # Normal operational state
    DORMANT = "DORMANT"    # No transactions for 12+ months (auto-set by scheduler)
    FROZEN = "FROZEN"      # Manually frozen by manager/compliance — no transactions
    CLOSED = "CLOSED"      # Permanently closed — no transactions


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_number = Column(String(20), unique=True, nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    account_type = Column(Enum(AccountType), nullable=False)
    status = Column(Enum(AccountStatus), nullable=False, default=AccountStatus.ACTIVE)
    # Balance in paise — NEVER use floats for money
    balance_paise = Column(BigInteger, nullable=False, default=0)
    # Minimum balance in paise (set at account creation based on type)
    min_balance_paise = Column(BigInteger, nullable=False)
    # For Fixed Deposits: maturity details
    fd_tenure_months = Column(Integer, nullable=True)   # e.g., 12, 24, 36
    fd_interest_rate = Column(Integer, nullable=True)   # In basis points: 650 = 6.50%
    fd_maturity_date = Column(DateTime, nullable=True)
    # Interest tracking
    last_interest_credited_at = Column(DateTime, nullable=True)
    # Daily withdrawal tracking (reset at midnight)
    daily_withdrawn_paise = Column(BigInteger, default=0)
    daily_withdrawal_reset_date = Column(DateTime, nullable=True)
    # Freeze/closure metadata
    frozen_reason = Column(String(500), nullable=True)
    frozen_by_user_id = Column(Integer, nullable=True)
    frozen_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    closed_by_user_id = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customer = relationship("Customer", back_populates="accounts")
    transactions = relationship(
        "Transaction",
        back_populates="account",
        primaryjoin="Account.id == Transaction.account_id",
        foreign_keys="[Transaction.account_id]",
    )
    loans = relationship("Loan", back_populates="linked_account")

