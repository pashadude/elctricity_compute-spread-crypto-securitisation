from datetime import datetime, timezone

import pytest

from agent import spread_proxy_history


def _point(date: str, close: float) -> dict:
    ts = int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp())
    return {"ts": ts, "close": close}


def _history(symbol: str, closes: list[tuple[str, float]]) -> dict:
    return {"symbol": symbol, "points": [_point(date, close) for date, close in closes]}


def test_proxy_index_rescales_latest_close_to_anchor():
    histories = {
        "NG=F": _history("NG=F", [("2026-05-26", 100), ("2026-05-27", 110), ("2026-05-28", 121)]),
        "NRG": _history("NRG", [("2026-05-26", 100), ("2026-05-27", 105), ("2026-05-28", 110)]),
    }

    index = spread_proxy_history.build_proxy_index(
        histories,
        weights={"NG=F": 0.5, "NRG": 0.5},
        anchor_value=62.6,
        label="electricity",
    )

    assert index.symbols_available == ["NG=F", "NRG"]
    assert index.values[-1] == pytest.approx(62.6)
    assert index.values[0] < index.values[-1]


def test_build_spread_rows_uses_anchored_electricity_and_compute_indexes():
    dates = ["2026-05-26", "2026-05-27", "2026-05-28"]
    histories = {
        "NG=F": _history("NG=F", list(zip(dates, [100, 105, 110]))),
        "NRG": _history("NRG", list(zip(dates, [100, 102, 104]))),
        "NVDA": _history("NVDA", list(zip(dates, [200, 210, 220]))),
        "VRT": _history("VRT", list(zip(dates, [100, 101, 103]))),
    }

    built = spread_proxy_history.build_spread_rows(
        histories,
        electricity_anchor_per_mwh=62.6,
        compute_anchor_per_gpu_hr=0.86635,
        electricity_weights={"NG=F": 0.5, "NRG": 0.5},
        compute_weights={"NVDA": 0.7, "VRT": 0.3},
    )

    assert built["status"] == "READY"
    assert len(built["rows"]) == 3
    latest = built["rows"][-1]
    assert latest["electricity_per_mwh"] == pytest.approx(62.6)
    assert latest["compute_per_gpu_hr"] == pytest.approx(0.86635)
    assert latest["S_t"] == pytest.approx(0.86635 - 0.5 * (62.6 / 1000.0) * 0.7)
    assert latest["mark_source"] == "public_proxy_history"


def test_build_spread_rows_requires_enough_symbols_per_index():
    histories = {
        "NG=F": _history("NG=F", [("2026-05-27", 100), ("2026-05-28", 101)]),
        "NVDA": _history("NVDA", [("2026-05-27", 200), ("2026-05-28", 201)]),
    }

    built = spread_proxy_history.build_spread_rows(
        histories,
        electricity_anchor_per_mwh=62.6,
        compute_anchor_per_gpu_hr=0.86635,
        min_symbols=2,
    )

    assert built["status"] == "INSUFFICIENT_HISTORY"
    assert built["rows"] == []
