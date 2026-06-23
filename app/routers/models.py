"""Model registry management — register, edit, activate (dual control), retire.

The scoring engine only ever uses the ACTIVE entry's artifact (a coupling
rule). Activation is dual-controlled: the person who registered a model cannot
activate it, and the artifact is validated against the data contract first.
Retiring (the safe direction) is single-control and immediate.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_internal
from app.config import MODELS_DIR
from app.core.model import validate_artifact
from app.db.database import get_db
from app.db.models import ModelRegistry, User
from app.services import governance
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
    active = governance.active_model_row(db)
    # Pre-flight validation hint for entries that carry an artifact path.
    validations = {}
    for r in rows:
        if r.artifact_path:
            good, msg = validate_artifact(r.artifact_path)
            validations[r.id] = {"ok": good, "msg": msg}
    return templates.TemplateResponse("models.html", {
        "request": request, "user": user, "screen": "models", "rows": rows,
        "active": active, "validations": validations, "error": error, "ok": ok},
        status_code=status_code)


@router.get("/models", response_class=HTMLResponse)
def models_page(request: Request, user: User = Depends(require_internal),
                db: Session = Depends(get_db)):
    return _render(request, user, db)


@router.post("/models/register")
async def register(request: Request, name: str = Form(...), version: str = Form(...),
                   kind: str = Form("real"), artifact_path: str = Form(""),
                   file: Optional[UploadFile] = File(None),
                   auc: str = Form(""), recall: str = Form(""),
                   precision: str = Form(""), fn_rate: str = Form(""),
                   notes: str = Form(""), user: User = Depends(require_internal),
                   db: Session = Depends(get_db)):
    path = artifact_path.strip() or None
    if file is not None and file.filename:
        content = await file.read()
        safe = file.filename.replace("/", "_").replace("\\", "_")
        dest = MODELS_DIR / f"{version.strip()}__{safe}"
        dest.write_bytes(content)
        path = str(dest)
    is_synthetic = kind == "synthetic" or path is None
    try:
        governance.register_model(
            db, actor=user.username, name=name.strip(), version=version.strip(),
            kind=kind, is_synthetic=is_synthetic, artifact_path=path,
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
        "locked": row.status == "active"})


@router.post("/models/{model_id}/edit")
def edit_save(model_id: int, request: Request, name: str = Form(...), kind: str = Form("real"),
              artifact_path: str = Form(""), auc: str = Form(""), recall: str = Form(""),
              precision: str = Form(""), fn_rate: str = Form(""), notes: str = Form(""),
              user: User = Depends(require_internal), db: Session = Depends(get_db)):
    path = artifact_path.strip() or None
    try:
        governance.update_model(
            db, actor=user.username, model_id=model_id, name=name.strip(), kind=kind,
            is_synthetic=(kind == "synthetic" or path is None), artifact_path=path,
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
