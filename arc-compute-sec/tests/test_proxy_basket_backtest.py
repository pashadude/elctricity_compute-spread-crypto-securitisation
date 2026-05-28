from agent import proxy_basket_backtest as pbb


def _history_on_dates(symbol: str, closes: list[tuple[int, float]]):
    return {
        "symbol": symbol,
        "points": [
            {"ts": 1_700_000_000 + day * 86_400, "close": close}
            for day, close in closes
        ],
    }


def _history(symbol: str, start: float, step: float, days: int = 30):
    return {
        "symbol": symbol,
        "points": [
            {"ts": 1_700_000_000 + idx * 86_400, "close": start + idx * step}
            for idx in range(days)
        ],
    }


def test_proxy_basket_replay_promotes_profitable_template():
    histories = {
        "NVDA": _history("NVDA", 100, 2.0),
        "VRT": _history("VRT", 50, 1.0),
        "ETN": _history("ETN", 80, 1.2),
        "CEG": _history("CEG", 120, -0.8),
        "NRG": _history("NRG", 90, -0.6),
        "BTC-USD": _history("BTC-USD", 60_000, 100),
        "ETH-USD": _history("ETH-USD", 3_000, 5),
    }
    basket = next(item for item in pbb.PROXY_BASKETS if item.basket_id == "compute_scarcity_ai_infra")

    replay = pbb.replay_basket(histories, basket, min_days=20, min_symbols=3)

    assert replay["status"] == "PROMOTABLE"
    assert replay["recommendation"] == "BUY_OR_HOLD"
    assert replay["latest_signal"] == "BUY"
    assert replay["total_return_pct"] > 0
    assert replay["win_rate"] >= 45
    assert replay["trailing_returns"]["5d"]["return_pct"] > 0
    assert len(replay["recent_index_marks"]) == 7
    assert replay["recent_index_marks"][0]["paper_return_since_entry_pct"] == 0.0
    assert replay["recent_index_marks"][-1]["paper_return_since_entry_pct"] > 0
    assert replay["recent_entry_date"] == replay["recent_index_marks"][0]["date"]
    assert replay["recent_exit_date"] == replay["recent_index_marks"][-1]["date"]
    assert replay["paper_trade_replay"]["version"] == "proxy_paper_trade_replay_v1"
    assert replay["paper_trade_replay"]["latest_trade_action"] == "HOLD_OPEN"
    assert replay["paper_trade_replay"]["open_trade"]["return_pct"] > 0
    assert replay["paper_trade_replay"]["total_return_pct"] > 0


def test_proxy_basket_replay_fails_loss_making_template():
    histories = {
        "NVDA": _history("NVDA", 100, -1.5),
        "VRT": _history("VRT", 50, -0.7),
        "ETN": _history("ETN", 80, -0.9),
        "CEG": _history("CEG", 120, 0.8),
        "NRG": _history("NRG", 90, 0.6),
        "BTC-USD": _history("BTC-USD", 60_000, -100),
        "ETH-USD": _history("ETH-USD", 3_000, -5),
    }
    basket = next(item for item in pbb.PROXY_BASKETS if item.basket_id == "compute_scarcity_ai_infra")

    replay = pbb.replay_basket(histories, basket, min_days=20, min_symbols=3)

    assert replay["status"] == "FAILED_REPLAY"
    assert replay["recommendation"] == "SELL_OR_AVOID"
    assert replay["latest_signal"] == "SELL"
    assert replay["total_return_pct"] < 0
    assert replay["paper_trade_replay"]["latest_trade_action"] in {"CLOSE_OR_SELL", "WAIT"}
    assert replay["paper_trade_replay"]["open_trade_count"] == 0


def test_proxy_basket_summary_keeps_missing_data_as_monitor_only():
    summary = pbb.summarize({"NVDA": _history("NVDA", 100, 1)}, min_days=20, min_symbols=3)

    assert summary["entry_gate_pass"] is False
    assert summary["primary_basket"]["status"] == "INSUFFICIENT_DATA"
    assert summary["primary_basket"]["recommendation"] == "MONITOR_ONLY"
    assert summary["primary_basket"]["latest_signal"] == "MONITOR"


def test_proxy_basket_replay_carries_non_trading_calendar_marks():
    # Equities can skip sessions while crypto has daily marks. The replay should
    # use the union calendar and carry the last close, not collapse to the strict
    # intersection of every symbol's timestamp set.
    histories = {
        "NVDA": _history_on_dates("NVDA", [(0, 100), (1, 102), (4, 108)]),
        "VRT": _history_on_dates("VRT", [(0, 50), (1, 51), (4, 55)]),
        "ETN": _history_on_dates("ETN", [(0, 80), (1, 82), (4, 86)]),
        "CEG": _history_on_dates("CEG", [(0, 120), (1, 119), (4, 118)]),
        "NRG": _history_on_dates("NRG", [(0, 90), (1, 89), (4, 88)]),
        "BTC-USD": _history_on_dates("BTC-USD", [(0, 60_000), (1, 61_000), (2, 61_500), (3, 62_000), (4, 62_500)]),
        "ETH-USD": _history_on_dates("ETH-USD", [(0, 3_000), (1, 3_030), (2, 3_040), (3, 3_050), (4, 3_060)]),
    }
    basket = next(item for item in pbb.PROXY_BASKETS if item.basket_id == "compute_scarcity_ai_infra")

    replay = pbb.replay_basket(histories, basket, min_days=5, min_symbols=3)

    assert replay["observations"] == 5
    assert replay["total_return_pct"] > 0
    assert replay["trailing_returns"]["5d"]["observations"] == 5


def test_proxy_basket_signal_can_sell_on_recent_negative_pnl_even_if_longer_replay_promotes():
    histories = {}
    for symbol, start in {
        "NVDA": 100,
        "VRT": 50,
        "ETN": 80,
        "CEG": 120,
        "NRG": 90,
        "BTC-USD": 60_000,
        "ETH-USD": 3_000,
    }.items():
        points = []
        for idx in range(30):
            if symbol in {"CEG", "NRG"}:
                close = start - idx * 0.2
            else:
                close = start + idx * 1.2
            if idx >= 26:
                close *= 0.85
            points.append((idx, close))
        histories[symbol] = _history_on_dates(symbol, points)
    basket = next(item for item in pbb.PROXY_BASKETS if item.basket_id == "compute_scarcity_ai_infra")

    replay = pbb.replay_basket(histories, basket, min_days=20, min_symbols=3)

    assert replay["status"] == "PROMOTABLE"
    assert replay["recommendation"] == "BUY_OR_HOLD"
    assert replay["latest_signal"] == "SELL"
    assert replay["trailing_returns"]["5d"]["return_pct"] < -2
