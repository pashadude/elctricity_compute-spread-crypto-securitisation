from agent import arb_identifier as ai
from agent import spread_package
from agent import surface_router as sr


def _signal(direction=ai.DIRECTION_ELEC_EXPENSIVE, z=-2.0):
    return ai.ArbSignal(
        signal_id="sig-package",
        ts=0.0,
        region="ERCOT|us-east-1",
        S_t=1.0,
        z=z,
        direction=direction,
        conviction=abs(z),
        ttl_hours=24,
        electricity_per_mwh=100.0,
        compute_per_gpu_hr=1.5,
    )


def test_spread_package_labels_crypto_as_proxy_not_claim():
    sig = _signal()
    cands = sr.route(sig, polymarket_events=[])
    crypto = next(c for c in cands if c.surface == "crypto")
    leg = crypto.metadata["spread_leg"]
    package = crypto.metadata["spread_package"]

    assert leg["role"] == "miner_margin_proxy"
    assert leg["directness"] == "proxy"
    assert "not the securitized claim" in leg["economic_link"]
    assert "Proxy legs" in package["risk_note"]
    assert package["package_hash"]


def test_spread_package_includes_direct_polymarket_pair_map():
    sig = _signal()
    cands = sr.route(sig, polymarket_events=[{
        "id": "energy",
        "slug": "ercot-power-stress",
        "title": "Will ERCOT power prices spike?",
        "yes_prices": [0.55, 0.50],
        "energy_template_id": "energy_power_price",
    }])
    package = cands[0].metadata["spread_package"]
    roles = {leg["role"] for leg in package["intended_direct_pair"]}

    assert roles == {"direct_energy_leg", "direct_compute_demand_leg"}
    assert package["intended_direct_pair"][0]["surface"] == "polymarket"
    assert len(package["flow"]) == 4


def test_compute_expensive_does_not_auto_route_crypto_proxy():
    sig = _signal(ai.DIRECTION_COMPUTE_EXPENSIVE, z=2.0)
    cands = sr.route(sig, polymarket_events=[])

    assert not any(c.surface == "crypto" for c in cands)


def test_package_summary_for_candidate_is_deliverable_safe():
    sig = _signal()
    cands = sr.route(sig, polymarket_events=[])
    candidate_dict = {
        "metadata": cands[0].metadata,
    }
    summary = spread_package.package_summary_for_candidate(candidate_dict)

    assert summary["version"] == spread_package.PACKAGE_VERSION
    assert summary["selected_leg"]["role"] in {"miner_margin_proxy", "liquid_equity_proxy"}
    assert summary["package_hash"]
