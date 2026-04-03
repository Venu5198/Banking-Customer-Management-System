"""Pydantic schemas for customer KYC onboarding."""

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import date, datetime
from models.customer import KYCStatus


class CustomerCreate(BaseModel):
    full_name: str
    date_of_birth: date
    national_id: str          # Will be encrypted before saving
    address: str
    phone: str
    email: EmailStr

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Full name cannot be blank")
        return v.strip()

    @field_validator("national_id")
    @classmethod
    def national_id_not_empty(cls, v):
        if not v.strip():
            raise ValueError("National ID cannot be blank")
        return v.strip()

    @field_validator("phone")
    @classmethod
    def phone_format(cls, v):
        digits = v.replace("+", "").replace("-", "").replace(" ", "")
        if not digits.isdigit() or len(digits) < 10:
            raise ValueError("Phone must be at least 10 digits")
        return v


class CustomerUpdate(BaseModel):
    full_name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    credit_score: Optional[int] = None


class KYCUpdateRequest(BaseModel):
    status: KYCStatus
    rejection_reason: Optional[str] = None


class CustomerResponse(BaseModel):
    id: int
    full_name: str
    date_of_birth: date
    # national_id intentionally EXCLUDED from response — never expose
    address: str
    phone: str
    email: str
    kyc_status: KYCStatus
    kyc_verified_at: Optional[datetime]
    credit_score: int
    created_at: datetime

    model_config = {"from_attributes": True}
