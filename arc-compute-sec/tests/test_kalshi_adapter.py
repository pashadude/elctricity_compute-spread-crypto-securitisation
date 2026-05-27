from adapters import kalshi


def test_fetch_ai_events_filters_and_normalizes(monkeypatch):
    raw_events = [
        {
            "event_ticker": "KXOPENAI-26",
            "series_ticker": "KXOPENAI",
            "category": "Science and Technology",
            "mutually_exclusive": True,
            "title": "Will OpenAI release GPT-6 before 2027?",
            "markets": [
                {
                    "ticker": "KXOPENAI-26",
                    "title": "Will OpenAI release GPT-6 before 2027?",
                    "yes_bid_dollars": "0.5200",
                    "yes_ask_dollars": "0.5600",
                    "volume_fp": "100",
                    "liquidity_dollars": "12.50",
                    "close_time": "2026-12-31T15:00:00Z",
                    "rules_primary": "If OpenAI releases GPT-6 before 2027, resolves Yes.",
                },
                {
                    "ticker": "KXOPENAI-26-ALT",
                    "title": "Will OpenAI release another frontier model?",
                    "yes_bid_dollars": "0.4900",
                    "yes_ask_dollars": "0.5100",
                    "volume_fp": "50",
                    "liquidity_dollars": "8.00",
                    "close_time": "2026-12-31T15:00:00Z",
                },
            ],
        },
        {
            "event_ticker": "KXMUSIC-26",
            "category": "Entertainment",
            "title": "Will a pop album release?",
            "markets": [{"ticker": "KXMUSIC-26", "yes_bid_dollars": "0.1", "yes_ask_dollars": "0.2"}],
        },
    ]
    monkeypatch.setattr(kalshi, "fetch_events", lambda **kwargs: raw_events)

    events = kalshi.fetch_ai_events(max_events=4)

    assert len(events) == 1
    assert events[0]["event_ticker"] == "KXOPENAI-26"
    assert events[0]["slug"] == "kxopenai-26"
    assert events[0]["yes_prices"] == [0.54, 0.5]
    assert events[0]["mutually_exclusive"] is True
    assert events[0]["category"] == "Science and Technology"
    assert events[0]["market_tickers"] == ["KXOPENAI-26", "KXOPENAI-26-ALT"]


def test_fetch_ai_events_does_not_match_short_terms_across_words(monkeypatch):
    raw_events = [{
        "event_ticker": "KXTRILLIONAIRE-30",
        "category": "Economics",
        "title": "Who will be the world's first trillionaire?",
        "markets": [{
            "ticker": "KXTRILLIONAIRE-30-MZ",
            "title": "Will Mark Zuckerberg be the world's first trillionaire?",
            "yes_bid_dollars": "0.01",
            "yes_ask_dollars": "0.02",
        }],
    }]
    monkeypatch.setattr(kalshi, "fetch_events", lambda **kwargs: raw_events)

    assert kalshi.fetch_ai_events(max_events=4) == []


def test_paper_fill_is_read_only_snapshot():
    fill = kalshi.paper_fill(
        "kalshi:KXOPENAI-26",
        "short",
        1.0,
        yes_prices=[0.54, 0.5],
        metadata={"event_id": "KXOPENAI-26"},
    )

    assert fill["surface"] == "kalshi"
    assert fill["paper"] is True
    assert fill["yes_prices_at_open"] == [0.54, 0.5]
    assert "no venue order" in fill["note"].lower()
    assert len(fill["raw_response_hash"]) == 16
