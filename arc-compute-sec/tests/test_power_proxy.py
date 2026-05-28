from feeds import power_proxy
import pytest


def test_power_proxy_adjusts_eia_anchor_with_weighted_public_returns():
    mark = power_proxy.mark_from_quotes(
        100.0,
        [
            power_proxy.PowerProxyQuote("NG=F", price=110.0, previous_close=100.0, return_pct=10.0, source="fixture"),
            power_proxy.PowerProxyQuote("NRG", price=95.0, previous_close=100.0, return_pct=-5.0, source="fixture"),
        ],
        weights={"NG=F": 0.5, "NRG": 0.5},
    )

    assert mark.source == "eia_plus_power_proxy"
    assert mark.status == "proxy_adjusted"
    assert mark.weighted_return_pct == 2.5
    assert mark.electricity_per_mwh == pytest.approx(102.5)
    assert mark.used_quotes == 2


def test_power_proxy_falls_back_when_quotes_are_insufficient():
    mark = power_proxy.mark_from_quotes(
        62.6,
        [power_proxy.PowerProxyQuote("NG=F", price=3.0, previous_close=2.9, return_pct=3.448, source="fixture")],
        weights={"NG=F": 0.7, "NRG": 0.3},
        min_quotes=2,
    )

    assert mark.source == "eia_retail_sales"
    assert mark.status == "insufficient_proxy_quotes"
    assert mark.electricity_per_mwh == 62.6


def test_power_proxy_clamps_daily_proxy_move():
    mark = power_proxy.mark_from_quotes(
        100.0,
        [
            power_proxy.PowerProxyQuote("NG=F", price=200.0, previous_close=100.0, return_pct=100.0, source="fixture"),
            power_proxy.PowerProxyQuote("NRG", price=200.0, previous_close=100.0, return_pct=100.0, source="fixture"),
        ],
        weights={"NG=F": 0.5, "NRG": 0.5},
        max_move_pct=0.10,
    )

    assert mark.weighted_return_pct == 100.0
    assert mark.electricity_per_mwh == pytest.approx(110.0)


def test_adjust_electricity_mark_uses_configured_fetcher(monkeypatch):
    monkeypatch.setenv("POWER_PROXY_SYMBOLS", "NG=F,NRG")
    monkeypatch.setenv("POWER_PROXY_WEIGHTS_JSON", '{"NG=F": 0.75, "NRG": 0.25}')

    def fetcher(symbol):
        prices = {"NG=F": (103.0, 100.0), "NRG": (98.0, 100.0)}
        price, previous = prices[symbol]
        return power_proxy.PowerProxyQuote(
            symbol=symbol,
            price=price,
            previous_close=previous,
            return_pct=((price / previous) - 1.0) * 100.0,
            source="fixture",
        )

    mark = power_proxy.adjust_electricity_mark(80.0, quote_fetcher=fetcher)

    assert mark.source == "eia_plus_power_proxy"
    assert round(mark.weighted_return_pct, 6) == 1.75
    assert round(mark.electricity_per_mwh, 6) == 81.4
    assert mark.symbols == ["NG=F", "NRG"]


def test_adjust_electricity_mark_can_be_disabled(monkeypatch):
    monkeypatch.setenv("POWER_PROXY_ENABLED", "0")

    mark = power_proxy.adjust_electricity_mark(80.0)

    assert mark.source == "eia_retail_sales"
    assert mark.status == "proxy_disabled"
    assert mark.electricity_per_mwh == 80.0
