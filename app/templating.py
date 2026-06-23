"""Shared Jinja2 environment with global helpers."""
from __future__ import annotations

from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, get_settings
from app.core.scoring import BAND_META, BANDS
from app.auth.deps import ROLE_LABELS
from app import web_help
from app import guide_content

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# Globals available in every template.
templates.env.globals.update(
    settings=get_settings(),
    BAND_META=BAND_META,
    BANDS=BANDS,
    ROLE_LABELS=ROLE_LABELS,
    purpose=web_help.purpose,
    field_help=web_help.FIELDS,
    guide_anchor=guide_content.section_for_screen,
)


def fmt_money(v) -> str:
    try:
        return f"RM {float(v):,.0f}"
    except (TypeError, ValueError):
        return "—"


def fmt_pct(v) -> str:
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


templates.env.filters["money"] = fmt_money
templates.env.filters["pct"] = fmt_pct
