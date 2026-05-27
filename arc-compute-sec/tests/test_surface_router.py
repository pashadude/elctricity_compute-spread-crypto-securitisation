from agent import arb_identifier as ai
from agent import surface_router as sr


def _signal(direction, z=2.0):
    return ai.ArbSignal(
        signal_id="sig1", ts=0.0, region="X", S_t=0.0, z=z,
        direction=direction, conviction=abs(z), ttl_hours=24,
        electricity_per_mwh=100.0, compute_per_gpu_hr=1.5,
    )


def test_route_compute_expensive_skips_equity_and_crypto():
    sig = _signal(ai.DIRECTION_COMPUTE_EXPENSIVE)
    cands = sr.route(sig, polymarket_events=[])
    surfaces = {c.surface for c in cands}
    assert "ibkr" not in surfaces
    assert "crypto" not in surfaces


def test_route_elec_expensive_emits_equity_and_crypto():
    sig = _signal(ai.DIRECTION_ELEC_EXPENSIVE)
    cands = sr.route(sig, polymarket_events=[])
    surfaces = {c.surface for c in cands}
    assert "ibkr" in surfaces
    assert "crypto" in surfaces


def test_runtime_multi_surface_keeps_all_surfaces(monkeypatch):
    from agent import runtime

    sig = _signal(ai.DIRECTION_ELEC_EXPENSIVE, z=-2.0)
    monkeypatch.setattr(
        runtime,
        "_polymarket_events_for_signal",
        lambda signal, live_scan: [{
            "id": "energy",
            "slug": "wti",
            "title": "Will WTI > $90?",
            "yes_prices": [0.55, 0.50],
            "energy_template_id": "energy_oil_price",
            "premium": 0.05,
            "scorer_result": {"passes_gate": True, "premium": 0.05},
        }],
    )
    monkeypatch.setattr(
        runtime,
        "_kalshi_events_for_signal",
        lambda signal: [{
            "id": "KXOPENAI-26",
            "event_ticker": "KXOPENAI-26",
            "slug": "kxopenai-26",
            "title": "Will OpenAI release GPT-6 before 2027?",
            "yes_prices": [0.54, 0.5],
            "mutually_exclusive": True,
        }],
    )

    cands = runtime._candidates_for_signal(
        sig,
        live_scan=True,
        multi_surface=True,
        sizing_equity=1.0,
        sizing_crypto=1.0,
        sizing_polymarket=1.0,
        sizing_ibkr_prediction=1.0,
        sizing_kalshi=1.0,
    )
    surfaces = {c.surface for c in cands}
    assert {"polymarket", "ibkr", "crypto", "kalshi"} <= surfaces


def test_runtime_default_scan_remains_polymarket_only(monkeypatch):
    from agent import runtime

    sig = _signal(ai.DIRECTION_ELEC_EXPENSIVE, z=-2.0)
    monkeypatch.setattr(
        runtime,
        "_polymarket_events_for_signal",
        lambda signal, live_scan: [{
            "id": "energy",
            "slug": "wti",
            "yes_prices": [0.55, 0.50],
            "energy_template_id": "energy_oil_price",
            "scorer_result": {"passes_gate": True, "premium": 0.05},
        }],
    )

    cands = runtime._candidates_for_signal(
        sig,
        live_scan=True,
        multi_surface=False,
        sizing_equity=1.0,
        sizing_crypto=1.0,
        sizing_polymarket=1.0,
        sizing_ibkr_prediction=1.0,
        sizing_kalshi=1.0,
    )
    assert {c.surface for c in cands} == {"polymarket"}


def test_scan_once_defaults_to_spread_package(monkeypatch):
    from agent import runtime

    calls = {}

    def fake_run_once(args):
        calls["args"] = args
        return 0

    monkeypatch.setattr(runtime, "run_once", fake_run_once)

    assert runtime.scan_once(no_persist=True) == 0
    assert calls["args"].multi_surface is True
    assert calls["args"].sizing_crypto > 0
    assert calls["args"].sizing_equity > 0


def test_polymarket_uses_yes_prices_for_pnl():
    sig = _signal(ai.DIRECTION_ELEC_EXPENSIVE)
    events = [{
        "id": "ev1", "slug": "ev-one", "yes_prices": [0.4, 0.4, 0.23],
    }]
    cands = sr.route(sig, polymarket_events=events)
    pm = [c for c in cands if c.surface == "polymarket"]
    assert len(pm) == 1
    # sum-1 = 0.03
    assert round(pm[0].est_pnl_per_dollar, 4) == 0.03


