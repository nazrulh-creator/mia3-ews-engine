"""Scheduled monthly scoring run (the Fly.io scheduled machine entrypoint).

    python -m scripts.run_batch [path/to/file.csv]

If a path is given, scores it. Otherwise it scores the newest file in the
upload area. With neither, it falls back to the synthetic demo portfolio so a
scheduled run never fails silently in a fresh environment. Results are
persisted and audited exactly like an interactive run.
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.config import UPLOAD_DIR
from app.core.synthetic import demo_portfolio
from app.core.validation import read_table
from app.db.database import init_db, session_scope
from app.services import runs
from app.services.seed import ensure_seed


def _newest_upload() -> Path:
    files = sorted(UPLOAD_DIR.glob("*.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def main(argv: list) -> int:
    init_db()
    path = Path(argv[0]) if argv else _newest_upload()
    with session_scope() as db:
        ensure_seed(db)
        if path and path.exists():
            df = read_table(path.read_bytes(), path.name)
            source, fp = "scheduled", runs.fingerprint(path.read_bytes())
        else:
            print("No input file found; scoring synthetic demo portfolio.")
            df = demo_portfolio()
            source, fp = "scheduled", "synthetic-demo"
        run = runs.execute_run(db, df, source=source, actor="scheduler",
                               input_fingerprint=fp)
        print(f"Run {run.run_ref}: scored {run.rows_scored}, "
              f"quarantined {run.rows_quarantined}, published={run.published}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
