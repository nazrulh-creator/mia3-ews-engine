"""Request-scoped auth dependencies and role guards.

Roles:
  internal — sees everything and can change governed settings.
  branch   — sees the action worklist across FIs (no tuning).
  fi       — sees ONLY its own book (row-level scope by fi_id).
  viewer   — sees the whole app read-only; cannot change anything (demo account).
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User

ROLE_LABELS = {"internal": "Internal Risk", "branch": "Branch",
               "fi": "Financial Institution", "viewer": "Viewer (read-only)"}

# Roles allowed to VIEW the internal/governance screens (read-only for viewer).
STAFF_VIEW_ROLES = ("internal", "viewer")


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
    """For MUTATIONS — only Internal Risk may change governed settings."""
    if user.role != "internal":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Internal Risk role required.")
    return user


def require_staff_view(user: User = Depends(require_user)) -> User:
    """For READ-ONLY access to internal/governance screens (internal + viewer)."""
    if user.role not in STAFF_VIEW_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Internal Risk or Viewer role required.")
    return user


def require_writer(user: User = Depends(require_user)) -> User:
    """For operational writes (review, outcomes, learnings) — blocks the
    read-only viewer while allowing internal/branch/fi."""
    if user.role == "viewer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Read-only account: this action is not available.")
    return user


def fi_scope(user: User) -> Optional[str]:
    """Return the fi_id a user is restricted to, or None for see-all roles."""
    return user.fi_id if user.role == "fi" else None
