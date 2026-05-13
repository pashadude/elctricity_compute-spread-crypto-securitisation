from adapters import polymarket


def test_simulate_gated_fill_records_snapshot():
    fr = polymarket.simulate_gated_fill("polymarket:ev1", [0.4, 0.4, 0.23])
    assert fr["surface"] == "polymarket"
    assert fr["instrument"] == "polymarket:ev1"
    assert fr["yes_prices_at_open"] == [0.4, 0.4, 0.23]
    assert round(fr["premium_at_open"], 4) == 0.03
    assert len(fr["fill_id"]) >= 8


def test_classify_and_gate_filters_non_energy(monkeypatch):
    # Build a small synthetic event list — one energy, one off-topic. The
    # energy one has overpriced YES sum so the scorer passes it.
    events = [
        {
            "id": "ev-energy", "slug": "wti-q3", "title": "Will WTI > $90 by Q3?",
            "description": "", "markets": [
                {"outcomePrice": "0.55"}, {"outcomePrice": "0.50"},
            ],
        },
        {
            "id": "ev-music", "slug": "ts-album", "title": "Will Taylor Swift release?",
            "description": "Music", "markets": [
                {"outcomePrice": "0.7"}, {"outcomePrice": "0.4"},
            ],
        },
    ]
    out = polymarket.classify_and_gate(events)
    ids = [e["id"] for e in out]
    assert "ev-energy" in ids
    assert "ev-music" not in ids
