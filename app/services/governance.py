"""Governed configuration: thresholds, calibration, and the model registry.

Every consequential change follows the MicroFlex dual-control pattern: a maker
proposes, a DIFFERENT checker approves (self-approval is blocked), the change
is versioned and audited, and turning something back to a safe state is always
available. Threshold and calibration changes can be previewed against the
latest portfolio before they go live, so tuning is never a leap in the dark.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import scoring as S
from app.db import audit
from app.db.models import (AccountScore, CalibrationConfig, ModelRegistry,
                          ScoringRun, ThresholdConfig)


class GovernanceError(Exception):
    """Raised on a governance rule violation (e.g. self-approval)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Thresholds ------------------------------------------------------------
def active_threshold(db: Session) -> Optional[ThresholdConfig]:
    stmt = select(ThresholdConfig).where(ThresholdConfig.status == "active")
    return db.execute(stmt).scalars().first()


def active_risk_config(db: Session) -> S.RiskConfig:
    row = active_threshold(db)
    if row is None:
        return S.DEFAULT_CONFIG
    cfg = S.RiskConfig(w_pd=row.w_pd, w_ead=row.w_ead, w_outratio=row.w_outratio,
                       t_very_high=row.t_very_high, t_high=row.t_high,
                       t_moderate=row.t_moderate)
    cfg.validate()
    return cfg


def propose_threshold(db: Session, *, actor: str, w_pd: float, w_ead: float,
                      w_outratio: float, t_very_high: float, t_high: float,
                      t_moderate: float, note: str) -> ThresholdConfig:
    # Validate before persisting so an impossible config never enters the queue.
    S.RiskConfig(w_pd=w_pd, w_ead=w_ead, w_outratio=w_outratio,
                 t_very_high=t_very_high, t_high=t_high, t_moderate=t_moderate).validate()
    last_ver = db.execute(select(ThresholdConfig.version)
                          .order_by(ThresholdConfig.version.desc()).limit(1)).scalar()
    version = (last_ver or 0) + 1
    row = ThresholdConfig(version=version, w_pd=w_pd, w_ead=w_ead, w_outratio=w_outratio,
                          t_very_high=t_very_high, t_high=t_high, t_moderate=t_moderate,
                          status="proposed", note=note, created_by=actor)
    db.add(row)
    db.flush()
    audit.record(db, actor=actor, action="threshold.propose", entity_type="threshold",
                 entity_id=str(version), after=_threshold_dict(row), detail=note)
    return row


def approve_threshold(db: Session, *, approver: str, config_id: int) -> ThresholdConfig:
    row = db.get(ThresholdConfig, config_id)
    if row is None or row.status != "proposed":
        raise GovernanceError("No such proposed threshold configuration.")
    if row.created_by == approver:
        raise GovernanceError("Dual control: the proposer cannot approve their own change.")
    previous = active_threshold(db)
    before = _threshold_dict(previous) if previous else None
    if previous:
        previous.status = "retired"
    row.status = "active"
    row.approved_by = approver
    row.approved_at = _now()
    db.flush()
    audit.record(db, actor=approver, action="threshold.activate", entity_type="threshold",
                 entity_id=str(row.version), before=before, after=_threshold_dict(row),
                 detail="Dual-control activation.")
    return row


def _threshold_dict(row: ThresholdConfig) -> dict:
    return {"version": row.version, "w_pd": row.w_pd, "w_ead": row.w_ead,
            "w_outratio": row.w_outratio, "t_very_high": row.t_very_high,
            "t_high": row.t_high, "t_moderate": row.t_moderate}


def preview_rebanding(db: Session, new_cfg: S.RiskConfig) -> Dict[str, object]:
    """Show how the latest published portfolio re-bands under new settings.

    Uses stored component ranks, so it is exact and needs no re-scoring.
    """
    run = _latest_published_run(db)
    if run is None:
        return {"run_ref": None, "before": {}, "after": {}, "moved": 0, "n": 0}
    scores = db.execute(select(AccountScore).where(AccountScore.run_id == run.id)).scalars().all()
    before = {b: 0 for b in S.BANDS}
    after = {b: 0 for b in S.BANDS}
    moved = 0
    for s in scores:
        before[s.band] += 1
        new_score = (new_cfg.w_pd * s.pd_rank + new_cfg.w_ead * s.ead_rank
                     + new_cfg.w_outratio * s.outratio_rank)
        new_band = S.classify(round(new_score, 4), new_cfg)
        after[new_band] += 1
        if new_band != s.band:
            moved += 1
    return {"run_ref": run.run_ref, "before": before, "after": after,
            "moved": moved, "n": len(scores)}


