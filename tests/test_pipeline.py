"""End-to-end scoring core: validation, scoring, routing, boundary cases."""
from app.core.batch import score_frame
from app.core.synthetic import demo_portfolio


def test_demo_portfolio_scores_and_quarantines():
    out = score_frame(demo_portfolio(n=80, seed=1))
    ids = {r["account_id"] for r in out.records}

    # The malformed row (missing EAD) must be quarantined, never scored.
    assert "MALFORMED-001" not in ids
    assert out.validation.n_quarantined >= 1

    # Multiple bands should be represented across a realistic book.
    bands = {r["band"] for r in out.records}
    assert len(bands) >= 3

    # Every scored record carries a probability, score, confidence and routing.
    for r in out.records:
        assert 0.0 <= r["probability"] <= 1.0
        assert r["band"] in {"Very High Risk", "High Risk", "Moderate Risk", "Low Risk"}
        assert 0 <= r["confidence"] <= 100
        assert r["review_status"] in {"no_review", "fast_track", "needs_review"}


def test_borderline_confidence_routes_to_review():
    out = score_frame(demo_portfolio(n=40, seed=2))
    borderline = next((r for r in out.records if r["account_id"] == "BORDERLINE-CONF"), None)
    assert borderline is not None
    # It has many defaulted inputs and elevated risk -> must be held for review.
    assert borderline["defaulted_fields"] >= 5
    assert borderline["review_status"] == "needs_review"


def test_low_exposure_high_prob_is_not_top_band():
    out = score_frame(demo_portfolio(n=20, seed=3))
    case = next(r for r in out.records if r["account_id"] == "HIPROB-LOWEXP")
    # High probability but tiny exposure/leverage should not be Very High.
    assert case["band"] != "Very High Risk"
