"""
Interest Engine Service.

Rules:
  - Savings: 3.5% p.a. — accrued daily, credited monthly
  - Fixed Deposit: 6.5–7.5% based on tenure — accrued daily, credited monthly
  - FD premature withdrawal: 1% penalty on principal
  - Interest stored and computed in paise (integer arithmetic)

This service should be called by a scheduled task (e.g., APScheduler or cron).
The /api/interest/credit endpoint triggers it manually for testing.
"""

from datetime import datetime, date
from typing import List
from sqlalchemy.orm import Session

from models.account import Account, AccountType, AccountStatus
from models.transaction import Transaction, TransactionType, TransactionStatus
from utils.id_generator import generate_txn_id
from utils.interest_calc import (
    calculate_daily_interest,
    calculate_fd_premature_penalty,
    SAVINGS_RATE_BPS,
)
from middleware.audit_logger import log_audit


class InterestService:

    @staticmethod
    def credit_monthly_interest(db: Session, performed_by_user_id: int = None) -> dict:
        """
        Credit monthly interest to all ACTIVE Savings and FD accounts.
        Run this monthly (e.g., first day of each month via scheduler).

        Returns summary dict: {accounts_credited: int, total_interest_paise: int}
        """
        accounts = (
            db.query(Account)
            .filter(
                Account.status == AccountStatus.ACTIVE,
                Account.account_type.in_([AccountType.SAVINGS, AccountType.FIXED_DEPOSIT])
            )
            .all()
        )

        credited_count = 0
        total_interest = 0

        for account in accounts:
            # Determine last credit date
            last_credit = account.last_interest_credited_at or account.created_at
            days_since = (datetime.utcnow() - last_credit).days

            if days_since < 1:
                continue  # Nothing to credit yet

            # Determine rate
            if account.account_type == AccountType.SAVINGS:
                rate_bps = SAVINGS_RATE_BPS
            else:
                rate_bps = account.fd_interest_rate or SAVINGS_RATE_BPS

            # Accumulate daily interest over elapsed days
            interest_paise = 0
            for _ in range(days_since):
                interest_paise += calculate_daily_interest(account.balance_paise, rate_bps)

            if interest_paise <= 0:
                continue

            # Credit interest
            account.balance_paise += interest_paise
            account.last_interest_credited_at = datetime.utcnow()

            txn = Transaction(
                txn_id=generate_txn_id(),
                account_id=account.id,
                txn_type=TransactionType.INTEREST_CREDIT,
                amount_paise=interest_paise,
                balance_after_paise=account.balance_paise,
                status=TransactionStatus.SUCCESS,
                description=f"Monthly interest credit ({days_since} days @ {rate_bps/100:.2f}% p.a.)",
                initiated_by_user_id=performed_by_user_id,
            )
            db.add(txn)
            db.flush()

            log_audit(
                db=db,
                entity_type="Account",
                entity_id=account.id,
                action="INTEREST_CREDITED",
                performed_by_user_id=performed_by_user_id,
                customer_id=account.customer_id,
                new_value=(
                    f"TxnID: {txn.txn_id} | Interest: {interest_paise} paise | "
                    f"Days: {days_since} | BalanceAfter: {account.balance_paise} paise"
                ),
            )

            credited_count += 1
            total_interest += interest_paise

        db.commit()
        return {
            "accounts_credited": credited_count,
            "total_interest_paise": total_interest,
            "total_interest_inr": round(total_interest / 100, 2),
        }

    @staticmethod
    def close_fd_premature(
        db: Session,
        account_id: int,
        performed_by_user_id: int = None,
    ) -> dict:
        """
        Handle premature FD closure with 1% penalty on principal.
        Returns net payout details.
        """
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Account not found")

        if account.account_type != AccountType.FIXED_DEPOSIT:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Account is not a Fixed Deposit.")

        if account.status != AccountStatus.ACTIVE:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=f"FD account is {account.status.value}, cannot be closed."
            )

        penalty_paise = calculate_fd_premature_penalty(account.balance_paise)
        payout_paise = account.balance_paise - penalty_paise

        # Record penalty transaction
        penalty_txn = Transaction(
            txn_id=generate_txn_id(),
            account_id=account.id,
            txn_type=TransactionType.FD_PENALTY,
            amount_paise=penalty_paise,
            balance_after_paise=payout_paise,
            status=TransactionStatus.SUCCESS,
            description="Premature FD closure penalty (1%)",
            initiated_by_user_id=performed_by_user_id,
        )
        db.add(penalty_txn)

        # Close the FD account
        account.balance_paise = 0
        account.status = AccountStatus.CLOSED
        account.closed_at = datetime.utcnow()
        account.closed_by_user_id = performed_by_user_id

        log_audit(
            db=db,
            entity_type="Account",
            entity_id=account.id,
            action="FD_PREMATURE_CLOSURE",
            performed_by_user_id=performed_by_user_id,
            customer_id=account.customer_id,
            new_value=(
                f"Penalty: {penalty_paise} paise | Payout: {payout_paise} paise"
            ),
        )
        db.commit()

        return {
            "account_number": account.account_number,
            "balance_paise": payout_paise + penalty_paise,
            "penalty_paise": penalty_paise,
            "payout_paise": payout_paise,
            "payout_inr": round(payout_paise / 100, 2),
        }
