"""Build the golden test pack (the safety net for AI-built code).

A fixed set of fully-specified accounts whose probability, risk score, band
and confidence are computed once and frozen. tests/test_golden.py then asserts
the engine reproduces the pack EXACTLY on every change; any divergence blocks
release. In production a human signs off the frozen pack.

    python -m scripts.build_golden_pack
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.core.batch import score_frame

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "tests" / "golden" / "golden_pack.json"

# Fully-specified accounts (no missing values -> deterministic confidence).
GOLDEN_INPUT = [
    {"account_id": "G-HEALTHY", "fi_id": "MBB", "fi_name": "Maybank", "scheme": "SME-Plus",
     "sector": "Services", "branch": "KL-Sentral", "as_of_date": "2026-06-01",
     "ead": 40_000, "outstanding_ratio": 0.20, "mia": 0, "prev_delinquency_count": 0,
     "arrears_movement_trend": -1, "payment_consistency": 0.98, "cost_to_income_ratio": 0.55,
     "profit_margin": 0.20, "length_of_business_months": 120, "outstanding_amount": 40_000,
     "utilization_ratio": 0.20, "debt_pressure_to_remaining": 0.10,
     "repayment_stress_ratio": 0.10, "payment_gap_x_pd": 0.02},
    {"account_id": "G-STRESSED", "fi_id": "CIMB", "fi_name": "CIMB Bank", "scheme": "MicroFlex",
     "sector": "Construction", "branch": "JB", "as_of_date": "2026-06-01",
     "ead": 600_000, "outstanding_ratio": 0.90, "mia": 2, "prev_delinquency_count": 4,
     "arrears_movement_trend": 1, "payment_consistency": 0.30, "cost_to_income_ratio": 1.10,
     "profit_margin": -0.10, "length_of_business_months": 14, "outstanding_amount": 600_000,
     "utilization_ratio": 0.95, "debt_pressure_to_remaining": 1.30,
     "repayment_stress_ratio": 1.40, "payment_gap_x_pd": 0.60},
    {"account_id": "G-MID", "fi_id": "PBB", "fi_name": "Public Bank", "scheme": "TradeGuarantee",
     "sector": "Retail", "branch": "Penang", "as_of_date": "2026-06-01",
     "ead": 250_000, "outstanding_ratio": 0.55, "mia": 1, "prev_delinquency_count": 1,
     "arrears_movement_trend": 0, "payment_consistency": 0.70, "cost_to_income_ratio": 0.75,
     "profit_margin": 0.05, "length_of_business_months": 48, "outstanding_amount": 250_000,
     "utilization_ratio": 0.60, "debt_pressure_to_remaining": 0.55,
     "repayment_stress_ratio": 0.55, "payment_gap_x_pd": 0.15},
]


def build() -> dict:
    df = pd.DataFrame(GOLDEN_INPUT)
    out = score_frame(df)
    cases = [{
        "account_id": r["account_id"], "probability": r["probability"],
        "pd_rank": r["pd_rank"], "ead_rank": r["ead_rank"], "outratio_rank": r["outratio_rank"],
        "risk_score": r["risk_score"], "band": r["band"], "confidence": r["confidence"],
        "confidence_band": r["confidence_band"], "review_status": r["review_status"],
    } for r in out.records]
    return {"model": out.model_name, "model_version": out.model_version,
            "is_synthetic": out.is_synthetic, "cases": cases}


def main() -> int:
    pack = build()
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(pack, indent=2))
    print(f"Wrote golden pack with {len(pack['cases'])} cases to {GOLDEN_PATH}")
    for c in pack["cases"]:
        print(f"  {c['account_id']}: p={c['probability']:.3f} "
              f"score={c['risk_score']} band={c['band']} conf={c['confidence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
