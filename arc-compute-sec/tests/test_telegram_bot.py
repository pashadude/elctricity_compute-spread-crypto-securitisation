import json

from integrations import telegram_bot
from services import scan_requests


def test_telegram_http_error_redacts_bot_token(monkeypatch):
    class Resp:
        status_code = 429
        text = '{"ok":false,"description":"Too Many Requests"}'

        def raise_for_status(self):
            err = telegram_bot.requests.HTTPError(
                "429 Client Error: Too Many Requests for url: https://api.telegram.org/botSECRET/sendMessage"
            )
            err.response = self
            raise err

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "SECRET")
    monkeypatch.setattr(telegram_bot.requests, "post", lambda *args, **kwargs: Resp())

    try:
        telegram_bot.telegram_call("sendMessage", {})
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected RuntimeError")

    assert "SECRET" not in message
    assert "Too Many Requests" in message


def test_configure_bot_profile_sets_description_commands_and_menu(monkeypatch):
    calls = []
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://power.example.com/")
    monkeypatch.setattr(
        telegram_bot,
        "telegram_call",
        lambda method, payload: calls.append((method, payload)) or {"ok": True},
    )

    assert telegram_bot.configure_bot_profile() == {
        "setMyShortDescription": True,
        "setMyDescription": True,
        "setMyCommands": True,
        "setChatMenuButton": True,
    }
    methods = [method for method, _payload in calls]
    assert methods == ["setMyShortDescription", "setMyDescription", "setMyCommands", "setChatMenuButton"]
    assert "live-priced compute/energy mock contract" in calls[1][1]["description"]
    assert "Raw REJECT/DEFER" in calls[1][1]["description"]
    assert calls[3][1]["menu_button"]["web_app"]["url"] == "https://power.example.com/tg"


def test_scan_command_requires_admin(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_USER_IDS", "42")

    assert telegram_bot.handle_command("/scan", 7, logs=tmp_path) == "Not authorized."
    reply = telegram_bot.handle_command("/scan", 42, logs=tmp_path)

    assert "Dry-run scan queued" in reply
    assert len(scan_requests.pending_requests(logs=tmp_path)) == 1


def test_channel_notify_dedupes_messages(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@desk")
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)))
    monkeypatch.setattr(telegram_bot, "snapshot", lambda logs=None: {
        "signal": {"latest": {"signal_id": "sig1", "direction": "electricity_expensive", "z": -2}},
        "synthetic_instrument": {
            "proposal_id": "abc",
            "instrument_name": "ERCOT power compute receivable hedge note abc",
            "outputs": {
                "mock_hedge_construction": {
                    "hedge_notional_usdc": 1500.0,
                    "circle_testnet_usdc_request": 1630.0,
                    "recommended_action": "BUY_CONTRACT",
                    "recommendation_label": "Open paper hedge",
                    "recommendation_summary": "Open a paper/testnet hedge ticket.",
                    "entry_signal_score": 83.0,
                    "entry_threshold_score": 70.0,
                    "judge_verdict": {"label": "EXECUTE", "reason_code": "all_gates_passed", "confidence": 0.95},
                    "quote_sources": ["yahoo_finance_chart"],
                    "weighted_legs": [{"slug": "NVDA", "side": "short", "weight": -0.2}],
                },
            },
        },
        "verdicts": [],
        "positions": [],
    })

    assert telegram_bot.notify_channel_once(logs=tmp_path) == 1
    assert telegram_bot.notify_channel_once(logs=tmp_path) == 0
    assert len(sent) == 1
    assert "Open paper hedge mock compute/energy contract" in sent[0][1]
    assert "entry score: 83/100 (threshold 70)" in sent[0][1]
    assert "judge: EXECUTE/all_gates_passed" in sent[0][1]


def test_channel_messages_mute_rejects():
    messages = telegram_bot.channel_messages({
        "runtime": {},
        "signal": {"latest": {"signal_id": "sig1", "direction": "electricity_expensive", "z": -2}},
        "verdicts": [{
            "action_payload_hash": "abc",
            "label": "REJECT",
            "surface": "polymarket",
            "instrument": "will-openai-launch-hardware",
            "reason_code": "premium_gate_fail",
        }],
        "positions": [],
    })

    assert messages == []


