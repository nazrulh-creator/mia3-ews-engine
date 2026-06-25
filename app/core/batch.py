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
from app.core.features import DEFAULT_SEGMENT, MODEL_FEATURE_NAMES
from app.core.model import ModelWrapper, get_active_model
from app.core.validation import ValidationResult, validate

# A calibrator maps a raw probability to a calibrated one. Identity = none.
Calibrator = Callable[[np.ndarray], np.ndarray]
# A resolver returns the model that scores a given portfolio segment.
ModelResolver = Callable[[str], ModelWrapper]


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
    # {segment: (name, version, is_synthetic)} for the models actually used.
    segment_models: Dict[str, tuple] = field(default_factory=dict)

    @property
    def n_scored(self) -> int:
        return len(self.records)

    def band_counts(self) -> Dict[str, int]:
        out = {b: 0 for b in S.BANDS}
        for r in self.records:
            out[str(r["band"])] += 1
        return out


_FEATURE_SET = set(MODEL_FEATURE_NAMES)


def _defaulted_per_account(vr: ValidationResult) -> Dict[str, int]:
    """Count defaulted MODEL inputs per account.

    Only model features count toward confidence — defaulting an informational
    identity field (fi_name, branch, as_of_date, segment) is not a data-quality
    concern for scoring and must not reduce confidence.
    """
    counts: Dict[str, int] = {}
    for issue in vr.issues:
        if (issue.problem == "defaulted" and issue.account_id is not None
                and issue.column in _FEATURE_SET):
            counts[str(issue.account_id)] = counts.get(str(issue.account_id), 0) + 1
    return counts


def score_frame(df: pd.DataFrame, *, model: Optional[ModelWrapper] = None,
                cfg: S.RiskConfig = S.DEFAULT_CONFIG,
                calibrator: Optional[Calibrator] = None,
                validation: Optional[ValidationResult] = None,
                model_for_segment: Optional[ModelResolver] = None,
                segment_meta: Optional[Dict[str, tuple]] = None) -> BatchOutput:
    """Score a portfolio frame end to end, routing each segment to its model.

    Single-model callers (CLI, tests) pass `model` (or nothing → the active
    model) and every row is scored by it. The run service passes
    `model_for_segment` so Guarantee and Financing accounts are scored by their
    own governed models; `segment_meta` supplies the registry name/version to
    record per account.
    """
    cfg.validate()
    vr = validation if validation is not None else validate(df)
    accepted = vr.accepted.copy()
    out = BatchOutput(validation=vr, calibrated=calibrator is not None)
    if accepted.empty:
        fallback = model or get_active_model()
        out.model_name, out.model_version, out.is_synthetic = (
            fallback.name, fallback.version, fallback.is_synthetic)
        return out

    if "segment" not in accepted.columns:
        accepted["segment"] = DEFAULT_SEGMENT
    defaulted = _defaulted_per_account(vr)
    meta = segment_meta or {}

    def resolve(segment: str):
        if model_for_segment is not None:
            m = model_for_segment(segment)
        else:
            m = model or get_active_model()
        if segment in meta:
            name, version, is_syn = meta[segment]
        else:
            name, version, is_syn = m.name, m.version, m.is_synthetic
        return m, name, version, is_syn

    records: List[Dict[str, object]] = []
    for segment, group in accepted.groupby("segment"):
        seg = str(segment)
        m, m_name, m_version, is_syn = resolve(seg)
        out.segment_models[seg] = (m_name, m_version, is_syn)
        X = group[MODEL_FEATURE_NAMES].astype(float)
        raw_proba = np.asarray(m.predict_proba(X), dtype=float)
        proba = calibrator(raw_proba) if calibrator is not None else raw_proba
        proba = np.clip(proba, 0.0, 1.0)
        contrib = E.contributions_matrix(m, group)
        model_perf = C.SYNTHETIC_MODEL_PERFORMANCE if is_syn else C.DEFAULT_MODEL_PERFORMANCE

        for pos, (idx, row) in enumerate(group.iterrows()):
            p = float(proba[pos])
            risk = S.compute_risk(p, float(row["ead"]), float(row["outstanding_ratio"]), cfg)
            acc_id = str(row["account_id"])
            conf = C.compute_confidence(
                row, defaulted_fields=defaulted.get(acc_id, 0),
                model_performance=model_perf, calibrated=out.calibrated)
            factors = E.top_factors(contrib[pos], row, k=5)
            records.append({
                "account_id": acc_id,
                "fi_id": str(row.get("fi_id")),
                "fi_name": row.get("fi_name"),
                "segment": seg,
                "model_version": m_version,
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

    # Summarise the model(s) used onto the run-level fields.
    if len(out.segment_models) == 1:
        only = next(iter(out.segment_models.values()))
        out.model_name, out.model_version, out.is_synthetic = only
    else:
        out.model_name = "; ".join(f"{s}: {v[0]}" for s, v in sorted(out.segment_models.items()))
        out.model_version = "; ".join(f"{s}: {v[1]}" for s, v in sorted(out.segment_models.items()))
        out.is_synthetic = all(v[2] for v in out.segment_models.values())
    return out
