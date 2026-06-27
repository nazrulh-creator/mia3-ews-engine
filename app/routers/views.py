"""Role-based views: dashboard, accounts, runs, demo, learnings, audit, models."""
from __future__ import annotations

import io
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import current_user, fi_scope, require_internal, require_user
from app.config import get_settings
from app.core import explain as E
from app.core.features import MODEL_FEATURE_NAMES, contract_as_dict
from app.core.model import get_active_model
from app.core.synthetic import demo_portfolio
from app.core.validation import read_table
from app.db import audit
from app.db.database import get_db
from app.db.models import (AccountScore, Learning, ModelRegistry, PortfolioAlert,
                          ProblemReport, ScoringRun, User)
from app.services import governance, runs
from app.services.case_report import build_case_report
from app.templating import templates

router = APIRouter()
settings = get_settings()


def _ctx(request: Request, user: User, screen: str, **kw) -> dict:
    base = {"request": request, "user": user, "screen": screen}
    base.update(kw)
    return base


# --- Dashboard -------------------------------------------------------------
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(require_user),
              db: Session = Depends(get_db)):
    scope = fi_scope(user)
    run = runs.latest_run(db)
    counts, by_fi, by_scheme, by_sector, by_segment, alerts = {}, [], [], [], [], []
    exposure, points = {}, []
    if run:
        counts = runs.band_counts(db, run.id, fi_id=scope)
        by_fi = runs.breakdown(db, run.id, "fi_id", fi_id=scope)
        by_scheme = runs.breakdown(db, run.id, "scheme", fi_id=scope)
        by_sector = runs.breakdown(db, run.id, "sector", fi_id=scope)
        by_segment = runs.breakdown(db, run.id, "segment", fi_id=scope)
        exposure = runs.exposure_by_band(db, run.id, fi_id=scope)
        points = runs.risk_points(db, run.id, fi_id=scope)
        alerts = db.execute(select(PortfolioAlert).where(PortfolioAlert.run_ref == run.run_ref)
                            ).scalars().all()
        if scope:
            alerts = [a for a in alerts if not (a.dimension == "fi" and a.key != scope)]
    trend = runs.trend(db, fi_id=scope)
    active_models = governance.active_models_by_segment(db)   # {segment: [rows]}
    active_rules = governance.active_rules_by_segment(db)     # {segment: rule}
    return templates.TemplateResponse("dashboard.html", _ctx(
        request, user, "dashboard", run=run, counts=counts, by_fi=by_fi,
        by_scheme=by_scheme, by_sector=by_sector, by_segment=by_segment,
        alerts=alerts, trend=trend, active_models=active_models,
        active_rules=active_rules, exposure=exposure, points=points))


# --- Movers (run-over-run band migration) ---------------------------------
@router.get("/movers", response_class=HTMLResponse)
def movers(request: Request, user: User = Depends(require_user),
           db: Session = Depends(get_db)):
    scope = fi_scope(user)
    run = runs.latest_run(db)
    prev = runs.previous_published_run(db, run) if run else None
    mig = runs.band_migration(db, run, prev, fi_id=scope) if (run and prev) else None
    return templates.TemplateResponse("movers.html", _ctx(
        request, user, "movers", run=run, prev=prev, mig=mig))


