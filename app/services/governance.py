"""Governed configuration: thresholds, calibration, and the model registry.

Every consequential change follows the MicroFlex dual-control pattern: a maker
proposes, a DIFFERENT checker approves (self-approval is blocked), the change
is versioned and audited, and turning something back to a safe state is always
available. Threshold and calibration changes can be previewed against the
latest portfolio before they go live, so tuning is never a leap in the dark.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import scoring as S
from app.db import audit
from app.db.models import (AccountScore, CalibrationConfig, DecisionRule,
                          ModelRegistry, ScoringRun, ThresholdConfig)


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


# --- Model registry (one active model per segment) -------------------------
def active_model_row(db: Session, segment: Optional[str] = None) -> Optional[ModelRegistry]:
    stmt = select(ModelRegistry).where(ModelRegistry.status == "active")
    if segment is not None:
        stmt = stmt.where(ModelRegistry.segment == segment)
    return db.execute(stmt).scalars().first()


def active_models_for_segment(db: Session, segment: str) -> List[ModelRegistry]:
    """All active models for a segment (an ensemble may use several)."""
    return db.execute(select(ModelRegistry).where(
        ModelRegistry.status == "active", ModelRegistry.segment == segment)
        .order_by(ModelRegistry.version)).scalars().all()


def active_models_by_segment(db: Session) -> Dict[str, List[ModelRegistry]]:
    """{segment: [active ModelRegistry, ...]} across all segments."""
    rows = db.execute(select(ModelRegistry).where(ModelRegistry.status == "active")
                      .order_by(ModelRegistry.version)).scalars().all()
    out: Dict[str, List[ModelRegistry]] = {}
    for r in rows:
        out.setdefault(r.segment, []).append(r)
    return out


def segment_scorer(db: Session, segment: str):
    """Build the scorer for a segment: a single model, or an Ensemble of the
    active models combined by the active Decision Rule. None if nothing active."""
    from app.core.ensemble import Ensemble
    from app.core.model import build_model
    rows = active_models_for_segment(db, segment)
    if not rows:
        return None
    members = [build_model(r.model_type, name=r.name, version=r.version,
                           artifact_path=r.artifact_path, spec=r.spec) for r in rows]
    rule = active_rule_for_segment(db, segment)
    if len(members) == 1 and (rule is None or rule.method == "single"):
        return members[0]
    method = rule.method if rule else "average"
    params = rule.params if rule else {}
    name = f"Ensemble[{method}]"
    version = f"rule-v{rule.version}" if rule else "auto-average"
    return Ensemble(members, method=method, params=params, name=name, version=version)


def active_model_path(db: Session, segment: Optional[str] = None):
    """Artifact path of the active registry entry for a segment, or None."""
    row = active_model_row(db, segment)
    if row and row.artifact_path:
        return Path(row.artifact_path)
    return None


def register_model(db: Session, *, actor: str, name: str, version: str,
                   model_type: str, is_synthetic: bool, artifact_path: Optional[str],
                   spec: Optional[dict], auc: Optional[float], recall: Optional[float],
                   precision: Optional[float], fn_rate: Optional[float],
                   notes: str, segment: str = "Guarantee") -> ModelRegistry:
    """Maker registers a new model version as a draft (not yet live).

    model_type is one of: synthetic, xgboost (uploaded artifact), logistic or
    ols (glass-box specs). The spec/artifact is validated on activation.
    """
    if not name or not version:
        raise GovernanceError("Name and version are required.")
    clash = db.execute(select(ModelRegistry).where(ModelRegistry.version == version)).scalars().first()
    if clash:
        raise GovernanceError(f"Version '{version}' already exists in the registry.")
    row = ModelRegistry(name=name, version=version, segment=segment, kind=model_type,
                        model_type=model_type, spec=spec, is_synthetic=is_synthetic,
                        artifact_path=artifact_path or None, status="draft", auc=auc,
                        recall=recall, precision=precision, fn_rate=fn_rate,
                        notes=notes or None, registered_by=actor)
    db.add(row)
    db.flush()
    audit.record(db, actor=actor, action="model.register", entity_type="model",
                 entity_id=version, after={"name": name, "segment": segment,
                 "model_type": model_type, "artifact": artifact_path}, detail=notes or None)
    return row


def update_model(db: Session, *, actor: str, model_id: int, **fields) -> ModelRegistry:
    """Edit a draft or retired entry's metadata. The active model is locked —
    retire it first to edit, so a live model never changes underneath users."""
    row = db.get(ModelRegistry, model_id)
    if row is None:
        raise GovernanceError("No such model registry entry.")
    if row.status == "active":
        raise GovernanceError("The active model is locked. Retire it before editing.")
    before = {k: getattr(row, k) for k in fields}
    for key, value in fields.items():
        setattr(row, key, value)
    db.flush()
    audit.record(db, actor=actor, action="model.update", entity_type="model",
                 entity_id=row.version, before=before, after=dict(fields))
    return row


def activate_model(db: Session, *, approver: str, model_id: int) -> ModelRegistry:
    """Checker activates a model. Dual control + artifact pre-flight."""
    from app.core import model as model_core
    row = db.get(ModelRegistry, model_id)
    if row is None:
        raise GovernanceError("No such model registry entry.")
    if row.status == "active":
        raise GovernanceError("That model is already active.")
    if row.registered_by and row.registered_by == approver:
        raise GovernanceError(
            "Dual control: the person who registered a model cannot activate it.")
    ok, message = model_core.validate_model(
        row.model_type, artifact_path=row.artifact_path, spec=row.spec)
    if not ok:
        raise GovernanceError(f"Cannot activate — failed validation: {message}")
    # Multiple models may be active per segment (an ensemble) — activation ADDS
    # to the active set; it does not retire the others. Use Retire to remove one.
    row.status = "active"
    row.activated_by = approver
    row.approved_by = approver
    row.activated_at = _now()
    db.flush()
    model_core.reset_model_cache()
    audit.record(db, actor=approver, action="model.activate", entity_type="model",
                 entity_id=row.version,
                 after={"segment": row.segment, "version": row.version, "validation": message},
                 detail=f"Activated {row.name} {row.version} for {row.segment}.")
    return row


def retire_model(db: Session, *, actor: str, model_id: int) -> ModelRegistry:
    """Retire the active model (the safe direction — single control)."""
    from app.core import model as model_core
    row = db.get(ModelRegistry, model_id)
    if row is None:
        raise GovernanceError("No such model registry entry.")
    row.status = "retired"
    db.flush()
    model_core.reset_model_cache()
    audit.record(db, actor=actor, action="model.retire", entity_type="model",
                 entity_id=row.version, detail=f"Retired {row.name} {row.version}.")
    return row


# --- Decision rules (governed ensemble combination) ------------------------
RULE_METHODS = ["single", "average", "weighted", "max", "min", "median", "majority"]


def active_rule_for_segment(db: Session, segment: str) -> Optional[DecisionRule]:
    return db.execute(select(DecisionRule).where(
        DecisionRule.status == "active", DecisionRule.segment == segment)).scalars().first()


def active_rules_by_segment(db: Session) -> Dict[str, DecisionRule]:
    rows = db.execute(select(DecisionRule).where(DecisionRule.status == "active")).scalars().all()
    return {r.segment: r for r in rows}


def proposed_rules(db: Session) -> List[DecisionRule]:
    return db.execute(select(DecisionRule).where(DecisionRule.status == "proposed")
                      .order_by(DecisionRule.created_at.desc())).scalars().all()


def propose_rule(db: Session, *, actor: str, segment: str, name: str, method: str,
                 params: dict, note: str) -> DecisionRule:
    if method not in RULE_METHODS:
        raise GovernanceError(f"Unknown method '{method}'.")
    last = db.execute(select(DecisionRule.version).where(DecisionRule.segment == segment)
                      .order_by(DecisionRule.version.desc()).limit(1)).scalar()
    version = (last or 0) + 1
    row = DecisionRule(version=version, segment=segment, name=name or f"{segment} {method}",
                       method=method, params=params or {}, status="proposed",
                       note=note or None, created_by=actor)
    db.add(row)
    db.flush()
    audit.record(db, actor=actor, action="rule.propose", entity_type="decision_rule",
                 entity_id=f"{segment} v{version}",
                 after={"segment": segment, "method": method, "params": params}, detail=note)
    return row


def approve_rule(db: Session, *, approver: str, rule_id: int) -> DecisionRule:
    row = db.get(DecisionRule, rule_id)
    if row is None or row.status != "proposed":
        raise GovernanceError("No such proposed decision rule.")
    if row.created_by == approver:
        raise GovernanceError("Dual control: the proposer cannot approve their own rule.")
    previous = active_rule_for_segment(db, row.segment)
    if previous and previous.id != row.id:
        previous.status = "retired"
    row.status = "active"
    row.approved_by = approver
    row.approved_at = _now()
    db.flush()
    audit.record(db, actor=approver, action="rule.activate", entity_type="decision_rule",
                 entity_id=f"{row.segment} v{row.version}",
                 detail=f"Activated {row.method} rule for {row.segment}.")
    return row


def deactivate_rule(db: Session, *, actor: str, rule_id: int) -> DecisionRule:
    """Deactivate the active rule (safe direction; the segment reverts to the
    default combination — single model, or average if several are active)."""
    row = db.get(DecisionRule, rule_id)
    if row is None:
        raise GovernanceError("No such decision rule.")
    row.status = "retired"
    db.flush()
    audit.record(db, actor=actor, action="rule.deactivate", entity_type="decision_rule",
                 entity_id=f"{row.segment} v{row.version}",
                 detail=f"Deactivated rule for {row.segment}.")
    return row


def _latest_published_run(db: Session) -> Optional[ScoringRun]:
    stmt = (select(ScoringRun)
            .where(ScoringRun.published.is_(True))
            .order_by(ScoringRun.created_at.desc()).limit(1))
    return db.execute(stmt).scalars().first()
