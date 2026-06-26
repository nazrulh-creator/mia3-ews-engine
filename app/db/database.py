"""Database engine and session management (SQLAlchemy 2.0).

Local default is sqlite (zero install); production uses PostgreSQL via
MIA3_DATABASE_URL. The LIVE and TEST environments use SEPARATE databases
(distinct URLs), so test data can never reach LIVE.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


# Columns added after an environment's DB was first created. Kept tiny and
# additive — create_all never adds columns to an existing table, so we ALTER.
_ADDITIVE_COLUMNS = {
    "model_registry": [("registered_by", "VARCHAR(64)"),
                       ("segment", "VARCHAR(16) DEFAULT 'Guarantee'"),
                       ("model_type", "VARCHAR(24) DEFAULT 'synthetic'"),
                       ("spec", "JSON")],
    "account_scores": [("segment", "VARCHAR(16) DEFAULT 'Guarantee'"),
                       ("model_version", "VARCHAR(64)")],
}


def _ensure_columns() -> None:
    """Idempotently add any missing additive columns (simple migration)."""
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, cols in _ADDITIVE_COLUMNS.items():
            if table not in existing_tables:
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl_type in cols:
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))


def init_db() -> None:
    """Create tables if absent, then apply additive column migrations."""
    from app.db import models  # noqa: F401  (register mappers)
    Base.metadata.create_all(bind=engine)
    _ensure_columns()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope. Commits on success, rolls back on error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
