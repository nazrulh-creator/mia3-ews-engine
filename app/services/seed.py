"""First-run bootstrap: default users, baseline governed config, model entry.

This runs once on an empty database. The baseline threshold (the deck's
50/30/20 and band cut-offs) is created already-active as a documented,
audited bootstrap exception — every later change goes through dual control.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.config import get_settings
from app.core.features import SEGMENTS
from app.core.model import get_active_model
from app.db import audit
from app.db.models import ModelRegistry, ThresholdConfig, User

# Default accounts for the TEST environment (synthetic data only).
DEFAULT_USERS = [
    ("internal", "internal123", "internal", "Aisha (Internal Risk)", None, None),
    ("checker", "checker123", "internal", "Ravi (Risk — Checker)", None, None),
    ("branch", "branch123", "branch", "Branch Officer — KL", None, "KL-Sentral"),
    ("fi_mbb", "fi123", "fi", "Maybank Portfolio Desk", "MBB", None),
    ("fi_cimb", "fi123", "fi", "CIMB Portfolio Desk", "CIMB", None),
]


def ensure_seed(db: Session) -> None:
    if db.execute(select(func.count(User.id))).scalar():
        return  # already seeded

    for username, pw, role, name, fi_id, branch in DEFAULT_USERS:
        db.add(User(username=username, password_hash=hash_password(pw), role=role,
                    display_name=name, fi_id=fi_id, branch=branch))

    db.add(ThresholdConfig(version=1, w_pd=0.50, w_ead=0.30, w_outratio=0.20,
                           t_very_high=3.5, t_high=3.0, t_moderate=2.0,
                           status="active", note="Baseline from EWS deck (bootstrap).",
                           created_by="system", approved_by="system"))

    # One active synthetic stand-in per segment (Guarantee, Financing). Metrics
    # are indicative and reflect the deck's real-world picture (high recall,
    # very low precision, AUC near 0.5) — the real artifacts drop in per segment.
    model = get_active_model()
    for seg in SEGMENTS:
        db.add(ModelRegistry(
            name=f"{seg} — {model.name}", version=f"synthetic-{seg.lower()}-1.0.0",
            segment=seg, kind=model.kind, is_synthetic=model.is_synthetic, status="active",
            auc=0.52, recall=0.90, precision=0.12, fn_rate=0.05,
            notes=(f"Synthetic stand-in for the back-tested {seg} model. "
                   "Drop in the real artifact via the registry / MIA3_MODEL_PATH. "
                   "Metrics indicative."),
            registered_by="system", activated_by="system", approved_by="system"))
    db.flush()

    audit.record(db, actor="system", action="system.seed", entity_type="system",
                 detail="Initial bootstrap: users, baseline thresholds, model registry.")


def ensure_demo_users(db: Session) -> None:
    """TEST only: guarantee the demo accounts exist with their known passwords.

    The TEST environment is a synthetic-data sandbox whose demo credentials are
    public by design. Re-asserting them on every startup means a deploy can
    never lock everyone out (and is skipped entirely on LIVE, where real
    accounts are managed properly).
    """
    if get_settings().is_live:
        return
    created = []
    for username, pw, role, name, fi_id, branch in DEFAULT_USERS:
        u = db.execute(select(User).where(User.username == username)).scalars().first()
        if u is None:
            db.add(User(username=username, password_hash=hash_password(pw), role=role,
                        display_name=name, fi_id=fi_id, branch=branch))
            created.append(username)
        else:
            # Keep the known demo password and role current.
            u.password_hash = hash_password(pw)
            u.role, u.fi_id, u.branch = role, fi_id, branch
    db.flush()
    if created:
        audit.record(db, actor="system", action="system.ensure_demo_users",
                     entity_type="system", detail=f"Created demo accounts: {created}")


def ensure_segment_models(db: Session) -> None:
    """Idempotently guarantee every segment has an active model.

    Runs on every startup so databases seeded before segments existed (or that
    have no active model for a segment) get a synthetic stand-in to fall back on.
    """
    model = get_active_model()
    created = False
    for seg in SEGMENTS:
        active = db.execute(select(ModelRegistry).where(
            ModelRegistry.status == "active", ModelRegistry.segment == seg)).scalars().first()
        if active:
            continue
        auto_ver = f"synthetic-{seg.lower()}-auto"
        existing = db.execute(select(ModelRegistry).where(
            ModelRegistry.version == auto_ver)).scalars().first()
        if existing:
            existing.status = "active"
            existing.activated_by = "system"
        else:
            db.add(ModelRegistry(
                name=f"{seg} — {model.name}", version=auto_ver, segment=seg,
                kind=model.kind, is_synthetic=True, status="active",
                auc=0.52, recall=0.90, precision=0.12, fn_rate=0.05,
                notes=f"Auto-provisioned synthetic stand-in for {seg}.",
                registered_by="system", activated_by="system", approved_by="system"))
        created = True
    if created:
        db.flush()
        audit.record(db, actor="system", action="system.ensure_segment_models",
                     entity_type="system", detail="Ensured an active model per segment.")
