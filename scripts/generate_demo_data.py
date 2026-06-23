"""Write the synthetic demonstration portfolio to data/synthetic/.

    python -m scripts.generate_demo_data

Produces both CSV and JSON so the upload path can be exercised with either.
"""
from __future__ import annotations

from app.config import SYNTHETIC_DIR
from app.core.synthetic import demo_portfolio


def main() -> int:
    df = demo_portfolio()
    csv_path = SYNTHETIC_DIR / "demo_portfolio.csv"
    json_path = SYNTHETIC_DIR / "demo_portfolio.json"
    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", indent=2)
    print(f"Wrote {len(df)} rows to:\n  {csv_path}\n  {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
