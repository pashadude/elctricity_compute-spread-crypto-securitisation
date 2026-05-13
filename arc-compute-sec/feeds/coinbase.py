"""Coinbase public ticker via CCXT. No auth.

Used by `adapters/crypto.py` to obtain paper-fill prices for BTC/ETH and
by the arb_identifier as an aux compute-side signal (miner economics).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import ccxt

from . import cache

_EXCHANGE_ID = "coinbase"


@dataclass(frozen=True, slots=True)
class CryptoQuote:
    symbol: str
    bid: float
    ask: float
    last: float
    timestamp_ms: int


def _client() -> "ccxt.Exchange":
    cls = getattr(ccxt, _EXCHANGE_ID)
    return cls({"enableRateLimit": True})


def fetch_ticker(symbol: str = "BTC/USD", ttl: float = 30.0) -> CryptoQuote:
    """Fetch a single ticker. CCXT normalises field names across exchanges."""
    hit = cache.get("coinbase_ticker", symbol)
    if hit is not None:
        return CryptoQuote(**hit)
    ex = _client()
    t = ex.fetch_ticker(symbol)
    bid = float(t.get("bid") or t.get("last") or 0.0)
    ask = float(t.get("ask") or t.get("last") or 0.0)
    last = float(t.get("last") or 0.0)
    ts = int(t.get("timestamp") or 0)
    quote = CryptoQuote(symbol=symbol, bid=bid, ask=ask, last=last, timestamp_ms=ts)
    cache.put("coinbase_ticker", symbol, quote.__dict__, ttl_seconds=ttl)
    return quote


def fetch_tickers(symbols: Iterable[str] = ("BTC/USD", "ETH/USD")) -> dict[str, CryptoQuote]:
    return {s: fetch_ticker(s) for s in symbols}
