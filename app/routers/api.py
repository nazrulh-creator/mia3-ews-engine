"""JSON API — self-documenting at /api/docs.

FI-facing reads are row-scoped to the caller's own book. The data contract is
exposed so an FI can build its monthly file against the canonical schema.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import fi_scope, require_user
from app.core.features import contract_as_dict
from app.db.database import get_db
from app.db.models import AccountScore, User
from app.services import runs

router = APIRouter(prefix="/api/v1", tags=["mia3"])


@router.get("/contract")
def get_contract():
    """The canonical input data contract (every expected column)."""
    return contract_as_dict()


@router.get("/portfolio/summary")
def portfolio_summary(user: User = Depends(require_user), db: Session = Depends(get_db)):
    scope = fi_scope(user)
    run = runs.latest_run(db)
    if not run:
        return {"run_ref": None, "counts": {}}
    return {"run_ref": run.run_ref, "as_of": run.created_at.isoformat(),
            "counts": runs.band_counts(db, run.id, fi_id=scope),
            "by_sector": runs.breakdown(db, run.id, "sector", fi_id=scope)}


@router.get("/accounts")
def list_accounts(band: Optional[str] = Query(None), limit: int = Query(100, le=1000),
                  user: User = Depends(require_user), db: Session = Depends(get_db)):
    scope = fi_scope(user)
    run = runs.latest_run(db)
    if not run:
        return {"accounts": []}
    stmt = select(AccountScore).where(AccountScore.run_id == run.id)
    if scope:
        stmt = stmt.where(AccountScore.fi_id == scope)
    if band:
        stmt = stmt.where(AccountScore.band == band)
    stmt = stmt.order_by(AccountScore.risk_score.desc()).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return {"run_ref": run.run_ref, "accounts": [_account_json(r) for r in rows]}


@router.get("/accounts/{account_id}")
def get_account(account_id: str, user: User = Depends(require_user),
                db: Session = Depends(get_db)):
    scope = fi_scope(user)
    run = runs.latest_run(db)
    if not run:
        return {"detail": "No published run."}
    stmt = select(AccountScore).where(AccountScore.run_id == run.id,
                                      AccountScore.account_id == account_id)
    if scope:
        stmt = stmt.where(AccountScore.fi_id == scope)
    row = db.execute(stmt).scalars().first()
    if row is None:
        return {"detail": "Account not found in the latest run (or out of scope)."}
    return _account_json(row, detail=True)


def _account_json(r: AccountScore, detail: bool = False) -> dict:
    out = {
        "account_id": r.account_id, "fi_id": r.fi_id, "scheme": r.scheme,
        "sector": r.sector, "probability": r.probability, "ead": r.ead,
        "outstanding_ratio": r.outstanding_ratio, "risk_score": r.risk_score,
        "band": r.band, "confidence": r.confidence, "review_status": r.review_status,
    }
    if detail:
        out.update({"breakdown": r.breakdown, "top_factors": r.top_factors,
                    "explanation": r.explanation_operational,
                    "confidence_components": r.confidence_components})
    return out
