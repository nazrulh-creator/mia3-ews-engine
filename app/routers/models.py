"""Model registry management — register, edit, activate, retire.

Supports several decision-model types: synthetic stand-in, uploaded ML
artifact (xgboost/sklearn), and glass-box logistic / OLS regressions defined
in-app by a coefficient spec. Multiple models may be active per segment; how
they combine into the trigger is set by a Decision Rule (see /rules).

Activation is dual-controlled (the registrant cannot activate their own model)
and the spec/artifact is validated against the data contract first. Retiring is
single-control and immediate.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_internal
from app.config import MODELS_DIR
from app.core.features import SEGMENTS
from app.core.model import coefficient_template, validate_model
from app.db.database import get_db
from app.db.models import ModelRegistry, User
from app.services import analytics, appsettings, governance
from app.templating import templates

router = APIRouter()


def _to_float(v: str) -> Optional[float]:
    v = (v or "").strip()
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _render(request: Request, user: User, db: Session, *, error=None, ok=None, status_code=200):
    rows = db.execute(select(ModelRegistry).order_by(ModelRegistry.created_at.desc())).scalars().all()
    active = governance.active_models_by_segment(db)        # {segment: [rows]}
    rules = governance.active_rules_by_segment(db)          # {segment: rule}
    validations = {}
    for r in rows:
        ok_v, msg = validate_model(r.model_type, artifact_path=r.artifact_path, spec=r.spec)
        validations[r.id] = {"ok": ok_v, "msg": msg}
    dispersions = []
    if appsettings.viz_flags().tier3:
        for seg in SEGMENTS:
            d = analytics.ensemble_dispersion(db, seg)
            if d:
                dispersions.append(d)
    return templates.TemplateResponse("models.html", {
        "request": request, "user": user, "screen": "models", "rows": rows,
        "active": active, "rules": rules, "validations": validations,
        "dispersions": dispersions,
        "spec_template": json.dumps(coefficient_template(), indent=2),
        "error": error, "ok": ok}, status_code=status_code)


@router.get("/models", response_class=HTMLResponse)
def models_page(request: Request, user: User = Depends(require_internal),
                db: Session = Depends(get_db)):
    return _render(request, user, db)


def _parse_spec(model_type: str, spec_text: str):
    if model_type in ("logistic", "ols"):
        try:
            return json.loads(spec_text), None
        except Exception as exc:  # noqa: BLE001
            return None, f"Coefficient spec is not valid JSON: {exc}"
    return None, None


@router.post("/models/register")
async def register(request: Request, name: str = Form(...), version: str = Form(...),
                   segment: str = Form("Guarantee"), model_type: str = Form("synthetic"),
                   artifact_path: str = Form(""), spec: str = Form(""),
                   file: Optional[UploadFile] = File(None),
                   auc: str = Form(""), recall: str = Form(""),
                   precision: str = Form(""), fn_rate: str = Form(""),
                   notes: str = Form(""), user: User = Depends(require_internal),
                   db: Session = Depends(get_db)):
    spec_obj, spec_err = _parse_spec(model_type, spec)
    if spec_err:
        return _render(request, user, db, error=spec_err, status_code=400)
    path = artifact_path.strip() or None
    if model_type == "xgboost" and file is not None and file.filename:
        content = await file.read()
        safe = file.filename.replace("/", "_").replace("\\", "_")
        dest = MODELS_DIR / f"{version.strip()}__{safe}"
        dest.write_bytes(content)
        path = str(dest)
    try:
        governance.register_model(
            db, actor=user.username, name=name.strip(), version=version.strip(),
            segment=segment, model_type=model_type,
            is_synthetic=(model_type == "synthetic"), artifact_path=path, spec=spec_obj,
            auc=_to_float(auc), recall=_to_float(recall),
            precision=_to_float(precision), fn_rate=_to_float(fn_rate), notes=notes)
        db.commit()
    except governance.GovernanceError as exc:
        return _render(request, user, db, error=str(exc), status_code=400)
    return RedirectResponse("/models", status_code=303)


@router.get("/models/{model_id}/edit", response_class=HTMLResponse)
def edit_form(model_id: int, request: Request, user: User = Depends(require_internal),
              db: Session = Depends(get_db)):
    row = db.get(ModelRegistry, model_id)
    if row is None:
        return RedirectResponse("/models", status_code=303)
    return templates.TemplateResponse("models_edit.html", {
        "request": request, "user": user, "screen": "models", "row": row,
        "spec_text": json.dumps(row.spec, indent=2) if row.spec else "",
        "locked": row.status == "active"})


@router.post("/models/{model_id}/edit")
def edit_save(model_id: int, request: Request, name: str = Form(...),
              model_type: str = Form("synthetic"), artifact_path: str = Form(""),
              spec: str = Form(""), auc: str = Form(""), recall: str = Form(""),
              precision: str = Form(""), fn_rate: str = Form(""), notes: str = Form(""),
              user: User = Depends(require_internal), db: Session = Depends(get_db)):
    spec_obj, spec_err = _parse_spec(model_type, spec)
    if spec_err:
        return _render(request, user, db, error=spec_err, status_code=400)
    path = artifact_path.strip() or None
    try:
        governance.update_model(
            db, actor=user.username, model_id=model_id, name=name.strip(),
            model_type=model_type, kind=model_type,
            is_synthetic=(model_type == "synthetic"), artifact_path=path, spec=spec_obj,
            auc=_to_float(auc), recall=_to_float(recall),
            precision=_to_float(precision), fn_rate=_to_float(fn_rate), notes=notes or None)
        db.commit()
    except governance.GovernanceError as exc:
        return _render(request, user, db, error=str(exc), status_code=400)
    return RedirectResponse("/models", status_code=303)


@router.post("/models/activate")
def activate(request: Request, model_id: int = Form(...),
             user: User = Depends(require_internal), db: Session = Depends(get_db)):
    try:
        row = governance.activate_model(db, approver=user.username, model_id=model_id)
        db.commit()
        return _render(request, user, db, ok=f"Activated {row.name} {row.version}.")
    except governance.GovernanceError as exc:
        db.rollback()
        return _render(request, user, db, error=str(exc), status_code=400)


@router.post("/models/retire")
def retire(request: Request, model_id: int = Form(...),
           user: User = Depends(require_internal), db: Session = Depends(get_db)):
    try:
        governance.retire_model(db, actor=user.username, model_id=model_id)
        db.commit()
    except governance.GovernanceError as exc:
        db.rollback()
        return _render(request, user, db, error=str(exc), status_code=400)
    return RedirectResponse("/models", status_code=303)
