"""Configuration — visualisation-tier toggles (internal-risk only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_internal, require_staff_view
from app.db.database import get_db
from app.db.models import User
from app.services import appsettings
from app.templating import templates

router = APIRouter()


@router.get("/config", response_class=HTMLResponse)
def config_page(request: Request, user: User = Depends(require_staff_view),
                db: Session = Depends(get_db)):
    appsettings.load_cache(db)  # ensure fresh
    return templates.TemplateResponse("config.html", {
        "request": request, "user": user, "screen": "config",
        "viz": appsettings.viz_flags()})


@router.post("/config/viz")
def save_viz(request: Request, preset: str = Form(""), tier1: str = Form(""),
             tier2: str = Form(""), tier3: str = Form(""),
             user: User = Depends(require_internal), db: Session = Depends(get_db)):
    if preset == "all_on":
        t1 = t2 = t3 = True
    elif preset == "all_off":
        t1 = t2 = t3 = False
    else:
        t1, t2, t3 = bool(tier1), bool(tier2), bool(tier3)
    appsettings.set_viz_flags(db, actor=user.username, tier1=t1, tier2=t2, tier3=t3)
    db.commit()
    return RedirectResponse("/config", status_code=303)
