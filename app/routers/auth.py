"""Login, logout, and per-user UI preferences."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require_user
from app.auth.security import authenticate
from app.db import audit
from app.db.database import get_db
from app.db.models import User
from app.templating import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, db: Session = Depends(get_db)):
    if current_user(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "screen": "login",
                                                     "user": None, "error": None})


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...),
          db: Session = Depends(get_db)):
    user = authenticate(db, username, password)
    if not user:
        return templates.TemplateResponse(
            "login.html", {"request": request, "screen": "login", "user": None,
                           "error": "Invalid username or password."}, status_code=401)
    request.session["user_id"] = user.id
    audit.record(db, actor=user.username, action="auth.login", entity_type="user",
                 entity_id=user.username)
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.post("/ui-mode")
def set_ui_mode(request: Request, mode: str = Form(...),
                user: User = Depends(require_user), db: Session = Depends(get_db)):
    user.ui_mode = "compact" if mode == "compact" else "guided"
    db.commit()
    referer = request.headers.get("referer", "/dashboard")
    return RedirectResponse(referer, status_code=303)
