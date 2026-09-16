"""GiftPool - Collaborative shared-expense FastAPI application."""
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Depends, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .database import engine, Base, get_db
from . import models, crud, schemas
from .auth import set_session_cookie, clear_session_cookie
from .dependencies import (
    get_current_user,
    get_optional_user,
    get_pool_membership,
    require_organiser,
    require_organiser_or_collaborator,
)
from .models import RoleEnum, InvitationStatus, PaymentMethod
from .services.settlement import (
    compute_fair_share,
    compute_balances,
    greedy_settlement,
)
from .services.invitations import accept_invitation, reject_invitation

# Create tables (skip errors in test environments that override the engine)
try:
    Base.metadata.create_all(bind=engine)
except Exception:
    pass

app = FastAPI(title="GiftPool", description="Collaborative shared-expense gift pool")

# Paths
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
class CompatibleTemplates(Jinja2Templates):
    """Support both legacy and modern TemplateResponse call signatures."""

    def TemplateResponse(self, *args, **kwargs):
        # Legacy form:
        # TemplateResponse("page.html", {"request": request, ...}, status_code=...)
        if args and isinstance(args[0], str):
            name = args[0]
            context = dict(args[1]) if len(args) > 1 else dict(kwargs.pop("context", {}))
            request = context.pop("request", None)

            if request is None:
                request = kwargs.pop("request", None)

            return super().TemplateResponse(
                request=request,
                name=name,
                context=context,
                **kwargs,
            )

        # Modern form:
        # TemplateResponse(request=request, name="page.html", context={...})
        return super().TemplateResponse(*args, **kwargs)


templates = CompatibleTemplates(directory=str(BASE_DIR / "templates"))


# ---------- Helpers ----------
def flash(request: Request, message: str, category: str = "info") -> None:
    """Store a flash message in the session (simple in-memory via request.state)."""
    if not hasattr(request.state, "flash"):
        request.state.flash = []
    request.state.flash.append({"message": message, "category": category})


def get_flashes(request: Request) -> list:
    return getattr(request.state, "flash", [])


def redirect_with_flash(url: str, message: str, category: str = "info") -> RedirectResponse:
    """Redirect and encode flash in query for simplicity (no server-side session store)."""
    from urllib.parse import quote
    sep = "&" if "?" in url else "?"
    return RedirectResponse(
        url=f"{url}{sep}flash={quote(message)}&cat={category}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def parse_flash(request: Request) -> list:
    """Parse flash from query params."""
    msg = request.query_params.get("flash")
    cat = request.query_params.get("cat", "info")
    if msg:
        return [{"message": msg, "category": cat}]
    return []


# ---------- Auth routes ----------
@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user=Depends(get_optional_user)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return RedirectResponse("/login", status_code=303)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, user=Depends(get_optional_user)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={
            "user": None,
            "flashes": parse_flash(request),
            "error": None,
        },
    )


@app.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    name = name.strip()
    email = email.strip().lower()
    if not name or not email or not password:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "user": None,
                "flashes": [],
                "error": "All fields are required.",
            },
            status_code=400,
        )
    if len(password) < 6:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "user": None,
                "flashes": [],
                "error": "Password must be at least 6 characters.",
            },
            status_code=400,
        )
    if crud.get_user_by_email(db, email):
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "user": None,
                "flashes": [],
                "error": "An account with this email already exists.",
            },
            status_code=400,
        )
    try:
        user = crud.create_user(db, name, email, password)
    except Exception:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "user": None,
                "flashes": [],
                "error": "Registration failed. Please try again.",
            },
            status_code=500,
        )
    response = RedirectResponse("/dashboard", status_code=303)
    set_session_cookie(response, user.id)
    return response


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user=Depends(get_optional_user)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
    request=request,
    name="login.html",
    context={
        "user": None,
        "flashes": parse_flash(request),
        "error": None,
    },
)

@app.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = crud.authenticate_user(db, email.strip().lower(), password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "user": None,
                "flashes": [],
                "error": "Invalid email or password.",
            },
            status_code=401,
        )
    response = RedirectResponse("/dashboard", status_code=303)
    set_session_cookie(response, user.id)
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    clear_session_cookie(response)
    return response


