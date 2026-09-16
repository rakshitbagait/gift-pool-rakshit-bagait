"""CRUD operations for GiftPool."""
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from . import models, schemas
from .auth import hash_password, verify_password
from .models import RoleEnum, InvitationStatus, PaymentMethod


# ---------- Users ----------
def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.email == email.lower()).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.id == user_id).first()


def create_user(db: Session, name: str, email: str, password: str) -> models.User:
    user = models.User(
        name=name.strip(),
        email=email.lower().strip(),
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


# ---------- Pools ----------
def create_pool(
    db: Session,
    name: str,
    target_amount: Decimal,
    organiser: models.User,
    member_emails: Optional[List[str]] = None,
) -> models.Pool:
    """Create a pool and add the organiser as a PoolMember with role organiser.
    Optionally add other registered users as members.
    """
    pool = models.Pool(
        name=name.strip(),
        target_amount=target_amount,
        organiser_id=organiser.id,
    )
    db.add(pool)
    db.flush()  # get pool.id

    # Organiser membership
    organiser_member = models.PoolMember(
        pool_id=pool.id,
        user_id=organiser.id,
        role=RoleEnum.organiser,
    )
    db.add(organiser_member)

    # Initial members by email (skip organiser if listed)
    if member_emails:
        for email in member_emails:
            email = email.lower().strip()
            if not email or email == organiser.email:
                continue
            user = get_user_by_email(db, email)
            if user:
                existing = (
                    db.query(models.PoolMember)
                    .filter(
                        models.PoolMember.pool_id == pool.id,
                        models.PoolMember.user_id == user.id,
                    )
                    .first()
                )
                if not existing:
                    db.add(
                        models.PoolMember(
                            pool_id=pool.id,
                            user_id=user.id,
                            role=RoleEnum.member,
                        )
                    )

    db.commit()
    db.refresh(pool)
    return pool


def get_pool(db: Session, pool_id: int) -> Optional[models.Pool]:
    return db.query(models.Pool).filter(models.Pool.id == pool_id).first()


def get_user_pools(db: Session, user_id: int) -> List[models.Pool]:
    """Return all pools the user is a member of."""
    return (
        db.query(models.Pool)
        .join(models.PoolMember)
        .filter(models.PoolMember.user_id == user_id)
        .order_by(models.Pool.created_at.desc())
        .all()
    )


def update_pool(
    db: Session, pool: models.Pool, name: Optional[str] = None, target_amount: Optional[Decimal] = None
) -> models.Pool:
    if name is not None:
        pool.name = name.strip()
    if target_amount is not None:
        pool.target_amount = target_amount
    db.commit()
    db.refresh(pool)
    return pool


def delete_pool(db: Session, pool: models.Pool) -> None:
    db.delete(pool)
    db.commit()


# ---------- Pool Members ----------
def get_pool_member(db: Session, pool_id: int, user_id: int) -> Optional[models.PoolMember]:
    return (
        db.query(models.PoolMember)
        .filter(models.PoolMember.pool_id == pool_id, models.PoolMember.user_id == user_id)
        .first()
    )


def get_pool_members(db: Session, pool_id: int) -> List[models.PoolMember]:
    return (
        db.query(models.PoolMember)
        .filter(models.PoolMember.pool_id == pool_id)
        .order_by(models.PoolMember.joined_at)
        .all()
    )


def add_member(
    db: Session, pool_id: int, user_id: int, role: RoleEnum = RoleEnum.member
) -> models.PoolMember:
    member = models.PoolMember(pool_id=pool_id, user_id=user_id, role=role)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def remove_member(db: Session, member: models.PoolMember) -> None:
    db.delete(member)
    db.commit()


def update_member_role(db: Session, member: models.PoolMember, role: RoleEnum) -> models.PoolMember:
    member.role = role
    db.commit()
    db.refresh(member)
    return member


# ---------- Payments ----------
def create_payment(
    db: Session,
    pool_id: int,
    paid_by_member_id: int,
    recorded_by_user_id: int,
    amount: Decimal,
    payment_method: PaymentMethod,
    note: Optional[str] = None,
) -> models.Payment:
    payment = models.Payment(
        pool_id=pool_id,
        paid_by_member_id=paid_by_member_id,
        recorded_by_user_id=recorded_by_user_id,
        amount=amount.quantize(Decimal("0.01")),
        payment_method=payment_method,
        note=note.strip() if note else None,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def get_pool_payments(db: Session, pool_id: int) -> List[models.Payment]:
    return (
        db.query(models.Payment)
        .filter(models.Payment.pool_id == pool_id)
        .order_by(models.Payment.created_at.desc())
        .all()
    )


def get_member_total_paid(db: Session, member_id: int) -> Decimal:
    result = (
        db.query(func.coalesce(func.sum(models.Payment.amount), 0))
        .filter(models.Payment.paid_by_member_id == member_id)
        .scalar()
    )
    return Decimal(str(result)).quantize(Decimal("0.01"))


def get_pool_total_collected(db: Session, pool_id: int) -> Decimal:
    result = (
        db.query(func.coalesce(func.sum(models.Payment.amount), 0))
        .filter(models.Payment.pool_id == pool_id)
        .scalar()
    )
    return Decimal(str(result)).quantize(Decimal("0.01"))


# ---------- Invitations ----------
def create_invitation(
    db: Session, pool_id: int, invited_email: str, invited_by_user_id: int
) -> models.Invitation:
    inv = models.Invitation(
        pool_id=pool_id,
        invited_email=invited_email.lower().strip(),
        invited_by_user_id=invited_by_user_id,
        status=InvitationStatus.pending,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def get_pending_invitations_for_email(db: Session, email: str) -> List[models.Invitation]:
    return (
        db.query(models.Invitation)
        .filter(
            models.Invitation.invited_email == email.lower(),
            models.Invitation.status == InvitationStatus.pending,
        )
        .order_by(models.Invitation.created_at.desc())
        .all()
    )


def get_pool_invitations(db: Session, pool_id: int) -> List[models.Invitation]:
    return (
        db.query(models.Invitation)
        .filter(models.Invitation.pool_id == pool_id)
        .order_by(models.Invitation.created_at.desc())
        .all()
    )


def get_invitation(db: Session, invitation_id: int) -> Optional[models.Invitation]:
    return db.query(models.Invitation).filter(models.Invitation.id == invitation_id).first()


def update_invitation_status(
    db: Session, invitation: models.Invitation, status: InvitationStatus
) -> models.Invitation:
    invitation.status = status
    db.commit()
    db.refresh(invitation)
    return invitation
