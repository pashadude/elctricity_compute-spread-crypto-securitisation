"""Historical replay for syndicated proxy basket templates.

Spread-family replay asks whether the recorded compute/electricity index is
moving enough. This module asks the separate execution question: if the desk
expresses that thesis through liquid public proxies, did that basket actually
make money over recent history?

The module is read-only and data-source agnostic. Callers pass sanitized close
histories from Yahoo, IBKR exports, or fixtures; this code never calls venues,
brokers, Circle, or Arc.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

DEFAULT_MIN_DAYS = 20
DEFAULT_MIN_SYMBOLS = 3
DEFAULT_MIN_RETURN_PCT = 0.0
DEFAULT_MIN_WIN_RATE = 45.0
DEFAULT_MAX_DRAWDOWN_PCT = -35.0
TRAILING_WINDOWS: tuple[tuple[str, int], ...] = (
    ("5d", 5),
    ("1m", 21),
    ("3m", 63),
    ("6m", 126),
)


@dataclass(frozen=True, slots=True)
class ProxyBasketTemplate:
    basket_id: str
    label: str
    direction: str
    thesis: str
    weights: dict[str, float]


PROXY_BASKETS: tuple[ProxyBasketTemplate, ...] = (
    ProxyBasketTemplate(
        basket_id="compute_scarcity_ai_infra",
        label="Compute scarcity AI-infra basket",
        direction="compute_expensive",
        thesis="Long AI compute-demand and datacenter infrastructure proxies, short selected power-cost proxies.",
        weights={
            "NVDA": 0.34,
            "VRT": 0.20,
            "ETN": 0.14,
            "CEG": -0.14,
            "NRG": -0.10,
            "BTC-USD": 0.05,
            "ETH-USD": 0.03,
        },
    ),
    ProxyBasketTemplate(
        basket_id="power_stress_receivable_hedge",
        label="Power-stress receivable hedge",
        direction="electricity_expensive",
        thesis="Long merchant/baseload/grid equipment exposure, short compute and miner-margin-sensitive proxies.",
        weights={
            "NRG": 0.24,
            "CEG": 0.20,
            "ETN": 0.14,
            "VRT": 0.12,
            "NVDA": -0.20,
            "BTC-USD": -0.07,
            "ETH-USD": -0.03,
        },
    ),
    ProxyBasketTemplate(
        basket_id="grid_equipment_load_growth",
        label="Grid equipment load-growth basket",
        direction="compute_load_growth",
        thesis="Long electrical equipment, cooling, and baseload beneficiaries against generic GPU beta.",
        weights={
            "VRT": 0.30,
            "ETN": 0.28,
            "CEG": 0.18,
            "NRG": 0.12,
            "NVDA": -0.12,
        },
    ),
    ProxyBasketTemplate(
        basket_id="miner_margin_power_pair",
        label="Miner-margin power pair",
        direction="electricity_expensive",
        thesis="Short crypto miner-margin beta against power beneficiaries when electricity pressure rises.",
        weights={
            "BTC-USD": -0.45,
            "ETH-USD": -0.25,
            "NRG": 0.18,
            "CEG": 0.12,
        },
    ),
    ProxyBasketTemplate(
        basket_id="fuel_stack_power_input",
        label="Fuel-stack power input basket",
        direction="electricity_expensive",
        thesis="Long gas/oil input-cost proxies and power beneficiaries, short generic compute beta.",
        weights={
            "NG=F": 0.30,
            "BZ=F": 0.18,
            "NRG": 0.18,
            "CEG": 0.14,
            "NVDA": -0.20,
        },
    ),
)


def required_symbols() -> list[str]:
    symbols: list[str] = []
    for basket in PROXY_BASKETS:
        for symbol in basket.weights:
            if symbol not in symbols:
                symbols.append(symbol)
    return symbols


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


def _max_drawdown_pct(index_values: list[float]) -> float:
    if not index_values:
        return 0.0
    peak = index_values[0]
    worst = 0.0
    for value in index_values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, ((value / peak) - 1.0) * 100.0)
    return worst


def _trailing_returns(index_values: list[float], replay_dates: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    observations = len(index_values)
    if observations < 2:
        return out
    for label, points in TRAILING_WINDOWS:
        used = min(points, observations)
        if used < 2:
            continue
        start = index_values[-used]
        end = index_values[-1]
        ret = ((end / start) - 1.0) * 100.0 if start else 0.0
        out[label] = {
            "return_pct": round(ret, 4),
            "observations": used,
            "start_date": replay_dates[-used] if len(replay_dates) >= used else "",
            "end_date": replay_dates[-1] if replay_dates else "",
        }
    return out


def _latest_signal(
    *,
    recommendation: str,
    status: str,
    trailing_returns: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    five_day = _num((trailing_returns.get("5d") or {}).get("return_pct"), 0.0)
    one_month = _num((trailing_returns.get("1m") or {}).get("return_pct"), 0.0)
    has_five_day = "5d" in trailing_returns
    has_one_month = "1m" in trailing_returns
    if recommendation == "SELL_OR_AVOID":
        return "SELL", "Replay status is failed or drawdown-heavy."
    if has_five_day and five_day <= -2.0:
        return "SELL", "Recent 5d proxy PnL is below the sell threshold."
    if has_five_day and has_one_month and five_day < 0 and one_month < 0:
        return "SELL", "Both 5d and 1m proxy PnL are negative."
    if recommendation == "BUY_OR_HOLD" and has_five_day and five_day >= 0:
        return "BUY", "Promotable replay and recent proxy PnL is non-negative."
    if recommendation == "BUY_OR_HOLD":
        return "HOLD", "Promotable replay, but recent proxy PnL is not confirming a fresh buy."
    if status in {"INSUFFICIENT_DATA", "INSUFFICIENT_HISTORY"}:
        return "MONITOR", "Not enough aligned close history for a trade signal."
    return "MONITOR", "Proxy replay is not strong enough for a buy or sell signal."


def _status(
    *,
    observations: int,
    symbols_available: int,
    total_return_pct: float,
    win_rate: float,
    max_drawdown_pct: float,
    min_days: int,
    min_symbols: int,
    min_return_pct: float,
    min_win_rate: float,
    max_drawdown_floor_pct: float,
) -> tuple[str, str, bool, str]:
    if symbols_available < min_symbols:
        return (
            "INSUFFICIENT_DATA",
            f"Only {symbols_available} priced symbols were available; need at least {min_symbols}.",
            False,
            "MONITOR_ONLY",
        )
    if observations < min_days:
        return (
            "INSUFFICIENT_HISTORY",
            f"Only {observations} aligned history days were available; need at least {min_days}.",
            False,
            "MONITOR_ONLY",
        )
    if total_return_pct >= min_return_pct and win_rate >= min_win_rate and max_drawdown_pct >= max_drawdown_floor_pct:
        return (
            "PROMOTABLE",
            "Historical proxy basket replay is positive enough for a paper/testnet buy or hold signal.",
            True,
            "BUY_OR_HOLD",
        )
    if total_return_pct < -2.0 or max_drawdown_pct < max_drawdown_floor_pct:
        return (
            "FAILED_REPLAY",
            "Historical proxy basket replay is negative or drawdown-heavy; avoid opening and sell local mock tickets if already open.",
            False,
            "SELL_OR_AVOID",
        )
    return (
        "OBSERVE",
        "Proxy basket replay is not strong enough to promote a user-facing buy.",
        False,
        "MONITOR_ONLY",
    )


def replay_basket(
    histories: dict[str, dict[str, Any]],
    basket: ProxyBasketTemplate,
    *,
    min_days: int = DEFAULT_MIN_DAYS,
    min_symbols: int = DEFAULT_MIN_SYMBOLS,
    min_return_pct: float = DEFAULT_MIN_RETURN_PCT,
    min_win_rate: float = DEFAULT_MIN_WIN_RATE,
    max_drawdown_floor_pct: float = DEFAULT_MAX_DRAWDOWN_PCT,
) -> dict[str, Any]:
    normalized = _normalize_weights(basket.weights)
    by_symbol = {
        symbol: _history_by_date(histories.get(symbol, {}))
        for symbol in normalized
        if histories.get(symbol)
    }
    available_symbols = [symbol for symbol, marks in by_symbol.items() if marks]
    active_weights = _normalize_weights({
        symbol: basket.weights[symbol]
        for symbol in available_symbols
        if symbol in basket.weights
    })
    union_dates = sorted({date for marks in by_symbol.values() for date in marks})
    index_values: list[float] = []
    daily_returns: list[float] = []
    replay_dates: list[str] = []
    last_prices: dict[str, float] = {}
    prev_prices: dict[str, float] | None = None
    for date in union_dates:
        for symbol in available_symbols:
            price = by_symbol[symbol].get(date)
            if price is not None and price > 0:
                last_prices[symbol] = price
        if any(symbol not in last_prices for symbol in available_symbols):
            continue
        current_prices = {symbol: last_prices[symbol] for symbol in available_symbols}
        replay_dates.append(date)
        if prev_prices is None:
            index_values.append(100.0)
            prev_prices = current_prices
            continue
        daily = 0.0
        for symbol in available_symbols:
            prev = prev_prices.get(symbol, 0.0)
            cur = current_prices.get(symbol, 0.0)
            if prev <= 0 or cur <= 0:
                continue
            daily += active_weights.get(symbol, 0.0) * ((cur / prev) - 1.0)
        daily_returns.append(daily)
        index_values.append(index_values[-1] * (1.0 + daily))
        prev_prices = current_prices
    observations = len(index_values)
    total_return_pct = ((index_values[-1] / index_values[0]) - 1.0) * 100.0 if observations >= 2 and index_values[0] else 0.0
    win_rate = (sum(1 for value in daily_returns if value > 0) / len(daily_returns) * 100.0) if daily_returns else 0.0
    max_dd = _max_drawdown_pct(index_values)
    trailing_returns = _trailing_returns(index_values, replay_dates)
    status, reason, promotable, recommendation = _status(
        observations=observations,
        symbols_available=len(available_symbols),
        total_return_pct=total_return_pct,
        win_rate=win_rate,
        max_drawdown_pct=max_dd,
        min_days=min_days,
        min_symbols=min_symbols,
        min_return_pct=min_return_pct,
        min_win_rate=min_win_rate,
        max_drawdown_floor_pct=max_drawdown_floor_pct,
    )
    latest_signal, signal_reason = _latest_signal(
        recommendation=recommendation,
        status=status,
        trailing_returns=trailing_returns,
    )
    return {
        "basket_id": basket.basket_id,
        "label": basket.label,
        "direction": basket.direction,
        "thesis": basket.thesis,
        "weights": {symbol: round(weight, 4) for symbol, weight in normalized.items()},
        "symbols_required": list(normalized),
        "symbols_available": available_symbols,
        "missing_symbols": [symbol for symbol in normalized if symbol not in available_symbols],
        "observations": observations,
        "start_date": replay_dates[0] if replay_dates else "",
        "end_date": replay_dates[-1] if replay_dates else "",
        "total_return_pct": round(total_return_pct, 4),
        "win_rate": round(win_rate, 2),
        "max_drawdown_pct": round(max_dd, 4),
        "status": status,
        "status_reason": reason,
        "is_promotable": promotable,
        "recommendation": recommendation,
        "latest_signal": latest_signal,
        "signal_reason": signal_reason,
        "trailing_returns": trailing_returns,
        "recent_daily_returns_pct": [round(value * 100.0, 4) for value in daily_returns[-5:]],
    }


def summarize(
    histories: dict[str, dict[str, Any]],
    *,
    min_days: int = DEFAULT_MIN_DAYS,
    min_symbols: int = DEFAULT_MIN_SYMBOLS,
    min_return_pct: float = DEFAULT_MIN_RETURN_PCT,
    min_win_rate: float = DEFAULT_MIN_WIN_RATE,
    max_drawdown_floor_pct: float = DEFAULT_MAX_DRAWDOWN_PCT,
) -> dict[str, Any]:
    baskets = [
        replay_basket(
            histories,
            basket,
            min_days=min_days,
            min_symbols=min_symbols,
            min_return_pct=min_return_pct,
            min_win_rate=min_win_rate,
            max_drawdown_floor_pct=max_drawdown_floor_pct,
        )
        for basket in PROXY_BASKETS
    ]
    baskets.sort(
        key=lambda item: (
            0 if item["is_promotable"] else 1,
            -float(item.get("total_return_pct") or 0.0),
            item["basket_id"],
        )
    )
    primary = baskets[0] if baskets else None
    return {
        "version": "proxy_basket_replay_v1",
        "policy": "public_proxy_basket_buy_hold_replay",
        "source": "sanitized_close_history",
        "entry_gate_pass": any(item["is_promotable"] for item in baskets),
        "primary_basket": primary,
        "baskets": baskets,
        "symbols": required_symbols(),
        "caveat": (
            "This validates liquid proxy expression only. It does not prove the "
            "direct compute/energy spread or any event-contract settlement."
        ),
    }
