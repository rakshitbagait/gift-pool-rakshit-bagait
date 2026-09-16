"""Invitation-related business logic."""
from sqlalchemy.orm import Session
from typing import Optional

from .. import crud, models
from ..models import InvitationStatus, RoleEnum


def accept_invitation(
    db: Session, invitation: models.Invitation, user: models.User
) -> Optional[models.PoolMember]:
    """
    Accept a pending invitation for the given user.
    - Verifies the invitation email matches the user's email.
    - Adds the user as a member of the pool (if not already).
    - Marks the invitation as accepted.
    Returns the PoolMember or None if already a member.
    """
    if invitation.status != InvitationStatus.pending:
        return None
    if invitation.invited_email.lower() != user.email.lower():
        return None

    # Already a member?
    existing = crud.get_pool_member(db, invitation.pool_id, user.id)
    if existing:
        crud.update_invitation_status(db, invitation, InvitationStatus.accepted)
        return existing

    member = crud.add_member(db, invitation.pool_id, user.id, RoleEnum.member)
    crud.update_invitation_status(db, invitation, InvitationStatus.accepted)
    return member


def reject_invitation(db: Session, invitation: models.Invitation, user: models.User) -> bool:
    """Reject a pending invitation. Returns True on success."""
    if invitation.status != InvitationStatus.pending:
        return False
    if invitation.invited_email.lower() != user.email.lower():
        return False
    crud.update_invitation_status(db, invitation, InvitationStatus.rejected)
    return True
