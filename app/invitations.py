"""Invitation handling and email delivery."""

import os
import smtplib
from email.message import EmailMessage

from fastapi import Request
from sqlalchemy.orm import Session

from .. import crud, models
from ..models import InvitationStatus


def accept_invitation(
    db: Session,
    invitation: models.Invitation,
    user: models.User,
):
    """Accept an invitation for the invited email address."""

    if invitation.status != InvitationStatus.pending:
        return None

    if invitation.invited_email.lower() != user.email.lower():
        return None

    existing_member = crud.get_pool_member(
        db,
        invitation.pool_id,
        user.id,
    )

    if existing_member:
        invitation.status = InvitationStatus.accepted
        db.commit()
        return existing_member

    member = crud.add_member(
        db,
        invitation.pool_id,
        user.id,
    )

    invitation.status = InvitationStatus.accepted
    db.commit()
    db.refresh(invitation)

    return member


def reject_invitation(
    db: Session,
    invitation: models.Invitation,
    user: models.User,
) -> bool:
    """Reject an invitation for the invited email address."""

    if invitation.status != InvitationStatus.pending:
        return False

    if invitation.invited_email.lower() != user.email.lower():
        return False

    invitation.status = InvitationStatus.rejected
    db.commit()

    return True


def send_invitation_email(
    invitation: models.Invitation,
    pool_name: str,
    inviter_name: str,
    request: Request,
) -> None:
    """Send a GiftPool invitation email using SMTP."""

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from_email = os.getenv("SMTP_FROM_EMAIL") or smtp_username
    smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    if not all(
        [
            smtp_host,
            smtp_username,
            smtp_password,
            smtp_from_email,
        ]
    ):
        raise RuntimeError(
            "SMTP configuration is missing. Check your .env file."
        )

    base_url = os.getenv("APP_BASE_URL")

    if not base_url:
        base_url = (
            f"{request.url.scheme}://"
            f"{request.headers.get('host')}"
        )

    invitation_url = (
        f"{base_url.rstrip('/')}"
        f"/invitations/{invitation.id}/accept"
    )

    message = EmailMessage()
    message["Subject"] = (
        f"Invitation to join GiftPool: {pool_name}"
    )
    message["From"] = smtp_from_email
    message["To"] = invitation.invited_email

    message.set_content(
        f"""Hello,

{inviter_name} has invited you to join the GiftPool group
"{pool_name}".

Accept your invitation using this link:

{invitation_url}

Please log in using the email address that received this invitation.

Regards,
GiftPool
"""
    )

    with smtplib.SMTP(
        smtp_host,
        smtp_port,
        timeout=30,
    ) as server:
        if smtp_use_tls:
            server.starttls()

        server.login(
            smtp_username,
            smtp_password,
        )

        server.send_message(message)