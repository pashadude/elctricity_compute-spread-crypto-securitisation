"""Kalshi adapter — read-only market data plus paper fills.

Kalshi is a direct event-contract surface for compute/AI and energy thesis
legs. This adapter reads public market data from Kalshi's unauthenticated
Trade API and never places venue orders.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from typing import Any, Iterable

import requests

from feeds import cache

KALSHI_API_BASE = "https://external-api.kalshi.com/trade-api/v2"
DEFAULT_AI_TERMS = (
    "ai",
    "artificial intelligence",
    "openai",
    "anthropic",
    "chatgpt",
    "deepseek",
    "gemini",
    "nvidia",
    "gpu",
    "llm",
    "agi",
    "frontier model",
    "ai model",
    "large language model",
    "data center",
    "compute",
    "semiconductor",
    "chip",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _yes_price(market: dict[str, Any]) -> float | None:
    bid = _float(market.get("yes_bid_dollars"))
    ask = _float(market.get("yes_ask_dollars"))
    if bid is not None and ask is not None and 0.0 <= bid <= ask <= 1.0:
        return round((bid + ask) / 2.0, 6)
    for key in ("last_price_dollars", "previous_price_dollars", "yes_ask_dollars", "yes_bid_dollars"):
        price = _float(market.get(key))
        if price is not None and 0.0 <= price <= 1.0:
            return price
    return None


def _event_text(event: dict[str, Any]) -> str:
    parts = [
        event.get("title"),
        event.get("sub_title"),
        event.get("category"),
        event.get("event_ticker"),
        event.get("series_ticker"),
    ]
    for market in event.get("markets") or []:
        if isinstance(market, dict):
            parts.extend([
                market.get("title"),
                market.get("yes_sub_title"),
                market.get("rules_primary"),
                market.get("rules_secondary"),
            ])
    return " ".join(_text(part) for part in parts if _text(part)).lower()


def _matches_terms(event: dict[str, Any], terms: Iterable[str] | None = None) -> bool:
    text = _event_text(event)
    for term in terms or DEFAULT_AI_TERMS:
        clean = _text(term).lower()
        if not clean:
            continue
        if clean in {"ai", "agi", "gpu", "llm", "chip"}:
            if re.search(rf"\b{re.escape(clean)}\b", text):
                return True
        elif clean in text:
            return True
    return False


def _event_sort_key(event: dict[str, Any]) -> tuple[int, float, str]:
    category = _text(event.get("category")).lower()
    category_score = 0 if "science" in category or "technology" in category else 1
    volume = 0.0
    for market in event.get("markets") or []:
        if isinstance(market, dict):
            volume += _float(market.get("volume_fp")) or 0.0
    return (category_score, -volume, _text(event.get("event_ticker")))


def _summarize_event(event: dict[str, Any]) -> dict[str, Any]:
    markets = [m for m in event.get("markets") or [] if isinstance(m, dict)]
    yes_prices = [price for price in (_yes_price(market) for market in markets) if price is not None]
    close_times = [
        _text(market.get("close_time") or market.get("expiration_time") or market.get("latest_expiration_time"))
        for market in markets
        if _text(market.get("close_time") or market.get("expiration_time") or market.get("latest_expiration_time"))
    ]
    descriptions = [
        _text(market.get("rules_primary") or market.get("title"))
        for market in markets[:3]
        if _text(market.get("rules_primary") or market.get("title"))
    ]
    liquidity = sum(_float(market.get("liquidity_dollars")) or 0.0 for market in markets)
    volume = sum(_float(market.get("volume_fp")) or 0.0 for market in markets)
    event_ticker = _text(event.get("event_ticker") or event.get("ticker"))
    return {
        "id": event_ticker,
        "event_ticker": event_ticker,
        "slug": event_ticker.lower(),
        "series_ticker": _text(event.get("series_ticker")),
        "title": _text(event.get("title") or event_ticker),
        "description": " ".join(descriptions),
        "category": _text(event.get("category")),
        "end_date": min(close_times) if close_times else "",
        "volume": round(volume, 2),
        "liquidity": round(liquidity, 2),
        "yes_prices": yes_prices,
        "mutually_exclusive": bool(event.get("mutually_exclusive")),
        "market_tickers": [_text(market.get("ticker")) for market in markets if _text(market.get("ticker"))],
        "markets_count": len(markets),
        "venue": "Kalshi",
        "source": "kalshi_public_api",
    }


def fetch_events(
    *,
    limit: int = 200,
    status: str = "open",
    with_nested_markets: bool = True,
    max_pages: int = 2,
    ttl: float = 60.0,
) -> list[dict[str, Any]]:
    """Fetch public Kalshi events without authentication."""
    limit = max(1, min(int(limit), 200))
    max_pages = max(1, int(max_pages))
    cache_key = f"limit={limit}|status={status}|nested={with_nested_markets}|pages={max_pages}"
    hit = cache.get("kalshi_events", cache_key)
    if hit is not None:
        return hit
    events: list[dict[str, Any]] = []
    cursor = ""
    for _page in range(max_pages):
        params: dict[str, Any] = {
            "limit": limit,
            "status": status,
            "with_nested_markets": str(bool(with_nested_markets)).lower(),
        }
        if cursor:
            params["cursor"] = cursor
        try:
            resp = requests.get(
                f"{KALSHI_API_BASE}/events",
                params=params,
                headers={"accept": "application/json", "user-agent": "arc-compute-sec/1.0"},
                timeout=12,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            if os.environ.get("KALSHI_DEBUG", "").strip():
                print(f"[kalshi] event fetch failed: {exc}", file=sys.stderr)
            break
        page_events = data.get("events") if isinstance(data, dict) else []
        if isinstance(page_events, list):
            events.extend(event for event in page_events if isinstance(event, dict))
        cursor = _text(data.get("cursor") if isinstance(data, dict) else "")
        if not cursor:
            break
    cache.put("kalshi_events", cache_key, events, ttl_seconds=ttl)
    return events


def fetch_ai_events(
    *,
    limit: int = 200,
    max_pages: int = 3,
    max_events: int = 8,
    terms: Iterable[str] | None = None,
    ttl: float = 60.0,
) -> list[dict[str, Any]]:
    """Return AI/compute-relevant Kalshi events normalized for routing."""
    raw = fetch_events(limit=limit, status="open", with_nested_markets=True, max_pages=max_pages, ttl=ttl)
    matched = [event for event in raw if _matches_terms(event, terms)]
    matched.sort(key=_event_sort_key)
    return [_summarize_event(event) for event in matched[:max_events]]


def paper_fill(
    instrument: str,
    direction: str,
    notional_usdc: float,
    *,
    yes_prices: list[float] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic paper fill snapshot; no Kalshi order is placed."""
    fill_ts = time.time()
    snapshot = {
        "surface": "kalshi",
        "instrument": instrument,
        "direction": direction,
        "notional_usdc": float(notional_usdc),
        "yes_prices_at_open": list(yes_prices or []),
        "metadata": metadata or {},
        "fill_ts": fill_ts,
    }
    raw = json.dumps(snapshot, sort_keys=True, default=str)
    snapshot.update({
        "entry_price": (sum(yes_prices or []) / len(yes_prices or [])) if yes_prices else 0.0,
        "fill_id": hashlib.sha256(f"{raw}|{fill_ts}".encode()).hexdigest()[:16],
        "raw_response_hash": hashlib.sha256(raw.encode()).hexdigest()[:16],
        "paper": True,
        "note": "Read-only Kalshi public-data snapshot; no venue order was placed.",
    })
    return snapshot