def test_ibkr_prediction_market_is_direct_event_leg():
    sig = _signal(ai.DIRECTION_ELEC_EXPENSIVE)
    events = [{
        "id": "fx-ercot",
        "slug": "ercot-conservation-appeal",
        "title": "Will ERCOT issue a conservation appeal?",
        "description": "ForecastEx event contract available through IBKR ForecastTrader.",
        "yes_prices": [0.52, 0.51],
        "exchange": "FORECASTX",
        "sec_type": "OPT",
        "energy_template_id": "energy_electricity",
    }]
    cands = sr.route(sig, polymarket_events=[], ibkr_prediction_events=events)
    ibkr_pred = next(c for c in cands if c.surface == "ibkr_prediction")

    assert cands[0].surface == "ibkr_prediction"
    assert round(ibkr_pred.est_pnl_per_dollar, 4) == 0.03
    assert ibkr_pred.metadata["spread_leg"]["role"] == "direct_prediction_event"
    assert ibkr_pred.metadata["spread_leg"]["venue"] == "IBKR ForecastTrader"
    assert ibkr_pred.metadata["exchange"] == "FORECASTX"


def test_kalshi_market_is_direct_event_leg():
    sig = _signal(ai.DIRECTION_ELEC_EXPENSIVE)
    events = [{
        "id": "KXOPENAI-26",
        "event_ticker": "KXOPENAI-26",
        "slug": "kxopenai-26",
        "title": "Will OpenAI release GPT-6 before 2027?",
        "description": "Kalshi AI frontier model event.",
        "yes_prices": [0.54, 0.5],
        "mutually_exclusive": True,
        "category": "Science and Technology",
        "market_tickers": ["KXOPENAI-26"],
    }]
    cands = sr.route(sig, polymarket_events=[], ibkr_prediction_events=[], kalshi_events=events)
    kalshi = next(c for c in cands if c.surface == "kalshi")

    assert kalshi.instrument == "kalshi:KXOPENAI-26"
    assert round(kalshi.est_pnl_per_dollar, 4) == 0.04
    assert kalshi.metadata["spread_leg"]["role"] == "direct_prediction_event"
    assert kalshi.metadata["spread_leg"]["venue"] == "Kalshi"
    assert kalshi.metadata["category"] == "Science and Technology"
    assert kalshi.metadata["mutually_exclusive"] is True


def test_kalshi_skips_non_positive_overlay():
    sig = _signal(ai.DIRECTION_ELEC_EXPENSIVE)
    cands = sr.route(
        sig,
        polymarket_events=[],
        ibkr_prediction_events=[],
        kalshi_events=[{"id": "KXONE", "yes_prices": [0.42], "mutually_exclusive": True}],
    )

    assert not any(c.surface == "kalshi" for c in cands)


def test_kalshi_skips_non_exclusive_overlay():
    sig = _signal(ai.DIRECTION_ELEC_EXPENSIVE)
    cands = sr.route(
        sig,
        polymarket_events=[],
        ibkr_prediction_events=[],
        kalshi_events=[{
            "id": "KXAGICO-COMP",
            "yes_prices": [0.04, 0.08, 0.14, 0.23],
            "mutually_exclusive": False,
        }],
    )

    assert not any(c.surface == "kalshi" for c in cands)


def test_ibkr_stock_remains_proxy_leg():
    sig = _signal(ai.DIRECTION_ELEC_EXPENSIVE)
    cands = sr.route(sig, polymarket_events=[], ibkr_prediction_events=[])
    stock = next(c for c in cands if c.surface == "ibkr")

    assert stock.metadata["spread_leg"]["role"] == "liquid_equity_proxy"
    assert stock.metadata["spread_leg"]["directness"] == "proxy"


def test_polymarket_skips_event_without_prices():
    sig = _signal(ai.DIRECTION_ELEC_EXPENSIVE)
    cands = sr.route(sig, polymarket_events=[{"id": "missing", "yes_prices": []}])
    assert not any(c.surface == "polymarket" for c in cands)


def test_route_ranks_by_est_pnl_desc():
    sig = _signal(ai.DIRECTION_ELEC_EXPENSIVE)
    events = [{
        "id": "ev-big", "slug": "big", "yes_prices": [0.9, 0.4],  # +0.3
    }]
    cands = sr.route(sig, polymarket_events=events)
    # The top candidate should be the high-premium polymarket one.
    assert cands[0].est_pnl_per_dollar >= cands[-1].est_pnl_per_dollar
