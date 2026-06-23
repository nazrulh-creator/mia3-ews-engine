"""Request-scoped auth dependencies and role guards.

Three roles:
  internal — sees everything and can tune governed settings.
  branch   — sees the action worklist across FIs (no tuning).
  fi       — sees ONLY its own book (row-level scope by fi_id).
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User

ROLE_LABELS = {"internal": "Internal Risk", "branch": "Branch", "fi": "Financial Institution"}


def current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = current_user(request, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Login required.",
                            headers={"Location": "/login"})
    return user


def require_internal(user: User = Depends(require_user)) -> User:
    if user.role != "internal":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Internal Risk role required.")
    return user


def fi_scope(user: User) -> Optional[str]:
    """Return the fi_id a user is restricted to, or None for see-all roles."""
    return user.fi_id if user.role == "fi" else None
