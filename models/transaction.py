"""
Transaction, AuditLog, CTR and AML models.
- Every monetary event creates a Transaction record.
- Every state change (any entity) creates an AuditLog record.
- CTR auto-generated for cash > ₹50,000.
- AML flag auto-generated for single transaction > ₹10,00,000.
"""

import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, Enum, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from database import Base


class TransactionType(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRANSFER = "TRANSFER"         # Debit from source, credit to destination
    INTEREST_CREDIT = "INTEREST_CREDIT"
    LOAN_DISBURSEMENT = "LOAN_DISBURSEMENT"
    LOAN_EMI = "LOAN_EMI"
    FD_PENALTY = "FD_PENALTY"     # 1% penalty for premature FD withdrawal


class TransactionStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class FailureReason(str, enum.Enum):
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    BELOW_MIN_BALANCE = "BELOW_MIN_BALANCE"
    DAILY_LIMIT_EXCEEDED = "DAILY_LIMIT_EXCEEDED"
    ACCOUNT_FROZEN = "ACCOUNT_FROZEN"
    ACCOUNT_CLOSED = "ACCOUNT_CLOSED"
    ACCOUNT_DORMANT = "ACCOUNT_DORMANT"
    ACCOUNT_NOT_ACTIVE = "ACCOUNT_NOT_ACTIVE"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    KYC_NOT_VERIFIED = "KYC_NOT_VERIFIED"
    TRANSFER_SAME_ACCOUNT = "TRANSFER_SAME_ACCOUNT"
    OTHER = "OTHER"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    txn_id = Column(String(30), unique=True, nullable=False, index=True)  # TXN-YYYYMMDD-XXXXXX
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    # For transfers: the counterpart account
    counterpart_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    txn_type = Column(Enum(TransactionType), nullable=False)
    # Amount in paise
    amount_paise = Column(BigInteger, nullable=False)
    # Balance after this transaction (for audit trail; -1 for failed)
    balance_after_paise = Column(BigInteger, nullable=True)
    status = Column(Enum(TransactionStatus), nullable=False)
    failure_reason = Column(Enum(FailureReason), nullable=True)
    failure_detail = Column(String(500), nullable=True)  # Human-readable detail
    description = Column(String(500), nullable=True)
    # Who initiated it
    initiated_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # AML/CTR flags
    is_aml_flagged = Column(Boolean, default=False)
    is_ctr_generated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="transactions", foreign_keys=[account_id])
    counterpart_account = relationship("Account", foreign_keys=[counterpart_account_id])
    initiated_by = relationship("User", foreign_keys=[initiated_by_user_id])


class AuditLog(Base):
    """
    Immutable audit trail for every state change in the system.
    Rule: No audit log should ever be deleted or modified.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(50), nullable=False)    # e.g. "Customer", "Account"
    entity_id = Column(Integer, nullable=False)
    action = Column(String(100), nullable=False)         # e.g. "KYC_VERIFIED"
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    performed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    ip_address = Column(String(45), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    performed_by = relationship("User", foreign_keys=[performed_by_user_id])
    customer = relationship("Customer", back_populates="audit_logs")


class CTRReport(Base):
    """
    Currency Transaction Report — auto-generated for cash transactions > ₹50,000.
    Required by banking compliance / RBI guidelines.
    """
    __tablename__ = "ctr_reports"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    amount_paise = Column(BigInteger, nullable=False)
    report_generated_at = Column(DateTime, default=datetime.utcnow)
    submitted_to_authority = Column(Boolean, default=False)

    transaction = relationship("Transaction", foreign_keys=[transaction_id])
    account = relationship("Account", foreign_keys=[account_id])
    customer = relationship("Customer", foreign_keys=[customer_id])


class AMLFlag(Base):
    """
    Anti-Money Laundering flag — raised for single transactions > ₹10,00,000.
    Must be reviewed by a MANAGER or ADMIN before clearing.
    """
    __tablename__ = "aml_flags"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    amount_paise = Column(BigInteger, nullable=False)
    flag_reason = Column(String(300), nullable=False)
    is_reviewed = Column(Boolean, default=False)
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_notes = Column(Text, nullable=True)
    flagged_at = Column(DateTime, default=datetime.utcnow)

    transaction = relationship("Transaction", foreign_keys=[transaction_id])
    account = relationship("Account", foreign_keys=[account_id])
    customer = relationship("Customer", foreign_keys=[customer_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_user_id])
