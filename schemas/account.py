"""Pydantic schemas for account management."""

from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
from models.account import AccountType, AccountStatus


class AccountCreate(BaseModel):
    customer_id: int
    account_type: AccountType
    # Opening deposit in paise
    opening_balance_paise: int
    # Only for Fixed Deposit
    fd_tenure_months: Optional[int] = None

    @field_validator("opening_balance_paise")
    @classmethod
    def positive_amount(cls, v):
        if v <= 0:
            raise ValueError("Opening balance must be positive")
        return v

    @field_validator("fd_tenure_months")
    @classmethod
    def valid_fd_tenure(cls, v):
        if v is not None and v not in [6, 12, 24, 36, 60]:
            raise ValueError("FD tenure must be 6, 12, 24, 36, or 60 months")
        return v


class AccountStatusUpdate(BaseModel):
    status: AccountStatus
    reason: Optional[str] = None


class AccountResponse(BaseModel):
    id: int
    account_number: str
    customer_id: int
    account_type: AccountType
    status: AccountStatus
    balance_paise: int
    min_balance_paise: int
    fd_tenure_months: Optional[int]
    fd_interest_rate: Optional[int]  # basis points
    fd_maturity_date: Optional[datetime]
    last_interest_credited_at: Optional[datetime]
    daily_withdrawn_paise: int
    frozen_reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountBalanceResponse(BaseModel):
    account_number: str
    account_type: AccountType
    status: AccountStatus
    balance_inr: float        # Convenience field for display (paise / 100)
    balance_paise: int
    min_balance_inr: float

    model_config = {"from_attributes": True}
