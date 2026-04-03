"""
Customer Service — KYC onboarding and management.

Banking Rules Enforced:
  - Age must be 18+ at time of onboarding
  - Duplicate detection via national_id_hash (no two customers with same ID)
  - National ID stored encrypted, hash stored for dedup
  - KYC transitions: PENDING → VERIFIED or PENDING → REJECTED
"""

from datetime import date, datetime
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.customer import Customer, KYCStatus
from schemas.customer import CustomerCreate, CustomerUpdate, KYCUpdateRequest
from utils.encryption import encrypt_national_id, hash_national_id
from middleware.audit_logger import log_audit


class CustomerService:

    @staticmethod
    def create_customer(
        db: Session,
        data: CustomerCreate,
        performed_by_user_id: Optional[int] = None,
    ) -> Customer:
        """
        Onboard a new customer with KYC data.
        Validates age (18+) and checks for duplicate national ID.
        """
        # ── Age Verification ────────────────────────────────────────────────
        today = date.today()
        age = (today - data.date_of_birth).days // 365
        if age < 18:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Customer must be at least 18 years old. Calculated age: {age}."
            )

        # ── Duplicate National ID Detection ─────────────────────────────────
        id_hash = hash_national_id(data.national_id)
        existing = db.query(Customer).filter(Customer.national_id_hash == id_hash).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A customer with this National ID already exists."
            )

        # ── Duplicate Email Detection ────────────────────────────────────────
        existing_email = db.query(Customer).filter(Customer.email == data.email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A customer with this email already exists."
            )

        # ── Create Customer ──────────────────────────────────────────────────
        customer = Customer(
            full_name=data.full_name,
            date_of_birth=data.date_of_birth,
            national_id_encrypted=encrypt_national_id(data.national_id),
            national_id_hash=id_hash,
            address=data.address,
            phone=data.phone,
            email=data.email,
            kyc_status=KYCStatus.PENDING,
        )
        db.add(customer)
        db.flush()  # Get ID for audit log

        log_audit(
            db=db,
            entity_type="Customer",
            entity_id=customer.id,
            action="CUSTOMER_ONBOARDED",
            performed_by_user_id=performed_by_user_id,
            customer_id=customer.id,
            new_value=f"KYC Status: PENDING | Name: {customer.full_name}",
        )
        db.commit()
        db.refresh(customer)
        return customer

    @staticmethod
    def get_customer(db: Session, customer_id: int) -> Customer:
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        return customer

    @staticmethod
    def list_customers(db: Session, skip: int = 0, limit: int = 50) -> List[Customer]:
        return db.query(Customer).offset(skip).limit(limit).all()

    @staticmethod
    def update_kyc_status(
        db: Session,
        customer_id: int,
        request: KYCUpdateRequest,
        performed_by_user_id: Optional[int] = None,
    ) -> Customer:
        """
        Update KYC status. Only MANAGER or ADMIN should call this.
        Valid transitions: PENDING → VERIFIED | PENDING → REJECTED
        """
        customer = CustomerService.get_customer(db, customer_id)
        old_status = customer.kyc_status

        if old_status == KYCStatus.VERIFIED and request.status == KYCStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Cannot revert a VERIFIED customer to PENDING."
            )

        if request.status == KYCStatus.REJECTED and not request.rejection_reason:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Rejection reason is required when rejecting KYC."
            )

        customer.kyc_status = request.status
        if request.status == KYCStatus.VERIFIED:
            customer.kyc_verified_at = datetime.utcnow()
            customer.kyc_rejected_reason = None
        elif request.status == KYCStatus.REJECTED:
            customer.kyc_rejected_reason = request.rejection_reason

        log_audit(
            db=db,
            entity_type="Customer",
            entity_id=customer.id,
            action=f"KYC_{request.status.value}",
            performed_by_user_id=performed_by_user_id,
            customer_id=customer.id,
            old_value=old_status.value,
            new_value=request.status.value,
            notes=request.rejection_reason,
        )
        db.commit()
        db.refresh(customer)
        return customer

    @staticmethod
    def update_customer(
        db: Session,
        customer_id: int,
        data: CustomerUpdate,
        performed_by_user_id: Optional[int] = None,
    ) -> Customer:
        customer = CustomerService.get_customer(db, customer_id)
        updates = data.model_dump(exclude_none=True)
        for field, value in updates.items():
            setattr(customer, field, value)

        log_audit(
            db=db,
            entity_type="Customer",
            entity_id=customer.id,
            action="CUSTOMER_UPDATED",
            performed_by_user_id=performed_by_user_id,
            customer_id=customer.id,
            new_value=str(updates),
        )
        db.commit()
        db.refresh(customer)
        return customer

    @staticmethod
    def delete_customer(
        db: Session,
        customer_id: int,
        performed_by_user_id: Optional[int] = None,
    ) -> dict:
        """
        Delete a customer. Only allowed if they do not have any linked accounts or loans.
        """
        customer = CustomerService.get_customer(db, customer_id)
        
        # Rule: Cannot delete if they have accounts or loans
        if getattr(customer, "accounts", []) or getattr(customer, "loans", []):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete a customer with active accounts or loans. Close them first."
            )
            
        full_name = customer.full_name
        
        # We delete the customer record
        db.delete(customer)
        
        # Note: we use entity_id 0 or the soft id since the record is gone
        log_audit(
            db=db,
            entity_type="Customer",
            entity_id=customer_id,
            action="CUSTOMER_DELETED",
            performed_by_user_id=performed_by_user_id,
            customer_id=None,
            old_value=f"Deleted user: {full_name}",
        )
        db.commit()
        
        return {"message": f"Customer {full_name} deleted successfully."}
