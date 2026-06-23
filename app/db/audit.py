"""Hash-chained, tamper-evident audit store (adopted from MicroFlex).

Every consequential action is appended as an AuditEvent whose `hash` covers
its own content plus the previous event's hash. Any later edit or deletion
breaks the chain and is detectable by verify_chain(). Writing an audit event
never mutates an earlier one, and the app exposes no update/delete path.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AuditEvent

GENESIS = "0" * 64


def _canonical(payload: Dict) -> str:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))


def _digest(seq: int, ts: str, environment: str, actor: str, action: str,
            entity_type: Optional[str], entity_id: Optional[str],
            before: Optional[dict], after: Optional[dict], detail: Optional[str],
            prev_hash: str) -> str:
    payload = {
        "seq": seq, "ts": ts, "env": environment, "actor": actor,
        "action": action, "entity_type": entity_type, "entity_id": entity_id,
        "before": before, "after": after, "detail": detail, "prev_hash": prev_hash,
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _last_event(db: Session, environment: str) -> Optional[AuditEvent]:
    stmt = (select(AuditEvent)
            .where(AuditEvent.environment == environment)
            .order_by(AuditEvent.seq.desc()).limit(1))
    return db.execute(stmt).scalars().first()


def record(db: Session, *, actor: str, action: str,
           entity_type: Optional[str] = None, entity_id: Optional[str] = None,
           before: Optional[dict] = None, after: Optional[dict] = None,
           detail: Optional[str] = None) -> AuditEvent:
    """Append one audit event to the chain for the current environment."""
    environment = get_settings().environment
    last = _last_event(db, environment)
    seq = (last.seq + 1) if last else 1
    prev_hash = last.hash if last else GENESIS
    # Store naive-UTC so the timestamp round-trips through the DB identically
    # (a tz-aware isoformat would not match after reload), and hash the exact
    # value we persist.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    h = _digest(seq, now.isoformat(), environment, actor, action, entity_type,
                entity_id, before, after, detail, prev_hash)
    event = AuditEvent(
        seq=seq, environment=environment, ts=now, actor=actor, action=action,
        entity_type=entity_type, entity_id=entity_id, before=before, after=after,
        detail=detail, prev_hash=prev_hash, hash=h,
    )
    db.add(event)
    db.flush()
    return event


def verify_chain(db: Session, environment: Optional[str] = None) -> Dict[str, object]:
    """Recompute the chain and report the first break, if any."""
    env = environment or get_settings().environment
    stmt = (select(AuditEvent)
            .where(AuditEvent.environment == env)
            .order_by(AuditEvent.seq.asc()))
    events: List[AuditEvent] = list(db.execute(stmt).scalars().all())
    prev = GENESIS
    for ev in events:
        expected = _digest(ev.seq, ev.ts.isoformat(), ev.environment, ev.actor,
                           ev.action, ev.entity_type, ev.entity_id, ev.before,
                           ev.after, ev.detail, prev)
        if ev.prev_hash != prev or ev.hash != expected:
            return {"ok": False, "events": len(events), "broken_at_seq": ev.seq}
        prev = ev.hash
    return {"ok": True, "events": len(events), "broken_at_seq": None}
