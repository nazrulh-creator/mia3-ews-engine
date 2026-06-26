"""Decision Rule management — governed ensemble combination per segment.

A Decision Rule says how a segment's active models combine into the early-
warning trigger (average, weighted, max, min, median, majority, or single).
Changes are dual-controlled: a maker proposes, a different checker approves.
Deactivating a rule (the safe direction) reverts the segment to the default
combination (a single model, or an average of several).
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_internal
from app.core.features import SEGMENTS
from app.db.database import get_db
from app.db.models import User
from app.services import governance
from app.templating import templates

router = APIRouter()


def _render(request: Request, user: User, db: Session, *, error=None, status_code=200):
    return templates.TemplateResponse("rules.html", {
        "request": request, "user": user, "screen": "rules",
        "active": governance.active_rules_by_segment(db),
        "proposed": governance.proposed_rules(db),
        "models": {seg: governance.active_models_for_segment(db, seg) for seg in SEGMENTS},
        "methods": governance.RULE_METHODS, "segments": SEGMENTS,
        "error": error}, status_code=status_code)


@router.get("/rules", response_class=HTMLResponse)
def rules_page(request: Request, user: User = Depends(require_internal),
               db: Session = Depends(get_db)):
    return _render(request, user, db)


@router.post("/rules/propose")
def propose(request: Request, segment: str = Form(...), method: str = Form(...),
            name: str = Form(""), threshold: str = Form("0.5"), weights: str = Form(""),
            note: str = Form(""), user: User = Depends(require_internal),
            db: Session = Depends(get_db)):
    params = {}
    if method == "weighted":
        try:
            params["weights"] = json.loads(weights) if weights.strip() else {}
        except Exception as exc:  # noqa: BLE001
            return _render(request, user, db, error=f"Weights must be valid JSON: {exc}",
                           status_code=400)
    if method == "majority":
        try:
            params["threshold"] = float(threshold)
        except ValueError:
            return _render(request, user, db, error="Threshold must be a number.", status_code=400)
    try:
        governance.propose_rule(db, actor=user.username, segment=segment, name=name,
                                method=method, params=params, note=note)
        db.commit()
    except governance.GovernanceError as exc:
        return _render(request, user, db, error=str(exc), status_code=400)
    return RedirectResponse("/rules", status_code=303)


@router.post("/rules/approve")
def approve(request: Request, rule_id: int = Form(...),
            user: User = Depends(require_internal), db: Session = Depends(get_db)):
    try:
        governance.approve_rule(db, approver=user.username, rule_id=rule_id)
        db.commit()
    except governance.GovernanceError as exc:
        return _render(request, user, db, error=str(exc), status_code=400)
    return RedirectResponse("/rules", status_code=303)


@router.post("/rules/deactivate")
def deactivate(request: Request, rule_id: int = Form(...),
               user: User = Depends(require_internal), db: Session = Depends(get_db)):
    governance.deactivate_rule(db, actor=user.username, rule_id=rule_id)
    db.commit()
    return RedirectResponse("/rules", status_code=303)
