"""Public power/fuel proxy for the live electricity mark.

EIA retail-sales data is monthly and stale by design. This module keeps EIA as
the anchor, then applies a small, labelled daily move from public power/fuel
quotes so the compute/energy spread can move between EIA releases.

This is not an ISO LMP feed. It is a transparent proxy mark used for demo
replay and routing evidence.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Callable

from adapters import yahoo_finance

DEFAULT_POWER_PROXY_WEIGHTS: dict[str, float] = {
    "NG=F": 0.45,
    "NRG": 0.25,
    "CEG": 0.20,
    "BZ=F": 0.10,
}
DEFAULT_MAX_MOVE_PCT = 0.25
DEFAULT_BETA = 1.0


@dataclass(frozen=True, slots=True)
class PowerProxyQuote:
    symbol: str
    price: float
    previous_close: float
    return_pct: float
    source: str


@dataclass(frozen=True, slots=True)
class PowerProxyMark:
    electricity_per_mwh: float
    base_electricity_per_mwh: float
    source: str
    status: str
    weighted_return_pct: float
    beta: float
    max_move_pct: float
    symbols: list[str]
    used_quotes: int
    quote_sources: list[str]
    formula: str
    quotes: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _configured_weights() -> dict[str, float]:
    raw_json = os.environ.get("POWER_PROXY_WEIGHTS_JSON", "").strip()
    weights: dict[str, float] = {}
    if raw_json:
        try:
            decoded = json.loads(raw_json)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, dict):
            for symbol, weight in decoded.items():
                try:
                    value = float(weight)
                except (TypeError, ValueError):
                    continue
                if value != 0:
                    weights[str(symbol).strip().upper()] = value
    if not weights:
        weights = dict(DEFAULT_POWER_PROXY_WEIGHTS)
    raw_symbols = os.environ.get("POWER_PROXY_SYMBOLS", "").strip()
    if raw_symbols:
        requested = [part.strip().upper() for part in raw_symbols.split(",") if part.strip()]
        weights = {symbol: weights.get(symbol, 1.0) for symbol in requested}
    return weights


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    gross = sum(abs(float(weight)) for weight in weights.values())
    if gross <= 0:
        return {}
    return {symbol: float(weight) / gross for symbol, weight in weights.items()}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _quote_from_chart(symbol: str, *, timeout: float) -> PowerProxyQuote | None:
    quote = yahoo_finance.fetch_chart_quote(symbol, timeout=timeout)
    if isinstance(quote, dict):
        price = _num(quote.get("price"))
        previous = _num(quote.get("previous_close"))
        if price > 0 and previous > 0:
            return PowerProxyQuote(
                symbol=str(quote.get("symbol") or symbol).upper(),
                price=price,
                previous_close=previous,
                return_pct=((price / previous) - 1.0) * 100.0,
                source=str(quote.get("source") or "yahoo_finance_chart"),
            )
    history = yahoo_finance.fetch_chart_history(symbol, range="5d", interval="1d", timeout=timeout)
    points = history.get("points") if isinstance(history, dict) else []
    valid = [point for point in points or [] if _num(point.get("close")) > 0]
    if len(valid) < 2:
        return None
    previous = _num(valid[-2].get("close"))
    price = _num(valid[-1].get("close"))
    if previous <= 0 or price <= 0:
        return None
    return PowerProxyQuote(
        symbol=str((history or {}).get("symbol") or symbol).upper(),
        price=price,
        previous_close=previous,
        return_pct=((price / previous) - 1.0) * 100.0,
        source=str((history or {}).get("source") or "yahoo_finance_chart"),
    )


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def mark_from_quotes(
    base_electricity_per_mwh: float,
    quotes: list[PowerProxyQuote],
    *,
    weights: dict[str, float] | None = None,
    beta: float = DEFAULT_BETA,
    max_move_pct: float = DEFAULT_MAX_MOVE_PCT,
    min_quotes: int = 2,
) -> PowerProxyMark:
    base = float(base_electricity_per_mwh)
    configured = weights or dict(DEFAULT_POWER_PROXY_WEIGHTS)
    normalized = _normalize_weights(configured)
    by_symbol = {quote.symbol.upper(): quote for quote in quotes}
    used = [symbol for symbol in normalized if symbol in by_symbol]
    quote_dicts = [
        {
            "symbol": quote.symbol,
            "price": round(quote.price, 6),
            "previous_close": round(quote.previous_close, 6),
            "return_pct": round(quote.return_pct, 6),
            "source": quote.source,
        }
        for quote in quotes
    ]
    if base <= 0:
        return PowerProxyMark(
            electricity_per_mwh=base,
            base_electricity_per_mwh=base,
            source="eia_retail_sales",
            status="invalid_base_mark",
            weighted_return_pct=0.0,
            beta=float(beta),
            max_move_pct=float(max_move_pct),
            symbols=list(configured),
            used_quotes=len(used),
            quote_sources=sorted({quote.source for quote in quotes}),
            formula="base_eia_mwh",
            quotes=quote_dicts,
        )
    if len(used) < min_quotes:
        return PowerProxyMark(
            electricity_per_mwh=base,
            base_electricity_per_mwh=base,
            source="eia_retail_sales",
            status="insufficient_proxy_quotes",
            weighted_return_pct=0.0,
            beta=float(beta),
            max_move_pct=float(max_move_pct),
            symbols=list(configured),
            used_quotes=len(used),
            quote_sources=sorted({quote.source for quote in quotes}),
            formula="base_eia_mwh",
            quotes=quote_dicts,
        )
    weighted_return = sum(normalized[symbol] * (by_symbol[symbol].return_pct / 100.0) for symbol in used)
    move = _clamp(float(beta) * weighted_return, -abs(float(max_move_pct)), abs(float(max_move_pct)))
    return PowerProxyMark(
        electricity_per_mwh=base * (1.0 + move),
        base_electricity_per_mwh=base,
        source="eia_plus_power_proxy",
        status="proxy_adjusted",
        weighted_return_pct=weighted_return * 100.0,
        beta=float(beta),
        max_move_pct=float(max_move_pct),
        symbols=used,
        used_quotes=len(used),
        quote_sources=sorted({by_symbol[symbol].source for symbol in used}),
        formula="base_eia_mwh * (1 + beta * weighted_public_power_return)",
        quotes=quote_dicts,
    )


def adjust_electricity_mark(
    base_electricity_per_mwh: float,
    *,
    enabled: bool | None = None,
    quote_fetcher: Callable[[str], PowerProxyQuote | None] | None = None,
) -> PowerProxyMark:
    """Return an EIA-anchored electricity mark with optional proxy adjustment."""
    is_enabled = bool_env("POWER_PROXY_ENABLED", True) if enabled is None else bool(enabled)
    weights = _configured_weights()
    beta = _float_env("POWER_PROXY_BETA", DEFAULT_BETA)
    max_move = _float_env("POWER_PROXY_MAX_MOVE_PCT", DEFAULT_MAX_MOVE_PCT)
    min_quotes = int(_float_env("POWER_PROXY_MIN_QUOTES", 2))
    if not is_enabled:
        base = float(base_electricity_per_mwh)
        return PowerProxyMark(
            electricity_per_mwh=base,
            base_electricity_per_mwh=base,
            source="eia_retail_sales",
            status="proxy_disabled",
            weighted_return_pct=0.0,
            beta=float(beta),
            max_move_pct=float(max_move),
            symbols=list(weights),
            used_quotes=0,
            quote_sources=[],
            formula="base_eia_mwh",
            quotes=[],
        )
    timeout = _float_env("POWER_PROXY_TIMEOUT", 2.5)
    quotes: list[PowerProxyQuote] = []
    fetcher = quote_fetcher or (lambda symbol: _quote_from_chart(symbol, timeout=timeout))
    for symbol in weights:
        try:
            quote = fetcher(symbol)
        except Exception:
            quote = None
        if quote is not None:
            quotes.append(quote)
    return mark_from_quotes(
        base_electricity_per_mwh,
        quotes,
        weights=weights,
        beta=beta,
        max_move_pct=max_move,
        min_quotes=min_quotes,
    )
