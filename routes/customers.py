"""Customer routes — KYC onboarding and management."""

from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models.auth import User, UserRole
from schemas.customer import CustomerCreate, CustomerResponse, CustomerUpdate, KYCUpdateRequest
from services.customer_service import CustomerService
from middleware.auth_middleware import get_current_user, require_role

router = APIRouter(prefix="/api/customers", tags=["Customers (KYC)"])


@router.post("/", response_model=CustomerResponse, status_code=201,
             summary="Onboard a new customer (KYC)")
def create_customer(
    data: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TELLER, UserRole.MANAGER, UserRole.ADMIN)),
):
    """
    Onboard a new customer. Enforces:
    - Age >= 18 years
    - No duplicate National ID
    - KYC status set to PENDING
    """
    return CustomerService.create_customer(db, data, performed_by_user_id=current_user.id)


@router.get("/", response_model=List[CustomerResponse], summary="List all customers")
def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TELLER, UserRole.MANAGER, UserRole.ADMIN)),
):
    return CustomerService.list_customers(db, skip=skip, limit=limit)


@router.get("/{customer_id}", response_model=CustomerResponse, summary="Get customer by ID")
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Any authenticated user can fetch customer details.
    CUSTOMER role users should only fetch their own record (enforced at app level).
    """
    customer = CustomerService.get_customer(db, customer_id)
    # Customers can only view their own profile
    if current_user.role == UserRole.CUSTOMER and current_user.customer_id != customer_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied")
    return customer


@router.put("/{customer_id}", response_model=CustomerResponse, summary="Update customer details")
def update_customer(
    customer_id: int,
    data: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.TELLER, UserRole.MANAGER, UserRole.ADMIN)),
):
    return CustomerService.update_customer(db, customer_id, data, performed_by_user_id=current_user.id)


@router.patch("/{customer_id}/kyc", response_model=CustomerResponse,
              summary="Update KYC status (Manager/Admin only)")
def update_kyc(
    customer_id: int,
    data: KYCUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MANAGER, UserRole.ADMIN)),
):
    """
    Approve or reject a customer's KYC.
    Only MANAGER or ADMIN can perform this action.
    Valid transitions: PENDING → VERIFIED | PENDING → REJECTED
    """
    return CustomerService.update_kyc_status(db, customer_id, data, performed_by_user_id=current_user.id)


@router.delete("/{customer_id}", summary="Delete a customer (Manager/Admin only)")
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.MANAGER, UserRole.ADMIN)),
):
    """
    Deletes a customer permanently. 
    Only MANAGER or ADMIN can perform this action.
    Will refuse to delete if the customer possesses active generated accounts or loans.
    """
    return CustomerService.delete_customer(db, customer_id, performed_by_user_id=current_user.id)