def test_latest_includes_direct_inventory_watchlist():
    text = telegram_bot.format_latest({
        "signal": {"latest": {"direction": "electricity_expensive", "z": -2}},
        "verdicts": [],
        "positions": [],
        "synthetic_instrument": {
            "instrument_name": "ERCOT power compute receivable hedge note abc123",
            "collateral_status": "not_asset_backed_v0",
            "outputs": {
                "agent_next_actions": ["Find one direct regional energy/grid-stress leg."],
                "priced_hedge_basket": [{"slug": "NVDA"}, {"slug": "CEG"}],
                "mock_hedge_construction": {
                    "hedge_notional_usdc": 1500.0,
                    "circle_testnet_usdc_request": 1630.0,
                    "recommended_action": "BUY_CONTRACT",
                    "recommendation_label": "Open paper hedge",
                    "recommendation_summary": "Open a paper/testnet hedge ticket.",
                    "entry_signal_score": 83.0,
                    "entry_threshold_score": 70.0,
                    "judge_verdict": {"label": "EXECUTE", "reason_code": "all_gates_passed", "confidence": 0.95},
                    "weighted_legs": [
                        {"slug": "NVDA", "side": "short", "weight": -0.2},
                        {"slug": "CEG", "side": "long", "weight": 0.2},
                    ],
                },
                "discovery_gaps": [{"slug": "retxc-ec", "status_label": "Needs live venue price"}],
                "agent_search_plan": [{"surface": "opoint_nebius", "target": "news-grounded spread drivers"}],
                "syndicated_instrument_menu": [{
                    "title": "Miner-margin power pair",
                    "instrument_type": "miner_margin_power_pair",
                    "latest_signal": "BUY",
                    "status": "PAPER_BUY_ONLY",
                    "trailing_returns": {
                        "5d": {"return_pct": 2.1},
                        "1m": {"return_pct": 6.1},
                    },
                }],
                "real_venue_copy_matrix": {
                    "rows": [
                        {
                            "surface": "polymarket",
                            "copy_role": "direct_event_leg",
                            "copy_status": "NEEDS_PREMIUM_AND_JUDGE",
                            "spread_links": [{"archetype_id": "fuel_stack_compute_spread"}],
                        },
                        {
                            "surface": "public_market",
                            "copy_role": "liquid_proxy_hedge",
                            "copy_status": "PROXY_LIVE",
                            "spread_links": [{"archetype_id": "fuel_stack_compute_spread"}],
                        },
                    ],
                },
            },
        },
        "direct_inventory": [{
            "surface": "ibkr_prediction",
            "leg_title": "Texas Commercial Electricity Generation Sales Revenue",
            "leg_slug": "retxc-ec",
            "direct_pair_role": "energy/grid-stress leg",
            "pricing_status": "unpriced_snapshot",
            "pricing_status_label": "Needs live venue price",
        }],
        "spread_families": {
            "primary_family": {
                "label": "Compute minus power cost",
                "status": "INSUFFICIENT_MARK_CHANGES",
                "raw_observations": 720,
                "observations": 11,
                "collapsed_repeated_marks": 709,
            },
        },
        "proxy_baskets": {
            "primary_basket": {
                "label": "Miner-margin power pair",
                "status": "PROMOTABLE",
                "recommendation": "BUY_OR_HOLD",
                "latest_signal": "BUY",
                "trailing_returns": {
                    "5d": {"return_pct": 2.1, "observations": 5},
                    "1m": {"return_pct": 1.5, "observations": 21},
                },
                "total_return_pct": 1.5,
                "win_rate": 46.67,
                "observations": 31,
            },
        },
        "pnl": {
            "status_label": "No settled PnL",
            "display_total": "No settled PnL",
            "display_trades": "0 settled",
        },
        "venue_evidence": {
            "rows": [
                {"surface": "polymarket", "status": "LIVE_PRICED", "priced_count": 1, "external_proxy_count": 0},
                {"surface": "ibkr_prediction", "status": "PROXY_PRICED", "priced_count": 0, "external_proxy_count": 1},
                {"surface": "opoint_nebius", "status": "EVIDENCE_LOGGED", "priced_count": 0, "external_proxy_count": 0},
            ],
        },
    })

    assert "Latest mock contract" in text
    assert "research watchlist:" in text
    assert "contract: ERCOT power compute receivable hedge note abc123" in text
    assert "live-priced basket: NVDA, CEG" in text
    assert "funding: 1500.00 USDC notional, Circle ask 1630.00 test USDC" in text
    assert "agent recommendation: Open paper hedge — Open a paper/testnet hedge ticket." in text
    assert "entry score: 83/100 (threshold 70)" in text
    assert "judge: EXECUTE/all_gates_passed" in text
    assert "weights: short NVDA -20.0%, long CEG +20.0%" in text
    assert "spread replay: INSUFFICIENT_MARK_CHANGES" in text
    assert "11/720 mark changes" in text
    assert "proxy replay: BUY/PROMOTABLE/BUY_OR_HOLD" in text
    assert "5d +2.10%" in text
    assert "settled PnL: No settled PnL" in text
    assert "venue copy matrix: polymarket:direct event leg/NEEDS PREMIUM AND JUDGE -> fuel_stack_compute_spread" in text
    assert "public_market:liquid proxy hedge/PROXY LIVE" in text
    assert "venue evidence: polymarket:LIVE PRICED (1 priced)" in text
    assert "ibkr_prediction:PROXY PRICED (0 priced, 1 proxy)" in text
    assert "syndicated structures:" in text
    assert "BUY | Miner-margin power pair | PAPER_BUY_ONLY" in text
    assert "pricing gaps:" not in text
    assert "agent scouting: opoint_nebius:news-grounded spread drivers" in text
    assert "next: Find one direct regional energy/grid-stress leg." in text
    assert "Texas Commercial Electricity Generation Sales Revenue" in text
    assert "Needs live venue price" in text
    assert "unpriced_snapshot" not in text


def test_status_uses_active_direction_matched_proxy_basket():
    text = telegram_bot.format_status({
        "runtime": {"state": "idle"},
        "mode": {"live_chain_enabled": False},
        "synthetic_instrument": {
            "proposal_id": "sig-sheet",
            "outputs": {
                "operator_signal_sheet": {
                    "overall_action": "AVOID_OR_CLOSE",
                    "headline": "Avoid fresh buys; close local mock exposure if already open.",
                    "reason": "Both 5d and 1m proxy PnL are negative.",
                    "direction": "compute_expensive",
                    "active_proxy_basket_id": "compute_scarcity_ai_infra",
                    "guardrail": "Operator signals are advisory. Circle/Arc remains locked unless judge.classify() returns EXECUTE.",
                    "rows": [
                        {
                            "key": "active_proxy_basket",
                            "label": "Compute scarcity AI-infra basket",
                            "action": "AVOID_OR_CLOSE",
                            "signal": "SELL",
                            "status": "OBSERVE",
                            "return_5d_pct": -0.4,
                            "return_1m_pct": -1.5,
                        },
                        {
                            "key": "best_collateral_profile",
                            "label": "Curtailable power GPU batch",
                            "action": "MONITOR",
                            "power_share_pct": 8.54,
                        },
                    ],
                },
            },
        },
        "proxy_baskets": {
            "active_direction": "compute_expensive",
            "primary_basket": {
                "label": "Miner-margin power pair",
                "direction": "electricity_expensive",
                "status": "PROMOTABLE",
                "recommendation": "BUY_OR_HOLD",
                "latest_signal": "BUY",
                "trailing_returns": {"5d": {"return_pct": 2.1}},
                "win_rate": 47.0,
            },
            "active_basket": {
                "label": "Compute scarcity AI-infra basket",
                "direction": "compute_expensive",
                "status": "OBSERVE",
                "recommendation": "MONITOR_ONLY",
                "latest_signal": "SELL",
                "trailing_returns": {"5d": {"return_pct": -0.4}, "1m": {"return_pct": -1.5}},
                "win_rate": 43.0,
            },
        },
    })

    assert "proxy replay: SELL/OBSERVE/MONITOR_ONLY | Compute scarcity AI-infra basket | compute_expensive" in text
    assert "operator signal: AVOID_OR_CLOSE | compute_expensive | compute_scarcity_ai_infra" in text
    assert "Avoid fresh buys; close local mock exposure" in text
    assert "Compute scarcity AI-infra basket: AVOID_OR_CLOSE/SELL/OBSERVE | 5d -0.40%, 1m -1.50%" in text
    assert "Curtailable power GPU batch: MONITOR | power share 8.54%" in text
    assert "Circle/Arc remains locked unless judge.classify() returns EXECUTE" in text
    assert "5d -0.40%" in text
    assert "Miner-margin power pair" not in text


