"""
Transaction routes — deposits, withdrawals, transfers, compliance reports.
"""

from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models.auth import User, UserRole
from models.transaction import AMLFlag, CTRReport
from schemas.transaction import (
    TransactionCreate, TransactionResponse, TransferRequest,
    AMLFlagResponse, CTRReportResponse
)
from services.transaction_service import TransactionService
from services.interest_service import InterestService
from middleware.auth_middleware import get_current_user, require_role

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])


@router.post("/deposit", response_model=TransactionResponse, status_code=201,
             summary="Deposit funds into an account")
def deposit(
    data: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TELLER, UserRole.MANAGER, UserRole.ADMIN)),
):
    """
    Credit funds to an active account.
    - AML flag raised if amount > ₹10,00,000
    - CTR generated if amount > ₹50,000
    """
    return TransactionService.deposit(
        db, data.account_id, data.amount_paise, data.description,
        performed_by_user_id=current_user.id,
    )


@router.post("/withdraw", response_model=TransactionResponse, status_code=201,
             summary="Withdraw funds from an account")
def withdraw(
    data: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TELLER, UserRole.MANAGER, UserRole.ADMIN)),
):
    """
    Debit funds from an active account. Rules enforced:
    - Cannot withdraw if balance would go below minimum balance
    - Daily withdrawal limit applies (₹50K Savings / ₹2L Current)
    - FROZEN/CLOSED accounts blocked; failure logged with reason code
    """
    return TransactionService.withdraw(
        db, data.account_id, data.amount_paise, data.description,
        performed_by_user_id=current_user.id,
    )


@router.post("/transfer", response_model=TransactionResponse, status_code=201,
             summary="Transfer funds between accounts")
def transfer(
    data: TransferRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Transfer funds from one account to another.
    Enforces all withdrawal rules on the source account.
    Transfers are not treated as cash (no CTR), but AML check still applies.
    """
    return TransactionService.transfer(
        db, data.from_account_id, data.to_account_id, data.amount_paise,
        data.description, performed_by_user_id=current_user.id,
    )


@router.get("/account/{account_id}", response_model=List[TransactionResponse],
            summary="List transactions for an account")
def list_transactions(
    account_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return TransactionService.list_account_transactions(db, account_id, skip=skip, limit=limit)


@router.get("/{txn_id}", response_model=TransactionResponse, summary="Get transaction by TXN-ID")
def get_transaction(
    txn_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return TransactionService.get_transaction(db, txn_id)


# ── Compliance Endpoints ──────────────────────────────────────────────────────

@router.get("/compliance/aml-flags", response_model=List[AMLFlagResponse],
            summary="List all AML flags (Manager/Admin only)")
def list_aml_flags(
    reviewed: bool = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MANAGER, UserRole.ADMIN)),
):
    query = db.query(AMLFlag)
    if reviewed is not None:
        query = query.filter(AMLFlag.is_reviewed == reviewed)
    return query.all()


@router.patch("/compliance/aml-flags/{flag_id}/review", response_model=AMLFlagResponse,
              summary="Review an AML flag (Manager/Admin only)")
def review_aml_flag(
    flag_id: int,
    notes: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MANAGER, UserRole.ADMIN)),
):
    from datetime import datetime
    flag = db.query(AMLFlag).filter(AMLFlag.id == flag_id).first()
    if not flag:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="AML flag not found")
    flag.is_reviewed = True
    flag.reviewed_by_user_id = current_user.id
    flag.reviewed_at = datetime.utcnow()
    flag.review_notes = notes
    db.commit()
    db.refresh(flag)
    return flag


@router.get("/compliance/ctr-reports", response_model=List[CTRReportResponse],
            summary="List all CTR reports (Manager/Admin only)")
def list_ctr_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MANAGER, UserRole.ADMIN)),
):
    return db.query(CTRReport).all()


@router.post("/interest/credit-all", summary="Trigger monthly interest credit (Admin only)")
def credit_interest(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Manually trigger monthly interest crediting for all active Savings and FD accounts.
    In production, this should run via a scheduled job (cron/APScheduler).
    """
    return InterestService.credit_monthly_interest(db, performed_by_user_id=current_user.id)