# --- Calibration -----------------------------------------------------------
def active_calibration(db: Session) -> Optional[CalibrationConfig]:
    stmt = select(CalibrationConfig).where(CalibrationConfig.status == "active")
    return db.execute(stmt).scalars().first()


def build_calibrator(row: Optional[CalibrationConfig]) -> Tuple[Optional[Callable], bool]:
    """Return (calibrator_fn, is_calibrated). Identity/none -> (None, False)."""
    if row is None or row.method == "identity":
        return None, False
    params = row.params or {}
    a = float(params.get("a", 1.0))
    b = float(params.get("b", 0.0))
    if row.method == "linear":
        def cal(p: np.ndarray) -> np.ndarray:
            return np.clip(a * np.asarray(p) + b, 0.0, 1.0)
        return cal, True
    if row.method == "platt":
        def cal(p: np.ndarray) -> np.ndarray:
            p = np.clip(np.asarray(p), 1e-6, 1 - 1e-6)
            logit = np.log(p / (1 - p))
            return 1.0 / (1.0 + np.exp(-(a * logit + b)))
        return cal, True
    return None, False


def active_calibrator(db: Session) -> Tuple[Optional[Callable], bool]:
    return build_calibrator(active_calibration(db))


def propose_calibration(db: Session, *, actor: str, method: str, params: dict,
                        note: str) -> CalibrationConfig:
    last_ver = db.execute(select(CalibrationConfig.version)
                          .order_by(CalibrationConfig.version.desc()).limit(1)).scalar()
    version = (last_ver or 0) + 1
    row = CalibrationConfig(version=version, method=method, params=params,
                            status="proposed", note=note, created_by=actor)
    db.add(row)
    db.flush()
    audit.record(db, actor=actor, action="calibration.propose", entity_type="calibration",
                 entity_id=str(version), after={"method": method, "params": params}, detail=note)
    return row


def approve_calibration(db: Session, *, approver: str, config_id: int) -> CalibrationConfig:
    row = db.get(CalibrationConfig, config_id)
    if row is None or row.status != "proposed":
        raise GovernanceError("No such proposed calibration.")
    if row.created_by == approver:
        raise GovernanceError("Dual control: the proposer cannot approve their own change.")
    previous = active_calibration(db)
    if previous:
        previous.status = "retired"
    row.status = "active"
    row.approved_by = approver
    row.approved_at = _now()
    db.flush()
    audit.record(db, actor=approver, action="calibration.activate", entity_type="calibration",
                 entity_id=str(row.version), after={"method": row.method, "params": row.params},
                 detail="Dual-control activation.")
    return row


# --- Model registry --------------------------------------------------------
def active_model_row(db: Session) -> Optional[ModelRegistry]:
    return db.execute(select(ModelRegistry).where(ModelRegistry.status == "active")).scalars().first()


def activate_model(db: Session, *, approver: str, model_id: int) -> ModelRegistry:
    row = db.get(ModelRegistry, model_id)
    if row is None:
        raise GovernanceError("No such model registry entry.")
    if row.approved_by and row.approved_by == approver and row.activated_by == approver:
        raise GovernanceError("Dual control: a different approver is required.")
    previous = active_model_row(db)
    if previous and previous.id != row.id:
        previous.status = "retired"
    row.status = "active"
    row.activated_by = approver
    row.activated_at = _now()
    db.flush()
    audit.record(db, actor=approver, action="model.activate", entity_type="model",
                 entity_id=row.version, detail=f"Activated model {row.name} {row.version}.")
    return row


def _latest_published_run(db: Session) -> Optional[ScoringRun]:
    stmt = (select(ScoringRun)
            .where(ScoringRun.published.is_(True))
            .order_by(ScoringRun.created_at.desc()).limit(1))
    return db.execute(stmt).scalars().first()