def test_latest_includes_operator_signal_sheet():
    text = telegram_bot.format_latest({
        "signal": {"latest": {"direction": "compute_expensive", "z": 1.1}},
        "synthetic_instrument": {
            "instrument_name": "ERCOT power compute receivable hedge note abc",
            "outputs": {
                "operator_signal_sheet": {
                    "overall_action": "AVOID_OR_CLOSE",
                    "headline": "Avoid fresh buys; close local mock exposure if already open.",
                    "reason": "Both 5d and 1m proxy PnL are negative.",
                    "direction": "compute_expensive",
                    "active_proxy_basket_id": "compute_scarcity_ai_infra",
                    "rows": [
                        {
                            "key": "active_proxy_basket",
                            "label": "Compute scarcity AI-infra basket",
                            "action": "AVOID_OR_CLOSE",
                            "signal": "SELL",
                            "status": "OBSERVE",
                            "return_5d_pct": -0.4,
                            "return_1m_pct": -1.5,
                        },
                        {
                            "key": "spread_replay",
                            "label": "Raw compute minus power",
                            "action": "PROMOTABLE",
                            "win_rate": 61.82,
                        },
                    ],
                },
                "spread_archetype_trade_map": [
                    {
                        "archetype_id": "compute_spark_spread",
                        "label": "Compute spark spread",
                        "tradability_action": "AVOID_OR_SELL",
                        "selected_expression": {
                            "basket_id": "compute_scarcity_ai_infra",
                            "latest_signal": "SELL",
                        },
                    },
                ],
                "spread_profitability_ledger": {
                    "realized": False,
                    "rows": [
                        {
                            "archetype_id": "fuel_stack_compute_spread",
                            "label": "Fuel-stack compute spread",
                            "profitability_status": "PAPER_BUY",
                            "latest_signal": "BUY",
                            "paper_5d_return_pct": 2.2,
                            "paper_1m_return_pct": 6.1,
                            "latest_paper_pnl_usdc": 52.5,
                            "latest_paper_return_pct": 2.0,
                            "paper_trade_total_pnl_usdc": 48.0,
                            "paper_trade_action": "HOLD_OPEN",
                            "paper_trade_hit_rate": 50.0,
                            "oos_status": "PASSED",
                            "oos_test_return_pct": 1.1,
                        },
                        {
                            "archetype_id": "compute_spark_spread",
                            "label": "Compute spark spread",
                            "profitability_status": "SELL_OR_AVOID",
                            "latest_signal": "SELL",
                            "paper_5d_return_pct": -0.4,
                            "paper_1m_return_pct": -1.5,
                        },
                    ],
                },
                "portfolio_signal_summary": {
                    "action": "ROTATE",
                    "paper_ticket_total_pnl_usdc": 48.0,
                    "latest_mark_total_pnl_usdc": 52.5,
                    "buy_count": 1,
                    "close_or_avoid_count": 1,
                    "wait_count": 0,
                },
                "direct_event_pair_candidates": {
                    "pair_count": 1,
                    "ready_for_judge_count": 1,
                    "rows": [
                        {
                            "readiness": "NEEDS_PREMIUM_AND_JUDGE",
                            "oracle_evidence": {
                                "gate": "EVIDENCE_ONLY_DEFER",
                                "receipts": 2,
                            },
                            "energy_leg": {
                                "slug": "ai-data-center-moratorium-passed-before-2027",
                                "pair_side": "long",
                            },
                            "compute_leg": {
                                "slug": "kxdatacenter-30",
                                "pair_side": "short",
                            },
                        },
                    ],
                },
            },
        },
    })

    assert "operator signal sheet:" in text
    assert "operator signal: AVOID_OR_CLOSE | compute_expensive | compute_scarcity_ai_infra" in text
    assert "Compute scarcity AI-infra basket: AVOID_OR_CLOSE/SELL/OBSERVE | 5d -0.40%, 1m -1.50%" in text
    assert "Raw compute minus power: PROMOTABLE | WR 62%" in text
    assert "portfolio signal: ROTATE | tickets $+48.00, marks $+52.50 | 1 buy/1 close/0 wait" in text
    assert "profitability ledger: Fuel-stack compute spread:PAPER_BUY/BUY (5d +2.20%, 1m +6.10%, mark $+52.50 / +2.00%, tickets $+48.00 HOLD_OPEN hit +50.00%, OOS PASSED +1.10%)" in text
    assert "not realized PnL" in text
    assert "spread trade map: Compute spark spread:AVOID_OR_SELL/SELL via compute_scarcity_ai_infra" in text
    assert "direct event pairs: 1/1 ready | NEEDS PREMIUM AND JUDGE long ai-data-center-moratorium-passed-before-2027 vs short kxdatacenter-30 (oracle EVIDENCE ONLY DEFER, 2 receipts)" in text


def test_status_formats_spread_archetype_scoreboard():
    text = telegram_bot.format_status({
        "runtime": {"state": "idle"},
        "mode": {"live_chain_enabled": False},
        "spread_families": {
            "index_coverage": {
                "electricity": {"usable": 4, "total": 12},
                "compute": {"usable": 4, "total": 13},
                "spread_archetypes": {
                    "replayed": 7,
                    "total": 8,
                    "needs_history": [{"archetype_id": "regional_compute_power_basis", "label": "Regional compute-power basis"}],
                },
                "summary": "4/12 electricity indexes usable, 4/13 compute indexes usable, 7/8 spread forms replayed.",
            },
            "archetype_scoreboard": [
                {"label": "Compute spark spread", "replay_status": "PROMOTABLE", "evidence_level": "replayed", "oos_status": "PASSED"},
                {"label": "Compute calendar spread", "replay_status": "NEEDS_INDEX_HISTORY", "evidence_level": "planned"},
            ],
        },
    })

    assert "index coverage: 4/12 electricity indexes usable, 4/13 compute indexes usable, 7/8 spread forms replayed." in text
    assert "needs history: Regional compute-power basis" in text
    assert "spread archetypes: Compute spark spread:PROMOTABLE/replayed/OOS PASSED" in text
    assert "Compute calendar spread:NEEDS_INDEX_HISTORY/planned" in text


