"""Tier 3 analytics — ensemble agreement / dispersion.

When a segment runs more than one active model, this scores a sample of the
latest run's accounts with each member (using their stored features) so the
spread between models is visible — the cases where the ensemble disagrees are
exactly the ones a validator should look at.
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.features import MODEL_FEATURE_NAMES
from app.core.model import build_model
from app.db.models import AccountScore
from app.services import governance, runs

_COLORS = ["#003A70", "#FF8819", "#4B6EEC", "#27ae60", "#c0392b", "#9b59b6"]


def ensemble_dispersion(db: Session, segment: str, *, fi_id: Optional[str] = None,
                        sample: int = 120) -> Optional[Dict[str, object]]:
    """Member probabilities across a sample of accounts (sorted by mean PD).

    Returns None unless the segment has at least two active models and data.
    """
    rows = governance.active_models_for_segment(db, segment)
    if len(rows) < 2:
        return None
    run = runs.latest_run(db)
    if run is None:
        return None
    stmt = select(AccountScore.features).where(
        AccountScore.run_id == run.id, AccountScore.segment == segment)
    if fi_id:
        stmt = stmt.where(AccountScore.fi_id == fi_id)
    feats = [f for (f,) in db.execute(stmt.limit(sample)).all() if f]
    if len(feats) < 2:
        return None

    X = pd.DataFrame(feats)
    for col in MODEL_FEATURE_NAMES:
        if col not in X.columns:
            X[col] = 0.0
    X = X[MODEL_FEATURE_NAMES].astype(float)

    members = [(r.version, build_model(r.model_type, name=r.name, version=r.version,
                                       artifact_path=r.artifact_path, spec=r.spec)) for r in rows]
    mat = np.column_stack([np.asarray(m.predict_proba(X), dtype=float) for _, m in members])
    order = np.argsort(mat.mean(axis=1))
    series = [{"name": ver, "color": _COLORS[i % len(_COLORS)],
               "values": [float(mat[order[j], i]) for j in range(len(order))]}
              for i, (ver, _) in enumerate(members)]
    spread = float(np.mean(mat.max(axis=1) - mat.min(axis=1)))
    return {"segment": segment, "series": series,
            "x": [str(i + 1) for i in range(len(order))],
            "spread": round(spread, 3), "n": len(order),
            "members": [ver for ver, _ in members]}
