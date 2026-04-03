"""
Loan Service — application, approval, disbursement, EMI payment.

Banking Rules Enforced:
  - KYC must be VERIFIED
  - Linked account must be ACTIVE
  - Account must be at least 6 months old
  - Credit score >= 650
  - EMI calculated using standard amortization
  - Loan statuses: APPLIED → APPROVED → DISBURSED → CLOSED | DEFAULTED
"""

from datetime import datetime, date
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from dateutil.relativedelta import relativedelta

from models.loan import Loan, LoanEMI, LoanType, LoanStatus, LOAN_INTEREST_RATES
from models.account import Account, AccountStatus
from models.customer import Customer, KYCStatus
from models.transaction import Transaction, TransactionType, TransactionStatus
from schemas.loan import LoanCreate, LoanApprovalRequest
from utils.id_generator import generate_loan_id, generate_txn_id
from utils.interest_calc import calculate_emi, calculate_amortization_schedule
from middleware.audit_logger import log_audit

MIN_CREDIT_SCORE = 650
MIN_ACCOUNT_AGE_MONTHS = 6


class LoanService:

    @staticmethod
    def apply_loan(
        db: Session,
        data: LoanCreate,
        performed_by_user_id: Optional[int] = None,
    ) -> Loan:
        """
        Apply for a loan. Runs all eligibility checks:
          1. KYC verified
          2. Linked account active
          3. Account age >= 6 months
          4. Credit score >= 650
        """
        customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Rule: KYC must be VERIFIED
        if customer.kyc_status != KYCStatus.VERIFIED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Customer KYC is {customer.kyc_status.value}. Loans require VERIFIED KYC."
            )

        # Rule: Credit score >= 650
        if customer.credit_score < MIN_CREDIT_SCORE:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Credit score {customer.credit_score} is below minimum {MIN_CREDIT_SCORE}."
            )

        account = db.query(Account).filter(Account.id == data.linked_account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail="Linked account not found")

        # Rule: Account must be ACTIVE
        if account.status != AccountStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Linked account is {account.status.value}. Must be ACTIVE for loan."
            )

        # Rule: Account must belong to the customer
        if account.customer_id != data.customer_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Account does not belong to this customer."
            )

        # Rule: Account age >= 6 months
        account_age_months = (
            (datetime.utcnow() - account.created_at).days // 30
        )
        if account_age_months < MIN_ACCOUNT_AGE_MONTHS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Account is only {account_age_months} months old. "
                    f"Minimum {MIN_ACCOUNT_AGE_MONTHS} months required for loan eligibility."
                )
            )

        # Determine interest rate
        annual_rate_bps = LOAN_INTEREST_RATES[data.loan_type]

        # Calculate EMI
        emi_paise = calculate_emi(data.principal_paise, annual_rate_bps, data.tenure_months)

        # Generate unique loan ID
        loan_id = generate_loan_id()
        while db.query(Loan).filter(Loan.loan_id == loan_id).first():
            loan_id = generate_loan_id()

        loan = Loan(
            loan_id=loan_id,
            customer_id=data.customer_id,
            linked_account_id=data.linked_account_id,
            loan_type=data.loan_type,
            status=LoanStatus.APPLIED,
            principal_paise=data.principal_paise,
            annual_rate_bps=annual_rate_bps,
            tenure_months=data.tenure_months,
            emi_paise=emi_paise,
            outstanding_paise=data.principal_paise,
            credit_score_at_application=customer.credit_score,
        )
        db.add(loan)
        db.flush()

        # Generate EMI schedule
        schedule = calculate_amortization_schedule(
            data.principal_paise, annual_rate_bps, data.tenure_months, emi_paise
        )
        for entry in schedule:
            due_date = datetime.utcnow() + relativedelta(months=entry["emi_number"])
            emi_record = LoanEMI(
                loan_id=loan.id,
                emi_number=entry["emi_number"],
                due_date=due_date,
                amount_paise=entry["emi_amount_paise"],
                principal_component_paise=entry["principal_component_paise"],
                interest_component_paise=entry["interest_component_paise"],
            )
            db.add(emi_record)

        log_audit(
            db=db,
            entity_type="Loan",
            entity_id=loan.id,
            action="LOAN_APPLIED",
            performed_by_user_id=performed_by_user_id,
            customer_id=data.customer_id,
            new_value=f"LoanID: {loan_id} | Type: {data.loan_type.value} | Principal: {data.principal_paise} paise",
        )
        db.commit()
        db.refresh(loan)
        return loan

    @staticmethod
    def approve_or_reject_loan(
        db: Session,
        loan_id: int,
        request: LoanApprovalRequest,
        performed_by_user_id: Optional[int] = None,
    ) -> Loan:
        """Approve or reject a loan application. Requires MANAGER or ADMIN role."""
        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        if loan.status != LoanStatus.APPLIED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Loan is in {loan.status.value} state. Can only approve/reject APPLIED loans."
            )

        if request.approved:
            loan.status = LoanStatus.APPROVED
            loan.approved_by_user_id = performed_by_user_id
            loan.approved_at = datetime.utcnow()
            action = "LOAN_APPROVED"
        else:
            if not request.rejection_reason:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Rejection reason is required."
                )
            loan.status = LoanStatus.REJECTED
            loan.rejection_reason = request.rejection_reason
            action = "LOAN_REJECTED"

        log_audit(
            db=db,
            entity_type="Loan",
            entity_id=loan.id,
            action=action,
            performed_by_user_id=performed_by_user_id,
            customer_id=loan.customer_id,
            old_value=LoanStatus.APPLIED.value,
            new_value=loan.status.value,
            notes=request.rejection_reason,
        )
        db.commit()
        db.refresh(loan)
        return loan

    @staticmethod
    def disburse_loan(
        db: Session,
        loan_id: int,
        performed_by_user_id: Optional[int] = None,
    ) -> Loan:
        """
        Disburse an approved loan — credits principal to linked account.
        Creates a LOAN_DISBURSEMENT transaction record.
        """
        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        if loan.status != LoanStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Loan must be APPROVED before disbursement. Current: {loan.status.value}"
            )

        account = db.query(Account).filter(Account.id == loan.linked_account_id).first()
        if account.status != AccountStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Linked account is not ACTIVE. Cannot disburse."
            )

        # Credit principal to account
        account.balance_paise += loan.principal_paise

        # Create disbursement transaction
        txn = Transaction(
            txn_id=generate_txn_id(),
            account_id=account.id,
            txn_type=TransactionType.LOAN_DISBURSEMENT,
            amount_paise=loan.principal_paise,
            balance_after_paise=account.balance_paise,
            status=TransactionStatus.SUCCESS,
            description=f"Loan disbursement: {loan.loan_id}",
            initiated_by_user_id=performed_by_user_id,
        )
        db.add(txn)
        db.flush()

        loan.status = LoanStatus.DISBURSED
        loan.disbursed_at = datetime.utcnow()
        # First EMI due 1 month from disbursement
        loan.next_emi_date = datetime.utcnow() + relativedelta(months=1)

        log_audit(
            db=db,
            entity_type="Loan",
            entity_id=loan.id,
            action="LOAN_DISBURSED",
            performed_by_user_id=performed_by_user_id,
            customer_id=loan.customer_id,
            new_value=f"TxnID: {txn.txn_id} | Amount: {loan.principal_paise} paise",
        )
        db.commit()
        db.refresh(loan)
        return loan

    @staticmethod
    def pay_emi(
        db: Session,
        loan_id: int,
        performed_by_user_id: Optional[int] = None,
    ) -> Loan:
        """
        Pay the next due EMI for a loan.
        Debits EMI from the linked account.
        """
        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        if loan.status != LoanStatus.DISBURSED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Loan must be DISBURSED to pay EMI. Current: {loan.status.value}"
            )

        # Find the next unpaid EMI
        next_emi = (
            db.query(LoanEMI)
            .filter(LoanEMI.loan_id == loan.id, LoanEMI.is_paid == False)
            .order_by(LoanEMI.emi_number)
            .first()
        )
        if not next_emi:
            raise HTTPException(status_code=400, detail="No pending EMIs found.")

        account = db.query(Account).filter(Account.id == loan.linked_account_id).first()

        # Check sufficient balance (EMI deducted from account)
        if account.balance_paise < next_emi.amount_paise:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Insufficient balance ₹{account.balance_paise/100:,.2f} for EMI "
                    f"₹{next_emi.amount_paise/100:,.2f}."
                )
            )

        # Debit EMI from account
        account.balance_paise -= next_emi.amount_paise

        # Record the transaction
        txn = Transaction(
            txn_id=generate_txn_id(),
            account_id=account.id,
            txn_type=TransactionType.LOAN_EMI,
            amount_paise=next_emi.amount_paise,
            balance_after_paise=account.balance_paise,
            status=TransactionStatus.SUCCESS,
            description=f"EMI #{next_emi.emi_number} for loan {loan.loan_id}",
            initiated_by_user_id=performed_by_user_id,
        )
        db.add(txn)
        db.flush()

        # Mark EMI as paid
        next_emi.is_paid = True
        next_emi.paid_date = datetime.utcnow()
        next_emi.transaction_id = txn.id

        # Update loan
        loan.emis_paid += 1
        loan.outstanding_paise -= next_emi.principal_component_paise

        # Check if all EMIs paid
        if loan.emis_paid >= loan.tenure_months:
            loan.status = LoanStatus.CLOSED
            loan.closed_at = datetime.utcnow()
            loan.outstanding_paise = 0
        else:
            loan.next_emi_date = datetime.utcnow() + relativedelta(months=1)

        log_audit(
            db=db,
            entity_type="Loan",
            entity_id=loan.id,
            action="EMI_PAID",
            performed_by_user_id=performed_by_user_id,
            customer_id=loan.customer_id,
            new_value=f"EMI#{next_emi.emi_number} | TxnID: {txn.txn_id} | Amount: {next_emi.amount_paise} paise",
        )
        db.commit()
        db.refresh(loan)
        return loan

    @staticmethod
    def get_loan(db: Session, loan_id: int) -> Loan:
        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")
        return loan

    @staticmethod
    def list_customer_loans(db: Session, customer_id: int) -> List[Loan]:
        return db.query(Loan).filter(Loan.customer_id == customer_id).all()
