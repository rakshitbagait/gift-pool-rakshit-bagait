"""SQLAlchemy models for GiftPool."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Numeric, Text, Enum as SAEnum
)
from sqlalchemy.orm import relationship
import enum

from .database import Base


class RoleEnum(str, enum.Enum):
    organiser = "organiser"
    collaborator = "collaborator"
    member = "member"


class InvitationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class PaymentMethod(str, enum.Enum):
    cash = "Cash"
    upi = "UPI"
    bank_transfer = "Bank Transfer"
    other = "Other"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    organised_pools = relationship("Pool", back_populates="organiser", foreign_keys="Pool.organiser_id")
    memberships = relationship("PoolMember", back_populates="user")
    recorded_payments = relationship("Payment", back_populates="recorded_by", foreign_keys="Payment.recorded_by_user_id")
    sent_invitations = relationship("Invitation", back_populates="invited_by", foreign_keys="Invitation.invited_by_user_id")


class Pool(Base):
    __tablename__ = "pools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    target_amount = Column(Numeric(12, 2), nullable=False)
    organiser_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    organiser = relationship("User", back_populates="organised_pools", foreign_keys=[organiser_id])
    members = relationship("PoolMember", back_populates="pool", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="pool", cascade="all, delete-orphan")
    invitations = relationship("Invitation", back_populates="pool", cascade="all, delete-orphan")


class PoolMember(Base):
    """Association between User and Pool with a role."""
    __tablename__ = "pool_members"

    id = Column(Integer, primary_key=True, index=True)
    pool_id = Column(Integer, ForeignKey("pools.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.member)
    joined_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    pool = relationship("Pool", back_populates="members")
    user = relationship("User", back_populates="memberships")
    payments = relationship("Payment", back_populates="paid_by_member", foreign_keys="Payment.paid_by_member_id")


class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(Integer, primary_key=True, index=True)
    pool_id = Column(Integer, ForeignKey("pools.id"), nullable=False)
    invited_email = Column(String(255), nullable=False, index=True)
    invited_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(SAEnum(InvitationStatus), default=InvitationStatus.pending, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    pool = relationship("Pool", back_populates="invitations")
    invited_by = relationship("User", back_populates="sent_invitations", foreign_keys=[invited_by_user_id])


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    pool_id = Column(Integer, ForeignKey("pools.id"), nullable=False)
    paid_by_member_id = Column(Integer, ForeignKey("pool_members.id"), nullable=False)
    recorded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    payment_method = Column(SAEnum(PaymentMethod), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    pool = relationship("Pool", back_populates="payments")
    paid_by_member = relationship("PoolMember", back_populates="payments", foreign_keys=[paid_by_member_id])
    recorded_by = relationship("User", back_populates="recorded_payments", foreign_keys=[recorded_by_user_id])
