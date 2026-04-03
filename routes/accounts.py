"""Account routes — opening accounts, balance queries, status changes."""

from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models.auth import User, UserRole
from schemas.account import AccountCreate, AccountResponse, AccountStatusUpdate, AccountBalanceResponse
from services.account_service import AccountService
from services.interest_service import InterestService
from middleware.auth_middleware import get_current_user, require_role

router = APIRouter(prefix="/api/accounts", tags=["Accounts"])


@router.post("/", response_model=AccountResponse, status_code=201,
             summary="Open a new bank account")
def create_account(
    data: AccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TELLER, UserRole.MANAGER, UserRole.ADMIN)),
):
    """
    Open a new account. Enforces:
    - KYC must be VERIFIED
    - Minimum opening balance per account type
    - FD requires tenure_months
    """
    return AccountService.create_account(db, data, performed_by_user_id=current_user.id)


@router.get("/customer/{customer_id}", response_model=List[AccountResponse],
            summary="List all accounts for a customer")
def list_customer_accounts(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.CUSTOMER and current_user.customer_id != customer_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")
    return AccountService.list_customer_accounts(db, customer_id)


@router.get("/{account_id}", response_model=AccountResponse, summary="Get account details")
def get_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account = AccountService.get_account(db, account_id)
    if current_user.role == UserRole.CUSTOMER and account.customer_id != current_user.customer_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")
    return account


@router.get("/{account_id}/balance", response_model=AccountBalanceResponse,
            summary="Get account balance")
def get_balance(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    account = AccountService.get_account(db, account_id)
    if current_user.role == UserRole.CUSTOMER and account.customer_id != current_user.customer_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")
    return AccountBalanceResponse(
        account_number=account.account_number,
        account_type=account.account_type,
        status=account.status,
        balance_inr=round(account.balance_paise / 100, 2),
        balance_paise=account.balance_paise,
        min_balance_inr=round(account.min_balance_paise / 100, 2),
    )


@router.patch("/{account_id}/status", response_model=AccountResponse,
              summary="Freeze, unfreeze, or close an account (Manager/Admin only)")
def update_account_status(
    account_id: int,
    data: AccountStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MANAGER, UserRole.ADMIN)),
):
    """
    Change account status. Only MANAGER or ADMIN.
    - FROZEN: blocks all transactions (requires reason)
    - CLOSED: permanently closes account
    """
    return AccountService.update_account_status(db, account_id, data, performed_by_user_id=current_user.id)


@router.post("/{account_id}/fd/close-premature", summary="Close FD prematurely (1% penalty)")
def close_fd_premature(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TELLER, UserRole.MANAGER, UserRole.ADMIN)),
):
    """
    Prematurely close a Fixed Deposit account.
    Banking Rule: 1% penalty on balance is deducted before payout.
    """
    return InterestService.close_fd_premature(db, account_id, performed_by_user_id=current_user.id)
