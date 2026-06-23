"""Batch scoring engine — the scoring core (Phase 1).

Given a validated portfolio frame and the active model, it produces one fully
populated result record per account: probability, the 50/30/20 risk score and
band, a confidence score and routing decision, and a stored explanation.

This module has NO database or web dependency, so it is unit-testable in
isolation and reused by the CLI, the scheduled run, and the web upload path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from app.core import confidence as C
from app.core import explain as E
from app.core import scoring as S
from app.core.features import MODEL_FEATURE_NAMES
from app.core.model import ModelWrapper, get_active_model
from app.core.validation import ValidationResult, validate

# A calibrator maps a raw probability to a calibrated one. Identity = none.
Calibrator = Callable[[np.ndarray], np.ndarray]


def _route(band: str, conf: C.Confidence) -> str:
    """Confidence-based routing (feature 4.7)."""
    high_risk = band in {"Very High Risk", "High Risk"}
    elevated = high_risk or band == "Moderate Risk"
    if conf.band == "high":
        return "fast_track" if high_risk else "no_review"
    # borderline / low confidence
    return "needs_review" if elevated else "no_review"


@dataclass
class BatchOutput:
    records: List[Dict[str, object]] = field(default_factory=list)
    validation: Optional[ValidationResult] = None
    model_name: str = ""
    model_version: str = ""
    is_synthetic: bool = True
    calibrated: bool = False

    @property
    def n_scored(self) -> int:
        return len(self.records)

    def band_counts(self) -> Dict[str, int]:
        out = {b: 0 for b in S.BANDS}
        for r in self.records:
            out[str(r["band"])] += 1
        return out


def _defaulted_per_account(vr: ValidationResult) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for issue in vr.issues:
        if issue.problem == "defaulted" and issue.account_id is not None:
            counts[str(issue.account_id)] = counts.get(str(issue.account_id), 0) + 1
    return counts


def score_frame(df: pd.DataFrame, *, model: Optional[ModelWrapper] = None,
                cfg: S.RiskConfig = S.DEFAULT_CONFIG,
                calibrator: Optional[Calibrator] = None,
                validation: Optional[ValidationResult] = None) -> BatchOutput:
    """Score an already-loaded portfolio frame end to end."""
    cfg.validate()
    model = model or get_active_model()
    vr = validation if validation is not None else validate(df)
    accepted = vr.accepted

    out = BatchOutput(validation=vr, model_name=model.name,
                      model_version=model.version, is_synthetic=model.is_synthetic,
                      calibrated=calibrator is not None)
    if accepted.empty:
        return out

    X = accepted[MODEL_FEATURE_NAMES].astype(float)
    raw_proba = model.predict_proba(X)
    proba = calibrator(raw_proba) if calibrator is not None else raw_proba
    proba = np.clip(np.asarray(proba, dtype=float), 0.0, 1.0)

    contrib = E.contributions_matrix(model, accepted)
    defaulted = _defaulted_per_account(vr)
    model_perf = (C.SYNTHETIC_MODEL_PERFORMANCE if model.is_synthetic
                  else C.DEFAULT_MODEL_PERFORMANCE)

    records: List[Dict[str, object]] = []
    for pos, (idx, row) in enumerate(accepted.iterrows()):
        p = float(proba[pos])
        risk = S.compute_risk(p, float(row["ead"]), float(row["outstanding_ratio"]), cfg)
        acc_id = str(row["account_id"])
        conf = C.compute_confidence(
            row, defaulted_fields=defaulted.get(acc_id, 0),
            model_performance=model_perf, calibrated=out.calibrated,
        )
        factors = E.top_factors(contrib[pos], row, k=5)
        records.append({
            "account_id": acc_id,
            "fi_id": str(row.get("fi_id")),
            "fi_name": row.get("fi_name"),
            "scheme": str(row.get("scheme")),
            "sector": str(row.get("sector")),
            "branch": row.get("branch"),
            "as_of_date": row.get("as_of_date"),
            "probability": round(p, 6),
            "probability_raw": round(float(raw_proba[pos]), 6),
            "ead": float(row["ead"]),
            "outstanding_ratio": float(row["outstanding_ratio"]),
            "pd_rank": risk.pd_rank,
            "ead_rank": risk.ead_rank,
            "outratio_rank": risk.outratio_rank,
            "risk_score": risk.risk_score,
            "band": risk.band,
            "breakdown": risk.breakdown,
            "features": {f: float(row[f]) for f in MODEL_FEATURE_NAMES},
            "confidence": conf.score,
            "confidence_band": conf.band,
            "confidence_components": conf.components,
            "review_status": _route(risk.band, conf),
            "top_factors": factors,
            "explanation_operational": E.explain_text(factors, "operational"),
            "explanation_technical": E.explain_text(factors, "technical"),
            "explanation_simplified": E.explain_text(factors, "simplified"),
            "defaulted_fields": defaulted.get(acc_id, 0),
        })
    out.records = records
    return out
