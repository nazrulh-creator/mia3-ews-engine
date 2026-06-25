"""Synthetic portfolio generation for demonstration mode and seeding.

Produces a realistic guaranteed-portfolio frame spanning all four risk bands,
several FIs, schemes and sectors — mirroring the structure of the deck tables —
plus a set of deliberate boundary cases that exercise every path:

  * an account sitting on the band edge,
  * high-probability / low-exposure,
  * low-probability / very-high-exposure,
  * a borderline-confidence case that should route to human review,
  * a malformed row that must be quarantined.

No real borrower data is ever used (a standing build rule).
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

FIS = [("MBB", "Maybank"), ("CIMB", "CIMB Bank"), ("PBB", "Public Bank"),
       ("RHB", "RHB Bank"), ("HLBB", "Hong Leong Bank"), ("AMB", "AmBank")]
SCHEMES = ["BizWanita", "SME-Plus", "MicroFlex", "TradeGuarantee", "GreenBiz"]
SECTORS = ["Retail", "Manufacturing", "Construction", "Services", "Agriculture", "F&B"]
BRANCHES = ["KL-Sentral", "Penang", "JB", "Kuching", "Kota-Kinabalu", "Ipoh"]


def _account(rng: np.random.RandomState, i: int, as_of: str) -> Dict[str, object]:
    # Latent health in [0,1]; lower = riskier. Skew toward healthy book.
    health = float(rng.beta(5, 2))
    bad = 1.0 - health

    mia_p = np.array([0.86 - 0.3 * bad, 0.10 + 0.2 * bad, 0.04 + 0.1 * bad])
    mia = int(rng.choice([0, 1, 2], p=mia_p / mia_p.sum()))
    prev_delinq = int(rng.poisson(0.4 + 2.0 * bad))
    trend_p = np.array([0.4 * health, 0.5, 0.1 + 0.4 * bad])
    arrears_trend = int(rng.choice([-1, 0, 1], p=trend_p / trend_p.sum()))
    payment_consistency = float(np.clip(rng.normal(0.85 - 0.4 * bad, 0.1), 0.05, 1.0))
    cost_to_income = float(np.clip(rng.normal(0.6 + 0.4 * bad, 0.12), 0.2, 1.5))
    profit_margin = float(np.clip(rng.normal(0.12 - 0.18 * bad, 0.08), -0.4, 0.5))
    length_months = int(np.clip(rng.normal(60 - 20 * bad, 28), 3, 300))
    outstanding_amount = float(np.clip(rng.lognormal(11.6, 0.9), 5_000, 3_000_000))
    utilization = float(np.clip(rng.normal(0.5 + 0.35 * bad, 0.18), 0.02, 1.3))
    debt_pressure = float(np.clip(rng.normal(0.4 + 0.5 * bad, 0.2), 0.0, 2.0))
    repayment_stress = float(np.clip(rng.normal(0.4 + 0.5 * bad, 0.2), 0.0, 2.0))
    payment_gap_x_pd = float(np.clip(rng.normal(0.08 + 0.25 * bad, 0.1), 0.0, 1.5))

    # EAD related to outstanding but not identical; outstanding_ratio is leverage.
    ead = float(np.clip(outstanding_amount * rng.uniform(0.7, 1.0), 3_000, 3_000_000))
    fi_id, fi_name = FIS[rng.randint(len(FIS))]

    return {
        "account_id": f"AC-{i:06d}",
        "fi_id": fi_id, "fi_name": fi_name,
        "segment": "Financing" if rng.random_sample() < 0.25 else "Guarantee",
        "scheme": SCHEMES[rng.randint(len(SCHEMES))],
        "sector": SECTORS[rng.randint(len(SECTORS))],
        "branch": BRANCHES[rng.randint(len(BRANCHES))],
        "as_of_date": as_of,
        "ead": round(ead, 2),
        "outstanding_ratio": round(float(np.clip(utilization, 0.0, 1.4)), 4),
        "mia": mia,
        "prev_delinquency_count": prev_delinq,
        "arrears_movement_trend": arrears_trend,
        "payment_consistency": round(payment_consistency, 4),
        "cost_to_income_ratio": round(cost_to_income, 4),
        "profit_margin": round(profit_margin, 4),
        "length_of_business_months": length_months,
        "outstanding_amount": round(outstanding_amount, 2),
        "utilization_ratio": round(utilization, 4),
        "debt_pressure_to_remaining": round(debt_pressure, 4),
        "repayment_stress_ratio": round(repayment_stress, 4),
        "payment_gap_x_pd": round(payment_gap_x_pd, 4),
    }


def generate_portfolio(n: int = 400, seed: int = 42,
                       as_of: str = "2026-06-01") -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    rows = [_account(rng, i, as_of) for i in range(1, n + 1)]
    return pd.DataFrame(rows)


def boundary_cases(as_of: str = "2026-06-01") -> pd.DataFrame:
    """The five teaching edge cases. The malformed row is intentionally bad."""
    base = {
        "fi_id": "MBB", "fi_name": "Maybank", "segment": "Guarantee", "scheme": "MicroFlex",
        "sector": "Retail", "branch": "KL-Sentral", "as_of_date": as_of,
        "prev_delinquency_count": 1, "arrears_movement_trend": 0,
        "cost_to_income_ratio": 0.7, "profit_margin": 0.05,
        "length_of_business_months": 36, "payment_gap_x_pd": 0.1,
    }
    hi = dict(base, mia=2, payment_consistency=0.2, utilization_ratio=0.9,
              debt_pressure_to_remaining=1.4, repayment_stress_ratio=1.4)
    lo = dict(base, mia=0, payment_consistency=0.98, utilization_ratio=0.1,
              debt_pressure_to_remaining=0.1, repayment_stress_ratio=0.1)

    rows: List[Dict[str, object]] = []
    # 1. Band edge — high prob, mid exposure, mid leverage.
    rows.append(dict(hi, account_id="EDGE-001", ead=300_000, outstanding_ratio=0.6,
                     outstanding_amount=300_000))
    # 2. High-probability / low-exposure.
    rows.append(dict(hi, account_id="HIPROB-LOWEXP", ead=20_000, outstanding_ratio=0.1,
                     outstanding_amount=20_000))
    # 3. Low-probability / very-high-exposure.
    rows.append(dict(lo, account_id="LOPROB-HIEXP", segment="Financing", ead=800_000,
                     outstanding_ratio=0.95, outstanding_amount=800_000, utilization_ratio=0.95))
    # 4. Borderline-confidence — elevated risk but several inputs missing
    #    (left blank so they default and depress completeness/quality).
    rows.append({
        "account_id": "BORDERLINE-CONF", "fi_id": "CIMB", "fi_name": "CIMB Bank",
        "segment": "Financing", "scheme": "SME-Plus", "sector": "Construction", "branch": "JB",
        "as_of_date": as_of, "ead": 260_000, "outstanding_ratio": 0.7,
        "mia": 2, "outstanding_amount": 260_000, "utilization_ratio": 0.85,
        # deliberately omitted: prev_delinquency_count, arrears_movement_trend,
        # payment_consistency, cost_to_income_ratio, profit_margin,
        # length_of_business_months, debt_pressure_to_remaining,
        # repayment_stress_ratio, payment_gap_x_pd
    })
    # 5. Malformed — missing required EAD; must be quarantined.
    rows.append({
        "account_id": "MALFORMED-001", "fi_id": "RHB", "fi_name": "RHB Bank",
        "segment": "Guarantee", "scheme": "TradeGuarantee", "sector": "Services", "branch": "Penang",
        "as_of_date": as_of, "ead": None, "outstanding_ratio": 0.5,
        "mia": 1, "outstanding_amount": 100_000, "utilization_ratio": 0.5,
    })
    return pd.DataFrame(rows)


def demo_portfolio(n: int = 400, seed: int = 42, as_of: str = "2026-06-01") -> pd.DataFrame:
    """Full demonstration set: a realistic book plus the boundary cases."""
    return pd.concat([generate_portfolio(n, seed, as_of), boundary_cases(as_of)],
                     ignore_index=True)
