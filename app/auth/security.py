"""Password hashing and user authentication helpers."""
from __future__ import annotations

from typing import Optional

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User

# pbkdf2_sha256 is pure-Python (hashlib) — no native bcrypt backend, which
# avoids the passlib/bcrypt-4.x detection bug and runs identically everywhere.
_pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(raw: str) -> str:
    return _pwd.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _pwd.verify(raw, hashed)
    except Exception:
        return False


def authenticate(db: Session, username: str, password: str) -> Optional[User]:
    user = db.execute(select(User).where(User.username == username)).scalars().first()
    if user and verify_password(password, user.password_hash):
        return user
    return None
