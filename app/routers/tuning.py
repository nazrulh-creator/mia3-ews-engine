"""Prediction-radar tuning: governed thresholds, calibration, model registry.

Internal-risk only. Every change previews, is logged, and needs a second
approver. Calibration defaults to uncalibrated so nothing changes silently.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_internal
from app.core import scoring as S
from app.db.database import get_db
from app.db.models import CalibrationConfig, ModelRegistry, ThresholdConfig, User
from app.services import governance
from app.templating import templates

router = APIRouter()


def _render(request, user, db, *, preview=None, error=None, status_code=200):
    active = governance.active_threshold(db)
    proposed = db.execute(select(ThresholdConfig).where(ThresholdConfig.status == "proposed")
                          .order_by(ThresholdConfig.version.desc())).scalars().all()
    cal_active = governance.active_calibration(db)
    cal_proposed = db.execute(select(CalibrationConfig).where(CalibrationConfig.status == "proposed")
                              .order_by(CalibrationConfig.version.desc())).scalars().all()
    models = db.execute(select(ModelRegistry).order_by(ModelRegistry.created_at.desc())).scalars().all()
    return templates.TemplateResponse("tuning.html", {
        "request": request, "user": user, "screen": "tuning",
        "active": active, "proposed": proposed, "cal_active": cal_active,
        "cal_proposed": cal_proposed, "models": models, "preview": preview,
        "error": error}, status_code=status_code)


@router.get("/tuning")
def tuning_page(request: Request, user: User = Depends(require_internal),
                db: Session = Depends(get_db)):
    return _render(request, user, db)


@router.post("/tuning/threshold/preview")
def threshold_preview(request: Request, w_pd: float = Form(...), w_ead: float = Form(...),
                      w_outratio: float = Form(...), t_very_high: float = Form(...),
                      t_high: float = Form(...), t_moderate: float = Form(...),
                      user: User = Depends(require_internal), db: Session = Depends(get_db)):
    try:
        cfg = S.RiskConfig(w_pd=w_pd, w_ead=w_ead, w_outratio=w_outratio,
                           t_very_high=t_very_high, t_high=t_high, t_moderate=t_moderate)
        cfg.validate()
        preview = governance.preview_rebanding(db, cfg)
        preview["proposed_cfg"] = cfg.__dict__
    except Exception as exc:  # noqa: BLE001
        return _render(request, user, db, error=str(exc), status_code=400)
    return _render(request, user, db, preview=preview)


@router.post("/tuning/threshold/propose")
def threshold_propose(request: Request, w_pd: float = Form(...), w_ead: float = Form(...),
                      w_outratio: float = Form(...), t_very_high: float = Form(...),
                      t_high: float = Form(...), t_moderate: float = Form(...),
                      note: str = Form(""), user: User = Depends(require_internal),
                      db: Session = Depends(get_db)):
    try:
        governance.propose_threshold(db, actor=user.username, w_pd=w_pd, w_ead=w_ead,
                                     w_outratio=w_outratio, t_very_high=t_very_high,
                                     t_high=t_high, t_moderate=t_moderate, note=note)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        return _render(request, user, db, error=str(exc), status_code=400)
    return RedirectResponse("/tuning", status_code=303)


@router.post("/tuning/threshold/approve")
def threshold_approve(request: Request, config_id: int = Form(...),
                      user: User = Depends(require_internal), db: Session = Depends(get_db)):
    try:
        governance.approve_threshold(db, approver=user.username, config_id=config_id)
        db.commit()
    except governance.GovernanceError as exc:
        return _render(request, user, db, error=str(exc), status_code=400)
    return RedirectResponse("/tuning", status_code=303)


@router.post("/tuning/calibration/propose")
def calibration_propose(request: Request, method: str = Form(...), a: float = Form(1.0),
                        b: float = Form(0.0), note: str = Form(""),
                        user: User = Depends(require_internal), db: Session = Depends(get_db)):
    governance.propose_calibration(db, actor=user.username, method=method,
                                   params={"a": a, "b": b}, note=note)
    db.commit()
    return RedirectResponse("/tuning", status_code=303)


@router.post("/tuning/calibration/approve")
def calibration_approve(request: Request, config_id: int = Form(...),
                        user: User = Depends(require_internal), db: Session = Depends(get_db)):
    try:
        governance.approve_calibration(db, approver=user.username, config_id=config_id)
        db.commit()
    except governance.GovernanceError as exc:
        return _render(request, user, db, error=str(exc), status_code=400)
    return RedirectResponse("/tuning", status_code=303)
