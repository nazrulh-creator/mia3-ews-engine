"""Risk-score calculation and four-band classification.

Implements the EWS deck framework exactly:

    Risk Score = 0.5 * Rank(P(MIA3 slip))
               + 0.3 * Rank(Exposure at Default)
               + 0.2 * Rank(Outstanding Ratio)

The component weights and the band cut-offs are NOT hard-coded business
numbers — they arrive as a RiskConfig that is loaded from governed,
dual-controlled settings in the database. The deck values are the defaults.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Ranking guidelines from the deck (rank, inclusive-exclusive upper bound).
# Rank rises with risk: 1 (lowest) .. 4 (highest).
PD_BANDS: List[Tuple[int, float]] = [(1, 0.25), (2, 0.50), (3, 0.75), (4, float("inf"))]
EAD_BANDS: List[Tuple[int, float]] = [(1, 50_000), (2, 200_000), (3, 500_000), (4, float("inf"))]
OUTRATIO_BANDS: List[Tuple[int, float]] = [(1, 0.25), (2, 0.50), (3, 0.75), (4, float("inf"))]


@dataclass(frozen=True)
class RiskConfig:
    """Governed weights + band thresholds. Defaults match the deck."""
    w_pd: float = 0.50
    w_ead: float = 0.30
    w_outratio: float = 0.20
    # Band cut-offs on the composite score.
    t_very_high: float = 3.5   # score >  t_very_high  -> Very High
    t_high: float = 3.0        # score >= t_high       -> High
    t_moderate: float = 2.0    # score >= t_moderate   -> Moderate ; else Low

    def validate(self) -> None:
        total = self.w_pd + self.w_ead + self.w_outratio
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Component weights must sum to 1.0 (got {total:.4f}).")
        if not (self.t_moderate < self.t_high <= self.t_very_high):
            raise ValueError("Band thresholds must satisfy moderate < high <= very_high.")


DEFAULT_CONFIG = RiskConfig()

# Display metadata for the four bands.
BANDS = ["Very High Risk", "High Risk", "Moderate Risk", "Low Risk"]
BAND_META: Dict[str, Dict[str, str]] = {
    "Very High Risk": {"color": "#c0392b", "definition": "Very likely to cause significant loss; requires immediate action."},
    "High Risk": {"color": "#e67e22", "definition": "Likely to cause loss with noticeable financial impact."},
    "Moderate Risk": {"color": "#f1c40f", "definition": "Shows early signs of risk but impact can still be managed."},
    "Low Risk": {"color": "#27ae60", "definition": "Unlikely to cause loss; considered financially stable."},
}


def _rank(value: float, bands: List[Tuple[int, float]]) -> int:
    for rank, upper in bands:
        if value < upper:
            return rank
    return bands[-1][0]


def rank_probability(p: float) -> int:
    return _rank(p, PD_BANDS)


def rank_ead(ead: float) -> int:
    return _rank(ead, EAD_BANDS)


def rank_outstanding_ratio(ratio: float) -> int:
    return _rank(ratio, OUTRATIO_BANDS)


def classify(score: float, cfg: RiskConfig = DEFAULT_CONFIG) -> str:
    if score > cfg.t_very_high:
        return "Very High Risk"
    if score >= cfg.t_high:
        return "High Risk"
    if score >= cfg.t_moderate:
        return "Moderate Risk"
    return "Low Risk"


@dataclass
class RiskResult:
    probability: float
    ead: float
    outstanding_ratio: float
    pd_rank: int
    ead_rank: int
    outratio_rank: int
    risk_score: float
    band: str
    # The full arithmetic, for the decision-explainability view.
    breakdown: Dict[str, float] = field(default_factory=dict)


def compute_risk(probability: float, ead: float, outstanding_ratio: float,
                 cfg: RiskConfig = DEFAULT_CONFIG) -> RiskResult:
    """Combine the three components into a risk score and band.

    This is the single function the worked example on page 3 of the deck
    is rendered from, so the on-screen arithmetic always matches reality.
    """
    pd_rank = rank_probability(probability)
    ead_rank = rank_ead(ead)
    out_rank = rank_outstanding_ratio(outstanding_ratio)

    pd_term = cfg.w_pd * pd_rank
    ead_term = cfg.w_ead * ead_rank
    out_term = cfg.w_outratio * out_rank
    score = round(pd_term + ead_term + out_term, 4)
    band = classify(score, cfg)

    return RiskResult(
        probability=probability, ead=ead, outstanding_ratio=outstanding_ratio,
        pd_rank=pd_rank, ead_rank=ead_rank, outratio_rank=out_rank,
        risk_score=score, band=band,
        breakdown={
            "w_pd": cfg.w_pd, "pd_rank": pd_rank, "pd_term": round(pd_term, 4),
            "w_ead": cfg.w_ead, "ead_rank": ead_rank, "ead_term": round(ead_term, 4),
            "w_outratio": cfg.w_outratio, "outratio_rank": out_rank, "out_term": round(out_term, 4),
            "risk_score": score,
        },
    )
