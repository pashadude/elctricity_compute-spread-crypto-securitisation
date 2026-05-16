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

    cands = runtime._candidates_for_signal(
        sig,
        live_scan=True,
        multi_surface=True,
        sizing_equity=1.0,
        sizing_crypto=1.0,
        sizing_polymarket=1.0,
    )
    surfaces = {c.surface for c in cands}
    assert {"polymarket", "ibkr", "crypto"} <= surfaces


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
    )
    assert {c.surface for c in cands} == {"polymarket"}


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
