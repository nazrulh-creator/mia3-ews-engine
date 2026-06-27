"""Model-performance monitoring against the deck's go-live goals.

Once realised MIA 3 outcomes are recorded, this computes Recall, Precision,
the false-negative rate and AUC per run and segment, and checks them against
the goals stated in the deck: FN < 20%, Recall > 75%, AUC > 65%.

It also exposes the selective-labels caveat (how many flagged accounts had an
intervention applied), since that biases the labels — the issue raised in the
reject-inference evaluation.
"""
from __future__ import annotations

import hashlib
from typing import Dict, List, Optional

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AccountScore, Outcome, ScoringRun

# Operating point: the probability at/above which the model "predicts MIA 3".
OPERATING_POINT = 0.50
GOAL_RECALL = 0.75
GOAL_AUC = 0.65
GOAL_FN_MAX = 0.20


def _auc(probs: List[float], labels: List[bool]) -> Optional[float]:
    """Rank-based AUC (Mann–Whitney). None if only one class present."""
    pos = [p for p, l in zip(probs, labels) if l]
    neg = [p for p, l in zip(probs, labels) if not l]
    if not pos or not neg:
        return None
    arr = np.asarray(probs, dtype=float)
    order = np.argsort(arr, kind="mergesort")
    ranks = np.empty(len(arr), dtype=float)
    ranks[order] = np.arange(1, len(arr) + 1)
    sum_pos = float(sum(ranks[i] for i, l in enumerate(labels) if l))
    n_pos, n_neg = len(pos), len(neg)
    return (sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def _seed(run_ref: str) -> int:
    return int(hashlib.sha256(run_ref.encode()).hexdigest()[:8], 16)


def record_outcome(db: Session, *, score: AccountScore, run_ref: str,
                   actual_mia3: bool, intervention_applied: bool,
                   exit_reason: Optional[str], source: str, actor: str) -> Outcome:
    """Record (or update) the realised outcome for one scored account."""
    existing = db.execute(select(Outcome).where(
        Outcome.run_ref == run_ref, Outcome.account_id == score.account_id)).scalars().first()
    if existing:
        existing.actual_mia3 = actual_mia3
        existing.intervention_applied = intervention_applied
        existing.exit_reason = exit_reason or None
        existing.source = source
        existing.recorded_by = actor
        db.flush()
        return existing
    out = Outcome(
        score_id=score.id, run_ref=run_ref, account_id=score.account_id,
        segment=score.segment or "Guarantee", probability=score.probability,
        predicted_positive=score.probability >= OPERATING_POINT, band=score.band,
        actual_mia3=actual_mia3, intervention_applied=intervention_applied,
        exit_reason=exit_reason or None, source=source, recorded_by=actor)
    db.add(out)
    db.flush()
    return out


def simulate_outcomes_for_run(db: Session, run: ScoringRun, actor: str) -> int:
    """TEST-only: synthesise realised outcomes so the view is demonstrable.

    Actual MIA 3 is drawn correlated (weakly) with the model probability, which
    reproduces the deck's picture — high recall, very low precision, AUC near 0.5.
    """
    scores = db.execute(select(AccountScore).where(AccountScore.run_id == run.id)).scalars().all()
    rng = np.random.RandomState(_seed(run.run_ref))
    for s in scores:
        base = float(np.clip(0.04 + 0.30 * s.probability + rng.normal(0, 0.06), 0.0, 0.95))
        actual = bool(rng.random_sample() < base)
        intervened = bool(s.band in ("Very High Risk", "High Risk") and rng.random_sample() < 0.4)
        record_outcome(db, score=s, run_ref=run.run_ref, actual_mia3=actual,
                       intervention_applied=intervened, exit_reason=None,
                       source="simulated", actor=actor)
    return len(scores)


def compute_performance(db: Session) -> List[Dict[str, object]]:
    """Per (run, segment) metrics with goal pass/fail flags, newest first."""
    rows = db.execute(select(Outcome)).scalars().all()
    groups: Dict[tuple, List[Outcome]] = {}
    for o in rows:
        groups.setdefault((o.run_ref, o.segment), []).append(o)

    results = []
    for (run_ref, segment), items in groups.items():
        n = len(items)
        probs = [i.probability for i in items]
        labels = [i.actual_mia3 for i in items]
        tp = sum(1 for i in items if i.predicted_positive and i.actual_mia3)
        fp = sum(1 for i in items if i.predicted_positive and not i.actual_mia3)
        fn = sum(1 for i in items if not i.predicted_positive and i.actual_mia3)
        recall = tp / (tp + fn) if (tp + fn) else None
        precision = tp / (tp + fp) if (tp + fp) else None
        fn_rate = fn / n if n else None
        auc = _auc(probs, labels)
        results.append({
            "run_ref": run_ref, "segment": segment, "n": n, "events": sum(labels),
            "recall": recall, "precision": precision, "fn_rate": fn_rate, "auc": auc,
            "intervention_rate": sum(1 for i in items if i.intervention_applied) / n if n else 0.0,
            "recall_ok": recall is not None and recall >= GOAL_RECALL,
            "auc_ok": auc is not None and auc >= GOAL_AUC,
            "fn_ok": fn_rate is not None and fn_rate < GOAL_FN_MAX,
        })
    results.sort(key=lambda r: (r["run_ref"], r["segment"]), reverse=True)
    return results


def performance_series(db: Session) -> Dict[str, Dict[str, list]]:
    """Per-segment, chronologically-ordered metric series for trend charts.

    {segment: {"x": [run labels], "recall": [...], "precision": [...],
               "auc": [...], "fn": [...]}}  (values 0..1, None where undefined).
    """
    rows = compute_performance(db)
    by_seg: Dict[str, list] = {}
    for r in rows:
        by_seg.setdefault(r["segment"], []).append(r)
    out: Dict[str, Dict[str, list]] = {}
    for seg, items in by_seg.items():
        items = sorted(items, key=lambda r: r["run_ref"])  # chronological (timestamped refs)
        out[seg] = {
            "x": [r["run_ref"].split("-")[-1] for r in items],  # short run label
            "recall": [r["recall"] for r in items],
            "precision": [r["precision"] for r in items],
            "auc": [r["auc"] for r in items],
            "fn": [r["fn_rate"] for r in items],
        }
    return out
