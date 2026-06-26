"""MIA3 Early Warning Engine — FastAPI application entrypoint.

Wires the scoring core, governance, and the role-based web views into one
deployable app (a modular monolith, per the MicroFlex adopt-list). The app
carries SDA ownership marks, never CGC corporate branding.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_DIR, get_settings
from app.db.database import init_db, session_scope
from app.routers import (api, auth, guide, models, performance, review, rules,
                        tuning, views)
from app.services.seed import ensure_seed, ensure_segment_models

settings = get_settings()
app = FastAPI(title=settings.app_name, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, max_age=60 * 60 * 8)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

app.include_router(auth.router)
app.include_router(guide.router)
app.include_router(models.router)
app.include_router(performance.router)
app.include_router(rules.router)
app.include_router(views.router)
app.include_router(review.router)
app.include_router(tuning.router)
app.include_router(api.router)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    with session_scope() as db:
        ensure_seed(db)
        ensure_segment_models(db)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "environment": settings.environment,
            "app": settings.app_name, "owner": settings.owner_team}


@app.exception_handler(401)
async def _unauthorized(request: Request, exc) -> RedirectResponse:  # noqa: ANN001
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Login required."}, status_code=401)
    return RedirectResponse("/login", status_code=303)


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse("/dashboard", status_code=303)