def test_profitability_ledger_line_includes_signal_reason_when_present():
    text = telegram_bot._profitability_ledger_line({
        "synthetic_instrument": {
            "outputs": {
                "spread_profitability_ledger": {
                    "realized": False,
                    "rows": [{
                        "label": "Compute calendar spread",
                        "profitability_status": "SELL_OR_AVOID",
                        "latest_signal": "SELL",
                        "paper_5d_return_pct": -0.4,
                        "paper_1m_return_pct": -1.5,
                        "signal_reason": "Both 5d and 1m proxy PnL are negative.",
                    }],
                },
            },
        },
    })

    assert "Compute calendar spread:SELL_OR_AVOID/SELL" in text
    assert "why Both 5d and 1m proxy PnL are negative." in text
    assert "not realized PnL" in text


def test_latest_marks_active_syndicated_structure():
    text = telegram_bot.format_latest({
        "signal": {"latest": {"direction": "compute_expensive", "z": 2.4}},
        "synthetic_instrument": {
            "instrument_name": "PJM compute receivable hedge note",
            "outputs": {
                "syndicated_instrument_menu": [
                    {
                        "title": "Compute scarcity receivable hedge note",
                        "instrument_type": "compute_receivable_hedge_note",
                        "latest_signal": "SELL",
                        "status": "AVOID_OR_SELL",
                        "basket_direction": "compute_expensive",
                        "direction_aligned": True,
                        "trailing_returns": {"5d": {"return_pct": -0.4}, "1m": {"return_pct": -1.5}},
                    },
                    {
                        "title": "Miner-margin power pair",
                        "instrument_type": "miner_margin_power_pair",
                        "latest_signal": "BUY",
                        "status": "PAPER_BUY_ONLY",
                        "basket_direction": "electricity_expensive",
                        "direction_aligned": False,
                        "trailing_returns": {"5d": {"return_pct": 2.1}, "1m": {"return_pct": 6.1}},
                    },
                ],
            },
        },
    })

    assert "- ACTIVE SELL | Compute scarcity receivable hedge note | AVOID_OR_SELL | compute_expensive" in text
    assert "- BUY | Miner-margin power pair | PAPER_BUY_ONLY | electricity_expensive" in text


def test_about_explains_watchlist_and_channel_policy(tmp_path):
    text = telegram_bot.handle_command("/start", 7, logs=tmp_path)

    assert "/latest and the Mini App show the mock contract" in text
    assert "Buy Contract freezes a local testnet entry ticket" in text
    assert "Settled PnL stays" in text
    assert "Venue evidence matrix shows" in text
    assert "The channel posts mock-contract updates" in text
    assert "premium_gate_fail" in text
    assert "judge.classify() returns EXECUTE" in text


def test_channel_messages_post_mock_contract_recommendation():
    messages = telegram_bot.channel_messages({
        "runtime": {},
        "synthetic_instrument": {
            "proposal_id": "abc123",
            "instrument_name": "ERCOT power compute receivable hedge note abc123",
            "outputs": {
                "mock_hedge_construction": {
                    "hedge_notional_usdc": 1500.0,
                    "circle_testnet_usdc_request": 1630.0,
                    "recommended_action": "BUY_CONTRACT",
                    "recommendation_label": "Open paper hedge",
                    "recommendation_summary": "Open a paper/testnet hedge ticket.",
                    "entry_signal_score": 83.0,
                    "entry_threshold_score": 70.0,
                    "judge_verdict": {"label": "EXECUTE", "reason_code": "all_gates_passed", "confidence": 0.95},
                    "quote_sources": ["yahoo_finance_chart"],
                    "weighted_legs": [
                        {"slug": "NVDA", "side": "short", "weight": -0.2},
                        {"slug": "CEG", "side": "long", "weight": 0.2},
                    ],
                },
            },
        },
        "verdicts": [],
        "positions": [],
    })

    assert len(messages) == 1
    key, text = messages[0]
    assert key == "mock-contract:abc123:BUY_CONTRACT:1630.0"
    assert "Open paper hedge mock compute/energy contract" in text
    assert "Circle ask: 1630.00 test USDC" in text
    assert "entry score: 83/100 (threshold 70)" in text
    assert "judge: EXECUTE/all_gates_passed" in text
    assert "weights: short NVDA -20%, long CEG +20%" in text


def test_channel_messages_skip_low_score_mock_contract():
    messages = telegram_bot.channel_messages({
        "runtime": {},
        "synthetic_instrument": {
            "proposal_id": "low-score",
            "outputs": {
                "mock_hedge_construction": {
                    "hedge_notional_usdc": 1500.0,
                    "circle_testnet_usdc_request": 1630.0,
                    "recommended_action": "BUY_CONTRACT",
                    "recommendation_label": "Open paper hedge",
                    "entry_signal_score": 22.5,
                    "entry_threshold_score": 70.0,
                    "judge_verdict": {"label": "EXECUTE", "reason_code": "all_gates_passed"},
                },
            },
        },
        "verdicts": [],
        "positions": [],
    })

    assert messages == []


def test_channel_messages_post_operator_sell_update_without_reject_spam(monkeypatch):
    monkeypatch.setattr(telegram_bot.time, "time", lambda: 1_779_960_000)
    messages = telegram_bot.channel_messages({
        "runtime": {},
        "synthetic_instrument": {
            "proposal_id": "operator-sell",
            "outputs": {
                "operator_signal_sheet": {
                    "overall_action": "AVOID_OR_CLOSE",
                    "headline": "Avoid fresh buys; close local mock exposure if already open.",
                    "reason": "Both 5d and 1m proxy PnL are negative.",
                    "direction": "compute_expensive",
                    "active_proxy_basket_id": "compute_scarcity_ai_infra",
                    "guardrail": "Operator signals are advisory. Circle/Arc remains locked unless judge.classify() returns EXECUTE.",
                    "rows": [
                        {
                            "key": "active_proxy_basket",
                            "label": "Compute scarcity AI-infra basket",
                            "action": "AVOID_OR_CLOSE",
                            "signal": "SELL",
                            "status": "OBSERVE",
                            "return_5d_pct": -0.4,
                            "return_1m_pct": -1.5,
                        },
                    ],
                },
            },
        },
        "proxy_baskets": {"active_basket": {"basket_id": "compute_scarcity_ai_infra", "end_date": "2026-05-28"}},
        "verdicts": [{
            "label": "REJECT",
            "reason_code": "premium_gate_fail",
            "instrument": "polymarket:bad-row",
        }],
    })

    assert len(messages) == 1
    key, text = messages[0]
    assert key == "operator-signal:operator-sell:2026-05-28:AVOID_OR_CLOSE:compute_scarcity_ai_infra"
    assert "Operator signal update" in text
    assert "AVOID_OR_CLOSE" in text
    assert "5d -0.40%" in text
    assert "No raw REJECT/DEFER/watchlist rows" in text
    assert "polymarket:bad-row" not in text


