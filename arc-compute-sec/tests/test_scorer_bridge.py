from agent import scorer_bridge


def test_gate_passes_when_premium_non_negative():
    # price + event_avg_yes = 0.55 + 0.50 = 1.05 ≥ 1.0
    r = scorer_bridge.score_candidate(price=0.55, event_avg_yes_price=0.50)
    assert r.passes_gate
    assert r.premium == 0.55 + 0.50 - 1.0


def test_gate_rejects_when_premium_negative():
    r = scorer_bridge.score_candidate(price=0.30, event_avg_yes_price=0.50)
    assert not r.passes_gate
    assert r.premium < 0


def test_gate_at_boundary_passes():
    r = scorer_bridge.score_candidate(price=0.50, event_avg_yes_price=0.50)
    assert r.passes_gate
