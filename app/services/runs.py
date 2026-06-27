"""Run orchestration, persistence, and portfolio aggregates.

One entry point — execute_run — takes a portfolio frame and drives it through
validation, scoring, persistence, audit and the early-warning ladder. Every
view in the app reads the numbers this module writes.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import pandas as pd

from app.config import get_settings
from app.core import scoring as S
from app.core.batch import score_frame
from app.core.model import get_active_model
from app.core.validation import validate
from app.db import audit
from app.db.models import AccountScore, PortfolioAlert, ScoringRun
from app.services import governance

# Early-warning ladder cut-offs on the high-risk share within a group.
LADDER_WATCH = 0.15
LADDER_HALT = 0.30
HIGH_BANDS = {"Very High Risk", "High Risk"}


def fingerprint(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:32]


def _run_ref(db: Session) -> str:
    settings = get_settings()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    n = db.execute(select(func.count(ScoringRun.id))).scalar() or 0
    return f"{settings.id_prefix}RUN-{ts}-{n + 1:04d}"


def execute_run(db: Session, df: pd.DataFrame, *, source: str, actor: str,
                input_fingerprint: Optional[str] = None,
                hold_for_signoff: bool = False) -> ScoringRun:
    """Validate, score, persist, audit and ladder-check a portfolio frame."""
    settings = get_settings()
    cfg = governance.active_risk_config(db)
    calibrator, calibrated = governance.active_calibrator(db)
    threshold_row = governance.active_threshold(db)
    # Each account is routed to its segment's scorer — a single active model or
    # an Ensemble of the active models combined by the active Decision Rule
    # (coupling rule: only active models, never a draft). No active model →
    # the synthetic stand-in.
    def resolver(segment: str):
        scorer = governance.segment_scorer(db, segment)
        return scorer if scorer is not None else get_active_model()

    vr = validate(df)
    result = score_frame(df, cfg=cfg, calibrator=calibrator, validation=vr,
                         model_for_segment=resolver)
    run_model_name = result.model_name
    run_model_version = result.model_version
    run_is_synthetic = result.is_synthetic

    quality = vr.quality_report()
    # Checkpoint: hold publication if asked, or if nothing could be scored,
    # or if more than a quarter of rows were quarantined.
    qrate = quality.get("acceptance_rate", 1.0)
    auto_hold = result.n_scored == 0 or (isinstance(qrate, (int, float)) and qrate < 0.75)
    held = hold_for_signoff or auto_hold

    run = ScoringRun(
        run_ref=_run_ref(db), environment=settings.environment, source=source,
        model_name=run_model_name, model_version=run_model_version,
        is_synthetic=run_is_synthetic, calibrated=calibrated,
        threshold_version=(threshold_row.version if threshold_row else None),
        input_fingerprint=input_fingerprint,
        rows_in=quality["rows_in"], rows_scored=result.n_scored,
        rows_quarantined=quality["rows_quarantined"], quality_report=quality,
        status="completed",
        checkpoint_status="held" if held else "published",
        published=not held,
    )
    db.add(run)
    db.flush()

    for rec in result.records:
        db.add(AccountScore(run_id=run.id, **_score_kwargs(rec)))
    db.flush()

    _raise_ladder_alerts(db, run, result.records)

    audit.record(db, actor=actor, action="run.execute", entity_type="run",
                 entity_id=run.run_ref, after={
                     "source": source, "rows_scored": run.rows_scored,
                     "rows_quarantined": run.rows_quarantined,
                     "model": f"{run.model_name}:{run.model_version}",
                     "calibrated": calibrated, "published": run.published,
                     "band_counts": result.band_counts(),
                 }, detail=("Held for sign-off." if held else "Published to views."))
    return run


def _score_kwargs(rec: Dict[str, object]) -> Dict[str, object]:
    keys = ["account_id", "fi_id", "fi_name", "segment", "model_version", "scheme",
            "sector", "branch", "as_of_date", "probability", "probability_raw", "ead",
            "outstanding_ratio", "pd_rank", "ead_rank", "outratio_rank",
            "risk_score", "band", "breakdown", "features", "confidence", "confidence_band",
            "confidence_components", "review_status", "top_factors",
            "explanation_operational", "explanation_technical",
            "explanation_simplified", "defaulted_fields"]
    return {k: rec[k] for k in keys}


def _raise_ladder_alerts(db: Session, run: ScoringRun, records: List[Dict]) -> None:
    for dim, field_name in (("fi", "fi_id"), ("sector", "sector")):
        totals: Dict[str, int] = {}
        highs: Dict[str, int] = {}
        for r in records:
            key = str(r.get(field_name))
            totals[key] = totals.get(key, 0) + 1
            if r["band"] in HIGH_BANDS:
                highs[key] = highs.get(key, 0) + 1
        for key, total in totals.items():
            if total < 5:  # too small to be meaningful
                continue
            share = highs.get(key, 0) / total
            if share >= LADDER_HALT:
                trip = "halt"
            elif share >= LADDER_WATCH:
                trip = "watch"
            else:
                continue
            db.add(PortfolioAlert(run_ref=run.run_ref, dimension=dim, key=key,
                                  high_risk_share=round(share, 4), tripwire=trip))
    db.flush()


# --- Read helpers used by the views ---------------------------------------
def latest_run(db: Session, *, published_only: bool = True) -> Optional[ScoringRun]:
    stmt = select(ScoringRun).order_by(ScoringRun.created_at.desc())
    if published_only:
        stmt = stmt.where(ScoringRun.published.is_(True))
    return db.execute(stmt.limit(1)).scalars().first()


def band_counts(db: Session, run_id: int, *, fi_id: Optional[str] = None) -> Dict[str, int]:
    stmt = select(AccountScore.band, func.count()).where(AccountScore.run_id == run_id)
    if fi_id:
        stmt = stmt.where(AccountScore.fi_id == fi_id)
    stmt = stmt.group_by(AccountScore.band)
    counts = {b: 0 for b in S.BANDS}
    for band, n in db.execute(stmt).all():
        counts[band] = n
    return counts


def breakdown(db: Session, run_id: int, dimension: str,
              *, fi_id: Optional[str] = None) -> List[Dict[str, object]]:
    """Counts by band within a grouping dimension (fi_id|scheme|sector)."""
    col = {"fi_id": AccountScore.fi_id, "scheme": AccountScore.scheme,
           "sector": AccountScore.sector, "segment": AccountScore.segment,
           "branch": AccountScore.branch}[dimension]
    stmt = select(col, AccountScore.band, func.count()).where(AccountScore.run_id == run_id)
    if fi_id:
        stmt = stmt.where(AccountScore.fi_id == fi_id)
    stmt = stmt.group_by(col, AccountScore.band)
    agg: Dict[str, Dict[str, int]] = {}
    for key, band, n in db.execute(stmt).all():
        agg.setdefault(str(key), {b: 0 for b in S.BANDS})[band] = n
    rows = []
    for key, bands in agg.items():
        total = sum(bands.values())
        high = bands["Very High Risk"] + bands["High Risk"]
        rows.append({"key": key, "total": total, "high_risk": high,
                     "high_share": round(high / total, 4) if total else 0.0, **bands})
    rows.sort(key=lambda r: r["high_share"], reverse=True)
    return rows


def previous_published_run(db: Session, before: ScoringRun) -> Optional[ScoringRun]:
    """The published run immediately before `before` — for run-over-run change."""
    stmt = (select(ScoringRun)
            .where(ScoringRun.published.is_(True), ScoringRun.created_at < before.created_at)
            .order_by(ScoringRun.created_at.desc()).limit(1))
    return db.execute(stmt).scalars().first()


def band_migration(db: Session, run: ScoringRun, prev_run: ScoringRun, *,
                   fi_id: Optional[str] = None, top: int = 12) -> Dict[str, object]:
    """Compare two runs account-by-account: transition matrix, summary, movers."""
    pstmt = select(AccountScore.account_id, AccountScore.band, AccountScore.risk_score
                   ).where(AccountScore.run_id == prev_run.id)
    if fi_id:
        pstmt = pstmt.where(AccountScore.fi_id == fi_id)
    prev = {aid: (band, score) for aid, band, score in db.execute(pstmt).all()}

    cstmt = select(AccountScore.id, AccountScore.account_id, AccountScore.segment,
                   AccountScore.band, AccountScore.risk_score, AccountScore.probability
                   ).where(AccountScore.run_id == run.id)
    if fi_id:
        cstmt = cstmt.where(AccountScore.fi_id == fi_id)

    rank = {b: i for i, b in enumerate(S.BANDS)}  # 0 = worst (Very High)
    matrix: Dict[str, Dict[str, int]] = {}
    max_cell = 0
    summary = {"deteriorated": 0, "improved": 0, "unchanged": 0, "new": 0, "exited": 0}
    changes, cur_ids = [], set()
    for sid, aid, seg, band, score, prob in db.execute(cstmt).all():
        cur_ids.add(aid)
        if aid not in prev:
            summary["new"] += 1
            continue
        pband, pscore = prev[aid]
        row = matrix.setdefault(pband, {})
        row[band] = row.get(band, 0) + 1
        max_cell = max(max_cell, row[band])
        ds = round(float(score) - float(pscore), 3)
        worse = rank[band] < rank[pband] or (band == pband and ds > 0)
        better = rank[band] > rank[pband] or (band == pband and ds < 0)
        summary["deteriorated" if worse else "improved" if better else "unchanged"] += 1
        changes.append({"score_id": sid, "account_id": aid, "segment": seg,
                        "from": pband, "to": band, "ds": ds, "prob": float(prob)})
    summary["exited"] = sum(1 for aid in prev if aid not in cur_ids)
    summary["total"] = len(cur_ids)

    deteriorated = sorted(changes, key=lambda c: (rank[c["to"]] - rank[c["from"]], -c["ds"]))
    det = [c for c in deteriorated if rank[c["to"]] < rank[c["from"]] or c["ds"] > 0][:top]
    improved = sorted(changes, key=lambda c: (rank[c["from"]] - rank[c["to"]], c["ds"]))
    imp = [c for c in improved if rank[c["to"]] > rank[c["from"]] or c["ds"] < 0][:top]
    return {"run_ref": run.run_ref, "prev_ref": prev_run.run_ref, "summary": summary,
            "matrix": matrix, "max_cell": max_cell, "deteriorated": det, "improved": imp}


def exposure_by_band(db: Session, run_id: int, *, fi_id: Optional[str] = None) -> Dict[str, float]:
    """Sum of EAD (RM at risk) by band — counts don't show where the money is."""
    stmt = select(AccountScore.band, func.sum(AccountScore.ead)).where(AccountScore.run_id == run_id)
    if fi_id:
        stmt = stmt.where(AccountScore.fi_id == fi_id)
    stmt = stmt.group_by(AccountScore.band)
    out = {b: 0.0 for b in S.BANDS}
    for band, total in db.execute(stmt).all():
        out[band] = float(total or 0)
    return out


