"""Generate three diverse test portfolios for uploading via the Runs screen.

    python -m scripts.make_test_portfolios [output_dir]

Writes three files (default: ~/Downloads) that each exercise a different part
of the engine:

  1. mia3_test_healthy_book.csv      — a calm, well-performing book (mostly
                                       Low/Moderate). Shows a quiet dashboard.
  2. mia3_test_sector_stress.json    — a sector downturn (Construction & F&B)
                                       that trips the portfolio early-warning
                                       ladder (high-risk share ≥ watch/halt).
  3. mia3_test_messy_dataquality.csv — a realistic messy file with malformed,
                                       out-of-range and missing values to
                                       exercise validation, quarantine and the
                                       data-quality report.

All files use the canonical data contract (app/core/features.py). Synthetic
data only — no real borrower data.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.core.synthetic import BRANCHES, FIS, SCHEMES, SECTORS

AS_OF = "2026-06-01"


def _account(rng: np.random.RandomState, i: int, *, health: float,
             ead_boost: float = 1.0, fi: Optional[tuple] = None,
             sector: Optional[str] = None) -> Dict[str, object]:
    """Build one contract-shaped account from a latent health score (0..1)."""
    bad = 1.0 - health
    mia_p = np.array([0.86 - 0.3 * bad, 0.10 + 0.2 * bad, 0.04 + 0.1 * bad])
    mia = int(rng.choice([0, 1, 2], p=mia_p / mia_p.sum()))
    trend_p = np.array([0.4 * health, 0.5, 0.1 + 0.4 * bad])
    arrears_trend = int(rng.choice([-1, 0, 1], p=trend_p / trend_p.sum()))
    outstanding = float(np.clip(rng.lognormal(11.6, 0.9) * ead_boost, 5_000, 3_000_000))
    util = float(np.clip(rng.normal(0.5 + 0.35 * bad, 0.18), 0.02, 1.3))
    fi_id, fi_name = fi if fi else FIS[rng.randint(len(FIS))]
    return {
        "account_id": f"AC-{i:06d}",
        "fi_id": fi_id, "fi_name": fi_name,
        "scheme": SCHEMES[rng.randint(len(SCHEMES))],
        "sector": sector or SECTORS[rng.randint(len(SECTORS))],
        "branch": BRANCHES[rng.randint(len(BRANCHES))],
        "as_of_date": AS_OF,
        "ead": round(float(np.clip(outstanding * rng.uniform(0.7, 1.0), 3_000, 3_000_000)), 2),
        "outstanding_ratio": round(float(np.clip(util, 0.0, 1.4)), 4),
        "mia": mia,
        "prev_delinquency_count": int(rng.poisson(0.4 + 2.0 * bad)),
        "arrears_movement_trend": arrears_trend,
        "payment_consistency": round(float(np.clip(rng.normal(0.85 - 0.4 * bad, 0.1), 0.05, 1.0)), 4),
        "cost_to_income_ratio": round(float(np.clip(rng.normal(0.6 + 0.4 * bad, 0.12), 0.2, 1.5)), 4),
        "profit_margin": round(float(np.clip(rng.normal(0.12 - 0.18 * bad, 0.08), -0.4, 0.5)), 4),
        "length_of_business_months": int(np.clip(rng.normal(60 - 20 * bad, 28), 3, 300)),
        "outstanding_amount": round(outstanding, 2),
        "utilization_ratio": round(util, 4),
        "debt_pressure_to_remaining": round(float(np.clip(rng.normal(0.4 + 0.5 * bad, 0.2), 0.0, 2.0)), 4),
        "repayment_stress_ratio": round(float(np.clip(rng.normal(0.4 + 0.5 * bad, 0.2), 0.0, 2.0)), 4),
        "payment_gap_x_pd": round(float(np.clip(rng.normal(0.08 + 0.25 * bad, 0.1), 0.0, 1.5)), 4),
    }


def healthy_book(n: int = 260, seed: int = 11) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    rows = [_account(rng, i, health=float(rng.beta(6.0, 1.6))) for i in range(1, n + 1)]
    return pd.DataFrame(rows)


def sector_stress(n: int = 320, seed: int = 23) -> pd.DataFrame:
    """Construction & F&B distressed (low health, higher exposure); rest healthy."""
    rng = np.random.RandomState(seed)
    stressed = {"Construction", "F&B"}
    rows: List[Dict[str, object]] = []
    for i in range(1, n + 1):
        sector = SECTORS[rng.randint(len(SECTORS))]
        if sector in stressed:
            health = float(rng.beta(1.6, 5.0))   # skews unhealthy
            rows.append(_account(rng, i, health=health, ead_boost=1.6, sector=sector))
        else:
            rows.append(_account(rng, i, health=float(rng.beta(5.0, 2.0)), sector=sector))
    return pd.DataFrame(rows)


def messy_dataquality(n: int = 200, seed: int = 37) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    rows = [_account(rng, i, health=float(rng.beta(4.0, 2.5))) for i in range(1, n + 1)]
    df = pd.DataFrame(rows)
    df["ead"] = df["ead"].astype(object)  # allow None and the "N/A" string below
    idx = df.index.to_numpy()
    rng.shuffle(idx)

    # ~8% malformed: missing required EAD -> quarantined.
    for j in idx[:16]:
        df.at[j, "ead"] = None
    # ~5% bad-type EAD ("N/A") -> quarantined (cannot read as float).
    for j in idx[16:26]:
        df.at[j, "ead"] = "N/A"
    # ~4% out-of-range mia (5 > max 2) -> quarantined.
    for j in idx[26:34]:
        df.at[j, "mia"] = 5
    # ~25% defaultable gaps (optional fields blank) -> filled, confidence reduced.
    for j in idx[34:84]:
        for col in ["prev_delinquency_count", "payment_consistency",
                    "cost_to_income_ratio", "debt_pressure_to_remaining"]:
            df.at[j, col] = None
    return df


def main(argv: List[str]) -> int:
    out_dir = Path(argv[0]) if argv else Path(os.path.expanduser("~/Downloads"))
    out_dir.mkdir(parents=True, exist_ok=True)

    healthy = healthy_book()
    healthy.to_csv(out_dir / "mia3_test_healthy_book.csv", index=False)

    stress = sector_stress()
    stress.to_json(out_dir / "mia3_test_sector_stress.json", orient="records", indent=2)

    messy = messy_dataquality()
    messy.to_csv(out_dir / "mia3_test_messy_dataquality.csv", index=False)

    print(f"Wrote three test portfolios to {out_dir}:")
    print(f"  1. mia3_test_healthy_book.csv      — {len(healthy)} accounts (calm book)")
    print(f"  2. mia3_test_sector_stress.json    — {len(stress)} accounts "
          f"(Construction & F&B stressed → ladder alerts)")
    print(f"  3. mia3_test_messy_dataquality.csv — {len(messy)} accounts "
          f"(~34 quarantined, ~50 with defaulted fields)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
