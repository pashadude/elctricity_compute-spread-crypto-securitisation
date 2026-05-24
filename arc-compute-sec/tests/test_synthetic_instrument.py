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
        public_hedges=[{
            "surface": "public_market",
            "instrument": "NVDA",
            "leg_title": "NVIDIA",
            "leg_slug": "NVDA",
            "direct_pair_role": "AI compute-demand equity proxy",
            "label": "PRICED",
            "pricing_status": "priced_public_market",
            "last_price": 180.0,
            "currency": "USD",
        }],
    )

    assert proposal["proposal_type"] == "compute_receivable_hedge_note"
    assert proposal["asset_backed"] is False
    assert proposal["collateral_status"] == "not_asset_backed_v0"
    assert proposal["region_profile"]["short_name"] == "ERCOT power"
    assert "gas-fired" in proposal["region_profile"]["source_note"]
    assert proposal["outputs"]["direct_reference_legs"][0]["slug"] == "ai-data-center-moratorium-passed-before-2027"
    assert proposal["outputs"]["discovery_gaps"][0]["slug"] == "retxc-ec"
    assert proposal["outputs"]["discovery_gaps"][0]["status_label"] == "Needs live venue price"
    assert "Reconnect IBKR" in proposal["outputs"]["discovery_gaps"][0]["next_step"]
    assert proposal["outputs"]["proxy_reference_legs"][0]["slug"] == "BTC/USD"
    assert proposal["outputs"]["priced_hedge_basket"][0]["slug"] == "NVDA"
    construction = proposal["outputs"]["mock_hedge_construction"]
    assert construction["demo"] is True
    assert construction["receivable_usdc"] == 7500.0
    assert construction["hedge_notional_usdc"] == 2625.0
    assert construction["circle_testnet_usdc_request"] == 2770.0
    assert construction["direct_event_budget_usdc"] == 0.0
    assert construction["recommended_action"] == "BUY_CONTRACT"
    assert construction["weighted_legs"][0]["slug"] == "NVDA"
    assert construction["weighted_legs"][0]["side"] == "short"
    assert construction["weighted_legs"][0]["description"] == "GPU supply and AI accelerator capex proxy."
    assert construction["weighted_legs"][0]["source"] == "public_quote"
    assert construction["agent_tooling"][0]["name"] == "Quote scout"
    assert "test USDC" in construction["circle_request_note"]
    assert proposal["structure"]["schematic_steps"][0]["label"] == "1. Compute sale"
    assert proposal["outputs"]["build_instructions"][0]["title"] == "Attach compute sale"
    assert proposal["outputs"]["build_instructions"][2]["title"] == "Request Circle test USDC"
    assert proposal["outputs"]["agent_search_plan"][0]["surface"] == "opoint_nebius"
    assert "ERCOT" in proposal["outputs"]["agent_search_plan"][0]["query"]
    assert proposal["inputs"]["underlying_contract"]["type"] == "forward_compute_sale"
    assert "not legal ABS" in proposal["structure"]["securitization_style"]
    assert "FDR-style" in proposal["inputs"]["search_adjustment"]["rule"]
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
        public_hedges=[],
    )

    assert proposal["status"] == "RESEARCH"
    assert proposal["direction"] == "no_signal"
    assert proposal["outputs"]["direct_reference_legs"] == []
    assert "discover one energy leg" in proposal["thesis"]
