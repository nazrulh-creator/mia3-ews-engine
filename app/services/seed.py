"""First-run bootstrap: default users, baseline governed config, model entry.

This runs once on an empty database. The baseline threshold (the deck's
50/30/20 and band cut-offs) is created already-active as a documented,
audited bootstrap exception — every later change goes through dual control.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
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

    model = get_active_model()
    db.add(ModelRegistry(
        name=model.name, version=model.version, kind=model.kind,
        is_synthetic=model.is_synthetic, status="active",
        # Plan's stated calibration posture: recall ~0.73, precision ~0.49.
        auc=0.86, recall=0.73, precision=0.49, fn_rate=0.077,
        notes=("Synthetic stand-in for the back-tested XGBoost model. "
               "Drop in the real artifact via MIA3_MODEL_PATH."),
        activated_by="system", approved_by="system"))
    db.flush()

    audit.record(db, actor="system", action="system.seed", entity_type="system",
                 detail="Initial bootstrap: users, baseline thresholds, model registry.")
