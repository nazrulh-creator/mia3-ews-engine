"""Ensemble combination of a segment's active models, per a decision rule.

When more than one model is active for a segment, the early-warning trigger is
no longer one model's probability — it is the combination defined by the active
Decision Rule. An Ensemble conforms to the ModelWrapper interface, so the
scoring engine treats it exactly like a single model.

Methods (all return a probability in [0,1]):
  single   — the designated (or first) model only
  average  — mean of member probabilities
  weighted — weighted mean (weights by model version; missing → equal)
  max      — most conservative (flags if any model is high)
  min      — least conservative
  median   — robust middle
  majority — share of models whose probability ≥ the rule threshold
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.core.features import MODEL_FEATURE_NAMES
from app.core.model import ModelWrapper

METHODS = ["single", "average", "weighted", "max", "min", "median", "majority"]


class Ensemble(ModelWrapper):
    feature_names = MODEL_FEATURE_NAMES

    def __init__(self, members: List[ModelWrapper], *, method: str = "average",
                 params: Optional[Dict] = None, name: str = "Ensemble",
                 version: str = "default"):
        if not members:
            raise ValueError("An ensemble needs at least one member model.")
        self.members = members
        self.method = method if method in METHODS else "average"
        self.params = params or {}
        self.name = name
        self.version = version
        self.is_synthetic = all(getattr(m, "is_synthetic", False) for m in members)
        self.kind = "ensemble"

    def _weights(self) -> np.ndarray:
        w_map = (self.params or {}).get("weights") or {}
        w = np.array([float(w_map.get(m.version, 1.0)) for m in self.members], dtype=float)
        if w.sum() <= 0:
            w = np.ones(len(self.members))
        return w / w.sum()

    def _member_probas(self, X: pd.DataFrame) -> np.ndarray:
        # (n_rows, n_members)
        return np.column_stack([np.asarray(m.predict_proba(X), dtype=float) for m in self.members])

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        P = self._member_probas(X)
        if P.shape[1] == 1 or self.method == "single":
            return P[:, 0]
        if self.method == "average":
            return P.mean(axis=1)
        if self.method == "weighted":
            return P @ self._weights()
        if self.method == "max":
            return P.max(axis=1)
        if self.method == "min":
            return P.min(axis=1)
        if self.method == "median":
            return np.median(P, axis=1)
        if self.method == "majority":
            threshold = float(self.params.get("threshold", 0.5))
            return (P >= threshold).mean(axis=1)
        return P.mean(axis=1)

    def contributions(self, X: pd.DataFrame) -> np.ndarray:
        """Weighted-average of members' contributions — the ensemble explanation.

        An approximation for non-linear combinations (max/min/majority), but it
        keeps a consistent, defensible per-feature story. Members that cannot
        produce contributions contribute zeros.
        """
        from app.core import explain as E  # local import avoids a cycle
        weights = self._weights() if self.method == "weighted" else np.ones(len(self.members)) / len(self.members)
        total = np.zeros((len(X), len(self.feature_names)), dtype=float)
        for w, member in zip(weights, self.members):
            total = total + w * E.contributions_matrix(member, X)
        return total

    def describe(self) -> str:
        names = ", ".join(m.version for m in self.members)
        return f"{self.method}({names})"
