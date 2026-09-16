"""Tests for pools, invitations, payments, and access control."""
from decimal import Decimal
from fastapi.testclient import TestClient
from app.main import app
from app import crud
from tests.conftest import TestingSessionLocal

client = TestClient(app)


def register_and_login(name: str, email: str, password: str = "secret12"):
    client.post("/register", data={"name": name, "email": email, "password": password})
    client.post("/login", data={"email": email, "password": password})


def test_create_pool():
    register_and_login("Org", "org@example.com")
    r = client.post(
        "/pools/create",
        data={"name": "Test Gift", "target_amount": "1000", "member_emails": ""},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "/pools/" in r.headers.get("location", "")


def test_pool_membership_restriction():
    register_and_login("Org", "org@example.com")
    r = client.post(
        "/pools/create",
        data={"name": "Private Pool", "target_amount": "500", "member_emails": ""},
        follow_redirects=False,
    )
    loc = r.headers.get("location", "")
    pool_id = loc.split("/pools/")[-1].split("?")[0]

    client.get("/logout")
    register_and_login("Other", "other@example.com")
    r2 = client.get(f"/pools/{pool_id}")
    assert r2.status_code == 403


def test_invitation_accept():
    register_and_login("Org", "org@example.com")
    r = client.post(
        "/pools/create",
        data={"name": "Invite Pool", "target_amount": "800", "member_emails": ""},
        follow_redirects=False,
    )
    pool_id = r.headers.get("location", "").split("/pools/")[-1].split("?")[0]

    client.get("/logout")
    register_and_login("Member", "member@example.com")
    client.get("/logout")

    register_and_login("Org", "org@example.com")
    r_inv = client.post(
        f"/pools/{pool_id}/invite",
        data={"invited_email": "member@example.com"},
        follow_redirects=False,
    )
    assert r_inv.status_code == 303

    client.get("/logout")
    register_and_login("Member", "member@example.com")
    db = TestingSessionLocal()
    invs = crud.get_pending_invitations_for_email(db, "member@example.com")
    assert len(invs) == 1
    inv_id = invs[0].id
    db.close()

    r_acc = client.post(f"/invitations/{inv_id}/accept", follow_redirects=False)
    assert r_acc.status_code == 303
    r_pool = client.get(f"/pools/{pool_id}")
    assert r_pool.status_code == 200


def test_payment_creation_and_multiple():
    register_and_login("Org", "org@example.com")
    r = client.post(
        "/pools/create",
        data={"name": "Pay Pool", "target_amount": "1000", "member_emails": ""},
        follow_redirects=False,
    )
    pool_id = r.headers.get("location", "").split("/pools/")[-1].split("?")[0]

    db = TestingSessionLocal()
    members = crud.get_pool_members(db, int(pool_id))
    member_id = members[0].id
    db.close()

    r1 = client.post(
        f"/pools/{pool_id}/payments/add",
        data={
            "paid_by_member_id": str(member_id),
            "amount": "300",
            "payment_method": "Cash",
            "note": "Partial",
        },
        follow_redirects=False,
    )
    assert r1.status_code == 303

    r2 = client.post(
        f"/pools/{pool_id}/payments/add",
        data={
            "paid_by_member_id": str(member_id),
            "amount": "800",
            "payment_method": "UPI",
            "note": "Extra",
        },
        follow_redirects=False,
    )
    assert r2.status_code == 303

    db = TestingSessionLocal()
    total = crud.get_member_total_paid(db, member_id)
    db.close()
    assert total == Decimal("1100.00")


def test_invalid_payment_amount():
    register_and_login("Org", "org@example.com")
    r = client.post(
        "/pools/create",
        data={"name": "Amt Pool", "target_amount": "500", "member_emails": ""},
        follow_redirects=False,
    )
    pool_id = r.headers.get("location", "").split("/pools/")[-1].split("?")[0]
    db = TestingSessionLocal()
    member_id = crud.get_pool_members(db, int(pool_id))[0].id
    db.close()

    r_bad = client.post(
        f"/pools/{pool_id}/payments/add",
        data={
            "paid_by_member_id": str(member_id),
            "amount": "-10",
            "payment_method": "Cash",
            "note": "",
        },
    )
    assert r_bad.status_code == 400
    assert b"positive" in r_bad.content.lower() or b"Amount" in r_bad.content
