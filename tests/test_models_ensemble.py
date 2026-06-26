"""Glass-box coefficient models and ensemble decision-rule combination."""
import numpy as np

from app.core.ensemble import Ensemble
from app.core.features import MODEL_FEATURE_NAMES
from app.core.model import CoefficientModel
from app.core.synthetic import generate_portfolio


def _X(n=5):
    return generate_portfolio(n=n, seed=1)[MODEL_FEATURE_NAMES].astype(float)


def test_logistic_in_range_and_exact_contributions():
    spec = {"intercept": -1.0, "standardize": False,
            "coefficients": {"mia": 1.0, "utilization_ratio": 0.5}}
    m = CoefficientModel(spec, name="L", version="L1", link="logit")
    X = _X()
    p = m.predict_proba(X)
    assert ((p >= 0) & (p <= 1)).all()
    c = m.contributions(X)
    j = MODEL_FEATURE_NAMES.index("mia")
    assert np.allclose(c[:, j], 1.0 * X["mia"].to_numpy())


def test_ols_output_clipped():
    spec = {"intercept": 0.5, "standardize": False, "coefficients": {"mia": 0.3}}
    m = CoefficientModel(spec, name="O", version="O1", link="identity")
    p = m.predict_proba(_X())
    assert ((p >= 0) & (p <= 1)).all()


class _Const:
    """Minimal duck-typed model returning a constant probability."""
    is_synthetic = False
    feature_names = MODEL_FEATURE_NAMES

    def __init__(self, p, version):
        self.p, self.version, self.name = p, version, version

    def predict_proba(self, X):
        return np.full(len(X), self.p)

    def contributions(self, X):
        return np.zeros((len(X), len(MODEL_FEATURE_NAMES)))


def test_ensemble_combination_methods():
    a, b = _Const(0.2, "a"), _Const(0.8, "b")
    X = _X(4)
    assert np.allclose(Ensemble([a, b], method="average").predict_proba(X), 0.5)
    assert np.allclose(Ensemble([a, b], method="max").predict_proba(X), 0.8)
    assert np.allclose(Ensemble([a, b], method="min").predict_proba(X), 0.2)
    w = Ensemble([a, b], method="weighted",
                 params={"weights": {"a": 3, "b": 1}}).predict_proba(X)
    assert np.allclose(w, (3 * 0.2 + 1 * 0.8) / 4)
    maj = Ensemble([a, b], method="majority",
                   params={"threshold": 0.5}).predict_proba(X)
    assert np.allclose(maj, 0.5)  # exactly one of two members is >= 0.5


def test_single_member_ensemble_is_passthrough():
    a = _Const(0.42, "solo")
    out = Ensemble([a], method="average").predict_proba(_X(3))
    assert np.allclose(out, 0.42)