def test_channel_messages_do_not_post_raw_execute_packages():
    messages = telegram_bot.channel_messages({
        "runtime": {},
        "packages": [{
            "id": "pkg1",
            "package_id": "pkg1",
            "label": "EXECUTE",
            "direction": "electricity_expensive",
            "legs": [
                {"label": "EXECUTE", "surface": "crypto", "instrument": "BTC/USD"},
                {
                    "label": "REJECT",
                    "surface": "polymarket",
                    "leg_title": "Rejected direct event",
                    "reason_code": "premium_gate_fail",
                },
            ],
        }],
        "verdicts": [],
        "positions": [],
    })

    assert messages == []


def test_channel_messages_include_runtime_errors():
    messages = telegram_bot.channel_messages({
        "runtime": {"last_error": "feed timeout", "last_failure_at": 123},
        "signal": {"latest": {}},
        "verdicts": [],
        "positions": [],
    })

    assert messages == [("runtime:error:123", "Runtime error: feed timeout")]


def test_channel_about_dedupes(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@desk")
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)))

    assert telegram_bot.notify_channel_about_once(logs=tmp_path) == 1
    assert telegram_bot.notify_channel_about_once(logs=tmp_path) == 0
    assert sent[0][0] == "@desk"
    assert "live-priced compute/energy mock contract" in sent[0][1]
    assert "This channel does not post repeated REJECT/DEFER rows" in sent[0][1]
    assert "Mini App shows live-priced weights" in sent[0][1]


def test_channel_feedback_update_dedupes(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@desk")
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)))

    assert telegram_bot.notify_channel_feedback_update_once(logs=tmp_path) == 1
    assert telegram_bot.notify_channel_feedback_update_once(logs=tmp_path) == 0
    assert sent[0][0] == "@desk"
    assert "feedback shipped" in sent[0][1]
    assert "live-priced mock contract" in sent[0][1]
    assert "channel and bot mute raw REJECT/DEFER/watchlist noise" in sent[0][1]


def test_channel_market_data_update_dedupes(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@desk")
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)))

    assert telegram_bot.notify_channel_market_data_update_once(logs=tmp_path) == 1
    assert telegram_bot.notify_channel_market_data_update_once(logs=tmp_path) == 0
    assert sent[0][0] == "@desk"
    assert "IBKR paper-terminal marks shipped" in sent[0][1]
    assert "IBKR paper CSV / stale" in sent[0][1]
    assert "not live EC prices" in sent[0][1]


def test_channel_instrument_menu_update_dedupes(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@desk")
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)))

    assert telegram_bot.notify_channel_instrument_menu_update_once(logs=tmp_path) == 1
    assert telegram_bot.notify_channel_instrument_menu_update_once(logs=tmp_path) == 0
    assert sent[0][0] == "@desk"
    assert "spread menu shipped" in sent[0][1]
    assert "compute calendar" in sent[0][1]
    assert "miner-margin power pair" in sent[0][1]
    assert "BUY, HOLD, SELL, or MONITOR" in sent[0][1]


def test_channel_profitability_update_dedupes(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@desk")
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)))

    assert telegram_bot.notify_channel_profitability_update_once(logs=tmp_path) == 1
    assert telegram_bot.notify_channel_profitability_update_once(logs=tmp_path) == 0
    assert sent[0][0] == "@desk"
    assert "profitability ledger shipped" in sent[0][1]
    assert "PAPER_BUY, SELL_OR_AVOID, MONITOR" in sent[0][1]
    assert "realized PnL remains separate" in sent[0][1]
    assert "Kalshi, Polymarket, IBKR ForecastTrader" in sent[0][1]
    assert "judge.classify() returns EXECUTE" in sent[0][1]


