"""Pydantic schemas for validation and serialization."""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator
from enum import Enum


class RoleEnum(str, Enum):
    organiser = "organiser"
    collaborator = "collaborator"
    member = "member"


class InvitationStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class PaymentMethod(str, Enum):
    cash = "Cash"
    upi = "UPI"
    bank_transfer = "Bank Transfer"
    other = "Other"


# ---------- Auth ----------
class UserRegister(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Pool ----------
class PoolCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    target_amount: Decimal = Field(..., gt=0)
    member_emails: Optional[List[str]] = []  # emails of initial members (must be registered)


class PoolUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    target_amount: Optional[Decimal] = Field(None, gt=0)


class PoolOut(BaseModel):
    id: int
    name: str
    target_amount: Decimal
    organiser_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Payment ----------
class PaymentCreate(BaseModel):
    paid_by_member_id: int
    amount: Decimal = Field(..., gt=0)
    payment_method: PaymentMethod
    note: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        return v.quantize(Decimal("0.01"))


class PaymentOut(BaseModel):
    id: int
    pool_id: int
    paid_by_member_id: int
    recorded_by_user_id: int
    amount: Decimal
    payment_method: PaymentMethod
    note: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Invitation ----------
class InvitationCreate(BaseModel):
    invited_email: EmailStr


class InvitationOut(BaseModel):
    id: int
    pool_id: int
    invited_email: str
    invited_by_user_id: int
    status: InvitationStatus
    created_at: datetime

    class Config:
        from_attributes = True
