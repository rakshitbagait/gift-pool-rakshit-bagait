"""Tests for authentication."""
from fastapi.testclient import TestClient
from app.main import app


def test_register_success():
    client = TestClient(app)
    r = client.post(
        "/register",
        data={"name": "Alice", "email": "alice@example.com", "password": "secret12"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "/dashboard" in r.headers.get("location", "")


def test_register_duplicate_email():
    client = TestClient(app)
    client.post(
        "/register",
        data={"name": "Alice", "email": "alice@example.com", "password": "secret12"},
    )
    r = client.post(
        "/register",
        data={"name": "Alice2", "email": "alice@example.com", "password": "otherpass"},
    )
    assert r.status_code == 400
    assert b"already exists" in r.content


def test_login_success():
    client = TestClient(app)
    client.post(
        "/register",
        data={"name": "Bob", "email": "bob@example.com", "password": "secret12"},
    )
    r = client.post(
        "/login",
        data={"email": "bob@example.com", "password": "secret12"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "giftpool_session" in r.cookies


def test_login_invalid():
    client = TestClient(app)
    r = client.post(
        "/login",
        data={"email": "nobody@example.com", "password": "wrong"},
    )
    assert r.status_code == 401
    assert b"Invalid" in r.content


def test_protected_route_requires_auth():
    client = TestClient(app)
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 401
