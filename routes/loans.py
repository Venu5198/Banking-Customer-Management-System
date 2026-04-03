"""Loan routes — application, approval, disbursement, EMI payment."""

from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models.auth import User, UserRole
from schemas.loan import LoanCreate, LoanResponse, LoanApprovalRequest, EMIScheduleResponse, LoanEMIResponse
from services.loan_service import LoanService
from middleware.auth_middleware import get_current_user, require_role

router = APIRouter(prefix="/api/loans", tags=["Loans"])


@router.post("/", response_model=LoanResponse, status_code=201,
             summary="Apply for a loan")
def apply_loan(
    data: LoanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Apply for a new loan. Eligibility checks:
    - KYC VERIFIED
    - Active account
    - Account age >= 6 months
    - Credit score >= 650
    EMI is auto-calculated using standard amortization formula.
    """
    return LoanService.apply_loan(db, data, performed_by_user_id=current_user.id)


@router.get("/customer/{customer_id}", response_model=List[LoanResponse],
            summary="List all loans for a customer")
def list_customer_loans(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.CUSTOMER and current_user.customer_id != customer_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")
    return LoanService.list_customer_loans(db, customer_id)


@router.get("/{loan_id}", response_model=LoanResponse, summary="Get loan details")
def get_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    loan = LoanService.get_loan(db, loan_id)
    if current_user.role == UserRole.CUSTOMER and loan.customer_id != current_user.customer_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")
    return loan


@router.get("/{loan_id}/schedule", response_model=EMIScheduleResponse,
            summary="Get full EMI amortization schedule")
def get_emi_schedule(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    loan = LoanService.get_loan(db, loan_id)
    total_payable = sum(e.amount_paise for e in loan.emis)
    total_interest = total_payable - loan.principal_paise
    return EMIScheduleResponse(
        loan_id=loan.loan_id,
        total_emis=loan.tenure_months,
        emi_amount_paise=loan.emi_paise,
        total_payable_paise=total_payable,
        total_interest_paise=total_interest,
        schedule=loan.emis,
    )


@router.patch("/{loan_id}/approve", response_model=LoanResponse,
              summary="Approve or reject a loan (Manager/Admin only)")
def approve_loan(
    loan_id: int,
    data: LoanApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MANAGER, UserRole.ADMIN)),
):
    """
    Approve or reject a APPLIED loan.
    Only MANAGER or ADMIN can take this action.
    Rejection requires a reason.
    """
    return LoanService.approve_or_reject_loan(db, loan_id, data, performed_by_user_id=current_user.id)


@router.post("/{loan_id}/disburse", response_model=LoanResponse,
             summary="Disburse an approved loan (Manager/Admin only)")
def disburse_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MANAGER, UserRole.ADMIN)),
):
    """
    Disburse loan principal to the linked account.
    Loan status must be APPROVED. Creates LOAN_DISBURSEMENT transaction.
    """
    return LoanService.disburse_loan(db, loan_id, performed_by_user_id=current_user.id)


@router.post("/{loan_id}/pay-emi", response_model=LoanResponse,
             summary="Pay the next EMI for a loan")
def pay_emi(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Pay the next due EMI. Debits from the linked account.
    Auto-closes loan when all EMIs are paid.
    """
    return LoanService.pay_emi(db, loan_id, performed_by_user_id=current_user.id)
