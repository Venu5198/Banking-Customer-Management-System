"""Pydantic schemas for loans."""

from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime
from models.loan import LoanType, LoanStatus


class LoanCreate(BaseModel):
    customer_id: int
    linked_account_id: int
    loan_type: LoanType
    principal_paise: int
    tenure_months: int
    purpose: Optional[str] = None

    @field_validator("principal_paise")
    @classmethod
    def positive_principal(cls, v):
        if v <= 0:
            raise ValueError("Loan principal must be positive")
        return v

    @field_validator("tenure_months")
    @classmethod
    def valid_tenure(cls, v):
        if v < 6 or v > 360:
            raise ValueError("Tenure must be between 6 and 360 months")
        return v


class LoanApprovalRequest(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None


class LoanEMIResponse(BaseModel):
    emi_number: int
    due_date: datetime
    paid_date: Optional[datetime]
    amount_paise: int
    principal_component_paise: int
    interest_component_paise: int
    is_paid: bool
    is_overdue: bool

    model_config = {"from_attributes": True}


class LoanResponse(BaseModel):
    id: int
    loan_id: str
    customer_id: int
    linked_account_id: int
    loan_type: LoanType
    status: LoanStatus
    principal_paise: int
    annual_rate_bps: int
    tenure_months: int
    emi_paise: int
    outstanding_paise: int
    emis_paid: int
    disbursed_at: Optional[datetime]
    next_emi_date: Optional[datetime]
    closed_at: Optional[datetime]
    credit_score_at_application: int
    created_at: datetime
    emis: List[LoanEMIResponse] = []

    model_config = {"from_attributes": True}


class EMIScheduleResponse(BaseModel):
    loan_id: str
    total_emis: int
    emi_amount_paise: int
    total_payable_paise: int
    total_interest_paise: int
    schedule: List[LoanEMIResponse]
