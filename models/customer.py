"""
Customer model: KYC data, personal information.
National ID is stored ENCRYPTED using Fernet — never in plain text.
"""

import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Date, Enum, Text
from sqlalchemy.orm import relationship
from database import Base


class KYCStatus(str, enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(150), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    # Encrypted national ID / passport — use utils.encryption to read/write
    national_id_encrypted = Column(String(500), nullable=False)
    # Hash of national ID for duplicate detection without decrypting
    national_id_hash = Column(String(64), unique=True, nullable=False, index=True)
    address = Column(Text, nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(100), unique=True, nullable=False, index=True)
    kyc_status = Column(Enum(KYCStatus), nullable=False, default=KYCStatus.PENDING)
    kyc_verified_at = Column(DateTime, nullable=True)
    kyc_rejected_reason = Column(Text, nullable=True)
    credit_score = Column(Integer, default=650)   # Default neutral score
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    accounts = relationship("Account", back_populates="customer")
    loans = relationship("Loan", back_populates="customer")
    user = relationship("User", back_populates="customer", uselist=False)
    audit_logs = relationship("AuditLog", back_populates="customer")
