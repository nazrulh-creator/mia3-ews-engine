"""The in-app User Guide and Quick Start.

`/guide` renders the full, anchored manual. `/guide?screen=<key>` redirects to
the section that explains that screen — this is what the contextual "User guide"
link in every screen's purpose banner points to. `/quickstart` is the one-page
getting-started card (reachable even before login).
"""
from __future__ import annotations

from typing import Optional

import io

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from app import guide_content
from app.auth.deps import current_user
from app.db.database import get_db
from app.services.guide_export import build_guide_docx, build_quickstart_docx
from app.templating import templates

router = APIRouter()

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx_response(data: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(io.BytesIO(data), media_type=_DOCX,
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


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


@router.get("/guide/download")
def guide_download():
    """Download the full User Guide as a Word document."""
    return _docx_response(build_guide_docx(), "MIA3_User_Guide.docx")


@router.get("/quickstart/download")
def quickstart_download():
    """Download the Quick Start as a Word document."""
    return _docx_response(build_quickstart_docx(), "MIA3_Quick_Start.docx")
