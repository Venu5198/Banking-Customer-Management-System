"""
Audit Logger middleware.
Every state change in the banking system creates an immutable AuditLog record.
Rule: Audit logs should NEVER be deleted.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from models.transaction import AuditLog


def log_audit(
    db: Session,
    entity_type: str,
    entity_id: int,
    action: str,
    performed_by_user_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    notes: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """
    Create an audit log entry. Call this for every significant state change.

    Args:
        entity_type: e.g. "Customer", "Account", "Transaction", "Loan"
        entity_id: Primary key of the entity
        action: e.g. "KYC_VERIFIED", "ACCOUNT_FROZEN", "DEPOSIT", "LOAN_APPROVED"
        performed_by_user_id: User who performed the action (None for system)
        customer_id: Associated customer (for quick filtering)
        old_value: Previous value (JSON string or simple string)
        new_value: New value (JSON string or simple string)
        notes: Additional context
        ip_address: Client IP for security tracking
    """
    log = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        performed_by_user_id=performed_by_user_id,
        customer_id=customer_id,
        old_value=old_value,
        new_value=new_value,
        notes=notes,
        ip_address=ip_address,
        created_at=datetime.utcnow(),
    )
    db.add(log)
    db.flush()  # Flush to get ID without committing — caller commits
    return log