def test_channel_campaign_messages_are_snapshot_grounded_and_mute_rejects():
    snap = {
        "spread_families": {
            "index_catalog": {
                "electricity": [{"id": "ercot"}, {"id": "pjm"}],
                "compute": [{"id": "aws"}, {"id": "h100"}, {"id": "runpod"}],
                "spread_archetypes": [{"id": "spark"}, {"id": "calendar"}],
            },
            "index_coverage": {
                "electricity": {"usable": 1, "total": 2},
                "compute": {"usable": 2, "total": 3},
                "spread_archetypes": {
                    "replayed": 1,
                    "total": 2,
                    "needs_history": [{"archetype_id": "calendar", "label": "Calendar spread"}],
                },
                "summary": "1/2 electricity indexes usable, 2/3 compute indexes usable, 1/2 spread forms replayed.",
            },
        },
        "synthetic_instrument": {
            "outputs": {
                "spread_profitability_ledger": {
                    "rows": [
                        {
                            "archetype_id": "fuel_stack_compute_spread",
                            "label": "Fuel-stack compute spread",
                            "profitability_status": "PAPER_BUY",
                            "latest_signal": "BUY",
                            "signal_reason": "Promotable replay and recent proxy PnL is non-negative.",
                            "paper_trade_total_pnl_usdc": 80.15,
                            "paper_trade_action": "HOLD_OPEN",
                            "latest_paper_pnl_usdc": 30.21,
                        },
                        {
                            "archetype_id": "compute_spark_spread",
                            "label": "Compute spark spread",
                            "profitability_status": "SELL_OR_AVOID",
                            "signal_reason": "Both 5d and 1m proxy PnL are negative.",
                            "paper_trade_action": "CLOSE_OR_SELL",
                        },
                    ],
                },
                "portfolio_signal_summary": {
                    "action": "CLOSE_OR_AVOID",
                    "top_buy": None,
                    "top_close_or_avoid": {
                        "archetype_id": "compute_spark_spread",
                        "label": "Compute spark spread",
                        "signal_reason": "Both 5d and 1m proxy PnL are negative.",
                    },
                },
                "direct_event_pair_candidates": {
                    "pair_count": 2,
                    "ready_for_judge_count": 1,
                    "rows": [
                        {
                            "readiness": "NEEDS_PREMIUM_AND_JUDGE",
                            "energy_leg": {"surface": "polymarket", "slug": "ai-data-center-moratorium-passed-before-2027"},
                            "compute_leg": {"surface": "kalshi", "slug": "kxdatacenter-30"},
                            "oracle_evidence": {"gate": "EVIDENCE_ONLY_DEFER", "receipts": 2},
                        },
                    ],
                },
                "real_venue_copy_matrix": {
                    "rows": [
                        {"surface": "polymarket", "copy_role": "direct_event_leg", "copy_status": "NEEDS_PREMIUM_AND_JUDGE"},
                        {"surface": "kalshi", "copy_role": "direct_event_leg", "copy_status": "NEEDS_JUDGE_PAIR"},
                        {"surface": "public_market", "copy_role": "liquid_proxy_hedge", "copy_status": "PROXY_LIVE"},
                        {"surface": "crypto", "copy_role": "miner_margin_proxy", "copy_status": "PROXY_LIVE"},
                    ],
                },
            },
        },
        "venue_evidence": {
            "rows": [
                {"surface": "polymarket", "status": "LIVE_PRICED", "priced_count": 1, "external_proxy_count": 0, "quote_sources": ["polymarket_direct_watchlist"]},
                {"surface": "kalshi", "status": "LIVE_PRICED", "priced_count": 1, "external_proxy_count": 0, "quote_sources": ["kalshi_direct_ai_watchlist"]},
                {
                    "surface": "ibkr_prediction",
                    "status": "PROXY_PRICED",
                    "priced_count": 0,
                    "external_proxy_count": 1,
                    "auth_status": "NEEDS_REAUTH",
                    "quote_sources": ["ibkr_forecast_inventory", "yahoo_finance_chart"],
                },
            ],
        },
        "verdicts": [{"label": "REJECT", "reason_code": "premium_gate_fail"}],
    }

    messages = telegram_bot.channel_campaign_messages(snap)
    text = "\n".join(message for _key, message in messages)

    assert len(messages) == 4
    assert "2 electricity indexes, 3 compute indexes, and 2 oil-style spread forms" in text
    assert "Currently usable/replayed: 1 electricity indexes, 2 compute indexes, 1 spread forms" in text
    assert "compute calendar forward hedge, electricity calendar power hedge, and compute-power calendar basis note" in text
    assert "Current buy signal: none. Portfolio action is CLOSE_OR_AVOID; avoid/close Compute spark spread. Why: Both 5d and 1m proxy PnL are negative." in text
    assert "Fuel-stack compute spread" in text
    assert "paper ticket PnL: $+80.15; latest mark PnL: $+30.21" in text
    assert "why: Promotable replay and recent proxy PnL is non-negative." in text
    assert "Compute spark spread is SELL_OR_AVOID with ticket action CLOSE_OR_SELL" in text
    assert "polymarket=direct event leg" in text
    assert "public_market=liquid proxy hedge" in text
    assert "Direct event pairs: 1/2 ready; top pair polymarket:ai-data-center-moratorium-passed-before-2027 vs kalshi:kxdatacenter-30; gate NEEDS_PREMIUM_AND_JUDGE; oracle EVIDENCE_ONLY_DEFER with 2 receipts." in text
    assert "Current venue evidence: polymarket:LIVE PRICED (1 priced), source Polymarket Gamma" in text
    assert "ibkr_prediction:PROXY PRICED (0 priced, 1 proxy), auth NEEDS REAUTH" in text
    assert "source IBKR ForecastTrader inventory/Yahoo fallback" in text
    assert "Live gate labels and IBKR auth hints stay in the Mini App" in text
    assert "judge.classify() first, Arc second" in text
    assert "premium_gate_fail" not in text


def test_campaign_direct_pair_fallback_uses_explicit_role_before_title_terms():
    snap = {
        "direct_inventory": [
            {
                "surface": "polymarket",
                "leg_slug": "ai-data-center-moratorium-passed-before-2027",
                "direct_pair_role": "energy/grid-stress leg",
                "pricing_status": "priced_watchlist",
            },
            {
                "surface": "kalshi",
                "leg_slug": "kxdatacenter-30",
                "leg_title": "Nuclear-powered data center before 2030?",
                "direct_pair_role": "AI compute-demand leg",
                "pricing_status": "priced_watchlist",
            },
        ],
        "oracle": {"latest_pricing_status": "DEFER", "row_count": 3},
        "synthetic_instrument": {"outputs": {"direct_event_pair_candidates": {"rows": []}}},
    }

    line = telegram_bot._campaign_direct_pair_line(snap)

    assert "Direct event pairs: 1/1 ready" in line
    assert "polymarket:ai-data-center-moratorium-passed-before-2027 vs kalshi:kxdatacenter-30" in line
    assert "gate NEEDS_PREMIUM_AND_JUDGE" in line


def test_campaign_venue_health_hides_low_quality_fallback_snapshot():
    snap = {
        "venue_evidence": {
            "rows": [
                {"surface": "polymarket", "status": "NEEDS_PRICE", "priced_count": 0, "quote_sources": ["polymarket_direct_watchlist"]},
                {"surface": "public_market", "status": "REPLAY_PRICED", "priced_count": 7},
                {"surface": "crypto", "status": "REPLAY_PRICED", "priced_count": 2},
            ],
        },
    }
    line = telegram_bot._campaign_venue_health_line(snap)
    direct = telegram_bot._campaign_direct_pair_line(snap)

    assert "draft snapshot is replay/local-fallback quality" in line
    assert "draft snapshot is replay/local-fallback quality" in direct
    assert "NEEDS PRICE" not in line
    assert "0/" not in direct


def test_campaign_snapshot_prefers_running_api(monkeypatch):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"ok": True, "source": "api"}).encode()

    monkeypatch.setenv("TELEGRAM_CAMPAIGN_SNAPSHOT_URL", "http://api.test/snapshot")
    monkeypatch.setattr(telegram_bot.urllib.request, "urlopen", lambda *args, **kwargs: Resp())
    monkeypatch.setattr(telegram_bot, "snapshot", lambda logs=None: (_ for _ in ()).throw(AssertionError("fallback should not run")))

    assert telegram_bot.campaign_snapshot()["source"] == "api"


