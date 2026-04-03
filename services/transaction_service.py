"""
Transaction Service — deposits, withdrawals, transfers.

Banking Rules Enforced:
  - Never allow negative balances
  - No transactions on FROZEN or CLOSED accounts
  - Withdrawal cannot bring balance below minimum balance
  - Daily withdrawal limits:
      SAVINGS: ₹50,000  (5000000 paise)
      CURRENT: ₹2,00,000 (20000000 paise)
  - All failed transactions are logged with reason codes
  - AML and CTR checks run on every successful transaction
  - Each transaction gets a unique TXN-ID with timestamp
"""

import os
from datetime import datetime, date
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from models.account import Account, AccountType, AccountStatus
from models.transaction import Transaction, TransactionType, TransactionStatus, FailureReason
from utils.id_generator import generate_txn_id
from middleware.audit_logger import log_audit
from middleware.aml_checker import check_aml_ctr

load_dotenv()

DAILY_LIMITS = {
    AccountType.SAVINGS:       int(os.getenv("SAVINGS_DAILY_WITHDRAWAL", "5000000")),
    AccountType.CURRENT:       int(os.getenv("CURRENT_DAILY_WITHDRAWAL", "20000000")),
    AccountType.FIXED_DEPOSIT: 0,   # No ad-hoc withdrawals from FD
}


