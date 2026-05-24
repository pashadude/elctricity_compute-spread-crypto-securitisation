"""Small public-market quote adapter using Yahoo Finance chart JSON.

The adapter is read-only and optional. It exists to give the demo a priced
public hedge basket when IBKR event contracts are unavailable or unpriced.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"


def fetch_chart_quote(symbol: str, *, timeout: float = 4.0) -> dict[str, Any] | None:
    clean = str(symbol or "").strip().upper()
    if not clean:
        return None
    url = YAHOO_CHART_URL.format(symbol=urllib.parse.quote(clean, safe="-=."))
    req = urllib.request.Request(url, headers={"User-Agent": "arc-compute-sec/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body)
    result = ((data.get("chart") or {}).get("result") or [None])[0]
    if not isinstance(result, dict):
        return None
    meta = result.get("meta") or {}
    price = meta.get("regularMarketPrice")
    if price is None:
        price = meta.get("previousClose")
    if price is None:
        return None
    return {
        "symbol": clean,
        "price": float(price),
        "currency": str(meta.get("currency") or "USD"),
        "exchange": str(meta.get("exchangeName") or meta.get("fullExchangeName") or ""),
        "instrument_type": str(meta.get("instrumentType") or ""),
        "regular_market_time": meta.get("regularMarketTime") or "",
        "source": "yahoo_finance_chart",
    }
