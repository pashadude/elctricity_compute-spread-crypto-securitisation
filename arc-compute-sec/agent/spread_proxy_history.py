"""Build daily compute/energy spread marks from public proxy histories.

The live spread history can be flat when EIA updates monthly and AWS spot only
moves occasionally. This module builds a separate, explicitly labelled replay
surface from public close histories:

- electricity index: fuel/power proxy basket anchored to the current EIA/power
  mark;
- compute index: compute-infra proxy basket anchored to the current AWS GPU
  spot mark.

It is read-only evidence. It does not route, judge, trade, call Circle, or call
Arc.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.arb_identifier import DEFAULT_K, DEFAULT_KWH_PER_GPU_HR

DEFAULT_ELECTRICITY_PROXY_WEIGHTS: dict[str, float] = {
    "NG=F": 0.45,
    "NRG": 0.25,
    "CEG": 0.20,
    "BZ=F": 0.10,
}
DEFAULT_COMPUTE_PROXY_WEIGHTS: dict[str, float] = {
    "NVDA": 0.45,
    "VRT": 0.25,
    "ETN": 0.20,
    "BTC-USD": 0.10,
}
DEFAULT_MIN_SYMBOLS = 2
DEFAULT_REGION = "ERCOT|public-proxy-compute"


@dataclass(frozen=True, slots=True)
class ProxyIndexResult:
    label: str
    weights: dict[str, float]
    symbols_available: list[str]
    missing_symbols: list[str]
    dates: list[str]
    values: list[float]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _date_key(ts: Any) -> str:
    try:
        timestamp = int(float(ts))
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()


def _history_by_date(history: dict[str, Any]) -> dict[str, float]:
    points = history.get("points") if isinstance(history, dict) else []
    out: dict[str, float] = {}
    for point in points or []:
        if not isinstance(point, dict):
            continue
        date = _date_key(point.get("ts"))
        close = _num(point.get("close"))
        if date and close > 0:
            out[date] = close
    return out


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    gross = sum(abs(_num(weight)) for weight in weights.values())
    if gross <= 0:
        return {}
    return {symbol: _num(weight) / gross for symbol, weight in weights.items()}


def build_proxy_index(
    histories: dict[str, dict[str, Any]],
    *,
    weights: dict[str, float],
    anchor_value: float,
    label: str,
    min_symbols: int = DEFAULT_MIN_SYMBOLS,
) -> ProxyIndexResult:
    """Build an anchored index from aligned public close histories.

    Daily returns are weight-summed. Missing closes are carried forward after a
    symbol has its first valid mark, matching the proxy-basket replay policy.
    The whole index is rescaled so the latest aligned value equals
    `anchor_value`.
    """
    normalized = _normalize_weights(weights)
    by_symbol = {
        symbol: _history_by_date(histories.get(symbol, {}))
        for symbol in normalized
        if histories.get(symbol)
    }
    available = [symbol for symbol, marks in by_symbol.items() if marks]
    missing = [symbol for symbol in normalized if symbol not in available]
    if len(available) < min_symbols or anchor_value <= 0:
        return ProxyIndexResult(
            label=label,
            weights=normalized,
            symbols_available=available,
            missing_symbols=missing,
            dates=[],
            values=[],
        )
    active_weights = _normalize_weights({symbol: weights[symbol] for symbol in available})
    union_dates = sorted({date for marks in by_symbol.values() for date in marks})
    last_prices: dict[str, float] = {}
    prev_prices: dict[str, float] | None = None
    dates: list[str] = []
    index_values: list[float] = []
    for date in union_dates:
        for symbol in available:
            price = by_symbol[symbol].get(date)
            if price is not None and price > 0:
                last_prices[symbol] = price
        if any(symbol not in last_prices for symbol in available):
            continue
        current = {symbol: last_prices[symbol] for symbol in available}
        dates.append(date)
        if prev_prices is None:
            index_values.append(1.0)
            prev_prices = current
            continue
        daily_return = 0.0
        for symbol in available:
            previous = prev_prices.get(symbol, 0.0)
            price = current.get(symbol, 0.0)
            if previous <= 0 or price <= 0:
                continue
            daily_return += active_weights.get(symbol, 0.0) * ((price / previous) - 1.0)
        index_values.append(index_values[-1] * (1.0 + daily_return))
        prev_prices = current
    if not index_values or index_values[-1] <= 0:
        values: list[float] = []
    else:
        scale = float(anchor_value) / index_values[-1]
        values = [value * scale for value in index_values]
    return ProxyIndexResult(
        label=label,
        weights={symbol: round(weight, 6) for symbol, weight in normalized.items()},
        symbols_available=available,
        missing_symbols=missing,
        dates=dates,
        values=values,
    )


def build_spread_rows(
    histories: dict[str, dict[str, Any]],
    *,
    electricity_anchor_per_mwh: float,
    compute_anchor_per_gpu_hr: float,
    electricity_weights: dict[str, float] | None = None,
    compute_weights: dict[str, float] | None = None,
    k: float = DEFAULT_K,
    kwh_per_gpu_hr: float = DEFAULT_KWH_PER_GPU_HR,
    region: str = DEFAULT_REGION,
    min_symbols: int = DEFAULT_MIN_SYMBOLS,
) -> dict[str, Any]:
    electricity = build_proxy_index(
        histories,
        weights=electricity_weights or DEFAULT_ELECTRICITY_PROXY_WEIGHTS,
        anchor_value=electricity_anchor_per_mwh,
        label="public fuel/power electricity proxy",
        min_symbols=min_symbols,
    )
    compute = build_proxy_index(
        histories,
        weights=compute_weights or DEFAULT_COMPUTE_PROXY_WEIGHTS,
        anchor_value=compute_anchor_per_gpu_hr,
        label="public compute-infra proxy",
        min_symbols=min_symbols,
    )
    by_date: dict[str, dict[str, float]] = {}
    for date, value in zip(electricity.dates, electricity.values):
        by_date.setdefault(date, {})["electricity_per_mwh"] = value
    for date, value in zip(compute.dates, compute.values):
        by_date.setdefault(date, {})["compute_per_gpu_hr"] = value
    rows: list[dict[str, Any]] = []
    for date in sorted(by_date):
        marks = by_date[date]
        elec = marks.get("electricity_per_mwh")
        compute_value = marks.get("compute_per_gpu_hr")
        if elec is None or compute_value is None:
            continue
        dt = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
        s_t = float(compute_value) - float(k) * (float(elec) / 1000.0) * float(kwh_per_gpu_hr)
        rows.append({
            "ts": int(dt.timestamp()),
            "date": date,
            "region": region,
            "electricity_per_mwh": round(float(elec), 6),
            "compute_per_gpu_hr": round(float(compute_value), 6),
            "S_t": round(s_t, 6),
            "k": round(float(k), 6),
            "kwh_per_gpu_hr": round(float(kwh_per_gpu_hr), 6),
            "mark_source": "public_proxy_history",
            "electricity_index": electricity.label,
            "compute_index": compute.label,
        })
    return {
        "version": "spread_proxy_history_v1",
        "source": "public_close_history",
        "rows": rows,
        "electricity_index": {
            "label": electricity.label,
            "symbols_available": electricity.symbols_available,
            "missing_symbols": electricity.missing_symbols,
            "weights": electricity.weights,
        },
        "compute_index": {
            "label": compute.label,
            "symbols_available": compute.symbols_available,
            "missing_symbols": compute.missing_symbols,
            "weights": compute.weights,
        },
        "status": "READY" if rows else "INSUFFICIENT_HISTORY",
    }


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "ts", "date", "region", "electricity_per_mwh", "compute_per_gpu_hr",
        "S_t", "k", "kwh_per_gpu_hr", "mark_source", "electricity_index",
        "compute_index",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in headers})
