"""Confidence score — adopted from MicroFlex, ingredients adapted for MIA3.

A 0-100 confidence accompanies every prediction (not just a score). It is a
weighted blend of five components and drives the confidence-based review flow:

    35%  model performance   — back-tested strength of the active model
    25%  data completeness   — were required inputs present (not defaulted)?
    20%  data quality        — were values clean / in range?
    10%  population fit       — how like the training portfolio is this account?
    10%  calibration         — is the active model calibrated to observed reality?

Thresholds route work: >= 70 high confidence, < 55 low confidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.core.features import MODEL_FEATURE_NAMES
from app.core.model import _REF  # reference means/scales describe the "training" shape

WEIGHTS = {
    "model_performance": 0.35,
    "data_completeness": 0.25,
    "data_quality": 0.20,
    "population_fit": 0.10,
    "calibration": 0.10,
}

HIGH_CONFIDENCE = 70.0
LOW_CONFIDENCE = 55.0

# Back-tested headline metric for the active model (deck: Avg AUC 0.86).
# For a real model this is read from the registry; the synthetic stand-in
# reports a deliberately modest figure so demos do not overstate certainty.
DEFAULT_MODEL_PERFORMANCE = 86.0
SYNTHETIC_MODEL_PERFORMANCE = 60.0


@dataclass
class Confidence:
    score: float
    band: str  # "high" | "medium" | "low"
    components: Dict[str, float]


def _population_fit(row: pd.Series) -> float:
    """100 when the account looks typical of training; falls with distance.

    Mean absolute z-score across model features, mapped through a soft curve.
    """
    zs: List[float] = []
    for f in MODEL_FEATURE_NAMES:
        mean, scale = _REF[f]
        if scale:
            zs.append(abs((float(row.get(f, mean)) - mean) / scale))
    if not zs:
        return 100.0
    mean_abs_z = float(np.mean(zs))
    # 0 z -> 100 ; ~2 z -> ~50 ; large -> approaches 0
    return float(round(100.0 * np.exp(-mean_abs_z / 2.0), 2))


def compute_confidence(row: pd.Series, *, defaulted_fields: int,
                       model_performance: float, calibrated: bool) -> Confidence:
    completeness = max(0.0, 100.0 - 12.0 * defaulted_fields)
    quality = 100.0 if defaulted_fields == 0 else max(40.0, 100.0 - 8.0 * defaulted_fields)
    pop_fit = _population_fit(row)
    calibration = 90.0 if calibrated else 65.0

    components = {
        "model_performance": round(model_performance, 2),
        "data_completeness": round(completeness, 2),
        "data_quality": round(quality, 2),
        "population_fit": round(pop_fit, 2),
        "calibration": round(calibration, 2),
    }
    score = round(sum(WEIGHTS[k] * v for k, v in components.items()), 2)
    if score >= HIGH_CONFIDENCE:
        band = "high"
    elif score < LOW_CONFIDENCE:
        band = "low"
    else:
        band = "medium"
    return Confidence(score=score, band=band, components=components)
