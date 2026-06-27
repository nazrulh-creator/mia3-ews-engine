"""Model-performance monitoring and realised-outcome capture."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_internal, require_user
from app.config import get_settings
from app.db import audit
from app.db.database import get_db
from app.db.models import AccountScore, ScoringRun, User
from app.services import performance, runs
from app.templating import templates

router = APIRouter()


@router.get("/performance")
def performance_page(request: Request, user: User = Depends(require_internal),
                     db: Session = Depends(get_db)):
    rows = performance.compute_performance(db)
    latest = runs.latest_run(db)
    return templates.TemplateResponse("performance.html", {
        "request": request, "user": user, "screen": "performance",
        "rows": rows, "latest": latest, "series": performance.performance_series(db),
        "goals": {"recall": performance.GOAL_RECALL, "auc": performance.GOAL_AUC,
                  "fn": performance.GOAL_FN_MAX}})


@router.post("/performance/simulate")
def performance_simulate(request: Request, user: User = Depends(require_internal),
                         db: Session = Depends(get_db)):
    settings = get_settings()
    if settings.is_live:
        # Outcomes on LIVE are real and recorded by people, never synthesised.
        return RedirectResponse("/performance", status_code=303)
    run = runs.latest_run(db)
    if run:
        n = performance.simulate_outcomes_for_run(db, run, actor=user.username)
        audit.record(db, actor=user.username, action="outcome.simulate", entity_type="run",
                     entity_id=run.run_ref, detail=f"Simulated {n} TEST outcomes.")
        db.commit()
    return RedirectResponse("/performance", status_code=303)


@router.post("/accounts/{score_id}/outcome")
def record_outcome(score_id: int, request: Request, actual_mia3: str = Form(...),
                   intervention_applied: str = Form(""), exit_reason: str = Form(""),
                   user: User = Depends(require_user), db: Session = Depends(get_db)):
    score = db.get(AccountScore, score_id)
    if score is None:
        return RedirectResponse("/accounts", status_code=303)
    run = db.get(ScoringRun, score.run_id)
    performance.record_outcome(
        db, score=score, run_ref=run.run_ref if run else "—",
        actual_mia3=(actual_mia3 == "yes"),
        intervention_applied=bool(intervention_applied),
        exit_reason=exit_reason or None, source="manual", actor=user.username)
    audit.record(db, actor=user.username, action="outcome.record", entity_type="account",
                 entity_id=score.account_id,
                 after={"actual_mia3": actual_mia3, "intervention": bool(intervention_applied)})
    db.commit()
    return RedirectResponse(f"/accounts/{score_id}", status_code=303)
