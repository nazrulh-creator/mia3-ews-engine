"""Risk-score arithmetic and band boundaries — must match the deck exactly."""
from app.core import scoring as S


def test_deck_worked_example():
    # Deck p.3: P(MIA3)=75.23% -> rank 4, EAD=92,677 -> rank 2,
    # Outstanding=77.90% -> rank 4 => 0.5*4 + 0.3*2 + 0.2*4 = 3.4 -> High.
    r = S.compute_risk(0.7523, 92_677, 0.7790)
    assert r.pd_rank == 4
    assert r.ead_rank == 2
    assert r.outratio_rank == 4
    assert r.risk_score == 3.4
    assert r.band == "High Risk"


def test_band_boundaries():
    cfg = S.DEFAULT_CONFIG
    assert S.classify(3.51, cfg) == "Very High Risk"
    assert S.classify(3.5, cfg) == "High Risk"
    assert S.classify(3.0, cfg) == "High Risk"
    assert S.classify(2.99, cfg) == "Moderate Risk"
    assert S.classify(2.0, cfg) == "Moderate Risk"
    assert S.classify(1.99, cfg) == "Low Risk"


def test_rank_edges():
    assert S.rank_ead(49_999) == 1
    assert S.rank_ead(50_000) == 2
    assert S.rank_ead(500_001) == 4
    assert S.rank_probability(0.7499) == 3
    assert S.rank_probability(0.75) == 4
    assert S.rank_outstanding_ratio(0.25) == 2


def test_weights_must_sum_to_one():
    import pytest
    with pytest.raises(ValueError):
        S.RiskConfig(w_pd=0.5, w_ead=0.3, w_outratio=0.3).validate()
