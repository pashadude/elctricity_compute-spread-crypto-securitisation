from adapters import yahoo_finance


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_fetch_chart_quote_parses_regular_market_price(monkeypatch):
    seen = {}

    def fake_get(url, headers, timeout):
        seen["url"] = url
        seen["headers"] = headers
        seen["timeout"] = timeout
        return _Resp({
            "chart": {
                "result": [{
                    "meta": {
                        "regularMarketPrice": 180.25,
                        "previousClose": 175.0,
                        "currency": "USD",
                        "exchangeName": "NMS",
                        "instrumentType": "EQUITY",
                        "regularMarketTime": 1779630000,
                    }
                }]
            }
        })

    monkeypatch.setattr(yahoo_finance.requests, "get", fake_get)

    quote = yahoo_finance.fetch_chart_quote("nvda", timeout=1.5)

    assert seen["url"].endswith("/NVDA?range=1d&interval=1d")
    assert seen["headers"]["User-Agent"] == "arc-compute-sec/1.0"
    assert seen["timeout"] == 1.5
    assert quote == {
        "symbol": "NVDA",
        "price": 180.25,
        "previous_close": 175.0,
        "return_pct": ((180.25 / 175.0) - 1.0) * 100.0,
        "currency": "USD",
        "exchange": "NMS",
        "instrument_type": "EQUITY",
        "regular_market_time": 1779630000,
        "source": "yahoo_finance_chart",
    }


def test_fetch_chart_quote_returns_none_without_price(monkeypatch):
    monkeypatch.setattr(
        yahoo_finance.requests,
        "get",
        lambda *_args, **_kwargs: _Resp({"chart": {"result": [{"meta": {}}]}}),
    )

    assert yahoo_finance.fetch_chart_quote("NVDA") is None


def test_fetch_chart_history_parses_daily_closes(monkeypatch):
    seen = {}

    def fake_get(url, headers, timeout):
        seen["url"] = url
        seen["headers"] = headers
        seen["timeout"] = timeout
        return _Resp({
            "chart": {
                "result": [{
                    "meta": {
                        "currency": "USD",
                        "exchangeName": "NMS",
                        "instrumentType": "EQUITY",
                    },
                    "timestamp": [1779400000, 1779486400, 1779572800],
                    "indicators": {
                        "quote": [{
                            "close": [180.0, None, 183.6],
                        }],
                    },
                }]
            }
        })

    monkeypatch.setattr(yahoo_finance.requests, "get", fake_get)

    history = yahoo_finance.fetch_chart_history("nvda", range="3mo", interval="1d", timeout=1.5)

    assert seen["url"].endswith("/NVDA?range=3mo&interval=1d")
    assert seen["headers"]["User-Agent"] == "arc-compute-sec/1.0"
    assert seen["timeout"] == 1.5
    assert history == {
        "symbol": "NVDA",
        "currency": "USD",
        "exchange": "NMS",
        "instrument_type": "EQUITY",
        "range": "3mo",
        "interval": "1d",
        "points": [
            {"ts": 1779400000, "close": 180.0},
            {"ts": 1779572800, "close": 183.6},
        ],
        "source": "yahoo_finance_chart",
    }
