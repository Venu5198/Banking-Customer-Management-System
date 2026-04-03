"""
AML (Anti-Money Laundering) and CTR (Currency Transaction Report) checker.

Rules enforced:
  - AML Flag: Single transaction amount > ₹10,00,000 (100000000 paise)
  - CTR Report: Cash transaction > ₹50,000 (5000000 paise)
"""

import os
from datetime import datetime
from sqlalchemy.orm import Session
from models.transaction import AMLFlag, CTRReport, Transaction
from dotenv import load_dotenv

load_dotenv()

AML_THRESHOLD_PAISE = int(os.getenv("AML_THRESHOLD", "100000000"))   # ₹10,00,000
CTR_THRESHOLD_PAISE = int(os.getenv("CTR_THRESHOLD", "5000000"))     # ₹50,000


def check_aml_ctr(
    db: Session,
    transaction: Transaction,
    customer_id: int,
    is_cash: bool = True,
) -> dict:
    """
    Run AML and CTR checks on a completed transaction.
    Flags transaction in DB and updates the transaction record.
    Returns dict: {"aml_flagged": bool, "ctr_generated": bool}
    """
    result = {"aml_flagged": False, "ctr_generated": False}

    # ── AML Check ────────────────────────────────────────────────────────────
    if transaction.amount_paise > AML_THRESHOLD_PAISE:
        aml_flag = AMLFlag(
            transaction_id=transaction.id,
            account_id=transaction.account_id,
            customer_id=customer_id,
            amount_paise=transaction.amount_paise,
            flag_reason=(
                f"Transaction amount ₹{transaction.amount_paise / 100:,.2f} "
                f"exceeds AML threshold ₹{AML_THRESHOLD_PAISE / 100:,.2f}. "
                f"Type: {transaction.txn_type.value}"
            ),
            flagged_at=datetime.utcnow(),
        )
        db.add(aml_flag)
        transaction.is_aml_flagged = True
        result["aml_flagged"] = True

    # ── CTR Check ────────────────────────────────────────────────────────────
    if is_cash and transaction.amount_paise > CTR_THRESHOLD_PAISE:
        ctr = CTRReport(
            transaction_id=transaction.id,
            account_id=transaction.account_id,
            customer_id=customer_id,
            amount_paise=transaction.amount_paise,
            report_generated_at=datetime.utcnow(),
        )
        db.add(ctr)
        transaction.is_ctr_generated = True
        result["ctr_generated"] = True

    return result
