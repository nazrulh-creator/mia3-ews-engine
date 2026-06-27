"""App-wide settings — notably which visualisation tiers are enabled.

Values are persisted in the app_settings table and mirrored in a small
in-process cache so templates can gate charts without a DB hit per render.
The cache is refreshed on change and on startup.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import audit
from app.db.models import AppSetting

VIZ_TIERS = ("tier1", "tier2", "tier3")
_DEFAULTS = {f"viz_{t}": "on" for t in VIZ_TIERS}
_CACHE: Dict[str, bool] = {t: True for t in VIZ_TIERS}


def _to_bool(v: str) -> bool:
    return str(v).strip().lower() in {"on", "1", "true", "yes"}


def load_cache(db: Session) -> None:
    """Populate the cache from the DB (defaults to all-on)."""
    rows = {s.key: s.value for s in db.execute(select(AppSetting)).scalars().all()}
    for t in VIZ_TIERS:
        _CACHE[t] = _to_bool(rows.get(f"viz_{t}", _DEFAULTS[f"viz_{t}"]))


class _Flags:
    """Attribute access for templates: viz_flags().tier1 etc."""
    @property
    def tier1(self) -> bool: return _CACHE["tier1"]
    @property
    def tier2(self) -> bool: return _CACHE["tier2"]
    @property
    def tier3(self) -> bool: return _CACHE["tier3"]
    @property
    def any(self) -> bool: return any(_CACHE.values())
    @property
    def all(self) -> bool: return all(_CACHE.values())


_FLAGS = _Flags()


def viz_flags() -> _Flags:
    return _FLAGS


def set_viz_flags(db: Session, *, actor: str, tier1: bool, tier2: bool, tier3: bool) -> None:
    """Persist the viz tier toggles, refresh the cache, and audit the change."""
    before = dict(_CACHE)
    new = {"tier1": tier1, "tier2": tier2, "tier3": tier3}
    for t in VIZ_TIERS:
        key = f"viz_{t}"
        row = db.get(AppSetting, key)
        val = "on" if new[t] else "off"
        if row is None:
            db.add(AppSetting(key=key, value=val, updated_by=actor))
        else:
            row.value = val
            row.updated_by = actor
            row.updated_at = datetime.now(timezone.utc)
        _CACHE[t] = new[t]
    audit.record(db, actor=actor, action="config.viz", entity_type="settings",
                 before=before, after=new, detail="Updated visualisation tiers.")