class TransactionService:

    @staticmethod
    def _check_account_active(account: Account) -> None:
        """Raise HTTPException if account is not ACTIVE."""
        if account.status == AccountStatus.FROZEN:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Account {account.account_number} is FROZEN. Transactions not allowed."
            )
        if account.status == AccountStatus.CLOSED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Account {account.account_number} is CLOSED. Transactions not allowed."
            )
        if account.status != AccountStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Account {account.account_number} is {account.status.value}. Transactions not allowed."
            )

    @staticmethod
    def _reset_daily_limit_if_needed(db: Session, account: Account) -> None:
        """Reset the daily withdrawal counter if a new calendar day has started."""
        today = date.today()
        reset_date = account.daily_withdrawal_reset_date
        if reset_date is None or reset_date.date() < today:
            account.daily_withdrawn_paise = 0
            account.daily_withdrawal_reset_date = datetime.utcnow()

    @staticmethod
    def _log_failed_transaction(
        db: Session,
        account: Account,
        txn_type: TransactionType,
        amount_paise: int,
        reason: FailureReason,
        detail: str,
        initiated_by_user_id: Optional[int] = None,
    ) -> Transaction:
        """Log a failed transaction for audit purposes."""
        txn = Transaction(
            txn_id=generate_txn_id(),
            account_id=account.id,
            txn_type=txn_type,
            amount_paise=amount_paise,
            balance_after_paise=None,
            status=TransactionStatus.FAILED,
            failure_reason=reason,
            failure_detail=detail,
            initiated_by_user_id=initiated_by_user_id,
        )
        db.add(txn)
        db.commit()
        return txn

    @staticmethod
    def deposit(
        db: Session,
        account_id: int,
        amount_paise: int,
        description: Optional[str] = None,
        performed_by_user_id: Optional[int] = None,
    ) -> Transaction:
        """
        Deposit funds into an account.
        Rules: Account must be ACTIVE. Amount must be positive.
        """
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        TransactionService._check_account_active(account)

        if amount_paise <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Deposit amount must be positive and non-zero."
            )

        # Credit the account
        account.balance_paise += amount_paise

        txn = Transaction(
            txn_id=generate_txn_id(),
            account_id=account.id,
            txn_type=TransactionType.DEPOSIT,
            amount_paise=amount_paise,
            balance_after_paise=account.balance_paise,
            status=TransactionStatus.SUCCESS,
            description=description,
            initiated_by_user_id=performed_by_user_id,
        )
        db.add(txn)
        db.flush()

        # AML/CTR compliance checks
        check_aml_ctr(db, txn, account.customer_id, is_cash=True)

        log_audit(
            db=db,
            entity_type="Account",
            entity_id=account.id,
            action="DEPOSIT",
            performed_by_user_id=performed_by_user_id,
            customer_id=account.customer_id,
            new_value=f"TxnID: {txn.txn_id} | Amount: {amount_paise} paise | BalanceAfter: {account.balance_paise} paise",
        )
        db.commit()
        db.refresh(txn)
        return txn

    @staticmethod
    def withdraw(
        db: Session,
        account_id: int,
        amount_paise: int,
        description: Optional[str] = None,
        performed_by_user_id: Optional[int] = None,
    ) -> Transaction:
        """
        Withdraw funds from an account.

        Rules enforced:
          1. Account must be ACTIVE
          2. Amount must be positive
          3. Balance after withdrawal cannot go below minimum balance
          4. Daily withdrawal limit must not be exceeded
          5. FD accounts: no direct withdrawal (must use FD close endpoint)
        """
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        try:
            TransactionService._check_account_active(account)
        except HTTPException as e:
            reason_map = {
                "FROZEN": FailureReason.ACCOUNT_FROZEN,
                "CLOSED": FailureReason.ACCOUNT_CLOSED,
            }
            r = FailureReason.ACCOUNT_NOT_ACTIVE
            for k, v in reason_map.items():
                if k in e.detail:
                    r = v
            TransactionService._log_failed_transaction(
                db, account, TransactionType.WITHDRAWAL, amount_paise, r, e.detail, performed_by_user_id
            )
            raise

        # FD — no direct withdrawal
        if account.account_type == AccountType.FIXED_DEPOSIT:
            detail = "Cannot withdraw directly from a Fixed Deposit. Use the FD close/premature withdrawal endpoint."
            TransactionService._log_failed_transaction(
                db, account, TransactionType.WITHDRAWAL, amount_paise,
                FailureReason.OTHER, detail, performed_by_user_id
            )
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)

        if amount_paise <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Withdrawal amount must be positive and non-zero."
            )

        # Reset daily limit if needed
        TransactionService._reset_daily_limit_if_needed(db, account)

        # Check daily withdrawal limit
        daily_limit = DAILY_LIMITS.get(account.account_type, 0)
        if daily_limit > 0 and (account.daily_withdrawn_paise + amount_paise) > daily_limit:
            remaining = daily_limit - account.daily_withdrawn_paise
            detail = (
                f"Daily withdrawal limit ₹{daily_limit/100:,.2f} exceeded. "
                f"Already withdrawn: ₹{account.daily_withdrawn_paise/100:,.2f}. "
                f"Remaining: ₹{remaining/100:,.2f}."
            )
            TransactionService._log_failed_transaction(
                db, account, TransactionType.WITHDRAWAL, amount_paise,
                FailureReason.DAILY_LIMIT_EXCEEDED, detail, performed_by_user_id
            )
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)

        # Check balance won't drop below minimum
        balance_after = account.balance_paise - amount_paise
        if balance_after < account.min_balance_paise:
            detail = (
                f"Withdrawal of ₹{amount_paise/100:,.2f} would leave balance "
                f"₹{balance_after/100:,.2f}, below minimum ₹{account.min_balance_paise/100:,.2f}."
            )
            TransactionService._log_failed_transaction(
                db, account, TransactionType.WITHDRAWAL, amount_paise,
                FailureReason.BELOW_MIN_BALANCE, detail, performed_by_user_id
            )
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)

        # Debit the account
        account.balance_paise = balance_after
        account.daily_withdrawn_paise += amount_paise

        txn = Transaction(
            txn_id=generate_txn_id(),
            account_id=account.id,
            txn_type=TransactionType.WITHDRAWAL,
            amount_paise=amount_paise,
            balance_after_paise=account.balance_paise,
            status=TransactionStatus.SUCCESS,
            description=description,
            initiated_by_user_id=performed_by_user_id,
        )
        db.add(txn)
        db.flush()

        check_aml_ctr(db, txn, account.customer_id, is_cash=True)

        log_audit(
            db=db,
            entity_type="Account",
            entity_id=account.id,
            action="WITHDRAWAL",
            performed_by_user_id=performed_by_user_id,
            customer_id=account.customer_id,
            new_value=f"TxnID: {txn.txn_id} | Amount: {amount_paise} paise | BalanceAfter: {account.balance_paise} paise",
        )
        db.commit()
        db.refresh(txn)
        return txn

    @staticmethod
    def transfer(
        db: Session,
        from_account_id: int,
        to_account_id: int,
        amount_paise: int,
        description: Optional[str] = None,
        performed_by_user_id: Optional[int] = None,
    ) -> Transaction:
        """
        Transfer funds between two accounts.
        Enforces all withdrawal rules on the source account.
        Transfer is NOT a cash transaction for CTR purposes.
        """
        if from_account_id == to_account_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot transfer to the same account."
            )

        from_account = db.query(Account).filter(Account.id == from_account_id).first()
        to_account = db.query(Account).filter(Account.id == to_account_id).first()

        if not from_account:
            raise HTTPException(status_code=404, detail="Source account not found")
        if not to_account:
            raise HTTPException(status_code=404, detail="Destination account not found")

        TransactionService._check_account_active(from_account)
        TransactionService._check_account_active(to_account)

        if amount_paise <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Transfer amount must be positive and non-zero."
            )

        # Apply same withdrawal rules to source
        TransactionService._reset_daily_limit_if_needed(db, from_account)

        daily_limit = DAILY_LIMITS.get(from_account.account_type, 0)
        if daily_limit > 0 and (from_account.daily_withdrawn_paise + amount_paise) > daily_limit:
            remaining = daily_limit - from_account.daily_withdrawn_paise
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Daily withdrawal limit exceeded. Remaining: ₹{remaining/100:,.2f}."
            )

        balance_after_source = from_account.balance_paise - amount_paise
        if balance_after_source < from_account.min_balance_paise:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Transfer would leave source balance ₹{balance_after_source/100:,.2f}, "
                    f"below minimum ₹{from_account.min_balance_paise/100:,.2f}."
                )
            )

        # Execute transfer
        from_account.balance_paise = balance_after_source
        from_account.daily_withdrawn_paise += amount_paise
        to_account.balance_paise += amount_paise

        txn = Transaction(
            txn_id=generate_txn_id(),
            account_id=from_account.id,
            counterpart_account_id=to_account.id,
            txn_type=TransactionType.TRANSFER,
            amount_paise=amount_paise,
            balance_after_paise=from_account.balance_paise,
            status=TransactionStatus.SUCCESS,
            description=description,
            initiated_by_user_id=performed_by_user_id,
        )
        db.add(txn)
        db.flush()

        # Transfers are not cash — is_cash=False skips CTR
        check_aml_ctr(db, txn, from_account.customer_id, is_cash=False)

        log_audit(
            db=db,
            entity_type="Account",
            entity_id=from_account.id,
            action="TRANSFER_OUT",
            performed_by_user_id=performed_by_user_id,
            customer_id=from_account.customer_id,
            new_value=f"TxnID: {txn.txn_id} | To: {to_account.account_number} | Amount: {amount_paise} paise",
        )
        db.commit()
        db.refresh(txn)
        return txn

    @staticmethod
    def get_transaction(db: Session, txn_id: str) -> Transaction:
        txn = db.query(Transaction).filter(Transaction.txn_id == txn_id).first()
        if not txn:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return txn

    @staticmethod
    def list_account_transactions(
        db: Session,
        account_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Transaction]:
        return (
            db.query(Transaction)
            .filter(Transaction.account_id == account_id)
            .order_by(Transaction.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
