from unittest.mock import patch

from adapters import crypto
from feeds.coinbase import CryptoQuote


def _quote(symbol="BTC/USD", bid=60000.0, ask=60100.0, last=60050.0, ts=1):
    return CryptoQuote(symbol=symbol, bid=bid, ask=ask, last=last, timestamp_ms=ts)


def test_paper_fill_long_uses_ask():
    with patch("adapters.crypto.fetch_ticker", return_value=_quote()):
        fr = crypto.paper_fill("BTC/USD", "long", notional_usdc=10.0)
    assert fr["surface"] == "crypto"
    assert fr["entry_price"] == 60100.0
    assert round(fr["qty"], 8) == round(10.0 / 60100.0, 8)


def test_paper_fill_short_uses_bid():
    with patch("adapters.crypto.fetch_ticker", return_value=_quote()):
        fr = crypto.paper_fill("BTC/USD", "short", notional_usdc=10.0)
    assert fr["entry_price"] == 60000.0


def test_paper_fill_falls_back_to_last_when_bid_zero():
    with patch("adapters.crypto.fetch_ticker", return_value=_quote(bid=0, ask=0)):
        fr = crypto.paper_fill("BTC/USD", "short", notional_usdc=10.0)
    assert fr["entry_price"] == 60050.0


def test_coinbase_quote_is_cache_serializable(monkeypatch, tmp_path):
    from feeds import coinbase

    class FakeExchange:
        def fetch_ticker(self, symbol):
            return {
                "bid": 60000.0,
                "ask": 60100.0,
                "last": 60050.0,
                "timestamp": 1,
            }

    monkeypatch.setattr(coinbase, "_client", lambda: FakeExchange())
    q1 = coinbase.fetch_ticker("UNIT-TEST/USD", ttl=60)
    q2 = coinbase.fetch_ticker("UNIT-TEST/USD", ttl=60)
    assert q1.symbol == "UNIT-TEST/USD"
    assert q1 == q2