# --- Accounts list + worklist ---------------------------------------------
@router.get("/accounts", response_class=HTMLResponse)
def accounts(request: Request, band: Optional[str] = None, fi: Optional[str] = None,
             scheme: Optional[str] = None, sector: Optional[str] = None,
             segment: Optional[str] = None, worklist: int = 0,
             user: User = Depends(require_user), db: Session = Depends(get_db)):
    scope = fi_scope(user)
    run = runs.latest_run(db)
    rows = []
    if run:
        stmt = select(AccountScore).where(AccountScore.run_id == run.id)
        if scope:
            stmt = stmt.where(AccountScore.fi_id == scope)
        if band:
            stmt = stmt.where(AccountScore.band == band)
        if fi:
            stmt = stmt.where(AccountScore.fi_id == fi)
        if scheme:
            stmt = stmt.where(AccountScore.scheme == scheme)
        if sector:
            stmt = stmt.where(AccountScore.sector == sector)
        if segment:
            stmt = stmt.where(AccountScore.segment == segment)
        if worklist:
            stmt = stmt.where(AccountScore.review_status.in_(["needs_review", "fast_track"]))
        stmt = stmt.order_by(AccountScore.risk_score.desc()).limit(500)
        rows = db.execute(stmt).scalars().all()
    screen = "worklist" if worklist else "accounts"
    return templates.TemplateResponse("accounts.html", _ctx(
        request, user, screen, rows=rows, run=run, worklist=worklist,
        filters={"band": band, "fi": fi, "scheme": scheme, "sector": sector,
                 "segment": segment}))


@router.get("/accounts/{score_id}", response_class=HTMLResponse)
def account_detail(score_id: int, request: Request, lime: int = 0,
                   user: User = Depends(require_user), db: Session = Depends(get_db)):
    score = db.get(AccountScore, score_id)
    if score is None:
        return RedirectResponse("/accounts", status_code=303)
    scope = fi_scope(user)
    if scope and score.fi_id != scope:
        return RedirectResponse("/accounts", status_code=303)
    lime_result = None
    if lime and score.features:
        model = get_active_model()
        X = pd.DataFrame([score.features])[MODEL_FEATURE_NAMES]
        lime_result = E.lime_explain(model, X, 0, background=X)
    run = db.get(ScoringRun, score.run_id)
    return templates.TemplateResponse("account_detail.html", _ctx(
        request, user, "account_detail", score=score, run=run, lime_result=lime_result))


@router.get("/accounts/{score_id}/report")
def account_report(score_id: int, user: User = Depends(require_user),
                   db: Session = Depends(get_db)):
    score = db.get(AccountScore, score_id)
    if score is None:
        return RedirectResponse("/accounts", status_code=303)
    scope = fi_scope(user)
    if scope and score.fi_id != scope:
        return RedirectResponse("/accounts", status_code=303)
    run = db.get(ScoringRun, score.run_id)
    data = build_case_report(score, run_ref=run.run_ref if run else "—")
    audit.record(db, actor=user.username, action="report.generate", entity_type="account",
                 entity_id=score.account_id)
    db.commit()
    fname = f"EWS_Case_{score.account_id}.docx"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# --- Runs: upload / manual run / list -------------------------------------
@router.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request, user: User = Depends(require_internal),
              db: Session = Depends(get_db)):
    rows = db.execute(select(ScoringRun).order_by(ScoringRun.created_at.desc()).limit(50)
                      ).scalars().all()
    return templates.TemplateResponse("runs.html", _ctx(request, user, "runs", rows=rows))


@router.post("/runs/upload")
async def runs_upload(request: Request, file: UploadFile = File(...),
                      hold: int = Form(0), user: User = Depends(require_internal),
                      db: Session = Depends(get_db)):
    content = await file.read()
    try:
        df = read_table(content, file.filename or "upload.csv")
    except Exception as exc:  # noqa: BLE001
        return templates.TemplateResponse("runs.html", _ctx(
            request, user, "runs",
            rows=db.execute(select(ScoringRun).order_by(ScoringRun.created_at.desc())
                            .limit(50)).scalars().all(),
            error=f"Could not read file: {exc}"), status_code=400)
    run = runs.execute_run(db, df, source="file", actor=user.username,
                           input_fingerprint=runs.fingerprint(content),
                           hold_for_signoff=bool(hold))
    db.commit()
    return RedirectResponse(f"/runs#{run.run_ref}", status_code=303)


