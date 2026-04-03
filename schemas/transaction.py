"""Pydantic schemas for transactions."""

from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
from models.transaction import TransactionType, TransactionStatus, FailureReason


class TransactionCreate(BaseModel):
    """For deposit or withdrawal on a single account."""
    account_id: int
    txn_type: TransactionType
    amount_paise: int
    description: Optional[str] = None

    @field_validator("amount_paise")
    @classmethod
    def positive_amount(cls, v):
        if v <= 0:
            raise ValueError("Transaction amount must be positive and non-zero")
        return v

    @field_validator("txn_type")
    @classmethod
    def not_transfer(cls, v):
        if v == TransactionType.TRANSFER:
            raise ValueError("Use the /transfer endpoint for transfers")
        return v


class TransferRequest(BaseModel):
    """For fund transfers between two accounts."""
    from_account_id: int
    to_account_id: int
    amount_paise: int
    description: Optional[str] = None

    @field_validator("amount_paise")
    @classmethod
    def positive_amount(cls, v):
        if v <= 0:
            raise ValueError("Transfer amount must be positive and non-zero")
        return v


class TransactionResponse(BaseModel):
    id: int
    txn_id: str
    account_id: int
    counterpart_account_id: Optional[int]
    txn_type: TransactionType
    amount_paise: int
    balance_after_paise: Optional[int]
    status: TransactionStatus
    failure_reason: Optional[FailureReason]
    failure_detail: Optional[str]
    description: Optional[str]
    is_aml_flagged: bool
    is_ctr_generated: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AMLFlagResponse(BaseModel):
    id: int
    transaction_id: int
    account_id: int
    customer_id: int
    amount_paise: int
    flag_reason: str
    is_reviewed: bool
    reviewed_at: Optional[datetime]
    flagged_at: datetime

    model_config = {"from_attributes": True}


class CTRReportResponse(BaseModel):
    id: int
    transaction_id: int
    account_id: int
    customer_id: int
    amount_paise: int
    report_generated_at: datetime
    submitted_to_authority: bool

    model_config = {"from_attributes": True}
