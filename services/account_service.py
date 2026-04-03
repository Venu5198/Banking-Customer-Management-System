"""
Account Service — account creation and management.

Banking Rules Enforced:
  - Customer must have VERIFIED KYC to open an account
  - Minimum opening balance per account type:
      SAVINGS:       ₹1,000   (100000 paise)
      CURRENT:       ₹5,000   (500000 paise)
      FIXED_DEPOSIT: ₹10,000 (1000000 paise)
  - One customer can have multiple accounts of different types
  - Account number format: ACC-YYYY-XXXXXX
"""

import os
from datetime import datetime
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from models.account import Account, AccountType, AccountStatus
from models.customer import Customer, KYCStatus
from schemas.account import AccountCreate, AccountStatusUpdate
from utils.id_generator import generate_account_number
from utils.interest_calc import get_fd_rate
from middleware.audit_logger import log_audit

load_dotenv()

# Minimum balances in paise
MIN_BALANCES = {
    AccountType.SAVINGS:       int(os.getenv("SAVINGS_MIN_BALANCE", "100000")),
    AccountType.CURRENT:       int(os.getenv("CURRENT_MIN_BALANCE", "500000")),
    AccountType.FIXED_DEPOSIT: int(os.getenv("FD_MIN_BALANCE", "1000000")),
}


class AccountService:

    @staticmethod
    def create_account(
        db: Session,
        data: AccountCreate,
        performed_by_user_id: Optional[int] = None,
    ) -> Account:
        """
        Open a new bank account.
        - KYC must be VERIFIED
        - Opening balance must meet minimum for the account type
        - FD requires tenure
        """
        # ── KYC Check ───────────────────────────────────────────────────────
        customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        if customer.kyc_status != KYCStatus.VERIFIED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Customer KYC is {customer.kyc_status.value}. "
                       f"Account can only be opened for VERIFIED customers."
            )

        # ── Minimum Balance Check ────────────────────────────────────────────
        min_bal = MIN_BALANCES[data.account_type]
        if data.opening_balance_paise < min_bal:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Opening balance ₹{data.opening_balance_paise/100:,.2f} is below "
                    f"minimum ₹{min_bal/100:,.2f} for {data.account_type.value} account."
                )
            )

        # ── FD-Specific Validation ───────────────────────────────────────────
        fd_tenure_months = None
        fd_interest_rate = None
        fd_maturity_date = None
        if data.account_type == AccountType.FIXED_DEPOSIT:
            if not data.fd_tenure_months:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="FD tenure (months) is required for Fixed Deposit accounts."
                )
            fd_tenure_months = data.fd_tenure_months
            fd_interest_rate = get_fd_rate(fd_tenure_months)
            # Maturity date = today + tenure months
            from dateutil.relativedelta import relativedelta
            fd_maturity_date = datetime.utcnow() + relativedelta(months=fd_tenure_months)

        # ── Generate Unique Account Number ────────────────────────────────────
        account_number = generate_account_number()
        # Ensure uniqueness (very unlikely collision, but good practice)
        while db.query(Account).filter(Account.account_number == account_number).first():
            account_number = generate_account_number()

        account = Account(
            account_number=account_number,
            customer_id=data.customer_id,
            account_type=data.account_type,
            status=AccountStatus.ACTIVE,
            balance_paise=data.opening_balance_paise,
            min_balance_paise=min_bal,
            fd_tenure_months=fd_tenure_months,
            fd_interest_rate=fd_interest_rate,
            fd_maturity_date=fd_maturity_date,
            daily_withdrawal_reset_date=datetime.utcnow(),
        )
        db.add(account)
        db.flush()

        log_audit(
            db=db,
            entity_type="Account",
            entity_id=account.id,
            action="ACCOUNT_OPENED",
            performed_by_user_id=performed_by_user_id,
            customer_id=data.customer_id,
            new_value=(
                f"AccountNumber: {account_number} | Type: {data.account_type.value} | "
                f"OpeningBalance: {data.opening_balance_paise} paise"
            ),
        )
        db.commit()
        db.refresh(account)
        return account

    @staticmethod
    def get_account(db: Session, account_id: int) -> Account:
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        return account

    @staticmethod
    def get_account_by_number(db: Session, account_number: str) -> Account:
        account = db.query(Account).filter(Account.account_number == account_number).first()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        return account

    @staticmethod
    def list_customer_accounts(db: Session, customer_id: int) -> List[Account]:
        return db.query(Account).filter(Account.customer_id == customer_id).all()

    @staticmethod
    def update_account_status(
        db: Session,
        account_id: int,
        request: AccountStatusUpdate,
        performed_by_user_id: Optional[int] = None,
    ) -> Account:
        """
        Change account status (ACTIVE → FROZEN, DORMANT, CLOSED etc.)
        Requires MANAGER or ADMIN role at route level.
        """
        account = AccountService.get_account(db, account_id)
        old_status = account.status

        # Cannot reopen a CLOSED account
        if old_status == AccountStatus.CLOSED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A closed account cannot be reactivated."
            )

        if request.status == AccountStatus.FROZEN:
            account.frozen_reason = request.reason
            account.frozen_by_user_id = performed_by_user_id
            account.frozen_at = datetime.utcnow()
        elif request.status == AccountStatus.CLOSED:
            account.closed_at = datetime.utcnow()
            account.closed_by_user_id = performed_by_user_id

        account.status = request.status
        log_audit(
            db=db,
            entity_type="Account",
            entity_id=account.id,
            action=f"ACCOUNT_{request.status.value}",
            performed_by_user_id=performed_by_user_id,
            customer_id=account.customer_id,
            old_value=old_status.value,
            new_value=request.status.value,
            notes=request.reason,
        )
        db.commit()
        db.refresh(account)
        return account
