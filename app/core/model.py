"""Model loading abstraction with a synthetic stand-in.

The engine never talks to a concrete model object directly — it talks to a
ModelWrapper. Two implementations exist behind that interface:

  * RealModel    — wraps the back-tested XGBoost artifact pointed to by
                   MIA3_MODEL_PATH (xgboost Booster, xgboost sklearn API, or
                   any object exposing predict_proba). DROP-IN POINT: set the
                   env var and ship the .json/.ubj/.pkl; no other code changes.

  * SyntheticModel — a fully deterministic logistic stand-in with transparent,
                     auditable coefficients. It needs no ML libraries, runs
                     anywhere, and gives reproducible probabilities so the
                     golden test pack is stable. It is always flagged in the UI
                     as synthetic so a demo is never mistaken for the real model.

Loading order: a registry-active artifact (handled by the caller) → the env
artifact → the synthetic stand-in.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from app.config import get_settings
from app.core.features import MODEL_FEATURE_NAMES

# --- Synthetic stand-in: transparent reference stats + coefficients --------
# Standardisation reference (mean, scale) per feature and the logistic
# coefficients on the resulting z-scores. These are deliberately legible so
# the synthetic model's behaviour can be reasoned about and audited.
_REF: Dict[str, tuple] = {
    "mia": (0.30, 0.60),
    "prev_delinquency_count": (0.80, 1.20),
    "arrears_movement_trend": (0.00, 1.00),
    "payment_consistency": (0.80, 0.20),
    "cost_to_income_ratio": (0.70, 0.20),
    "profit_margin": (0.08, 0.12),
    "length_of_business_months": (48.0, 30.0),
    "outstanding_amount": (200_000.0, 250_000.0),
    "utilization_ratio": (0.60, 0.25),
    "debt_pressure_to_remaining": (0.50, 0.30),
    "repayment_stress_ratio": (0.50, 0.30),
    "payment_gap_x_pd": (0.12, 0.15),
}
_COEF: Dict[str, float] = {
    "mia": 1.40,
    "prev_delinquency_count": 0.50,
    "arrears_movement_trend": 0.60,
    "payment_consistency": -0.80,
    "cost_to_income_ratio": 0.50,
    "profit_margin": -0.50,
    "length_of_business_months": -0.40,
    "outstanding_amount": 0.15,
    "utilization_ratio": 0.60,
    "debt_pressure_to_remaining": 0.80,
    "repayment_stress_ratio": 0.80,
    "payment_gap_x_pd": 0.70,
}
_INTERCEPT = -1.20


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


class ModelWrapper:
    """Common interface every part of the engine codes against."""

    name: str = "model"
    version: str = "0.0.0"
    kind: str = "abstract"
    is_synthetic: bool = True
    feature_names: List[str] = MODEL_FEATURE_NAMES

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError

    def contributions(self, X: pd.DataFrame) -> Optional[np.ndarray]:
        """Optional exact per-feature contributions to the log-odds.

        Returned only when the model can produce them cheaply (the synthetic
        stand-in can). Used as a SHAP fallback. None means 'use SHAP/importance'.
        """
        return None

    def _align(self, X: pd.DataFrame) -> pd.DataFrame:
        missing = [c for c in self.feature_names if c not in X.columns]
        if missing:
            raise ValueError(f"Input is missing model features: {missing}")
        return X[self.feature_names]


class SyntheticModel(ModelWrapper):
    name = "MIA3-Synthetic-Logit"
    version = "synthetic-1.0.0"
    kind = "synthetic-logit"
    is_synthetic = True

    def _z(self, X: pd.DataFrame) -> pd.DataFrame:
        z = pd.DataFrame(index=X.index)
        for f in self.feature_names:
            mean, scale = _REF[f]
            z[f] = (X[f].astype(float) - mean) / scale
        return z

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        X = self._align(X)
        z = self._z(X)
        logit = np.full(len(X), _INTERCEPT, dtype=float)
        for f in self.feature_names:
            logit = logit + _COEF[f] * z[f].to_numpy()
        return _sigmoid(logit)

    def contributions(self, X: pd.DataFrame) -> np.ndarray:
        """Exact additive log-odds contributions (coef * z) per feature."""
        X = self._align(X)
        z = self._z(X)
        contrib = np.zeros((len(X), len(self.feature_names)), dtype=float)
        for j, f in enumerate(self.feature_names):
            contrib[:, j] = _COEF[f] * z[f].to_numpy()
        return contrib


class RealModel(ModelWrapper):
    is_synthetic = False
    kind = "real"

    def __init__(self, obj, feature_names: Sequence[str], version: str, name: str):
        self._obj = obj
        self.feature_names = list(feature_names)
        self.version = version
        self.name = name

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        X = self._align(X)
        obj = self._obj
        # scikit-learn-style API
        if hasattr(obj, "predict_proba"):
            proba = obj.predict_proba(X)
            return np.asarray(proba)[:, 1]
        # xgboost Booster API
        try:
            import xgboost as xgb  # type: ignore
            if isinstance(obj, xgb.Booster):
                dm = xgb.DMatrix(X, feature_names=self.feature_names)
                return np.asarray(obj.predict(dm))
        except Exception:  # pragma: no cover - only if xgboost absent
            pass
        # last resort: a plain predict returning scores in [0,1]
        return np.asarray(obj.predict(X)).astype(float)


def _load_real(path: Path) -> Optional[RealModel]:
    if not path or not path.exists():
        return None
    suffix = path.suffix.lower()
    try:
        if suffix in {".json", ".ubj", ".bst"}:
            import xgboost as xgb  # type: ignore
            booster = xgb.Booster()
            booster.load_model(str(path))
            names = booster.feature_names or MODEL_FEATURE_NAMES
            return RealModel(booster, names, version=path.stem, name=f"XGBoost:{path.stem}")
        # pickle/joblib
        import pickle
        with open(path, "rb") as fh:
            obj = pickle.load(fh)
        names = getattr(obj, "feature_names_in_", None)
        names = list(names) if names is not None else MODEL_FEATURE_NAMES
        return RealModel(obj, names, version=path.stem, name=f"Model:{path.stem}")
    except Exception as exc:  # noqa: BLE001 - surfaced to caller as a fallback
        raise RuntimeError(f"Failed to load model artifact at {path}: {exc}") from exc


_CACHE: Dict[str, ModelWrapper] = {}


def get_active_model(model_path: Optional[Path] = None) -> ModelWrapper:
    """Return the active model, caching by resolved path.

    Validates that the model's feature list matches the data contract, so a
    mismatched artifact is refused rather than scoring on the wrong columns.
    """
    settings = get_settings()
    path = model_path if model_path is not None else settings.model_path
    cache_key = str(path) if path else "__synthetic__"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    model: ModelWrapper
    real = _load_real(path) if path else None
    if real is not None:
        contract = set(MODEL_FEATURE_NAMES)
        artifact = set(real.feature_names)
        if contract != artifact:
            raise RuntimeError(
                "Model feature mismatch — artifact features do not match the "
                f"data contract. Missing={contract - artifact}, "
                f"unexpected={artifact - contract}. Align app/core/features.py."
            )
        model = real
    else:
        model = SyntheticModel()

    _CACHE[cache_key] = model
    return model


def reset_model_cache() -> None:
    _CACHE.clear()


def validate_artifact(path: Optional[Path]) -> tuple:
    """Pre-flight a model artifact before it is activated.

    Returns (ok, message). A synthetic entry (no path) is always valid.
    A real artifact must load and its features must match the data contract.
    """
    if not path:
        return True, "Synthetic stand-in — no artifact to validate."
    p = Path(path)
    if not p.exists():
        return False, f"Artifact not found at {p}."
    try:
        real = _load_real(p)
    except RuntimeError as exc:
        return False, str(exc)
    if real is None:
        return False, "Could not load the artifact."
    contract, artifact = set(MODEL_FEATURE_NAMES), set(real.feature_names)
    if contract != artifact:
        return False, (f"Feature mismatch — missing={sorted(contract - artifact)}, "
                       f"unexpected={sorted(artifact - contract)}.")
    return True, f"Loaded OK ({len(real.feature_names)} features match the contract)."
