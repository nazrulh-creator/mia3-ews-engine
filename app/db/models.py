"""ORM models for the MIA3 Early Warning Engine.

Governance tables (model registry, threshold config, calibration, audit,
reviews, learnings) are lifted from the MicroFlex patterns. The audit table
is append-only and hash-chained (see app/db/audit.py).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Integer, JSON,
                        String, Text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16))  # internal | branch | fi
    display_name: Mapped[str] = mapped_column(String(128))
    fi_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)   # FI scoping
    branch: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ui_mode: Mapped[str] = mapped_column(String(16), default="guided")  # guided | compact
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    artifact_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|active|retired
    # Back-test metrics (deck): AUC, Recall, Precision, False-Negative rate.
    auc: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recall: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    precision: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fn_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    registered_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    activated_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class ThresholdConfig(Base):
    """Governed 50/30/20 weights + band cut-offs. Dual-control to activate."""
    __tablename__ = "threshold_config"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    w_pd: Mapped[float] = mapped_column(Float, default=0.50)
    w_ead: Mapped[float] = mapped_column(Float, default=0.30)
    w_outratio: Mapped[float] = mapped_column(Float, default=0.20)
    t_very_high: Mapped[float] = mapped_column(Float, default=3.5)
    t_high: Mapped[float] = mapped_column(Float, default=3.0)
    t_moderate: Mapped[float] = mapped_column(Float, default=2.0)
    status: Mapped[str] = mapped_column(String(16), default="proposed")  # proposed|active|retired
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    approved_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class CalibrationConfig(Base):
    """Governed calibration mapping. Defaults to uncalibrated (identity)."""
    __tablename__ = "calibration_config"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(32), default="identity")  # identity|linear|platt
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="proposed")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    approved_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ScoringRun(Base):
    __tablename__ = "scoring_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    environment: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(16))  # file|db|manual|scheduled|demo
    model_name: Mapped[str] = mapped_column(String(128))
    model_version: Mapped[str] = mapped_column(String(64))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    calibrated: Mapped[bool] = mapped_column(Boolean, default=False)
    threshold_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    input_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rows_in: Mapped[int] = mapped_column(Integer, default=0)
    rows_scored: Mapped[int] = mapped_column(Integer, default=0)
    rows_quarantined: Mapped[int] = mapped_column(Integer, default=0)
    quality_report: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="completed")
    checkpoint_status: Mapped[str] = mapped_column(String(16), default="published")  # held|published
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    scores: Mapped[list["AccountScore"]] = relationship(back_populates="run",
                                                       cascade="all, delete-orphan")


class AccountScore(Base):
    __tablename__ = "account_scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("scoring_runs.id"), index=True)
    account_id: Mapped[str] = mapped_column(String(64), index=True)
    fi_id: Mapped[str] = mapped_column(String(32), index=True)
    fi_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    scheme: Mapped[str] = mapped_column(String(64), index=True)
    sector: Mapped[str] = mapped_column(String(64), index=True)
    branch: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    as_of_date: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    probability: Mapped[float] = mapped_column(Float)
    probability_raw: Mapped[float] = mapped_column(Float)
    ead: Mapped[float] = mapped_column(Float)
    outstanding_ratio: Mapped[float] = mapped_column(Float)
    pd_rank: Mapped[int] = mapped_column(Integer)
    ead_rank: Mapped[int] = mapped_column(Integer)
    outratio_rank: Mapped[int] = mapped_column(Integer)
    risk_score: Mapped[float] = mapped_column(Float, index=True)
    band: Mapped[str] = mapped_column(String(20), index=True)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    features: Mapped[dict] = mapped_column(JSON, default=dict)  # stored model inputs
    confidence: Mapped[float] = mapped_column(Float)
    confidence_band: Mapped[str] = mapped_column(String(8))
    confidence_components: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(String(16), index=True)  # no_review|fast_track|needs_review|reviewed
    top_factors: Mapped[list] = mapped_column(JSON, default=list)
    explanation_operational: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    explanation_technical: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    explanation_simplified: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    defaulted_fields: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    run: Mapped["ScoringRun"] = relationship(back_populates="scores")
    reviews: Mapped[list["ReviewDecision"]] = relationship(back_populates="score",
                                                          cascade="all, delete-orphan")


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    score_id: Mapped[int] = mapped_column(ForeignKey("account_scores.id"), index=True)
    reviewer: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(16))  # confirm|override|escalate
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    observed_outcome: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # for relabel
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    score: Mapped["AccountScore"] = relationship(back_populates="reviews")


class AuditEvent(Base):
    """Append-only, hash-chained. Never updated or deleted via the app."""
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, index=True)
    environment: Mapped[str] = mapped_column(String(8), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    before: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), index=True)


class Learning(Base):
    __tablename__ = "learnings"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    author: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(24))  # outcome|note|change
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    linked_account: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    linked_run: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class PortfolioAlert(Base):
    """Early-warning ladder alerts at FI / sector level."""
    __tablename__ = "portfolio_alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_ref: Mapped[str] = mapped_column(String(64), index=True)
    dimension: Mapped[str] = mapped_column(String(16))  # fi|sector
    key: Mapped[str] = mapped_column(String(128))
    high_risk_share: Mapped[float] = mapped_column(Float)
    tripwire: Mapped[str] = mapped_column(String(16))  # watch|halt
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ProblemReport(Base):
    __tablename__ = "problem_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    reporter: Mapped[str] = mapped_column(String(64))
    screen: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    record_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    detail: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    audit_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
