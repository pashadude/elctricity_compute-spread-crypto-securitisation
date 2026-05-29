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
DEFAULT_RECENT_MARK_DAYS = 7
DEFAULT_TRADE_SHORT_WINDOW = 5
DEFAULT_TRADE_LONG_WINDOW = 21
DEFAULT_TRADE_EXIT_RETURN_PCT = -2.0
DEFAULT_OOS_TRAIN_SHARE = 0.70
DEFAULT_OOS_MIN_TRAIN_OBSERVATIONS = 15
DEFAULT_OOS_MIN_TEST_OBSERVATIONS = 5
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
    ProxyBasketTemplate(
        basket_id="compute_calendar_ai_capex",
        label="Compute calendar AI-capex basket",
        direction="compute_expensive",
        thesis="Long prompt AI compute beneficiaries against power-cost proxies when spot GPU rental tightens versus term history.",
        weights={
            "NVDA": 0.36,
            "VRT": 0.22,
            "ETN": 0.16,
            "CEG": -0.12,
            "NRG": -0.08,
            "BTC-USD": 0.04,
            "ETH-USD": 0.02,
        },
    ),
    ProxyBasketTemplate(
        basket_id="electricity_calendar_power_prompt",
        label="Electricity calendar power-prompt basket",
        direction="electricity_expensive",
        thesis="Long prompt power/fuel beneficiaries and short generic compute beta when front power tightens versus term history.",
        weights={
            "NG=F": 0.26,
            "BZ=F": 0.16,
            "NRG": 0.22,
            "CEG": 0.18,
            "ETN": 0.10,
            "NVDA": -0.08,
        },
    ),
    ProxyBasketTemplate(
        basket_id="compute_power_calendar_pair",
        label="Compute-power calendar basis basket",
        direction="compute_expensive",
        thesis="Long prompt compute beneficiaries and short power/fuel proxies when compute calendar premium widens versus power calendar premium.",
        weights={
            "NVDA": 0.34,
            "VRT": 0.20,
            "ETN": 0.16,
            "NG=F": -0.12,
            "CEG": -0.10,
            "NRG": -0.08,
        },
    ),
    ProxyBasketTemplate(
        basket_id="regional_compute_capacity_basis",
        label="Regional compute capacity basis basket",
        direction="compute_expensive",
        thesis="Long regional compute-capacity beneficiaries and short power-cost proxies when one compute region gets rich versus another.",
        weights={
            "NVDA": 0.32,
            "VRT": 0.24,
            "ETN": 0.16,
            "CEG": -0.12,
            "NRG": -0.10,
            "BTC-USD": 0.06,
        },
    ),
    ProxyBasketTemplate(
        basket_id="regional_power_congestion_basis",
        label="Regional power congestion basis basket",
        direction="electricity_expensive",
        thesis="Long merchant power, baseload, and grid-equipment proxies when one power region gets rich/congested versus another.",
        weights={
            "NRG": 0.26,
            "CEG": 0.20,
            "ETN": 0.18,
            "VRT": 0.12,
            "NG=F": 0.12,
            "NVDA": -0.12,
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


def _recent_index_marks(
    index_values: list[float],
    replay_dates: list[str],
    daily_returns: list[float],
    *,
    days: int = DEFAULT_RECENT_MARK_DAYS,
) -> list[dict[str, Any]]:
    if not index_values or not replay_dates:
        return []
    start_idx = max(0, len(index_values) - max(1, days))
    entry_value = index_values[start_idx]
    rows: list[dict[str, Any]] = []
    for idx in range(start_idx, len(index_values)):
        daily_return = daily_returns[idx - 1] if idx > 0 and idx - 1 < len(daily_returns) else 0.0
        since_entry = ((index_values[idx] / entry_value) - 1.0) * 100.0 if entry_value else 0.0
        rows.append({
            "date": replay_dates[idx] if idx < len(replay_dates) else "",
            "mark_type": "entry" if idx == start_idx else "mark",
            "index_close": round(index_values[idx], 4),
            "daily_return_pct": round(daily_return * 100.0, 4),
            "paper_return_since_entry_pct": round(since_entry, 4),
        })
    return rows


def _win_rate_pct(values: list[float]) -> float:
    return sum(1 for value in values if value > 0.0) / len(values) * 100.0 if values else 0.0


def _out_of_sample_replay(
    index_values: list[float],
    replay_dates: list[str],
    daily_returns: list[float],
    *,
    train_share: float = DEFAULT_OOS_TRAIN_SHARE,
    min_train_observations: int = DEFAULT_OOS_MIN_TRAIN_OBSERVATIONS,
    min_test_observations: int = DEFAULT_OOS_MIN_TEST_OBSERVATIONS,
    min_test_return_pct: float = DEFAULT_MIN_RETURN_PCT,
    min_test_win_rate: float = DEFAULT_MIN_WIN_RATE,
) -> dict[str, Any]:
    """Split the basket replay into train and test windows.

    This is not a fitted model yet; it is a discipline check. A basket that
    only looks good because of the early sample should not be promoted as a
    fresh paper buy without showing the test slice separately.
    """
    observations = min(len(index_values), len(replay_dates))
    if observations < min_train_observations + min_test_observations:
        return {
            "version": "proxy_oos_replay_v1",
            "policy": "fixed_70_30_train_test_split",
            "status": "INSUFFICIENT_HISTORY",
            "passed": False,
            "reason": (
                f"Need at least {min_train_observations + min_test_observations} aligned marks "
                "for a train/test replay."
            ),
            "observations": observations,
        }

    split_idx = int(round((observations - 1) * max(0.1, min(0.9, train_share))))
    split_idx = max(min_train_observations - 1, min(split_idx, observations - min_test_observations))
    train_start = index_values[0]
    train_end = index_values[split_idx]
    test_start = index_values[split_idx]
    test_end = index_values[-1]
    train_daily = daily_returns[:split_idx]
    test_daily = daily_returns[split_idx:]
    train_return = ((train_end / train_start) - 1.0) * 100.0 if train_start else 0.0
    test_return = ((test_end / test_start) - 1.0) * 100.0 if test_start else 0.0
    train_win = _win_rate_pct(train_daily)
    test_win = _win_rate_pct(test_daily)
    passed = test_return >= min_test_return_pct and test_win >= min_test_win_rate
    return {
        "version": "proxy_oos_replay_v1",
        "policy": "fixed_70_30_train_test_split",
        "status": "PASSED" if passed else "FAILED",
        "passed": passed,
        "reason": (
            "Test slice return and hit rate clear the replay floor."
            if passed
            else "Test slice does not clear the replay floor; do not promote from full-sample PnL alone."
        ),
        "observations": observations,
        "train_observations": split_idx + 1,
        "test_observations": observations - split_idx,
        "train_start_date": replay_dates[0] if replay_dates else "",
        "train_end_date": replay_dates[split_idx] if split_idx < len(replay_dates) else "",
        "test_start_date": replay_dates[split_idx] if split_idx < len(replay_dates) else "",
        "test_end_date": replay_dates[-1] if replay_dates else "",
        "train_return_pct": round(train_return, 4),
        "train_win_rate": round(train_win, 2),
        "test_return_pct": round(test_return, 4),
        "test_win_rate": round(test_win, 2),
    }


def _window_return_pct(index_values: list[float], end_idx: int, points: int) -> float | None:
    if points < 2 or end_idx < points - 1 or end_idx >= len(index_values):
        return None
    start_idx = end_idx - points + 1
    start = index_values[start_idx]
    end = index_values[end_idx]
    if start <= 0:
        return None
    return ((end / start) - 1.0) * 100.0


def _paper_trade_replay(
    index_values: list[float],
    replay_dates: list[str],
    *,
    short_window: int = DEFAULT_TRADE_SHORT_WINDOW,
    long_window: int = DEFAULT_TRADE_LONG_WINDOW,
    exit_return_pct: float = DEFAULT_TRADE_EXIT_RETURN_PCT,
) -> dict[str, Any]:
    """Simulate simple close-to-close paper tickets from prior close signals.

    This is intentionally conservative and venue-agnostic. It does not infer
    fills; it asks whether the proxy basket would have generated usable
    operator tickets if the desk only entered after short and long trailing
    returns were non-negative, then exited on a short-term loss break.
    """
    observations = min(len(index_values), len(replay_dates))
    if observations < max(short_window, long_window):
        return {
            "version": "proxy_paper_trade_replay_v1",
            "policy": "prior_close_trailing_return_ticket_replay",
            "closed_trades": [],
            "open_trade": None,
            "closed_trade_count": 0,
            "open_trade_count": 0,
            "realized_return_pct": 0.0,
            "open_return_pct": 0.0,
            "total_return_pct": 0.0,
            "hit_rate": 0.0,
            "latest_trade_action": "WAIT_FOR_HISTORY",
            "latest_trade_reason": f"Need at least {max(short_window, long_window)} index marks for ticket replay.",
        }

    position: dict[str, Any] | None = None
    closed: list[dict[str, Any]] = []
    latest_action = "WAIT"
    latest_reason = "No open ticket and trailing returns do not clear the entry gate."
    closed_at_latest = False
    latest_short = 0.0
    latest_long = 0.0

    for idx in range(max(short_window, long_window) - 1, observations):
        short_ret = _window_return_pct(index_values, idx, short_window)
        long_ret = _window_return_pct(index_values, idx, long_window)
        if short_ret is None or long_ret is None:
            continue
        latest_short = short_ret
        latest_long = long_ret
        should_enter = short_ret >= 0.0 and long_ret >= 0.0
        should_exit = short_ret <= exit_return_pct or (short_ret < 0.0 and long_ret < 0.0)

        if position is not None and should_exit:
            entry_idx = int(position["entry_idx"])
            entry_value = index_values[entry_idx]
            exit_value = index_values[idx]
            trade_return = ((exit_value / entry_value) - 1.0) * 100.0 if entry_value else 0.0
            closed.append({
                "entry_date": replay_dates[entry_idx],
                "exit_date": replay_dates[idx],
                "entry_index": round(entry_value, 4),
                "exit_index": round(exit_value, 4),
                "return_pct": round(trade_return, 4),
                "holding_days": max(0, idx - entry_idx),
                "exit_reason": "short_return_break" if short_ret <= exit_return_pct else "negative_short_and_long_returns",
            })
            position = None
            closed_at_latest = idx == observations - 1
            if closed_at_latest:
                latest_action = "CLOSE_OR_SELL"
                latest_reason = "Latest close tripped the proxy-ticket exit rule."
            continue

        if position is None and should_enter:
            position = {
                "entry_idx": idx,
                "entry_date": replay_dates[idx],
                "entry_index": round(index_values[idx], 4),
                "entry_short_return_pct": round(short_ret, 4),
                "entry_long_return_pct": round(long_ret, 4),
            }
            if idx == observations - 1:
                latest_action = "OPEN_BUY"
                latest_reason = "Latest close cleared the proxy-ticket entry rule."

    open_trade = None
    open_return = 0.0
    if position is not None:
        entry_idx = int(position["entry_idx"])
        entry_value = index_values[entry_idx]
        mark_value = index_values[observations - 1]
        open_return = ((mark_value / entry_value) - 1.0) * 100.0 if entry_value else 0.0
        open_trade = {
            **{key: value for key, value in position.items() if key != "entry_idx"},
            "mark_date": replay_dates[observations - 1],
            "mark_index": round(mark_value, 4),
            "return_pct": round(open_return, 4),
            "holding_days": max(0, observations - 1 - entry_idx),
        }
        if latest_action != "OPEN_BUY":
            latest_action = "HOLD_OPEN"
            latest_reason = "Proxy-ticket is open and no exit rule is active."
    elif not closed_at_latest:
        latest_should_enter = latest_short >= 0.0 and latest_long >= 0.0
        latest_should_exit = latest_short <= exit_return_pct or (latest_short < 0.0 and latest_long < 0.0)
        if latest_should_enter:
            latest_action = "OPEN_BUY"
            latest_reason = "Latest close clears the proxy-ticket entry rule."
        elif latest_should_exit:
            latest_action = "CLOSE_OR_SELL"
            latest_reason = "Latest close is in sell/avoid mode; do not open a fresh ticket."

    realized_return = sum(_num(trade.get("return_pct")) for trade in closed)
    winners = sum(1 for trade in closed if _num(trade.get("return_pct")) > 0.0)
    hit_rate = winners / len(closed) * 100.0 if closed else 0.0
    return {
        "version": "proxy_paper_trade_replay_v1",
        "policy": "prior_close_trailing_return_ticket_replay",
        "entry_rule": f"{short_window}-mark return >= 0 and {long_window}-mark return >= 0",
        "exit_rule": f"{short_window}-mark return <= {exit_return_pct}% or both windows negative",
        "latest_short_return_pct": round(latest_short, 4),
        "latest_long_return_pct": round(latest_long, 4),
        "closed_trades": closed[-12:],
        "open_trade": open_trade,
        "closed_trade_count": len(closed),
        "open_trade_count": 1 if open_trade else 0,
        "realized_return_pct": round(realized_return, 4),
        "open_return_pct": round(open_return, 4),
        "total_return_pct": round(realized_return + open_return, 4),
        "hit_rate": round(hit_rate, 2),
        "latest_trade_action": latest_action,
        "latest_trade_reason": latest_reason,
    }


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


def _current_action(*, latest_signal: str, recommendation: str) -> tuple[str, str]:
    """Translate historical replay status plus latest mark into an operator action."""
    if latest_signal == "SELL" or recommendation == "SELL_OR_AVOID":
        return "SELL_OR_AVOID", "Do not open a fresh ticket; close local mock exposure if already open."
    if latest_signal == "BUY" and recommendation == "BUY_OR_HOLD":
        return "BUY_CANDIDATE", "Historical replay is promotable and recent marks confirm the direction."
    if latest_signal == "HOLD" and recommendation == "BUY_OR_HOLD":
        return "HOLD_EXISTING_ONLY", "Historical replay is promotable, but recent marks do not justify a fresh buy."
    return "MONITOR_ONLY", "Insufficient or mixed proxy evidence; keep this in watch mode."


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
    recent_index_marks = _recent_index_marks(index_values, replay_dates, daily_returns)
    paper_trade_replay = _paper_trade_replay(index_values, replay_dates)
    out_of_sample_replay = _out_of_sample_replay(index_values, replay_dates, daily_returns)
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
    current_action, current_action_reason = _current_action(
        latest_signal=latest_signal,
        recommendation=recommendation,
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
        "current_action": current_action,
        "current_action_reason": current_action_reason,
        "trailing_returns": trailing_returns,
        "recent_daily_returns_pct": [round(value * 100.0, 4) for value in daily_returns[-5:]],
        "recent_index_marks": recent_index_marks,
        "recent_entry_date": recent_index_marks[0]["date"] if recent_index_marks else "",
        "recent_exit_date": recent_index_marks[-1]["date"] if recent_index_marks else "",
        "paper_trade_replay": paper_trade_replay,
        "out_of_sample_replay": out_of_sample_replay,
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