def probability_values(db: Session, run_id: int, *, fi_id: Optional[str] = None,
                       limit: int = 5000) -> List[float]:
    """Probabilities for the latest run — for the distribution histogram."""
    stmt = select(AccountScore.probability).where(AccountScore.run_id == run_id)
    if fi_id:
        stmt = stmt.where(AccountScore.fi_id == fi_id)
    return [float(p) for (p,) in db.execute(stmt.limit(limit)).all()]


def risk_points(db: Session, run_id: int, *, fi_id: Optional[str] = None,
                limit: int = 3000) -> List[tuple]:
    """(probability, ead, outstanding_ratio, band) per account — for the risk map."""
    stmt = select(AccountScore.probability, AccountScore.ead,
                  AccountScore.outstanding_ratio, AccountScore.band).where(
        AccountScore.run_id == run_id)
    if fi_id:
        stmt = stmt.where(AccountScore.fi_id == fi_id)
    stmt = stmt.limit(limit)
    return [(float(p), float(e), float(o), b) for p, e, o, b in db.execute(stmt).all()]


def trend(db: Session, *, limit: int = 12, fi_id: Optional[str] = None) -> List[Dict[str, object]]:
    runs = db.execute(select(ScoringRun).where(ScoringRun.published.is_(True))
                      .order_by(ScoringRun.created_at.asc())).scalars().all()
    runs = runs[-limit:]
    out = []
    for run in runs:
        out.append({"run_ref": run.run_ref,
                    "created_at": run.created_at.strftime("%Y-%m-%d"),
                    **band_counts(db, run.id, fi_id=fi_id)})
    return out
