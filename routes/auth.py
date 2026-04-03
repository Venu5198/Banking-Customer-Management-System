"""
Auth routes — login, user creation, token management.
Enforces:
  - 3 failed logins → account locked for 15 minutes
  - Passwords verified against bcrypt hash only
"""

import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import get_db
from models.auth import User, UserRole, LoginAttempt
from schemas.auth import TokenResponse, UserCreate, UserResponse, PasswordChangeRequest
from middleware.auth_middleware import (
    hash_password, verify_password, create_access_token, get_current_user, require_role
)
from middleware.audit_logger import log_audit

load_dotenv()

MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "3"))
LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", "15"))

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse, summary="Login and get JWT token")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Authenticate user with username + password.
    Returns a JWT access token.
    3 consecutive failures lock the account for 15 minutes.
    """
    ip_address = request.client.host if request.client else "unknown"
    user = db.query(User).filter(User.username == form_data.username).first()

    # Unknown user — don't reveal existence
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if account is currently locked
    if user.is_locked:
        if user.locked_until and datetime.utcnow() < user.locked_until:
            remaining_min = int((user.locked_until - datetime.utcnow()).total_seconds() // 60) + 1
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account locked due to multiple failed attempts. Try again in {remaining_min} minute(s)."
            )
        else:
            # Lock period expired — auto-unlock
            user.is_locked = False
            user.locked_until = None
            db.commit()

    # Verify password
    if not verify_password(form_data.password, user.hashed_password):
        # Log failed attempt
        attempt = LoginAttempt(
            user_id=user.id,
            ip_address=ip_address,
            success=False,
            failure_reason="Invalid password",
        )
        db.add(attempt)

        # Count recent failed attempts
        recent_failures = (
            db.query(LoginAttempt)
            .filter(
                LoginAttempt.user_id == user.id,
                LoginAttempt.success == False,
                LoginAttempt.attempted_at >= datetime.utcnow() - timedelta(minutes=LOCKOUT_MINUTES)
            )
            .count()
        )

        # +1 for the attempt we just added (not yet committed)
        if recent_failures + 1 >= MAX_LOGIN_ATTEMPTS:
            user.is_locked = True
            user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Too many failed attempts. Account locked for {LOCKOUT_MINUTES} minutes."
            )

        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Successful login
    attempt = LoginAttempt(
        user_id=user.id,
        ip_address=ip_address,
        success=True,
    )
    db.add(attempt)
    db.commit()

    access_token = create_access_token(data={"sub": user.username, "role": user.role.value})
    return TokenResponse(
        access_token=access_token,
        role=user.role,
        username=user.username,
    )


@router.post("/users", response_model=UserResponse, summary="Create a new user (Admin only)")
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Create a new system user. Admin only."""
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=409, detail="Username already exists")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=409, detail="Email already exists")

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=data.role,
        customer_id=data.customer_id,
    )
    db.add(user)
    db.flush()

    log_audit(
        db=db,
        entity_type="User",
        entity_id=user.id,
        action="USER_CREATED",
        performed_by_user_id=current_user.id,
        new_value=f"Username: {user.username} | Role: {user.role.value}",
    )
    db.commit()
    db.refresh(user)
    return user


@router.get("/me", response_model=UserResponse, summary="Get current user profile")
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password", summary="Change own password")
def change_password(
    data: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.hashed_password = hash_password(data.new_password)
    log_audit(
        db=db,
        entity_type="User",
        entity_id=current_user.id,
        action="PASSWORD_CHANGED",
        performed_by_user_id=current_user.id,
    )
    db.commit()
    return {"message": "Password changed successfully"}


@router.get("/users", response_model=list[UserResponse], summary="List all users (Admin only)")
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    return db.query(User).all()
