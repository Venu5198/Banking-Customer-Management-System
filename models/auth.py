"""
Auth models: User accounts (bank staff + portal users) and login tracking.
Passwords are hashed with bcrypt — NEVER stored in plain text.
"""

import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class UserRole(str, enum.Enum):
    CUSTOMER = "CUSTOMER"   # Limited to own account operations
    TELLER = "TELLER"       # Can process deposits, withdrawals, account queries
    MANAGER = "MANAGER"     # Can approve loans, freeze accounts
    ADMIN = "ADMIN"         # Full access including user management


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    # bcrypt hashed password — raw password never stored
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.CUSTOMER)
    is_active = Column(Boolean, default=True)
    is_locked = Column(Boolean, default=False)       # True if 3 failed logins
    locked_until = Column(DateTime, nullable=True)   # Lockout expiry (15 min)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer", back_populates="user")
    login_attempts = relationship("LoginAttempt", back_populates="user")


class LoginAttempt(Base):
    """Tracks every login attempt for brute-force protection and audit."""
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ip_address = Column(String(45), nullable=True)   # IPv6 max length = 45
    success = Column(Boolean, nullable=False)
    attempted_at = Column(DateTime, default=datetime.utcnow)
    failure_reason = Column(String(200), nullable=True)

    user = relationship("User", back_populates="login_attempts")
