from agent import synthetic_instrument
from agent.synthetic_instrument import propose_synthetic_instrument


def test_proposal_is_synthetic_not_asset_backed_and_source_aware():
    proposal = propose_synthetic_instrument(
        spread={"latest": {"region": "ERCOT|us-east-1", "electricity_per_mwh": "95", "compute_per_gpu_hr": "1.5", "S_t": "1.46", "kwh_per_gpu_hr": "1.2"}},
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
    assert construction["recommendation_label"] == "Open paper hedge"
    assert "not guaranteed profit" in construction["recommendation_reason"]
    assert 0 <= construction["entry_signal_score"] <= 100
    assert construction["entry_threshold_score"] == 70.0
    assert construction["score_scale"] == "0-100 entry score; buy threshold is 70 and raw z-score is not shown to users"
    assert len(construction["decision_basis_hash"]) == 16
    assert construction["decision_basis"]["signal"]["z"] == -2.2
    assert construction["decision_basis"]["spread"]["kWh_per_gpu_hr"] == 1.2
    assert construction["modeled_power_cost_share_pct"] > 2.5
    profiles = proposal["outputs"]["collateral_profile_candidates"]
    current_profile = next(row for row in profiles if row["profile_id"] == "cloud_gpu_receivable")
    assert profiles[0]["profile_id"] != "cloud_gpu_receivable"
    assert profiles[0]["materiality_gate"] == "PASS"
    assert current_profile["status"] == "THIN_ENERGY_LINK"
    assert current_profile["materiality_gate"] == "MONITOR"
    assert construction["judge_verdict"]["label"] == "EXECUTE"
    assert construction["judge_verdict"]["reason_code"] == "all_gates_passed"
    assert len(construction["judge_candidate_hash"]) == 16
    assert "Non-logging spread-decision judge pass" in construction["judge_scope"]
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
    sheet = proposal["outputs"]["operator_signal_sheet"]
    assert sheet["version"] == "operator_signal_sheet_v1"
    assert sheet["overall_action"] in {"PAPER_BUY_CANDIDATE", "MONITOR", "STRUCTURE_THEN_JUDGE", "AVOID_OR_CLOSE"}
    assert any(row["key"] == "active_proxy_basket" for row in sheet["rows"])
    assert "judge.classify()" in sheet["guardrail"]
    trade_map = proposal["outputs"]["spread_archetype_trade_map"]
    assert len(trade_map) >= 5
    assert {row["archetype_id"] for row in trade_map} >= {"compute_spark_spread", "power_cost_share", "fuel_stack_compute_spread"}
    assert all(row["arc_gate"] == "LOCKED_UNTIL_JUDGE_EXECUTE" for row in trade_map)
    ledger = proposal["outputs"]["spread_profitability_ledger"]
    assert ledger["version"] == "spread_profitability_ledger_v1"
    assert ledger["realized"] is False
    assert "not reconciled fills" in ledger["realized_note"]
    assert len(ledger["rows"]) == len(trade_map)
    assert proposal["inputs"]["underlying_contract"]["type"] == "forward_compute_sale"
    assert "not legal ABS" in proposal["structure"]["securitization_style"]
    assert "FDR-style" in proposal["inputs"]["search_adjustment"]["rule"]
    assert any("real collateral" in action for action in proposal["outputs"]["agent_next_actions"])


def test_mock_recommendation_refresh_key_changes_with_spread_state():
    base_kwargs = {
        "signal": {"latest": {"signal_id": "sig-1", "direction": "compute_expensive", "region": "PJM", "z": "2.4"}},
        "direct_inventory": [],
        "packages": [],
        "verdicts": [],
        "public_hedges": [{
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
    }
    first = propose_synthetic_instrument(
        spread={"latest": {"region": "PJM", "electricity_per_mwh": "62.6", "compute_per_gpu_hr": "0.84", "S_t": "0.82"}},
        **base_kwargs,
    )
    second = propose_synthetic_instrument(
        spread={"latest": {"region": "PJM", "electricity_per_mwh": "88.0", "compute_per_gpu_hr": "0.84", "S_t": "0.78"}},
        **base_kwargs,
    )

    first_decision = first["outputs"]["mock_hedge_construction"]
    second_decision = second["outputs"]["mock_hedge_construction"]

    assert first_decision["decision_basis_hash"] != second_decision["decision_basis_hash"]
    assert first_decision["judge_candidate_hash"] != second_decision["judge_candidate_hash"]
    assert first_decision["recommended_action"] == "BUY_CONTRACT"
    assert first_decision["profitability_score"] == first_decision["entry_signal_score"]


def test_mock_recommendation_blocks_buy_when_energy_materiality_is_too_weak(monkeypatch):
    def fake_classify(candidate, state, scorer_result=None):
        return synthetic_instrument.judge.Verdict(synthetic_instrument.judge.LABEL_EXECUTE, "all_gates_passed", 0.95)

    monkeypatch.setattr(synthetic_instrument.judge, "classify", fake_classify)
    proposal = propose_synthetic_instrument(
        spread={"latest": {"region": "PJM", "electricity_per_mwh": "60.0", "compute_per_gpu_hr": "3.0", "S_t": "2.98", "k": "0.5", "kwh_per_gpu_hr": "0.7"}},
        signal={"latest": {"signal_id": "sig-weak-energy", "direction": "compute_expensive", "region": "PJM", "z": "4.0"}},
        direct_inventory=[],
        packages=[],
        verdicts=[],
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
        spread_family_validation={
            "entry_gate_pass": True,
            "primary_family": {
                "family_id": "compute_net_power_margin",
                "status": "PROMOTABLE",
                "tested_trades": 12,
                "win_rate": 60.0,
                "total_pnl_per_unit": 0.5,
            },
        },
        proxy_basket_validation={
            "entry_gate_pass": True,
            "primary_basket": {
                "basket_id": "compute_scarcity_ai_infra",
                "direction": "compute_expensive",
                "status": "PROMOTABLE",
                "recommendation": "BUY_OR_HOLD",
                "latest_signal": "BUY",
                "signal_reason": "Promotable replay and recent proxy PnL is non-negative.",
                "is_promotable": True,
            },
            "baskets": [{
                "basket_id": "compute_scarcity_ai_infra",
                "direction": "compute_expensive",
                "status": "PROMOTABLE",
                "recommendation": "BUY_OR_HOLD",
                "latest_signal": "BUY",
                "signal_reason": "Promotable replay and recent proxy PnL is non-negative.",
                "is_promotable": True,
            }],
        },
    )

    construction = proposal["outputs"]["mock_hedge_construction"]

    assert construction["recommended_action"] == "MONITOR_ONLY"
    assert construction["recommendation_label"] == "Monitor: weak energy link"
    assert construction["modeled_power_cost_share_pct"] < 2.5
    assert "mostly a compute-price signal" in construction["recommendation_reason"]
    profiles = proposal["outputs"]["collateral_profile_candidates"]
    current = next(row for row in profiles if row["profile_id"] == "cloud_gpu_receivable")
    miner = next(row for row in profiles if row["profile_id"] == "miner_margin_energy_package")
    assert current["status"] == "WEAK_ENERGY_LINK"
    assert current["materiality_gate"] == "MONITOR"
    assert miner["modeled_power_cost_share_pct"] > 10.0
    assert miner["materiality_gate"] == "PASS"


def test_mock_recommendation_calls_judge_on_decision_basis(monkeypatch):
    calls = []

    def fake_classify(candidate, state, scorer_result=None):
        calls.append((candidate, state, scorer_result))
        return synthetic_instrument.judge.Verdict(synthetic_instrument.judge.LABEL_EXECUTE, "all_gates_passed", 0.95)

    monkeypatch.setattr(synthetic_instrument.judge, "classify", fake_classify)
    proposal = propose_synthetic_instrument(
        spread={"latest": {"region": "PJM", "electricity_per_mwh": "62.6", "compute_per_gpu_hr": "0.84", "S_t": "0.82"}},
        signal={"latest": {"signal_id": "sig-judge", "direction": "compute_expensive", "region": "PJM", "z": "2.4"}},
        direct_inventory=[],
        packages=[],
        verdicts=[],
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

    construction = proposal["outputs"]["mock_hedge_construction"]

    assert calls
    candidate, state, scorer_result = calls[0]
    assert scorer_result is None
    assert candidate["metadata"]["decision_basis_hash"] == construction["decision_basis_hash"]
    assert candidate["surface"] == "mock_contract"
    assert candidate["sizing_usdc"] <= state["max_position_usdc"]
    assert construction["judge_verdict"]["label"] == "EXECUTE"


def test_mock_recommendation_blocks_buy_when_judge_defers(monkeypatch):
    def fake_classify(candidate, state, scorer_result=None):
        return synthetic_instrument.judge.Verdict(synthetic_instrument.judge.LABEL_DEFER, "stale_data", 0.9)

    monkeypatch.setattr(synthetic_instrument.judge, "classify", fake_classify)
    proposal = propose_synthetic_instrument(
        spread={"latest": {"region": "PJM", "electricity_per_mwh": "62.6", "compute_per_gpu_hr": "0.84", "S_t": "0.82"}},
        signal={"latest": {"signal_id": "sig-defer", "direction": "compute_expensive", "region": "PJM", "z": "4.0"}},
        direct_inventory=[],
        packages=[],
        verdicts=[],
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

    construction = proposal["outputs"]["mock_hedge_construction"]

    assert construction["recommended_action"] == "MONITOR_ONLY"
    assert construction["recommendation_label"] == "Monitor: judge defer"
    assert construction["judge_verdict"] == {"label": "DEFER", "reason_code": "stale_data", "confidence": 0.9}


def test_mock_recommendation_blocks_fresh_buy_when_proxy_signal_sells(monkeypatch):
    def fake_classify(candidate, state, scorer_result=None):
        return synthetic_instrument.judge.Verdict(synthetic_instrument.judge.LABEL_EXECUTE, "all_gates_passed", 0.95)

    monkeypatch.setattr(synthetic_instrument.judge, "classify", fake_classify)
    proposal = propose_synthetic_instrument(
        spread={"latest": {"region": "PJM", "electricity_per_mwh": "62.6", "compute_per_gpu_hr": "1.5", "S_t": "1.47"}},
        signal={"latest": {"signal_id": "sig-sell-proxy", "direction": "compute_expensive", "region": "PJM", "z": "4.0"}},
        direct_inventory=[],
        packages=[],
        verdicts=[],
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
        spread_family_validation={
            "entry_gate_pass": True,
            "primary_family": {
                "family_id": "compute_net_power_margin",
                "status": "PROMOTABLE",
                "tested_trades": 12,
                "win_rate": 60.0,
                "total_pnl_per_unit": 0.5,
            },
        },
        proxy_basket_validation={
            "entry_gate_pass": True,
            "primary_basket": {
                "basket_id": "compute_scarcity_ai_infra",
                "status": "PROMOTABLE",
                "recommendation": "BUY_OR_HOLD",
                "latest_signal": "SELL",
                "signal_reason": "Recent 5d proxy PnL is below the sell threshold.",
                "trailing_returns": {"5d": {"return_pct": -3.1, "observations": 5}},
                "total_return_pct": 12.0,
                "win_rate": 55.0,
                "max_drawdown_pct": -8.0,
            },
        },
    )

    construction = proposal["outputs"]["mock_hedge_construction"]

    assert construction["recommended_action"] == "MONITOR_ONLY"
    assert construction["recommendation_label"] == "Sell/avoid: proxy PnL"
    assert "5d proxy PnL" in construction["recommendation_reason"]
    assert construction["decision_basis"]["proxy_basket_validation"]["primary_latest_signal"] == "SELL"


def test_mock_recommendation_uses_proxy_basket_matching_signal_direction(monkeypatch):
    def fake_classify(candidate, state, scorer_result=None):
        return synthetic_instrument.judge.Verdict(synthetic_instrument.judge.LABEL_EXECUTE, "all_gates_passed", 0.95)

    monkeypatch.setattr(synthetic_instrument.judge, "classify", fake_classify)
    proposal = propose_synthetic_instrument(
        spread={"latest": {"region": "PJM", "electricity_per_mwh": "62.6", "compute_per_gpu_hr": "1.5", "S_t": "1.47"}},
        signal={"latest": {"signal_id": "sig-direction-proxy", "direction": "compute_expensive", "region": "PJM", "z": "4.0"}},
        direct_inventory=[],
        packages=[],
        verdicts=[],
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
        spread_family_validation={
            "entry_gate_pass": True,
            "primary_family": {
                "family_id": "compute_net_power_margin",
                "status": "PROMOTABLE",
                "tested_trades": 12,
                "win_rate": 60.0,
                "total_pnl_per_unit": 0.5,
            },
        },
        proxy_basket_validation={
            "entry_gate_pass": True,
            "primary_basket": {
                "basket_id": "miner_margin_power_pair",
                "direction": "electricity_expensive",
                "status": "PROMOTABLE",
                "recommendation": "BUY_OR_HOLD",
                "latest_signal": "BUY",
                "signal_reason": "Electricity basket is green, but it is not the active signal.",
                "is_promotable": True,
            },
            "baskets": [
                {
                    "basket_id": "miner_margin_power_pair",
                    "direction": "electricity_expensive",
                    "status": "PROMOTABLE",
                    "recommendation": "BUY_OR_HOLD",
                    "latest_signal": "BUY",
                    "signal_reason": "Electricity basket is green, but it is not the active signal.",
                    "is_promotable": True,
                },
                {
                    "basket_id": "compute_scarcity_ai_infra",
                    "direction": "compute_expensive",
                    "status": "PROMOTABLE",
                    "recommendation": "BUY_OR_HOLD",
                    "latest_signal": "SELL",
                    "signal_reason": "Both 5d and 1m proxy PnL are negative.",
                    "trailing_returns": {"5d": {"return_pct": -0.4}, "1m": {"return_pct": -1.4}},
                    "total_return_pct": 2.2,
                    "win_rate": 43.0,
                    "max_drawdown_pct": -8.0,
                    "is_promotable": True,
                },
            ],
        },
    )

    construction = proposal["outputs"]["mock_hedge_construction"]

    assert construction["recommended_action"] == "MONITOR_ONLY"
    assert construction["recommendation_label"] == "Sell/avoid: proxy PnL"
    assert construction["decision_basis"]["proxy_basket_validation"]["primary_basket"] == "compute_scarcity_ai_infra"
    assert construction["decision_basis"]["proxy_basket_validation"]["primary_latest_signal"] == "SELL"
    sheet = proposal["outputs"]["operator_signal_sheet"]
    assert sheet["overall_action"] == "AVOID_OR_CLOSE"
    assert sheet["active_proxy_basket_id"] == "compute_scarcity_ai_infra"
    assert next(row for row in sheet["rows"] if row["key"] == "active_proxy_basket")["action"] == "AVOID_OR_CLOSE"
    menu = proposal["outputs"]["syndicated_instrument_menu"]
    assert menu[0]["instrument_type"] == "compute_receivable_hedge_note"
    assert menu[0]["basket_direction"] == "compute_expensive"
    assert menu[0]["direction_aligned"] is True
    assert menu[0]["latest_signal"] == "SELL"
    assert menu[1]["direction_aligned"] is False
    trade_map = proposal["outputs"]["spread_archetype_trade_map"]
    active_spread = next(row for row in trade_map if row["archetype_id"] == "compute_spark_spread")
    assert active_spread["selected_expression"]["basket_id"] == "compute_scarcity_ai_infra"
    assert active_spread["selected_expression"]["direction_aligned"] is True
    assert active_spread["tradability_action"] == "AVOID_OR_SELL"
    assert "sell" in active_spread["tradability_reason"].lower()
    ledger = proposal["outputs"]["spread_profitability_ledger"]
    avoid_row = next(row for row in ledger["rows"] if row["archetype_id"] == "compute_spark_spread")
    assert avoid_row["profitability_status"] == "SELL_OR_AVOID"
    assert avoid_row["requires_close_or_avoid"] is True
    assert ledger["first_avoid_candidate"]["archetype_id"] == "compute_spark_spread"


def test_proposal_exposes_multiple_syndicated_instrument_types(monkeypatch):
    def fake_classify(candidate, state, scorer_result=None):
        return synthetic_instrument.judge.Verdict(synthetic_instrument.judge.LABEL_EXECUTE, "all_gates_passed", 0.95)

    monkeypatch.setattr(synthetic_instrument.judge, "classify", fake_classify)
    proposal = propose_synthetic_instrument(
        spread={"latest": {"region": "ERCOT", "electricity_per_mwh": "62.6", "compute_per_gpu_hr": "1.5", "S_t": "1.47"}},
        signal={"latest": {"signal_id": "sig-menu", "direction": "electricity_expensive", "region": "ERCOT", "z": "-3.2"}},
        direct_inventory=[{
            "surface": "polymarket",
            "leg_title": "AI data center moratorium passed before 2027?",
            "leg_slug": "ai-data-center-moratorium-passed-before-2027",
            "direct_pair_role": "energy/grid-stress leg",
            "pricing_status": "priced_watchlist",
            "label": "WATCHLIST",
        }],
        packages=[],
        verdicts=[],
        public_hedges=[
            {"surface": "public_market", "instrument": "NRG", "leg_slug": "NRG", "last_price": 80, "pricing_status": "priced_public_market", "label": "PRICED"},
            {"surface": "public_market", "instrument": "CEG", "leg_slug": "CEG", "last_price": 250, "pricing_status": "priced_public_market", "label": "PRICED"},
            {"surface": "public_market", "instrument": "BTC-USD", "leg_slug": "BTC-USD", "last_price": 100000, "pricing_status": "priced_public_market", "label": "PRICED"},
            {"surface": "public_market", "instrument": "ETH-USD", "leg_slug": "ETH-USD", "last_price": 4000, "pricing_status": "priced_public_market", "label": "PRICED"},
        ],
        proxy_basket_validation={
            "entry_gate_pass": True,
            "primary_basket": {
                "basket_id": "miner_margin_power_pair",
                "status": "PROMOTABLE",
                "recommendation": "BUY_OR_HOLD",
                "latest_signal": "BUY",
                "signal_reason": "Promotable replay and recent proxy PnL is non-negative.",
                "weights": {"BTC-USD": -0.45, "ETH-USD": -0.25, "NRG": 0.18, "CEG": 0.12},
                "trailing_returns": {"5d": {"return_pct": 2.2}, "1m": {"return_pct": 6.1}},
                "total_return_pct": 1.5,
                "win_rate": 46.67,
                "max_drawdown_pct": -6.88,
            },
            "baskets": [{
                "basket_id": "miner_margin_power_pair",
                "status": "PROMOTABLE",
                "recommendation": "BUY_OR_HOLD",
                "latest_signal": "BUY",
                "signal_reason": "Promotable replay and recent proxy PnL is non-negative.",
                "weights": {"BTC-USD": -0.45, "ETH-USD": -0.25, "NRG": 0.18, "CEG": 0.12},
                "trailing_returns": {"5d": {"return_pct": 2.2}, "1m": {"return_pct": 6.1}},
                "total_return_pct": 1.5,
                "win_rate": 46.67,
                "max_drawdown_pct": -6.88,
            }],
        },
        oracle_evidence={
            "status": "EVIDENCE_LOGGED",
            "role": "news-grounded evidence only",
            "row_count": 2,
            "latest_title": "AI data center moratorium passed before 2027?",
            "latest_slug": "ai-data-center-moratorium-passed-before-2027",
            "latest_pricing_status": "DEFER",
            "latest_model": "deepseek-ai/DeepSeek-V3.2",
            "latest_reason_code": "insufficient_evidence",
            "verdict_counts": {"DEFER": 2},
            "reason_counts": {"insufficient_evidence": 2},
            "raw_articles": 40,
            "filtered_articles": 8,
        },
    )

    menu = proposal["outputs"]["syndicated_instrument_menu"]

    assert len(menu) >= 5
    assert menu[0]["instrument_type"] == "miner_margin_power_pair"
    assert menu[0]["latest_signal"] == "BUY"
    assert menu[0]["status"] == "PAPER_BUY_ONLY"
    assert menu[0]["spread_archetype"] == "fuel_stack_compute_spread"
    assert menu[0]["priced_symbols"] == ["BTC-USD", "ETH-USD", "NRG", "CEG"]
    assert menu[0]["arc_gate"] == "LOCKED_UNTIL_JUDGE_EXECUTE"
    assert "priced public basket" in menu[0]["copying_spread"]
    trade_map = proposal["outputs"]["spread_archetype_trade_map"]
    fuel_stack = next(row for row in trade_map if row["archetype_id"] == "fuel_stack_compute_spread")
    assert fuel_stack["tradability_action"] == "PAPER_BUY_ONLY"
    assert fuel_stack["selected_expression"]["basket_id"] == "miner_margin_power_pair"
    assert fuel_stack["selected_expression"]["latest_signal"] == "BUY"
    assert "BTC-USD" in fuel_stack["selected_expression"]["priced_symbols"]
    ledger = proposal["outputs"]["spread_profitability_ledger"]
    assert ledger["best_buy_candidate"]["archetype_id"] == "fuel_stack_compute_spread"
    assert ledger["best_buy_candidate"]["profitability_status"] == "PAPER_BUY"
    assert ledger["best_buy_candidate"]["supports_fresh_buy"] is True
    assert ledger["counts"]["paper_buy"] >= 1
    oracle = proposal["outputs"]["oracle_judge_evidence"]
    assert oracle["status"] == "EVIDENCE_LOGGED"
    assert oracle["latest_verdict"] == "DEFER"
    assert oracle["verdict_counts"] == {"DEFER": 2}
    assert oracle["can_drive_arc"] is False
    assert oracle["oracle_evidence_hash"]
    assert proposal["inputs"]["oracle_evidence_hash"] == oracle["oracle_evidence_hash"]


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
