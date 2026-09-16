"""FastAPI dependencies for authentication and authorization."""
from fastapi import Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from typing import Optional

from .database import get_db
from .models import User, Pool, PoolMember, RoleEnum
from .auth import get_user_id_from_token, SESSION_COOKIE_NAME


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Require an authenticated user. Raises 401 if not logged in."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    user_id = get_user_id_from_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Return the current user if logged in, otherwise None."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    user_id = get_user_id_from_token(token)
    if user_id is None:
        return None
    return db.query(User).filter(User.id == user_id).first()


def get_pool_membership(
    pool_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PoolMember:
    """Ensure the current user is a member of the pool. Raises 403/404 otherwise."""
    pool = db.query(Pool).filter(Pool.id == pool_id).first()
    if not pool:
        raise HTTPException(status_code=404, detail="Pool not found")
    membership = (
        db.query(PoolMember)
        .filter(PoolMember.pool_id == pool_id, PoolMember.user_id == user.id)
        .first()
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this pool",
        )
    return membership


def require_organiser(
    membership: PoolMember = Depends(get_pool_membership),
) -> PoolMember:
    """Require the user to be the organiser of the pool."""
    if membership.role != RoleEnum.organiser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the organiser can perform this action",
        )
    return membership


def require_organiser_or_collaborator(
    membership: PoolMember = Depends(get_pool_membership),
) -> PoolMember:
    """Require organiser or collaborator role."""
    if membership.role not in (RoleEnum.organiser, RoleEnum.collaborator):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organisers and collaborators can perform this action",
        )
    return membership
