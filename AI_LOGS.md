@app.post("/pools/{pool_id}/invite")
async def send_invitation(
    request: Request,
    pool_id: int,
    invited_email: str = Form(...),
    user: models.User = Depends(get_current_user),
    membership: models.PoolMember = Depends(require_organiser),
    db: Session = Depends(get_db),
):
    email = invited_email.strip().lower()

    if not email:
        return redirect_with_flash(
            f"/pools/{pool_id}",
            "Email is required.",
            "error",
        )

    # Check whether the user is already a pool member
    target_user = crud.get_user_by_email(db, email)

    if target_user:
        existing_member = crud.get_pool_member(
            db,
            pool_id,
            target_user.id,
        )

        if existing_member:
            return redirect_with_flash(
                f"/pools/{pool_id}",
                "User is already a member of this pool.",
                "error",
            )

    # Check for an existing pending invitation
    existing_invitations = crud.get_pool_invitations(db, pool_id)

    for inv in existing_invitations:
        if (
            inv.invited_email.strip().lower() == email
            and inv.status == InvitationStatus.pending
        ):
            return redirect_with_flash(
                f"/pools/{pool_id}",
                "A pending invitation already exists for this email.",
                "error",
            )

    # Create invitation in the database
    invitation = crud.create_invitation(
        db=db,
        pool_id=pool_id,
        invited_email=email,
        invited_by=user.id,
    )

    pool = crud.get_pool(db, pool_id)

    # Send email
    try:
        send_invitation_email(
            invitation=invitation,
            pool_name=pool.name if pool else "GiftPool",
            inviter_name=user.name,
            request=request,
        )

        return redirect_with_flash(
            f"/pools/{pool_id}",
            f"Invitation email sent to {email}.",
            "success",
        )

    except Exception as exc:
        print("INVITATION EMAIL ERROR:", repr(exc))

        return redirect_with_flash(
            f"/pools/{pool_id}",
            f"Invitation was created, but email failed: {str(exc)}",
            "error",
        )