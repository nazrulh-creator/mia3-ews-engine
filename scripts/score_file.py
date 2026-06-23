"""Phase 1 milestone CLI: score a file, print bands. No database, no web.

    python -m scripts.score_file path/to/portfolio.csv [out.csv]

Feeds a file to the scoring core and prints (or writes) the scores and bands —
the smallest end-to-end proof that the engine works.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from app.core.batch import score_frame
from app.core.validation import read_table


def main(argv: list) -> int:
    if not argv:
        print(__doc__)
        return 1
    path = Path(argv[0])
    content = path.read_bytes()
    df = read_table(content, path.name)
    out = score_frame(df)

    print(f"Model: {out.model_name} ({out.model_version}) "
          f"{'[synthetic]' if out.is_synthetic else ''}")
    print(f"Scored {out.n_scored}, quarantined {out.validation.n_quarantined}.")
    print("Band counts:", out.band_counts())
    table = pd.DataFrame([{
        "account_id": r["account_id"], "probability": round(r["probability"], 3),
        "risk_score": r["risk_score"], "band": r["band"],
        "confidence": r["confidence"], "routing": r["review_status"],
    } for r in out.records])
    if len(argv) > 1:
        table.to_csv(argv[1], index=False)
        print(f"Wrote {argv[1]}")
    else:
        print(table.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
