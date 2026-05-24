import json

from adapters import yahoo_finance


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def test_fetch_chart_quote_parses_regular_market_price(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["timeout"] = timeout
        return _Resp({
            "chart": {
                "result": [{
                    "meta": {
                        "regularMarketPrice": 180.25,
                        "currency": "USD",
                        "exchangeName": "NMS",
                        "instrumentType": "EQUITY",
                        "regularMarketTime": 1779630000,
                    }
                }]
            }
        })

    monkeypatch.setattr(yahoo_finance.urllib.request, "urlopen", fake_urlopen)

    quote = yahoo_finance.fetch_chart_quote("nvda", timeout=1.5)

    assert seen["url"].endswith("/NVDA?range=1d&interval=1d")
    assert seen["timeout"] == 1.5
    assert quote == {
        "symbol": "NVDA",
        "price": 180.25,
        "currency": "USD",
        "exchange": "NMS",
        "instrument_type": "EQUITY",
        "regular_market_time": 1779630000,
        "source": "yahoo_finance_chart",
    }


def test_fetch_chart_quote_returns_none_without_price(monkeypatch):
    monkeypatch.setattr(
        yahoo_finance.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _Resp({"chart": {"result": [{"meta": {}}]}}),
    )

    assert yahoo_finance.fetch_chart_quote("NVDA") is None
