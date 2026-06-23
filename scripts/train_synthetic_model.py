"""Optionally train a synthetic XGBoost artifact to demonstrate the drop-in path.

    python -m scripts.train_synthetic_model

The engine runs perfectly well on the built-in deterministic logit stand-in.
This script exists only to show how a REAL artifact is produced and loaded:
it trains an XGBoost classifier on synthetic data labelled by the stand-in,
saves it to artifacts/mia3_xgb.json, and prints the env var to activate it.
Requires xgboost + scikit-learn; exits gracefully if they are absent.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from app.config import ARTIFACTS_DIR
from app.core.features import MODEL_FEATURE_NAMES
from app.core.model import SyntheticModel
from app.core.synthetic import generate_portfolio


def main() -> int:
    try:
        import xgboost as xgb  # type: ignore
    except Exception:
        print("xgboost not installed — skipping. The deterministic stand-in is used instead.")
        return 0

    df = generate_portfolio(n=4000, seed=7)
    X = df[MODEL_FEATURE_NAMES].astype(float)
    # Label with the deterministic stand-in's probability + noise -> binary event.
    p = SyntheticModel().predict_proba(X)
    rng = np.random.RandomState(7)
    y = (rng.uniform(size=len(p)) < p).astype(int)

    clf = xgb.XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.1,
                            subsample=0.9, eval_metric="logloss")
    clf.fit(X, y)
    out = Path(ARTIFACTS_DIR) / "mia3_xgb.json"
    clf.get_booster().feature_names = MODEL_FEATURE_NAMES
    clf.save_model(str(out))
    print(f"Saved XGBoost artifact to {out}")
    print(f"Activate it with:  export MIA3_MODEL_PATH={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
