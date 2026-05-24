import math
import pytest

from agent.pnl_probe import (
    polymarket_pnl_per_dollar,
    equity_pnl_per_dollar,
    crypto_pnl_per_dollar,
    estimate,
)


def test_polymarket_overpriced_event_positive():
    # sum=1.03 → +0.03
    assert math.isclose(polymarket_pnl_per_dollar([0.40, 0.40, 0.23]), 0.03, abs_tol=1e-9)


def test_polymarket_fair_event_zero():
    assert math.isclose(polymarket_pnl_per_dollar([0.5, 0.5]), 0.0, abs_tol=1e-9)


def test_polymarket_underpriced_event_negative():
    assert math.isclose(polymarket_pnl_per_dollar([0.3, 0.4, 0.28]), -0.02, abs_tol=1e-9)


def test_polymarket_extreme_overlay():
    # Degenerate 2-outcome where one resolves with near-certainty but sum is 1.5
    assert math.isclose(polymarket_pnl_per_dollar([1.5, 0.0]), 0.5, abs_tol=1e-9)


def test_polymarket_empty_raises():
    with pytest.raises(ValueError):
        polymarket_pnl_per_dollar([])


def test_equity_pnl_scales_with_z():
    a = equity_pnl_per_dollar(z=1.0, direction="short")
    b = equity_pnl_per_dollar(z=2.0, direction="short")
    assert b > a > 0
    assert math.isclose(b / a, 2.0, abs_tol=1e-9)


def test_equity_pnl_direction_validated():
    with pytest.raises(ValueError):
        equity_pnl_per_dollar(z=1.0, direction="upupup")


def test_crypto_pnl_higher_beta_than_equity():
    e = equity_pnl_per_dollar(z=1.0, direction="short")
    c = crypto_pnl_per_dollar(z=1.0, direction="short")
    assert c > e


def test_estimate_dispatch_polymarket():
    est = estimate(surface="polymarket", instrument="poly:x", direction="short",
                   yes_prices=[0.5, 0.55])
    assert math.isclose(est.est_pnl_per_dollar, 0.05, abs_tol=1e-9)


def test_estimate_dispatch_ibkr_prediction():
    est = estimate(surface="ibkr_prediction", instrument="IBKR-FX:ercot", direction="short",
                   yes_prices=[0.51, 0.52])
    assert math.isclose(est.est_pnl_per_dollar, 0.03, abs_tol=1e-9)


def test_estimate_dispatch_ibkr():
    est = estimate(surface="ibkr", instrument="GOOGL", direction="short", z=2.0)
    assert est.est_pnl_per_dollar > 0


def test_estimate_dispatch_crypto():
    est = estimate(surface="crypto", instrument="BTC/USD", direction="short", z=1.5)
    assert est.est_pnl_per_dollar > 0


def test_estimate_polymarket_requires_yes_prices():
    with pytest.raises(ValueError):
        estimate(surface="polymarket", instrument="x", direction="short")


def test_estimate_unknown_surface_raises():
    with pytest.raises(ValueError):
        estimate(surface="commodities", instrument="x", direction="short", z=1)
