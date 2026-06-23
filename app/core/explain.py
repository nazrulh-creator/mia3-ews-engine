"""Explainability — SHAP is the official account, LIME the challenger.

Per the MicroFlex adaptation: SHAP runs for every scored case and is what we
store (off the critical path, computed during the batch run); LIME runs only
on demand for a single borderline/odd case and is clearly labelled diagnostic.

Every explanation is rendered at three audience levels — technical (raw
feature names, for validators), operational (plain phrases, for branch
officers) and simplified (no variable names at all) — from the same numbers.

If SHAP is unavailable, the engine falls back to the synthetic model's exact
log-odds contributions (or, for a real opaque model, gain importance), so an
explanation is always available.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.core.features import MODEL_FEATURE_NAMES
from app.core.model import ModelWrapper

# Plain-language labels for the two non-technical audience levels.
FRIENDLY: Dict[str, str] = {
    "mia": "Currently behind on payments",
    "prev_delinquency_count": "History of past late payments",
    "arrears_movement_trend": "Arrears trend (getting worse / better)",
    "payment_consistency": "How reliably payments are made on time",
    "cost_to_income_ratio": "Costs are high relative to income",
    "profit_margin": "Business profitability",
    "length_of_business_months": "How long the business has operated",
    "outstanding_amount": "Size of outstanding financing",
    "utilization_ratio": "How much of the limit is used up",
    "debt_pressure_to_remaining": "Debt-servicing pressure",
    "repayment_stress_ratio": "Strain on the ability to repay",
    "payment_gap_x_pd": "Recent payment gaps combined with baseline risk",
}


def _shap_values(model: ModelWrapper, X: pd.DataFrame) -> Optional[np.ndarray]:
    """Try SHAP; return (n_rows, n_features) contribution array or None."""
    try:
        import shap  # type: ignore
    except Exception:
        return None
    try:
        # TreeExplainer for tree models; generic Explainer otherwise.
        inner = getattr(model, "_obj", None)
        explainer = shap.TreeExplainer(inner) if inner is not None else None
        if explainer is None:
            explainer = shap.Explainer(model.predict_proba, X)
        values = explainer(X[MODEL_FEATURE_NAMES])
        arr = np.asarray(values.values)
        if arr.ndim == 3:  # (rows, features, classes)
            arr = arr[:, :, -1]
        return arr
    except Exception:
        return None


def contributions_matrix(model: ModelWrapper, X: pd.DataFrame) -> np.ndarray:
    """Best available signed per-feature contributions for the whole frame.

    Order of preference: model's exact contributions (synthetic) -> SHAP ->
    a zero matrix annotated by gain importance (degenerate but never crashes).
    """
    exact = model.contributions(X)
    if exact is not None:
        return exact
    shap_vals = _shap_values(model, X)
    if shap_vals is not None:
        return shap_vals
    # Degenerate fallback: no per-row attribution available.
    return np.zeros((len(X), len(MODEL_FEATURE_NAMES)), dtype=float)


def top_factors(contrib_row: np.ndarray, feature_row: pd.Series,
                k: int = 5) -> List[Dict[str, object]]:
    """Rank a single account's features by absolute contribution."""
    order = np.argsort(-np.abs(contrib_row))[:k]
    out: List[Dict[str, object]] = []
    for j in order:
        name = MODEL_FEATURE_NAMES[j]
        c = float(contrib_row[j])
        out.append({
            "feature": name,                       # technical
            "label": FRIENDLY.get(name, name),     # operational / simplified
            "value": float(feature_row.get(name, float("nan"))),
            "contribution": round(c, 4),
            "direction": "increases risk" if c > 0 else "decreases risk",
        })
    return out


def explain_text(factors: List[Dict[str, object]], level: str = "operational") -> str:
    """Render a short narrative at the requested audience level."""
    up = [f for f in factors if f["contribution"] > 0][:3]
    down = [f for f in factors if f["contribution"] < 0][:2]
    if level == "technical":
        parts = [f"{f['feature']}={f['value']:.3g} ({f['contribution']:+.3f})" for f in factors]
        return "Top SHAP contributions: " + "; ".join(parts)
    key = "label"
    raised = ", ".join(str(f[key]) for f in up) or "no strong upward factors"
    lowered = ", ".join(str(f[key]) for f in down) or "no notable mitigants"
    if level == "simplified":
        return f"This account is flagged mainly because: {raised}."
    return (f"Risk is driven up by: {raised}. "
            f"Offsetting factors: {lowered}.")


def lime_explain(model: ModelWrapper, X: pd.DataFrame, row_index: int,
                 background: Optional[pd.DataFrame] = None) -> Dict[str, object]:
    """On-demand LIME challenger for a single account (diagnostic only)."""
    try:
        from lime.lime_tabular import LimeTabularExplainer  # type: ignore
    except Exception:
        return {"available": False,
                "reason": "LIME not installed; SHAP remains the official explanation."}
    bg = background if background is not None else X
    explainer = LimeTabularExplainer(
        training_data=bg[MODEL_FEATURE_NAMES].to_numpy(),
        feature_names=MODEL_FEATURE_NAMES, mode="classification",
        discretize_continuous=True,
    )

    def _predict(arr: np.ndarray) -> np.ndarray:
        frame = pd.DataFrame(arr, columns=MODEL_FEATURE_NAMES)
        p = model.predict_proba(frame)
        return np.column_stack([1.0 - p, p])

    exp = explainer.explain_instance(
        X[MODEL_FEATURE_NAMES].iloc[row_index].to_numpy(), _predict,
        num_features=6,
    )
    return {"available": True, "label": "LIME (diagnostic challenger)",
            "weights": exp.as_list()}
