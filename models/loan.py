"""
Loan and EMI models.
EMI calculated using standard amortization formula:
  EMI = P * r * (1+r)^n / ((1+r)^n - 1)
  where P = principal, r = monthly rate, n = tenure in months
"""

import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, Enum, ForeignKey, Text, Boolean, Float
from sqlalchemy.orm import relationship
from database import Base


class LoanType(str, enum.Enum):
    PERSONAL = "PERSONAL"     # Up to ₹15L, rate ~12%
    HOME = "HOME"             # Up to ₹1Cr, rate ~8.5%
    VEHICLE = "VEHICLE"       # Up to ₹20L, rate ~10%
    EDUCATION = "EDUCATION"   # Up to ₹25L, rate ~9%


class LoanStatus(str, enum.Enum):
    APPLIED = "APPLIED"
    APPROVED = "APPROVED"
    DISBURSED = "DISBURSED"
    CLOSED = "CLOSED"
    DEFAULTED = "DEFAULTED"
    REJECTED = "REJECTED"


# Annual interest rates in basis points per loan type
LOAN_INTEREST_RATES = {
    LoanType.PERSONAL: 1200,   # 12.00% p.a.
    LoanType.HOME: 850,        # 8.50% p.a.
    LoanType.VEHICLE: 1000,    # 10.00% p.a.
    LoanType.EDUCATION: 900,   # 9.00% p.a.
}

# Max loan amounts in paise
LOAN_MAX_AMOUNTS = {
    LoanType.PERSONAL: 150000000,   # ₹15,00,000
    LoanType.HOME: 10000000000,     # ₹1,00,00,000 (1 Cr)
    LoanType.VEHICLE: 2000000000,   # ₹20,00,00,000
    LoanType.EDUCATION: 2500000000, # ₹25,00,00,000
}


class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(String(25), unique=True, nullable=False, index=True)  # LN-YYYY-XXXXXX
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    linked_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    loan_type = Column(Enum(LoanType), nullable=False)
    status = Column(Enum(LoanStatus), nullable=False, default=LoanStatus.APPLIED)
    # Principal in paise
    principal_paise = Column(BigInteger, nullable=False)
    # Interest rate in basis points (e.g., 1200 = 12.00%)
    annual_rate_bps = Column(Integer, nullable=False)
    tenure_months = Column(Integer, nullable=False)
    # Computed EMI in paise
    emi_paise = Column(BigInteger, nullable=False)
    # Outstanding balance
    outstanding_paise = Column(BigInteger, nullable=False)
    # EMIs paid so far
    emis_paid = Column(Integer, default=0)
    disbursed_at = Column(DateTime, nullable=True)
    next_emi_date = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    defaulted_at = Column(DateTime, nullable=True)
    # Approval workflow
    approved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    # Eligibility snapshot at time of application
    credit_score_at_application = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer", back_populates="loans")
    linked_account = relationship("Account", back_populates="loans")
    approved_by = relationship("User", foreign_keys=[approved_by_user_id])
    emis = relationship("LoanEMI", back_populates="loan")


class LoanEMI(Base):
    """Individual EMI payment record for a loan."""
    __tablename__ = "loan_emis"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False)
    emi_number = Column(Integer, nullable=False)        # 1-based sequence
    due_date = Column(DateTime, nullable=False)
    paid_date = Column(DateTime, nullable=True)
    amount_paise = Column(BigInteger, nullable=False)   # Total EMI
    principal_component_paise = Column(BigInteger, nullable=False)
    interest_component_paise = Column(BigInteger, nullable=False)
    is_paid = Column(Boolean, default=False)
    is_overdue = Column(Boolean, default=False)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)

    loan = relationship("Loan", back_populates="emis")
    transaction = relationship("Transaction")
