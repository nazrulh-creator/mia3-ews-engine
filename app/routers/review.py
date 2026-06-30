"""Confidence-based human review queue.

A human override changes the *treatment*, never the model's number — the
estimate and the decision are recorded as two distinct facts (coupling rule).
Decisions are captured as labelled records to feed future re-calibration.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import fi_scope, require_user, require_writer
from app.db import audit
from app.db.database import get_db
from app.db.models import AccountScore, Learning, ReviewDecision, User
from app.services import runs
from app.templating import templates

router = APIRouter()


@router.get("/review")
def review_queue(request: Request, user: User = Depends(require_user),
                 db: Session = Depends(get_db)):
    run = runs.latest_run(db)
    items = []
    if run:
        stmt = (select(AccountScore)
                .where(AccountScore.run_id == run.id,
                       AccountScore.review_status == "needs_review")
                .order_by(AccountScore.risk_score.desc()))
        scope = fi_scope(user)
        if scope:
            stmt = stmt.where(AccountScore.fi_id == scope)
        items = db.execute(stmt).scalars().all()
    return templates.TemplateResponse("review.html", {"request": request, "user": user,
                                                      "screen": "review", "items": items,
                                                      "run": run})


@router.post("/review/{score_id}")
def review_decision(score_id: int, request: Request, decision: str = Form(...),
                    reason: str = Form(""), observed_outcome: str = Form(""),
                    user: User = Depends(require_writer), db: Session = Depends(get_db)):
    score = db.get(AccountScore, score_id)
    if score is None:
        return RedirectResponse("/review", status_code=303)
    if decision == "override" and not reason.strip():
        return RedirectResponse(f"/accounts/{score_id}?error=reason_required", status_code=303)

    db.add(ReviewDecision(score_id=score.id, reviewer=user.username, decision=decision,
                          reason=reason or None, observed_outcome=observed_outcome or None))
    score.review_status = "reviewed"
    audit.record(db, actor=user.username, action=f"review.{decision}", entity_type="account",
                 entity_id=score.account_id,
                 before={"review_status": "needs_review", "model_band": score.band},
                 after={"review_status": "reviewed", "decision": decision},
                 detail=reason or None)
    # Confirmed/observed outcomes feed the learnings evidence base.
    if observed_outcome:
        db.add(Learning(author=user.username, category="outcome",
                        title=f"Outcome recorded for {score.account_id}",
                        body=f"Model band {score.band}; reviewer {decision}; "
                             f"observed: {observed_outcome}. {reason}".strip(),
                        linked_account=score.account_id))
    db.commit()
    return RedirectResponse("/review", status_code=303)