def test_campaign_snapshot_uses_requests_for_localhost_api(monkeypatch):
    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True, "source": "local-api"}

    calls = []

    def fake_get(url, timeout):
        calls.append((url, timeout))
        return Resp()

    monkeypatch.setenv("TELEGRAM_CAMPAIGN_SNAPSHOT_URL", "http://127.0.0.1:8080/api/snapshot")
    monkeypatch.setattr(telegram_bot.requests, "get", fake_get)
    monkeypatch.setattr(telegram_bot.urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("urllib should not run for localhost")))
    monkeypatch.setattr(telegram_bot, "snapshot", lambda logs=None: (_ for _ in ()).throw(AssertionError("fallback should not run")))

    assert telegram_bot.campaign_snapshot()["source"] == "local-api"
    assert calls == [("http://127.0.0.1:8080/api/snapshot", 15.0)]


def test_campaign_snapshot_retries_transient_api_failure(monkeypatch):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"ok": True, "source": "api-after-retry"}).encode()

    calls = {"count": 0}

    def fake_urlopen(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise telegram_bot.urllib.error.URLError("starting")
        return Resp()

    monkeypatch.setenv("TELEGRAM_CAMPAIGN_SNAPSHOT_URL", "http://api.test/snapshot")
    monkeypatch.setenv("TELEGRAM_CAMPAIGN_SNAPSHOT_ATTEMPTS", "3")
    monkeypatch.setenv("TELEGRAM_CAMPAIGN_SNAPSHOT_RETRY_DELAY", "0")
    monkeypatch.setattr(telegram_bot.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(telegram_bot, "snapshot", lambda logs=None: (_ for _ in ()).throw(AssertionError("fallback should not run")))

    assert telegram_bot.campaign_snapshot()["source"] == "api-after-retry"
    assert calls["count"] == 2


def test_campaign_snapshot_retries_cold_liquid_proxy_evidence(monkeypatch):
    class Resp:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    cold = {
        "ok": True,
        "source": "cold-api",
        "venue_evidence": {
            "rows": [
                {"surface": "public_market", "status": "NEEDS_PRICE", "priced_count": 0},
                {"surface": "crypto", "status": "NEEDS_PRICE", "priced_count": 0},
            ],
        },
    }
    warm = {
        "ok": True,
        "source": "warm-api",
        "venue_evidence": {
            "rows": [
                {"surface": "public_market", "status": "LIVE_PRICED", "priced_count": 7},
                {"surface": "crypto", "status": "LIVE_PRICED", "priced_count": 2},
            ],
        },
    }
    payloads = [cold, warm]

    def fake_urlopen(*args, **kwargs):
        return Resp(payloads.pop(0))

    monkeypatch.setenv("TELEGRAM_CAMPAIGN_SNAPSHOT_URL", "http://api.test/snapshot")
    monkeypatch.setenv("TELEGRAM_CAMPAIGN_SNAPSHOT_ATTEMPTS", "3")
    monkeypatch.setenv("TELEGRAM_CAMPAIGN_SNAPSHOT_RETRY_DELAY", "0")
    monkeypatch.setattr(telegram_bot.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(telegram_bot, "snapshot", lambda logs=None: (_ for _ in ()).throw(AssertionError("fallback should not run")))

    assert telegram_bot.campaign_snapshot()["source"] == "warm-api"


def test_campaign_snapshot_retries_cold_polymarket_evidence(monkeypatch):
    class Resp:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    cold = {
        "ok": True,
        "source": "cold-polymarket",
        "venue_evidence": {
            "rows": [
                {"surface": "polymarket", "status": "NEEDS_PRICE", "priced_count": 0, "quote_sources": ["polymarket_direct_watchlist"]},
                {"surface": "public_market", "status": "REPLAY_PRICED", "priced_count": 7},
                {"surface": "crypto", "status": "REPLAY_PRICED", "priced_count": 2},
            ],
        },
    }
    warm = {
        "ok": True,
        "source": "warm-polymarket",
        "venue_evidence": {
            "rows": [
                {"surface": "polymarket", "status": "LIVE_PRICED", "priced_count": 2, "quote_sources": ["polymarket_direct_watchlist"]},
                {"surface": "public_market", "status": "REPLAY_PRICED", "priced_count": 7},
                {"surface": "crypto", "status": "REPLAY_PRICED", "priced_count": 2},
            ],
        },
    }
    payloads = [cold, warm]

    def fake_urlopen(*args, **kwargs):
        return Resp(payloads.pop(0))

    monkeypatch.setenv("TELEGRAM_CAMPAIGN_SNAPSHOT_URL", "http://api.test/snapshot")
    monkeypatch.setenv("TELEGRAM_CAMPAIGN_SNAPSHOT_ATTEMPTS", "3")
    monkeypatch.setenv("TELEGRAM_CAMPAIGN_SNAPSHOT_RETRY_DELAY", "0")
    monkeypatch.setattr(telegram_bot.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(telegram_bot, "snapshot", lambda logs=None: (_ for _ in ()).throw(AssertionError("fallback should not run")))

    assert telegram_bot.campaign_snapshot()["source"] == "warm-polymarket"


def test_campaign_snapshot_fallback_keeps_direct_events_but_disables_heavy_proxy_refresh(monkeypatch):
    seen = {}

    def fake_snapshot(logs=None):
        for name in (
            "KALSHI_DIRECT_EVENT_FETCH",
            "POLYMARKET_DIRECT_EVENT_FETCH",
            "PUBLIC_HEDGE_FETCH",
            "IBKR_FORECAST_PROXY_QUOTE_FETCH",
            "PROXY_BASKET_BACKTEST_FETCH",
        ):
            seen[name] = telegram_bot.os.environ.get(name)
        return {"ok": True, "source": "fallback"}

    monkeypatch.setenv("TELEGRAM_CAMPAIGN_SNAPSHOT_URL", "http://api.test/snapshot")
    monkeypatch.setenv("KALSHI_DIRECT_EVENT_FETCH", "1")
    monkeypatch.setenv("POLYMARKET_DIRECT_EVENT_FETCH", "1")
    monkeypatch.setenv("PUBLIC_HEDGE_FETCH", "1")
    monkeypatch.setattr(telegram_bot.urllib.request, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(telegram_bot.urllib.error.URLError("down")))
    monkeypatch.setattr(telegram_bot, "snapshot", fake_snapshot)

    assert telegram_bot.campaign_snapshot()["source"] == "fallback"
    assert seen["KALSHI_DIRECT_EVENT_FETCH"] == "1"
    assert seen["POLYMARKET_DIRECT_EVENT_FETCH"] == "1"
    assert seen["PUBLIC_HEDGE_FETCH"] == "0"
    assert seen["IBKR_FORECAST_PROXY_QUOTE_FETCH"] == "0"
    assert seen["PROXY_BASKET_BACKTEST_FETCH"] == "0"
    assert telegram_bot.os.environ["KALSHI_DIRECT_EVENT_FETCH"] == "1"
    assert telegram_bot.os.environ["POLYMARKET_DIRECT_EVENT_FETCH"] == "1"
    assert telegram_bot.os.environ["PUBLIC_HEDGE_FETCH"] == "1"


def test_campaign_snapshot_for_messaging_keeps_warmest_venue_evidence(monkeypatch):
    cold = {
        "ok": True,
        "venue_evidence": {
            "rows": [
                {"surface": "polymarket", "status": "NEEDS_PRICE", "priced_count": 0},
                {"surface": "public_market", "status": "REPLAY_PRICED", "priced_count": 7},
                {"surface": "crypto", "status": "REPLAY_PRICED", "priced_count": 2},
            ],
        },
    }
    warm = {
        "ok": True,
        "venue_evidence": {
            "rows": [
                {"surface": "polymarket", "status": "LIVE_PRICED", "priced_count": 2},
                {"surface": "kalshi", "status": "LIVE_PRICED", "priced_count": 5},
                {"surface": "ibkr_prediction", "status": "PROXY_PRICED", "priced_count": 0, "external_proxy_count": 4},
                {"surface": "public_market", "status": "LIVE_PRICED", "priced_count": 9},
                {"surface": "crypto", "status": "LIVE_PRICED", "priced_count": 2},
            ],
        },
    }
    payloads = [cold, warm]

    monkeypatch.setenv("TELEGRAM_CAMPAIGN_MESSAGE_ATTEMPTS", "2")
    monkeypatch.setenv("TELEGRAM_CAMPAIGN_MESSAGE_RETRY_DELAY", "0")
    monkeypatch.setattr(telegram_bot, "campaign_snapshot", lambda logs=None: payloads.pop(0))

    rows = telegram_bot.campaign_snapshot_for_messaging()["venue_evidence"]["rows"]
    by_surface = {row["surface"]: row for row in rows}

    assert by_surface["polymarket"]["status"] == "LIVE_PRICED"
    assert by_surface["public_market"]["status"] == "LIVE_PRICED"


def test_channel_campaign_post_dedupes(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@desk")
    monkeypatch.setenv("TELEGRAM_CAMPAIGN_SNAPSHOT_URL", "0")
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)))
    monkeypatch.setattr(telegram_bot, "snapshot", lambda logs=None: {
        "spread_families": {"index_catalog": {"electricity": [], "compute": [], "spread_archetypes": []}},
        "synthetic_instrument": {"outputs": {"spread_profitability_ledger": {"rows": []}, "real_venue_copy_matrix": {"rows": []}}},
    })

    assert telegram_bot.notify_channel_campaign_once(logs=tmp_path) == 4
    assert telegram_bot.notify_channel_campaign_once(logs=tmp_path) == 0
    assert len(sent) == 4
    assert sent[0][0] == "@desk"
    assert "campaign 1/4" in sent[0][1]
    assert "campaign 4/4" in sent[-1][1]


def test_ibkr_reauth_reminder_goes_to_private_admin_and_dedupes(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_USER_IDS", "1145119")
    monkeypatch.setenv("IBKR_REAUTH_REMINDER_ENABLED", "1")
    monkeypatch.setenv("IBKR_REAUTH_REMINDER_INTERVAL_HOURS", "4")
    monkeypatch.setattr(telegram_bot.time, "time", lambda: 16_000)
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)))

    assert telegram_bot.notify_ibkr_reauth_reminder_once(logs=tmp_path) == 1
    assert telegram_bot.notify_ibkr_reauth_reminder_once(logs=tmp_path) == 0
    assert sent[0][0] == "1145119"
    assert "https://localhost:5055" in sent[0][1]
    assert "npm run ibkr:cp-watchdog-once" in sent[0][1]