# ---------- Dashboard ----------
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pools = crud.get_user_pools(db, user.id)
    invitations = crud.get_pending_invitations_for_email(db, user.email)
    # Enrich pools with role and totals
    pool_data = []
    for p in pools:
        membership = crud.get_pool_member(db, p.id, user.id)
        total = crud.get_pool_total_collected(db, p.id)
        pool_data.append(
            {
                "pool": p,
                "role": membership.role.value if membership else "member",
                "total_collected": total,
                "remaining": p.target_amount - total,
            }
        )
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "pools": pool_data,
            "invitations": invitations,
            "flashes": parse_flash(request),
        },
    )


# ---------- Create Pool ----------
@app.get("/pools/create", response_class=HTMLResponse)
async def create_pool_page(
    request: Request,
    user: models.User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        "create_pool.html",
        {"request": request, "user": user, "flashes": parse_flash(request), "error": None},
    )


@app.post("/pools/create", response_class=HTMLResponse)
async def create_pool(
    request: Request,
    name: str = Form(...),
    target_amount: str = Form(...),
    member_emails: str = Form(""),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = name.strip()
    if not name:
        return templates.TemplateResponse(
            "create_pool.html",
            {
                "request": request,
                "user": user,
                "flashes": [],
                "error": "Pool name is required.",
            },
            status_code=400,
        )
    try:
        amount = Decimal(target_amount).quantize(Decimal("0.01"))
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        return templates.TemplateResponse(
            "create_pool.html",
            {
                "request": request,
                "user": user,
                "flashes": [],
                "error": "Target amount must be a positive number.",
            },
            status_code=400,
        )
    emails = [e.strip() for e in member_emails.split(",") if e.strip()] if member_emails else []
    pool = crud.create_pool(db, name, amount, user, emails)
    return redirect_with_flash(f"/pools/{pool.id}", "Pool created successfully!", "success")


# ---------- Pool Detail / Dashboard ----------
@app.get("/pools/{pool_id}", response_class=HTMLResponse)
async def pool_detail(
    request: Request,
    pool_id: int,
    user: models.User = Depends(get_current_user),
    membership: models.PoolMember = Depends(get_pool_membership),
    db: Session = Depends(get_db),
):
    pool = crud.get_pool(db, pool_id)
    members = crud.get_pool_members(db, pool_id)
    payments = crud.get_pool_payments(db, pool_id)
    total_collected = crud.get_pool_total_collected(db, pool_id)
    num_members = len(members)
    fair_share = compute_fair_share(pool.target_amount, num_members)
    remaining = pool.target_amount - total_collected
    progress = float((total_collected / pool.target_amount * 100) if pool.target_amount else 0)
    progress = min(100.0, max(0.0, progress))

    # Build member balance info
    member_info = []
    for m in members:
        total_paid = crud.get_member_total_paid(db, m.id)
        member_info.append(
            {
                "id": m.id,
                "user_id": m.user_id,
                "name": m.user.name,
                "email": m.user.email,
                "role": m.role.value,
                "total_paid": total_paid,
            }
        )
    balances = compute_balances(member_info, fair_share)
    settlements = greedy_settlement(balances)

    # Enrich payments with names
    payment_list = []
    for p in payments:
        paid_by = next((m for m in members if m.id == p.paid_by_member_id), None)
        recorded_by = crud.get_user_by_id(db, p.recorded_by_user_id)
        payment_list.append(
            {
                "payment": p,
                "paid_by_name": paid_by.user.name if paid_by else "Unknown",
                "recorded_by_name": recorded_by.name if recorded_by else "Unknown",
            }
        )

    can_manage = membership.role == RoleEnum.organiser
    can_add_payment = membership.role in (RoleEnum.organiser, RoleEnum.collaborator)

    return templates.TemplateResponse(
        "pool_detail.html",
        {
            "request": request,
            "user": user,
            "pool": pool,
            "membership": membership,
            "members": balances,
            "payments": payment_list,
            "total_collected": total_collected,
            "remaining": remaining,
            "fair_share": fair_share,
            "progress": progress,
            "num_members": num_members,
            "settlements": settlements,
            "can_manage": can_manage,
            "can_add_payment": can_add_payment,
            "flashes": parse_flash(request),
        },
    )


# ---------- Add Payment ----------
@app.get("/pools/{pool_id}/payments/add", response_class=HTMLResponse)
async def add_payment_page(
    request: Request,
    pool_id: int,
    user: models.User = Depends(get_current_user),
    membership: models.PoolMember = Depends(require_organiser_or_collaborator),
    db: Session = Depends(get_db),
):
    pool = crud.get_pool(db, pool_id)
    members = crud.get_pool_members(db, pool_id)
    return templates.TemplateResponse(
        "add_payment.html",
        {
            "request": request,
            "user": user,
            "pool": pool,
            "members": members,
            "methods": [m.value for m in PaymentMethod],
            "flashes": parse_flash(request),
            "error": None,
        },
    )


@app.post("/pools/{pool_id}/payments/add", response_class=HTMLResponse)
async def add_payment(
    request: Request,
    pool_id: int,
    paid_by_member_id: int = Form(...),
    amount: str = Form(...),
    payment_method: str = Form(...),
    note: str = Form(""),
    user: models.User = Depends(get_current_user),
    membership: models.PoolMember = Depends(require_organiser_or_collaborator),
    db: Session = Depends(get_db),
):
    pool = crud.get_pool(db, pool_id)
    members = crud.get_pool_members(db, pool_id)

    # Validate member belongs to pool
    member = next((m for m in members if m.id == paid_by_member_id), None)
    if not member:
        return templates.TemplateResponse(
            "add_payment.html",
            {
                "request": request,
                "user": user,
                "pool": pool,
                "members": members,
                "methods": [m.value for m in PaymentMethod],
                "flashes": [],
                "error": "Invalid member selected.",
            },
            status_code=400,
        )

    try:
        amt = Decimal(amount).quantize(Decimal("0.01"))
        if amt <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        return templates.TemplateResponse(
            "add_payment.html",
            {
                "request": request,
                "user": user,
                "pool": pool,
                "members": members,
                "methods": [m.value for m in PaymentMethod],
                "flashes": [],
                "error": "Amount must be a positive number.",
            },
            status_code=400,
        )

    # Map method string to enum
    method_map = {m.value: m for m in PaymentMethod}
    method = method_map.get(payment_method)
    if not method:
        return templates.TemplateResponse(
            "add_payment.html",
            {
                "request": request,
                "user": user,
                "pool": pool,
                "members": members,
                "methods": [m.value for m in PaymentMethod],
                "flashes": [],
                "error": "Invalid payment method.",
            },
            status_code=400,
        )

    crud.create_payment(
        db,
        pool_id=pool_id,
        paid_by_member_id=paid_by_member_id,
        recorded_by_user_id=user.id,
        amount=amt,
        payment_method=method,
        note=note or None,
    )
    return redirect_with_flash(f"/pools/{pool_id}", "Payment recorded successfully!", "success")


# ---------- Invitations ----------
@app.get("/invitations", response_class=HTMLResponse)
async def invitations_page(
    request: Request,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pending = crud.get_pending_invitations_for_email(db, user.email)
    # Enrich with pool name
    inv_data = []
    for inv in pending:
        pool = crud.get_pool(db, inv.pool_id)
        inv_data.append({"invitation": inv, "pool_name": pool.name if pool else "Unknown"})
    return templates.TemplateResponse(
        "invitations.html",
        {
            "request": request,
            "user": user,
            "invitations": inv_data,
            "flashes": parse_flash(request),
        },
    )


@app.post("/pools/{pool_id}/invite")
async def send_invitation(
    pool_id: int,
    invited_email: str = Form(...),
    user: models.User = Depends(get_current_user),
    membership: models.PoolMember = Depends(require_organiser),
    db: Session = Depends(get_db),
):
    email = invited_email.strip().lower()
    if not email:
        return redirect_with_flash(f"/pools/{pool_id}", "Email is required.", "error")

    # Check if already a member
    target_user = crud.get_user_by_email(db, email)
    if target_user:
        existing = crud.get_pool_member(db, pool_id, target_user.id)
        if existing:
            return redirect_with_flash(
                f"/pools/{pool_id}", "User is already a member of this pool.", "error"
            )

    # Check for existing pending invitation
    existing_invs = crud.get_pool_invitations(db, pool_id)
    for inv in existing_invs:
        if inv.invited_email == email and inv.status == InvitationStatus.pending:
            return redirect_with_flash(
                f"/pools/{pool_id}", "A pending invitation already exists for this email.", "error"
            )

    crud.create_invitation(db, pool_id, email, user.id)
    return redirect_with_flash(f"/pools/{pool_id}", f"Invitation sent to {email}.", "success")


@app.post("/invitations/{invitation_id}/accept")
async def accept_inv(
    invitation_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inv = crud.get_invitation(db, invitation_id)
    if not inv:
        return redirect_with_flash("/invitations", "Invitation not found.", "error")
    result = accept_invitation(db, inv, user)
    if result is None and inv.status != InvitationStatus.accepted:
        return redirect_with_flash("/invitations", "Could not accept invitation.", "error")
    return redirect_with_flash(
        f"/pools/{inv.pool_id}", "Invitation accepted! You are now a member.", "success"
    )


@app.post("/invitations/{invitation_id}/reject")
async def reject_inv(
    invitation_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inv = crud.get_invitation(db, invitation_id)
    if not inv:
        return redirect_with_flash("/invitations", "Invitation not found.", "error")
    if not reject_invitation(db, inv, user):
        return redirect_with_flash("/invitations", "Could not reject invitation.", "error")
    return redirect_with_flash("/invitations", "Invitation rejected.", "info")


# ---------- Member management (organiser only) ----------
@app.post("/pools/{pool_id}/members/add")
async def add_member_by_email(
    pool_id: int,
    email: str = Form(...),
    role: str = Form("member"),
    user: models.User = Depends(get_current_user),
    membership: models.PoolMember = Depends(require_organiser),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    target = crud.get_user_by_email(db, email)
    if not target:
        return redirect_with_flash(
            f"/pools/{pool_id}", "No registered user found with that email.", "error"
        )
    existing = crud.get_pool_member(db, pool_id, target.id)
    if existing:
        return redirect_with_flash(f"/pools/{pool_id}", "User is already a member.", "error")
    role_map = {"member": RoleEnum.member, "collaborator": RoleEnum.collaborator}
    r = role_map.get(role, RoleEnum.member)
    crud.add_member(db, pool_id, target.id, r)
    return redirect_with_flash(f"/pools/{pool_id}", f"{target.name} added as {r.value}.", "success")


@app.post("/pools/{pool_id}/members/{member_id}/remove")
async def remove_member(
    pool_id: int,
    member_id: int,
    user: models.User = Depends(get_current_user),
    membership: models.PoolMember = Depends(require_organiser),
    db: Session = Depends(get_db),
):
    members = crud.get_pool_members(db, pool_id)
    target = next((m for m in members if m.id == member_id), None)
    if not target:
        return redirect_with_flash(f"/pools/{pool_id}", "Member not found.", "error")
    if target.role == RoleEnum.organiser:
        return redirect_with_flash(
            f"/pools/{pool_id}", "Cannot remove the organiser.", "error"
        )
    crud.remove_member(db, target)
    return redirect_with_flash(f"/pools/{pool_id}", "Member removed.", "success")


@app.post("/pools/{pool_id}/delete")
async def delete_pool(
    pool_id: int,
    user: models.User = Depends(get_current_user),
    membership: models.PoolMember = Depends(require_organiser),
    db: Session = Depends(get_db),
):
    pool = crud.get_pool(db, pool_id)
    if pool:
        crud.delete_pool(db, pool)
    return redirect_with_flash("/dashboard", "Pool deleted.", "info")


# ---------- Health / root API ----------
@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "GiftPool"}