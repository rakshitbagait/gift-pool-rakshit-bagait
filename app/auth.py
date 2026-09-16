"""Authentication utilities: password hashing and session management."""
import os
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request, HTTPException, status

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Session secret - use env var in production; fallback for development only
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production-giftpool-2024")
SESSION_COOKIE_NAME = "giftpool_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

serializer = URLSafeTimedSerializer(SECRET_KEY)


def hash_password(password: str) -> str:
    """Hash a plain-text password."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against a hash."""
    return pwd_context.verify(plain, hashed)


def create_session_token(user_id: int) -> str:
    """Create a signed session token containing the user id."""
    return serializer.dumps({"user_id": user_id})


def get_user_id_from_token(token: str) -> int | None:
    """Extract user_id from a session token. Returns None if invalid/expired."""
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE)
        return data.get("user_id")
    except (BadSignature, SignatureExpired):
        return None


def set_session_cookie(response, user_id: int) -> None:
    """Set the session cookie on a response."""
    token = create_session_token(user_id)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=SESSION_MAX_AGE,
        samesite="lax",
        # secure=True  # enable in production with HTTPS
    )


def clear_session_cookie(response) -> None:
    """Clear the session cookie."""
    response.delete_cookie(SESSION_COOKIE_NAME)
