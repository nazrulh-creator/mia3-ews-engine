"""The in-app User Guide and Quick Start.

`/guide` renders the full, anchored manual. `/guide?screen=<key>` redirects to
the section that explains that screen — this is what the contextual "User guide"
link in every screen's purpose banner points to. `/quickstart` is the one-page
getting-started card (reachable even before login).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import guide_content
from app.auth.deps import current_user
from app.db.database import get_db
from app.templating import templates

router = APIRouter()


@router.get("/guide", response_class=HTMLResponse)
def guide(request: Request, screen: Optional[str] = None, db=Depends(get_db)):
    user = current_user(request, db)
    if screen:
        anchor = guide_content.section_for_screen(screen)
        return RedirectResponse(f"/guide#{anchor}", status_code=303)
    return templates.TemplateResponse("guide.html", {
        "request": request, "user": user, "screen": None,
        "sections": guide_content.SECTIONS, "toc": guide_content.toc()})


@router.get("/quickstart", response_class=HTMLResponse)
def quickstart(request: Request, db=Depends(get_db)):
    user = current_user(request, db)
    return templates.TemplateResponse("quickstart.html", {
        "request": request, "user": user, "screen": None})
