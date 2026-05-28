"""Small public-market quote adapter using Yahoo Finance chart JSON.

The adapter is read-only and optional. It exists to give the demo a priced
public hedge basket when IBKR event contracts are unavailable or unpriced.
"""
from __future__ import annotations

import urllib.parse
from typing import Any

import requests

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range}&interval={interval}"


def _load_chart_json(url: str, *, timeout: float) -> dict[str, Any]:
    resp = requests.get(url, headers={"User-Agent": "arc-compute-sec/1.0"}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def fetch_chart_quote(symbol: str, *, timeout: float = 4.0) -> dict[str, Any] | None:
    clean = str(symbol or "").strip().upper()
    if not clean:
        return None
    url = YAHOO_CHART_URL.format(symbol=urllib.parse.quote(clean, safe="-=."), range="1d", interval="1d")
    data = _load_chart_json(url, timeout=timeout)
    result = ((data.get("chart") or {}).get("result") or [None])[0]
    if not isinstance(result, dict):
        return None
    meta = result.get("meta") or {}
    price = meta.get("regularMarketPrice")
    if price is None:
        price = meta.get("previousClose")
    if price is None:
        return None
    previous_close = meta.get("previousClose")
    if previous_close is None:
        previous_close = meta.get("chartPreviousClose")
    out = {
        "symbol": clean,
        "price": float(price),
        "currency": str(meta.get("currency") or "USD"),
        "exchange": str(meta.get("exchangeName") or meta.get("fullExchangeName") or ""),
        "instrument_type": str(meta.get("instrumentType") or ""),
        "regular_market_time": meta.get("regularMarketTime") or "",
        "source": "yahoo_finance_chart",
    }
    if previous_close is not None:
        try:
            previous = float(previous_close)
        except (TypeError, ValueError):
            previous = 0.0
        if previous > 0:
            out["previous_close"] = previous
            out["return_pct"] = ((float(price) / previous) - 1.0) * 100.0
    return out


def fetch_chart_history(
    symbol: str,
    *,
    range: str = "6mo",
    interval: str = "1d",
    timeout: float = 4.0,
) -> dict[str, Any] | None:
    """Fetch daily public close history from Yahoo's chart endpoint.

    The adapter is intentionally small and read-only. It returns sanitized
    timestamp/close rows so callers can run local backtests without storing
    Yahoo's raw response in product state.
    """
    clean = str(symbol or "").strip().upper()
    if not clean:
        return None
    url = YAHOO_CHART_URL.format(
        symbol=urllib.parse.quote(clean, safe="-=."),
        range=urllib.parse.quote(str(range), safe=""),
        interval=urllib.parse.quote(str(interval), safe=""),
    )
    data = _load_chart_json(url, timeout=timeout)
    result = ((data.get("chart") or {}).get("result") or [None])[0]
    if not isinstance(result, dict):
        return None
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    quotes = (((result.get("indicators") or {}).get("quote") or [{}])[0]) or {}
    closes = quotes.get("close") or []
    points = []
    for ts, close in zip(timestamps, closes):
        try:
            price = float(close)
            ts_value = int(ts)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        points.append({"ts": ts_value, "close": price})
    if not points:
        return None
    return {
        "symbol": clean,
        "currency": str(meta.get("currency") or "USD"),
        "exchange": str(meta.get("exchangeName") or meta.get("fullExchangeName") or ""),
        "instrument_type": str(meta.get("instrumentType") or ""),
        "range": str(range),
        "interval": str(interval),
        "points": points,
        "source": "yahoo_finance_chart",
    }