@router.post("/runs/publish/{run_id}")
def runs_publish(run_id: int, request: Request, user: User = Depends(require_internal),
                 db: Session = Depends(get_db)):
    run = db.get(ScoringRun, run_id)
    if run and not run.published:
        run.published = True
        run.checkpoint_status = "published"
        audit.record(db, actor=user.username, action="run.publish", entity_type="run",
                     entity_id=run.run_ref, detail="Checkpoint sign-off; results published.")
        db.commit()
    return RedirectResponse("/runs", status_code=303)


# --- Demonstration mode ----------------------------------------------------
@router.get("/demo", response_class=HTMLResponse)
def demo_page(request: Request, user: User = Depends(require_user),
              db: Session = Depends(get_db)):
    last_demo = db.execute(select(ScoringRun).where(ScoringRun.source == "demo")
                           .order_by(ScoringRun.created_at.desc()).limit(1)).scalars().first()
    return templates.TemplateResponse("demo.html", _ctx(request, user, "demo",
                                                        last_demo=last_demo))


@router.post("/demo/run")
def demo_run(request: Request, user: User = Depends(require_internal),
             db: Session = Depends(get_db)):
    # Vary the seed per demo run so account ids stay stable but scores drift —
    # otherwise repeated demo runs are identical and Movers shows no change.
    n = db.execute(select(func.count(ScoringRun.id))
                   .where(ScoringRun.source == "demo")).scalar() or 0
    df = demo_portfolio(seed=42 + n)
    run = runs.execute_run(db, df, source="demo", actor=user.username,
                           input_fingerprint="synthetic-demo")
    db.commit()
    return RedirectResponse(f"/runs#{run.run_ref}", status_code=303)


# --- Learnings library -----------------------------------------------------
@router.get("/learnings", response_class=HTMLResponse)
def learnings_page(request: Request, user: User = Depends(require_user),
                   db: Session = Depends(get_db)):
    items = db.execute(select(Learning).order_by(Learning.created_at.desc()).limit(200)
                       ).scalars().all()
    return templates.TemplateResponse("learnings.html", _ctx(request, user, "learnings",
                                                            items=items))


@router.post("/learnings/add")
def learnings_add(request: Request, title: str = Form(...), body: str = Form(...),
                  category: str = Form("note"), linked_account: str = Form(""),
                  user: User = Depends(require_user), db: Session = Depends(get_db)):
    item = Learning(author=user.username, category=category, title=title, body=body,
                    linked_account=linked_account or None)
    db.add(item)
    audit.record(db, actor=user.username, action="learning.add", entity_type="learning",
                 detail=title)
    db.commit()
    return RedirectResponse("/learnings", status_code=303)


# --- Audit -----------------------------------------------------------------
@router.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, user: User = Depends(require_internal),
               db: Session = Depends(get_db)):
    events = db.execute(select(audit.AuditEvent).order_by(audit.AuditEvent.seq.desc())
                        .limit(300)).scalars().all()
    integrity = audit.verify_chain(db)
    return templates.TemplateResponse("audit.html", _ctx(request, user, "audit",
                                                        events=events, integrity=integrity))


# --- Data contract ---------------------------------------------------------
@router.get("/contract", response_class=HTMLResponse)
def contract_page(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse("contract.html",
                                      _ctx(request, user, "contract",
                                           contract=contract_as_dict()))


# --- Universal problem reporting ------------------------------------------
@router.post("/report-problem")
def report_problem(request: Request, screen: str = Form(""), record_ref: str = Form(""),
                   detail: str = Form(...), user: User = Depends(require_user),
                   db: Session = Depends(get_db)):
    ev = audit.record(db, actor=user.username, action="problem.report",
                      entity_type="screen", entity_id=screen, detail=detail)
    db.add(ProblemReport(reporter=user.username, screen=screen,
                         record_ref=record_ref or None, detail=detail, audit_ref=ev.hash[:12]))
    db.commit()
    referer = request.headers.get("referer", "/dashboard")
    return RedirectResponse(referer, status_code=303)