def test_ibkr_reauth_reminder_can_be_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_USER_IDS", "1145119")
    monkeypatch.setenv("IBKR_REAUTH_REMINDER_ENABLED", "0")
    monkeypatch.setattr(telegram_bot, "send_message", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no send")))

    assert telegram_bot.notify_ibkr_reauth_reminder_once(logs=tmp_path) == 0


def test_webhook_url_uses_public_base(monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.ngrok-free.app/")

    assert telegram_bot.webhook_url() == "https://example.ngrok-free.app/api/telegram/webhook"


def test_set_webhook_passes_secret(monkeypatch):
    calls = []
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.ngrok-free.app")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "abc")
    monkeypatch.setattr(telegram_bot, "telegram_call", lambda method, payload: calls.append((method, payload)) or {"ok": True})

    assert telegram_bot.set_webhook() == {"ok": True}
    assert calls == [("setWebhook", {
        "url": "https://example.ngrok-free.app/api/telegram/webhook",
        "allowed_updates": ["message"],
        "secret_token": "abc",
    })]


def test_process_update_ignores_channel_post_commands(monkeypatch):
    monkeypatch.setattr(
        telegram_bot,
        "send_message",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no channel reply")),
    )

    telegram_bot.process_update({
        "channel_post": {
            "chat": {"id": "@desk", "type": "channel"},
            "text": "/scan",
        }
    })


def test_process_update_ignores_group_commands(monkeypatch):
    monkeypatch.setattr(
        telegram_bot,
        "send_message",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no group reply")),
    )

    telegram_bot.process_update({
        "message": {
            "chat": {"id": -100, "type": "supergroup"},
            "from": {"id": 42},
            "text": "/status",
        }
    })


def test_process_update_allows_private_command(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda chat_id, text, reply_markup=None: sent.append((chat_id, text)))
    monkeypatch.setenv("TELEGRAM_ADMIN_USER_IDS", "42")

    telegram_bot.process_update({
        "message": {
            "chat": {"id": 42, "type": "private"},
            "from": {"id": 42},
            "text": "/scan",
        }
    }, logs=tmp_path)

    assert sent and sent[0][0] == 42
    assert "Dry-run scan queued" in sent[0][1]
