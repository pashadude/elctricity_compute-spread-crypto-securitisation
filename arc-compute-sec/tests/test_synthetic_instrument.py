from agent.synthetic_instrument import propose_synthetic_instrument


def test_proposal_is_synthetic_not_asset_backed_and_source_aware():
    proposal = propose_synthetic_instrument(
        spread={"latest": {"region": "ERCOT|us-east-1", "electricity_per_mwh": "95", "compute_per_gpu_hr": "1.5", "S_t": "1.46"}},
        signal={"latest": {"signal_id": "sig-1", "direction": "electricity_expensive", "region": "ERCOT|us-east-1", "z": "-2.2"}},
        direct_inventory=[
            {
                "surface": "ibkr_prediction",
                "leg_title": "Texas Commercial Electricity Generation Sales Revenue",
                "leg_slug": "retxc-ec",
                "direct_pair_role": "energy/grid-stress leg",
                "pricing_status": "unpriced_snapshot",
            },
            {
                "surface": "polymarket",
                "leg_title": "AI data center moratorium passed before 2027?",
                "leg_slug": "ai-data-center-moratorium-passed-before-2027",
                "direct_pair_role": "energy/grid-stress leg",
                "label": "WATCHLIST",
            },
        ],
        packages=[],
        verdicts=[{
            "surface": "crypto",
            "instrument": "BTC/USD",
            "leg_title": "BTC/USD miner-margin proxy",
            "leg_role": "miner_margin_proxy",
            "direction": "short",
            "label": "EXECUTE",
        }],
    )

    assert proposal["proposal_type"] == "synthetic_reference_instrument"
    assert proposal["asset_backed"] is False
    assert proposal["collateral_status"] == "not_asset_backed_v0"
    assert proposal["region_profile"]["short_name"] == "ERCOT power"
    assert "gas-fired" in proposal["region_profile"]["source_note"]
    assert proposal["outputs"]["direct_reference_legs"][0]["slug"] == "retxc-ec"
    assert proposal["outputs"]["proxy_reference_legs"][0]["slug"] == "BTC/USD"
    assert "not legal ABS" in proposal["structure"]["securitization_style"]
    assert any("real collateral" in action for action in proposal["outputs"]["agent_next_actions"])


def test_proposal_prefers_execute_package_legs_over_watchlist():
    proposal = propose_synthetic_instrument(
        spread={"latest": {"region": "PJM", "S_t": "1.7"}},
        signal={"latest": {"signal_id": "sig-2", "direction": "compute_expensive", "region": "PJM", "z": "2.1"}},
        direct_inventory=[{
            "surface": "polymarket",
            "leg_title": "Watchlist leg",
            "leg_slug": "watchlist-leg",
            "direct_pair_role": "energy/grid-stress leg",
        }],
        packages=[{
            "package_id": "pkg-1",
            "label": "EXECUTE",
            "direction": "compute_expensive",
            "direct_legs": [{
                "surface": "ibkr_prediction",
                "leg_title": "NVIDIA inference vs training revenue",
                "leg_slug": "itnvd-ec",
                "direct_pair_role": "AI compute-demand leg",
                "label": "EXECUTE",
            }],
            "proxy_legs": [],
        }],
        verdicts=[],
    )

    assert proposal["reference_package_id"] == "pkg-1"
    assert proposal["direction"] == "compute_expensive"
    assert proposal["outputs"]["direct_reference_legs"][0]["slug"] == "itnvd-ec"
    assert proposal["outputs"]["direct_reference_legs"][1]["slug"] == "watchlist-leg"
    assert proposal["region_profile"]["short_name"] == "PJM data-center power"
    assert any("real collateral" in action for action in proposal["outputs"]["agent_next_actions"])


def test_proposal_ignores_rejected_direct_package_legs():
    proposal = propose_synthetic_instrument(
        spread={"latest": {"region": "ERCOT", "S_t": "1.4"}},
        signal={"latest": {"signal_id": "sig-3", "direction": "electricity_expensive", "region": "ERCOT", "z": "-2.4"}},
        direct_inventory=[{
            "surface": "ibkr_prediction",
            "leg_title": "Texas Commercial Electricity Generation Sales Revenue",
            "leg_slug": "retxc-ec",
            "direct_pair_role": "energy/grid-stress leg",
            "label": "WATCHLIST",
        }],
        packages=[{
            "package_id": "pkg-2",
            "label": "EXECUTE",
            "direction": "electricity_expensive",
            "direct_legs": [{
                "surface": "polymarket",
                "leg_title": "Rejected unrelated AI hardware event",
                "leg_slug": "will-openai-launch-hardware",
                "leg_role": "direct_prediction_event",
                "label": "REJECT",
            }],
            "proxy_legs": [{
                "surface": "crypto",
                "instrument": "BTC/USD",
                "leg_title": "BTC/USD miner-margin proxy",
                "leg_role": "miner_margin_proxy",
                "label": "EXECUTE",
            }],
        }],
        verdicts=[],
    )

    slugs = [leg["slug"] for leg in proposal["outputs"]["direct_reference_legs"]]
    assert "retxc-ec" in slugs
    assert "will-openai-launch-hardware" not in slugs


def test_research_proposal_still_explains_missing_signal():
    proposal = propose_synthetic_instrument(
        spread={"latest": {}},
        signal={"latest": None},
        direct_inventory=[],
        packages=[],
        verdicts=[],
    )

    assert proposal["status"] == "RESEARCH"
    assert proposal["direction"] == "no_signal"
    assert proposal["outputs"]["direct_reference_legs"] == []
    assert "discover one energy leg" in proposal["thesis"]
