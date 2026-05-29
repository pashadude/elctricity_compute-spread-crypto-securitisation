import csv
import json
import math
import sqlite3

from services import state


def _write_tsv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def test_snapshot_sanitizes_identity_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    _write_tsv(tmp_path / "positions.tsv", [{
        "ts": "1",
        "stage": "settled",
        "job_id": "19091",
        "surface": "crypto",
        "instrument": "BTC/USD",
        "tx_hash": "0xabc",
        "client_wallet_id": "must-not-leak",
    }])
    _write_tsv(tmp_path / "judgements.tsv", [{
        "ts": "2",
        "surface": "crypto",
        "instrument": "BTC/USD",
        "label": "EXECUTE",
        "reason_code": "all_gates_passed",
        "api_key": "must-not-leak",
    }])

    snap = state.snapshot()

    assert snap["positions"][0]["job_id"] == 19091
    assert snap["positions"][0]["status"] == "completed"
    assert snap["positions"][0]["arcscan_url"].endswith("/tx/0xabc")
    assert "client_wallet_id" not in snap["positions"][0]
    assert "api_key" not in snap["verdicts"][0]


def test_identity_log_is_not_readable(tmp_path):
    (tmp_path / "identity.tsv").write_text("wallet_id\nsecret\n")
    try:
        state.read_tsv("identity.tsv", logs=tmp_path)
    except ValueError as exc:
        assert "private runtime state" in str(exc)
    else:
        raise AssertionError("identity.tsv must not be API-readable")


def test_runtime_status_json_is_included(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("DIRECT_EVENT_INVENTORY_ENABLED", "0")
    monkeypatch.setenv("PUBLIC_HEDGE_FETCH", "0")
    monkeypatch.setenv("PROXY_BASKET_BACKTEST_FETCH", "0")
    monkeypatch.setenv("IBKR_FORECAST_PROXY_QUOTE_FETCH", "0")
    (tmp_path / "runtime_status.json").write_text(json.dumps({
        "state": "idle",
        "last_error": "",
        "desk_wallet_id": "must-not-leak",
    }))

    assert state.snapshot()["runtime"] == {"state": "idle", "last_error": ""}


def test_telegram_campaign_state_reads_sent_keys_without_message_bodies(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@desk")
    (tmp_path / "telegram_sent.jsonl").write_text(
        "\n".join([
            json.dumps({"ts": 1, "key": "channel-campaign:v1:indexes-spreads", "text": "must-not-leak"}),
            json.dumps({"ts": 2, "key": "channel-campaign:v1:profitability"}),
        ])
    )

    campaign = state.telegram_campaign_state()

    assert campaign["version"] == "telegram_campaign_state_v1"
    assert campaign["channel_configured"] is True
    assert campaign["total_posts"] == 4
    assert campaign["posted_count"] == 2
    assert campaign["pending_count"] == 2
    assert campaign["status"] == "READY_TO_POST"
    assert campaign["posts"][0]["status"] == "POSTED"
    assert campaign["posts"][2]["status"] == "READY_TO_POST"
    assert "must-not-leak" not in json.dumps(campaign)


def test_telegram_miniapp_release_state_reads_sent_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@desk")
    (tmp_path / "telegram_sent.jsonl").write_text(
        "\n".join([
            json.dumps({"ts": 1, "key": "channel-miniapp-release:v1:home", "text": "must-not-leak"}),
            json.dumps({"ts": 2, "key": "channel-miniapp-release:v1:contract"}),
        ])
    )

    release = state.telegram_miniapp_release_state()

    assert release["version"] == "telegram_miniapp_release_state_v1"
    assert release["channel_configured"] is True
    assert release["total_posts"] == 5
    assert release["posted_count"] == 2
    assert release["pending_count"] == 3
    assert release["posts"][0]["status"] == "POSTED"
    assert release["posts"][2]["status"] == "READY_TO_POST"
    assert release["post_command"] == "npm run telegram:miniapp-release-post"
    assert "must-not-leak" not in json.dumps(release)


def test_goal_coverage_summarizes_product_goal_without_secret_text():
    coverage = state.goal_coverage_state(
        spread_families={
            "index_coverage": {
                "summary": "5/12 electricity indexes usable, 4/15 compute indexes usable, 10/10 spread forms replayed.",
                "electricity": {
                    "usable": 5,
                    "total": 12,
                    "family_counts": {"physical_power": 5, "fuel_stack": 2},
                    "tradeability_counts": {"live_mark": 1, "priced_proxy": 4},
                },
                "compute": {
                    "usable": 4,
                    "total": 15,
                    "family_counts": {"gpu_rental": 5, "miner_margin": 2},
                    "tradeability_counts": {"live_mark": 1, "direct_event_watchlist": 3},
                },
                "spread_archetypes": {"total": 10, "replayed": 10, "oos_passed": 3},
            }
        },
        synthetic_instrument={
            "outputs": {
                "syndicated_instrument_menu": [{"title": f"note-{i}"} for i in range(5)],
                "spread_archetype_trade_map": [
                    {"is_promotable": True, "oos_status": "PASSED"},
                    {"is_promotable": True},
                ],
                "direct_event_pair_candidates": {"ready_for_judge_count": 1, "total_count": 3},
            }
        },
        profitability_ledger={
            "realized_note": "Replay is paper-only.",
            "rows": [
                {"paper_total_return_pct": 4.2, "profitability_status": "PAPER_BUY"},
                {"latest_mark_pnl_usdc": 2.0, "profitability_status": "CLOSE_OR_AVOID"},
            ],
        },
        portfolio_signal={"action": "CLOSE_OR_AVOID", "rows": [{"id": "row"}]},
        venue_evidence={
            "guardrail": "judge before Arc",
            "summary": {"direct_event_surfaces": 3, "priced_surfaces": 2, "real_feed_surfaces": 4},
            "rows": [{}, {}, {}],
        },
        oracle_evidence={"current_desk_row_count": 2},
        telegram_campaign={"posted_count": 4, "total_posts": 4},
        telegram_miniapp_release={"posted_count": 5, "total_posts": 5},
        pnl={"paper_buy_count": 1, "paper_latest_mark_pnl_usdc": 12.3, "mark_to_market_note": "paper only"},
    )

    assert coverage["version"] == "goal_coverage_v1"
    assert coverage["overall_status"] == "READY"
    assert coverage["items"][0]["id"] == "indexes_spreads"
    assert coverage["items"][2]["status"] == "READY"
    assert coverage["requirements"][0]["id"] == "req_1_indexes_spreads"
    assert coverage["requirements"][0]["status"] == "READY"
    assert coverage["requirements"][2]["status"] == "READY"
    assert "5 syndicated instruments" in coverage["summary"]
    assert "judge.classify() returns EXECUTE" in coverage["guardrail"]
    assert "secret" not in json.dumps(coverage).lower()


def test_snapshot_includes_spread_family_replay_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    rows = []
    for i in range(80):
        rows.append({
            "ts": str(i),
            "region": "ERCOT|us-east-1",
            "electricity_per_mwh": "62.6",
            "compute_per_gpu_hr": "0.86635",
            "S_t": "0.84444",
            "k": "0.5",
            "kwh_per_gpu_hr": "0.7",
        })
    _write_tsv(tmp_path / "spread_history.tsv", rows)

    snap = state.snapshot()

    assert snap["spread_families"]["version"] == "spread_family_replay_v1"
    assert snap["spread_families"]["entry_gate_pass"] is False
    assert snap["spread_families"]["primary_family"]["status"] == "INSUFFICIENT_VARIANCE"
    assert snap["synthetic_instrument"]["outputs"]["spread_family_validation"]["entry_gate_pass"] is False


def test_spread_state_merges_latest_power_proxy_source(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    _write_tsv(tmp_path / "spread_history.tsv", [{
        "ts": "1779931022",
        "region": "ERCOT|us-east-1",
        "electricity_per_mwh": "63.535",
        "compute_per_gpu_hr": "0.86635",
        "S_t": "0.844113",
        "k": "0.5",
        "kwh_per_gpu_hr": "0.7",
    }])
    (tmp_path / "spread_mark_sources.jsonl").write_text(json.dumps({
        "ts": 1779931022,
        "electricity_source": "eia_plus_power_proxy",
        "electricity_source_status": "proxy_adjusted",
        "electricity_base_per_mwh": 62.6,
        "electricity_proxy_weighted_return_pct": 1.493,
        "electricity_proxy_symbols": ["NG=F", "NRG", "CEG"],
        "electricity_proxy_used_quotes": 3,
        "electricity_proxy_quote_sources": ["yahoo_finance_chart"],
        "eia_period": "2026-03",
        "compute_source": "aws_spot",
        "compute_instance": "p4d.24xlarge",
    }) + "\n")

    latest = state.spread_state()["latest"]

    assert latest["electricity_source"] == "eia_plus_power_proxy"
    assert latest["electricity_source_status"] == "proxy_adjusted"
    assert latest["electricity_base_per_mwh"] == 62.6
    assert latest["electricity_proxy_used_quotes"] == 3
    assert latest["compute_instance"] == "p4d.24xlarge"
    assert latest["power_cost_per_gpu_hr"] == 0.022237
    assert latest["power_cost_share_pct"] == 2.5668


def test_spread_family_state_uses_proxy_history_when_runtime_marks_are_flat(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    flat_rows = []
    for i in range(120):
        flat_rows.append({
            "ts": str(i),
            "region": "ERCOT|us-east-1",
            "electricity_per_mwh": "62.6",
            "compute_per_gpu_hr": "0.86635",
            "S_t": "0.84444",
            "k": "0.5",
            "kwh_per_gpu_hr": "0.7",
        })
    _write_tsv(tmp_path / "spread_history.tsv", flat_rows)
    proxy_rows = []
    for i in range(240):
        s_t = 0.84 + 0.02 * math.sin(i * 2 * math.pi / 24)
        proxy_rows.append({
            "ts": str(i),
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "region": "ERCOT|public-proxy-compute",
            "electricity_per_mwh": "62.6",
            "compute_per_gpu_hr": f"{s_t + 0.02191:.6f}",
            "S_t": f"{s_t:.6f}",
            "k": "0.5",
            "kwh_per_gpu_hr": "0.7",
            "mark_source": "public_proxy_history",
            "electricity_index": "public fuel/power electricity proxy",
            "compute_index": "public compute-infra proxy",
        })
    _write_tsv(tmp_path / "spread_proxy_history.tsv", proxy_rows)

    spread_families = state.snapshot()["spread_families"]

    assert spread_families["primary_source"] == "proxy_history"
    assert spread_families["entry_gate_pass"] is True
    assert spread_families["recorded_history_replay"]["entry_gate_pass"] is False
    assert spread_families["proxy_history_replay"]["entry_gate_pass"] is True


def test_snapshot_reads_saved_proxy_basket_backtest(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    report = {
        "version": "proxy_basket_replay_v1",
        "entry_gate_pass": True,
        "primary_basket": {
            "basket_id": "compute_scarcity_ai_infra",
            "label": "Compute scarcity AI-infra basket",
            "status": "PROMOTABLE",
            "recommendation": "BUY_OR_HOLD",
            "total_return_pct": 12.5,
            "win_rate": 61.0,
            "max_drawdown_pct": -8.0,
            "status_reason": "Historical proxy basket replay is positive enough.",
        },
        "baskets": [],
    }
    (tmp_path / "proxy_basket_backtest.json").write_text(json.dumps(report))

    snap = state.snapshot()

    assert snap["proxy_baskets"]["entry_gate_pass"] is True
    assert snap["proxy_baskets"]["primary_basket"]["basket_id"] == "compute_scarcity_ai_infra"
    assert snap["proxy_baskets"]["active_basket"]["basket_id"] == "compute_scarcity_ai_infra"
    assert snap["synthetic_instrument"]["outputs"]["proxy_basket_validation"]["entry_gate_pass"] is True


def test_venue_evidence_uses_saved_proxy_replay_when_live_public_quotes_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_HEDGE_FETCH", "0")
    monkeypatch.setenv("DIRECT_EVENT_INVENTORY_ENABLED", "0")
    report = {
        "version": "proxy_basket_replay_v1",
        "entry_gate_pass": True,
        "primary_basket": {
            "basket_id": "miner_margin_power_pair",
            "label": "Miner-margin power pair",
            "status": "PROMOTABLE",
            "recommendation": "BUY_OR_HOLD",
            "latest_signal": "BUY",
            "symbols_available": ["NRG", "CEG", "BTC-USD", "ETH-USD"],
            "total_return_pct": 7.1,
            "win_rate": 55.0,
        },
        "baskets": [],
    }
    (tmp_path / "proxy_basket_backtest.json").write_text(json.dumps(report))

    snap = state.snapshot()
    by_surface = {row["surface"]: row for row in snap["venue_evidence"]["rows"]}

    assert by_surface["public_market"]["status"] == "REPLAY_PRICED"
    assert by_surface["crypto"]["status"] == "REPLAY_PRICED"
    assert "yahoo_close_history" in by_surface["public_market"]["quote_sources"]
    assert "yahoo_close_history" in by_surface["crypto"]["quote_sources"]
    assert by_surface["public_market"]["latest_pricing_status"] == "Close-history replay available"


def test_snapshot_pnl_uses_proxy_basket_matching_signal_direction(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    _write_tsv(tmp_path / "arb_signals.tsv", [{
        "ts": "1",
        "signal_id": "sig-proxy-direction",
        "direction": "compute_expensive",
        "region": "ERCOT|us-east-1",
        "z": "2.4",
    }])
    report = {
        "version": "proxy_basket_replay_v1",
        "entry_gate_pass": True,
        "primary_basket": {
            "basket_id": "miner_margin_power_pair",
            "direction": "electricity_expensive",
            "label": "Miner-margin power pair",
            "status": "PROMOTABLE",
            "recommendation": "BUY_OR_HOLD",
            "latest_signal": "BUY",
            "trailing_returns": {"5d": {"return_pct": 2.2}, "1m": {"return_pct": 6.1}},
            "is_promotable": True,
        },
        "baskets": [
            {
                "basket_id": "miner_margin_power_pair",
                "direction": "electricity_expensive",
                "label": "Miner-margin power pair",
                "status": "PROMOTABLE",
                "recommendation": "BUY_OR_HOLD",
                "latest_signal": "BUY",
                "trailing_returns": {"5d": {"return_pct": 2.2}, "1m": {"return_pct": 6.1}},
                "is_promotable": True,
            },
            {
                "basket_id": "compute_scarcity_ai_infra",
                "direction": "compute_expensive",
                "label": "Compute scarcity AI-infra basket",
                "status": "OBSERVE",
                "recommendation": "MONITOR_ONLY",
                "latest_signal": "SELL",
                "trailing_returns": {"5d": {"return_pct": -0.4}, "1m": {"return_pct": -1.5}},
                "total_return_pct": 2.2,
                "win_rate": 43.3,
                "is_promotable": False,
            },
        ],
    }
    (tmp_path / "proxy_basket_backtest.json").write_text(json.dumps(report))

    snap = state.snapshot()

    assert snap["proxy_baskets"]["primary_basket"]["basket_id"] == "miner_margin_power_pair"
    assert snap["proxy_baskets"]["active_basket"]["basket_id"] == "compute_scarcity_ai_infra"
    assert snap["proxy_baskets"]["active_entry_gate_pass"] is False
    assert snap["pnl"]["proxy_basket_id"] == "compute_scarcity_ai_infra"
    assert snap["pnl"]["proxy_latest_signal"] == "SELL"
    assert snap["pnl"]["proxy_5d_return_pct"] == -0.4


def test_snapshot_exposes_gated_pnl_status_without_reconciliation(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    rows = []
    for i in range(80):
        rows.append({
            "ts": str(i),
            "region": "ERCOT|us-east-1",
            "electricity_per_mwh": "62.6",
            "compute_per_gpu_hr": "0.86635",
            "S_t": "0.84444",
            "k": "0.5",
            "kwh_per_gpu_hr": "0.7",
        })
    _write_tsv(tmp_path / "spread_history.tsv", rows)

    pnl = state.snapshot()["pnl"]

    assert pnl["has_reconciled"] is False
    assert pnl["status"] == "NO_SETTLED_PNL"
    assert pnl["display_total"] == "No settled PnL"
    assert pnl["display_trades"] == "0 settled"
    assert pnl["spread_replay_status"] == "INSUFFICIENT_VARIANCE"
    assert "not realized PnL" in pnl["mark_to_market_note"]


def test_snapshot_exposes_paper_portfolio_signal_next_to_settled_pnl(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("DIRECT_EVENT_INVENTORY_ENABLED", "0")
    monkeypatch.setenv("PUBLIC_HEDGE_FETCH", "0")
    monkeypatch.setenv("PROXY_BASKET_BACKTEST_FETCH", "0")
    monkeypatch.setenv("IBKR_FORECAST_PROXY_QUOTE_FETCH", "0")
    proposal = {
        "outputs": {
            "spread_profitability_ledger": {
                "version": "spread_profitability_ledger_v1",
                "paper_notional_usdc": 1500,
                "rows": [],
            },
            "portfolio_signal_summary": {
                "version": "portfolio_signal_summary_v1",
                "action": "CLOSE_OR_AVOID",
                "headline": "Close or avoid current sell signal: Compute calendar spread.",
                "paper_ticket_total_pnl_usdc": 42.5,
                "paper_ticket_realized_pnl_usdc": 31.0,
                "paper_ticket_open_pnl_usdc": 11.5,
                "latest_mark_total_pnl_usdc": -7.25,
                "buy_count": 0,
                "close_or_avoid_count": 2,
                "wait_count": 1,
                "realized": False,
            },
        },
    }
    monkeypatch.setattr(state, "propose_synthetic_instrument", lambda **_kwargs: proposal)

    snap = state.snapshot()

    assert snap["portfolio_signal"]["action"] == "CLOSE_OR_AVOID"
    assert snap["profitability_ledger"]["paper_notional_usdc"] == 1500
    assert snap["pnl"]["status"] == "NO_SETTLED_PNL"
    assert snap["pnl"]["paper_portfolio_action"] == "CLOSE_OR_AVOID"
    assert snap["pnl"]["paper_portfolio_headline"].startswith("Close or avoid")
    assert snap["pnl"]["paper_ticket_total_pnl_usdc"] == 42.5
    assert snap["pnl"]["paper_ticket_realized_pnl_usdc"] == 31.0
    assert snap["pnl"]["paper_ticket_open_pnl_usdc"] == 11.5
    assert snap["pnl"]["paper_latest_mark_pnl_usdc"] == -7.25
    assert snap["pnl"]["paper_close_or_avoid_count"] == 2


def test_snapshot_exposes_real_venue_evidence_matrix(tmp_path, monkeypatch):
    state.cache.clear("public_quote")
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("DIRECT_EVENT_INVENTORY_ENABLED", "1")
    monkeypatch.setenv("IBKR_DIRECT_EVENT_SYMBOLS", "RETXC")
    monkeypatch.setenv("POLYMARKET_DIRECT_EVENT_SLUGS", "ai-data-center-moratorium-passed-before-2027")
    monkeypatch.setenv("POLYMARKET_DIRECT_EVENT_FETCH", "1")
    monkeypatch.setenv("KALSHI_DIRECT_EVENT_FETCH", "1")
    monkeypatch.setenv("PUBLIC_HEDGE_FETCH", "1")
    monkeypatch.setenv("PUBLIC_HEDGE_SYMBOLS", "NVDA,BTC-USD")
    monkeypatch.setattr(state, "_fetch_kalshi_ai_events", lambda: [{
        "id": "KXOPENAI-26",
        "event_ticker": "KXOPENAI-26",
        "slug": "kxopenai-26",
        "title": "Will OpenAI release GPT-6 before 2027?",
        "description": "AI compute event.",
        "yes_prices": [0.54],
    }])
    monkeypatch.setattr(state, "_fetch_polymarket_event", lambda key: {
        "id": "108522",
        "slug": "ai-data-center-moratorium-passed-before-2027",
        "title": "AI data center moratorium passed before 2027?",
        "description": "AI data-center grid-stress event.",
        "yes_prices": [0.32],
    })
    monkeypatch.setattr(state, "_fetch_public_quote", lambda symbol, sources=None: {
        "symbol": symbol,
        "price": 181.25 if symbol == "NVDA" else 74_000.0,
        "currency": "USD",
        "exchange": "NMS",
        "source": "yahoo_finance_chart",
        "source_priority": "ibkr,yahoo",
    })
    monkeypatch.setattr(state, "_ibkr_client_portal_health", lambda: {
        "status": "NEEDS_REAUTH",
        "reachable": True,
        "authenticated": False,
        "connected": False,
        "competing": False,
        "action": "Open Client Portal and finish login/2FA.",
    })
    (tmp_path / "ibkr_forecast_inventory.json").write_text(json.dumps({
        "events": [{
            "symbol": "RETXC",
            "slug": "retxc-ec",
            "title": "Texas Commercial Electricity Generation Sales Revenue",
            "pricing_status": "ibkr_quote_unavailable",
        }],
    }))
    (tmp_path / "energy_llm_oracle.jsonl").write_text(json.dumps({
        "ts": "2026-05-23T20:48:43+00:00",
        "analyst_model": "deepseek-ai/DeepSeek-V3.2",
        "verdict": "DEFER",
        "reason_code": "no_opoint_evidence",
        "event_slug": "ai-data-center-moratorium",
        "coverage": {"raw": 50, "after_filter": 0},
    }) + "\n")

    snap = state.snapshot()
    matrix = snap["venue_evidence"]
    by_surface = {row["surface"]: row for row in matrix["rows"]}

    assert matrix["version"] == "venue_evidence_matrix_v1"
    assert matrix["summary"]["arc_ready_surfaces"] == 0
    assert by_surface["polymarket"]["status"] == "LIVE_PRICED"
    assert by_surface["polymarket"]["premium_gate_required"] is True
    assert by_surface["kalshi"]["status"] == "LIVE_PRICED"
    assert by_surface["ibkr_prediction"]["status"] == "PROXY_PRICED"
    assert by_surface["ibkr_prediction"]["auth_status"] == "NEEDS_REAUTH"
    assert by_surface["ibkr_prediction"]["auth_authenticated"] is False
    assert by_surface["ibkr_prediction"]["external_proxy_count"] == 1
    assert "IBKR Client Portal needs reauth" in by_surface["ibkr_prediction"]["gaps"][0]
    assert by_surface["public_market"]["priced_count"] == 2
    assert by_surface["public_market"]["quote_sources"] == ["yahoo_finance_chart"]
    assert by_surface["crypto"]["status"] == "LIVE_PRICED"
    assert by_surface["opoint_nebius"]["evidence_only"] is True
    assert by_surface["opoint_nebius"]["can_drive_arc"] is False
    assert by_surface["opoint_nebius"]["latest_model"] == "deepseek-ai/DeepSeek-V3.2"
    assert all(row["can_drive_arc"] is False for row in matrix["rows"])
    assert snap["oracle"]["status"] == "EVIDENCE_LOGGED"
    assert snap["oracle"]["row_count"] == 1
    assert snap["oracle"]["verdict_counts"] == {"DEFER": 1}
    oracle_output = snap["synthetic_instrument"]["outputs"]["oracle_judge_evidence"]
    assert oracle_output["status"] == "EVIDENCE_LOGGED"
    assert oracle_output["can_drive_arc"] is False
    assert oracle_output["judge_required"] is True
    assert oracle_output["oracle_evidence_hash"]


def test_oracle_evidence_prefers_compute_power_receipts_for_current_desk(tmp_path):
    (tmp_path / "energy_llm_oracle.jsonl").write_text(
        "\n".join([
            json.dumps({
                "ts": "2026-05-23T20:48:43+00:00",
                "slug": "ai-data-center-moratorium-passed-before-2027",
                "event_slug": "ai-data-center-moratorium-passed-before-2027",
                "energy_template_id": "energy_ai_infra",
                "analyst_model": "deepseek-ai/DeepSeek-V3.2",
                "verdict": "DEFER",
                "reason_code": "no_opoint_evidence",
                "coverage": {"raw": 50, "after_filter": 0},
                "query": {"label": "data_center_power_policy"},
            }),
            json.dumps({
                "ts": "2026-05-24T20:48:43+00:00",
                "slug": "will-80-or-more-ships-transit-the-strait-of-hormuz-between-april-13-april-19",
                "event_slug": "how-many-ships-transit-the-strait-of-hormuz-this-week-apr-13-19",
                "energy_template_id": "energy_geopolitics",
                "analyst_model": "deepseek-ai/DeepSeek-V3.2",
                "verdict": "VETO",
                "reason_code": "analyst_veto",
                "coverage": {"raw": 20, "after_filter": 4},
                "query": {"label": "hormuz_transit"},
            }),
        ]) + "\n"
    )

    oracle_state = state._oracle_evidence_state(logs=tmp_path)

    assert oracle_state["row_count"] == 2
    assert oracle_state["current_desk_row_count"] == 1
    assert oracle_state["latest_scope"] == "compute_power"
    assert oracle_state["latest_query_label"] == "data_center_power_policy"
    assert oracle_state["latest_slug"] == "ai-data-center-moratorium-passed-before-2027"
    assert oracle_state["latest_pricing_status"] == "DEFER"
    assert oracle_state["verdict_counts"] == {"DEFER": 1, "VETO": 1}


def test_public_quote_uses_configured_source_order(monkeypatch):
    state.cache.clear("public_quote")
    monkeypatch.setenv("PUBLIC_HEDGE_PRICE_SOURCES", "alpaca,yahoo")
    monkeypatch.setattr(state, "_fetch_alpaca_public_quote", lambda symbol: {
        "symbol": symbol,
        "price": None,
        "source": "alpaca_market_data",
        "error": "Unauthorized",
    })
    monkeypatch.setattr(state, "_fetch_yahoo_public_quote", lambda symbol: {
        "symbol": symbol,
        "price": 181.5,
        "currency": "USD",
        "exchange": "NMS",
        "source": "yahoo_finance_chart",
    })

    quote = state._fetch_public_quote("NVDA")

    assert quote["price"] == 181.5
    assert quote["source"] == "yahoo_finance_chart"
    assert quote["source_priority"] == "alpaca,yahoo"
    assert quote["fallback_errors"] == ["alpaca_market_data:Unauthorized"]


def test_public_quote_can_use_call_site_source_order(monkeypatch):
    state.cache.clear("public_quote")
    monkeypatch.setenv("PUBLIC_HEDGE_PRICE_SOURCES", "yahoo")
    monkeypatch.setattr(state, "_fetch_ibkr_public_quote", lambda symbol: {
        "symbol": symbol,
        "price": 96.5,
        "currency": "USD",
        "exchange": "NYMEX",
        "source": "ibkr_tws_front_future",
    })
    monkeypatch.setattr(state, "_fetch_yahoo_public_quote", lambda symbol: {
        "symbol": symbol,
        "price": 100.0,
        "currency": "USD",
        "exchange": "NYM",
        "source": "yahoo_finance_chart",
    })

    quote = state._fetch_public_quote("BZ=F", sources=["ibkr", "yahoo"])

    assert quote["price"] == 96.5
    assert quote["source"] == "ibkr_tws_front_future"
    assert quote["source_priority"] == "ibkr,yahoo"


def test_ibkr_public_quote_skips_container_localhost(monkeypatch):
    monkeypatch.delenv("IBKR_HOST", raising=False)
    monkeypatch.setattr(state, "_running_in_docker", lambda: True)

    quote = state._fetch_ibkr_public_quote("NVDA")

    assert quote["price"] is None
    assert quote["source"] == "ibkr_tws"
    assert quote["error"] == "ibkr_host_points_to_container"
    assert "host.docker.internal" in quote["action"]


def test_ibkr_public_quote_fast_skips_unreachable_socket(monkeypatch):
    monkeypatch.setenv("IBKR_HOST", "host.docker.internal")
    monkeypatch.setenv("IBKR_GATEWAY_PORT", "4002")
    monkeypatch.setattr(state, "_running_in_docker", lambda: False)
    monkeypatch.setattr(
        state.socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("closed")),
    )

    quote = state._fetch_ibkr_public_quote("NVDA")

    assert quote["price"] is None
    assert quote["source"] == "ibkr_tws"
    assert quote["error"] == "ibkr_tws_unreachable"
    assert "host.docker.internal:4002" in quote["action"]


def test_snapshot_enriches_polymarket_leg_identity_from_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    _write_tsv(tmp_path / "positions.tsv", [{
        "ts": "1",
        "stage": "wrapped",
        "job_id": "36844",
        "arb_signal_id": "sig-1",
        "surface": "polymarket",
        "instrument": "polymarket:32224",
        "direction": "short",
        "notional_usdc": "1",
        "tx_hash": "0xabc",
    }])
    _write_tsv(tmp_path / "judgements.tsv", [{
        "ts": "2",
        "surface": "polymarket",
        "instrument": "polymarket:32224",
        "direction": "short",
        "sizing_usdc": "1",
        "est_pnl_per_dollar": "0.04",
        "action_payload_hash": "hash-1",
        "label": "EXECUTE",
        "reason_code": "all_gates_passed",
    }])
    conn = sqlite3.connect(tmp_path / "_feed_cache.sqlite")
    conn.execute(
        "CREATE TABLE cache (ns TEXT, key TEXT, expires_at REAL, value TEXT, PRIMARY KEY (ns, key))"
    )
    conn.execute(
        "INSERT INTO cache (ns, key, expires_at, value) VALUES (?, ?, ?, ?)",
        (
            "polymarket_events",
            "limit=50|active=True",
            1,
            json.dumps([{
                "id": "32224",
                "slug": "will-ercot-issue-a-conservation-appeal",
                "title": "Will ERCOT issue a conservation appeal?",
                "description": "Resolves Yes if ERCOT publishes a conservation appeal before the deadline.",
                "endDate": "2026-08-01T00:00:00Z",
            }]),
        ),
    )
    conn.commit()
    conn.close()

    snap = state.snapshot()
    position = snap["positions"][0]
    verdict = snap["verdicts"][0]

    assert position["display_label"] == "Will ERCOT issue a conservation appeal?"
    assert position["leg_slug"] == "will-ercot-issue-a-conservation-appeal"
    assert position["leg_end_date"] == "2026-08-01T00:00:00Z"
    assert "Direct event leg" in position["leg_connection"]
    assert verdict["display_label"] == position["display_label"]
    assert snap["pnl"]["wrapped_jobs"] == 1
    assert snap["pnl"]["executed_verdicts"] == 1
    assert snap["pnl"]["has_reconciled"] is False


def test_snapshot_marks_mock_polymarket_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    _write_tsv(tmp_path / "judgements.tsv", [{
        "ts": "2",
        "surface": "polymarket",
        "instrument": "polymarket:mock-event-A",
        "direction": "short",
        "label": "EXECUTE",
        "reason_code": "all_gates_passed",
    }])

    snap = state.snapshot()

    assert snap["verdicts"][0]["is_mock"] is True
    assert snap["pnl"]["executed_verdicts"] == 0


def test_snapshot_marks_legacy_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("DIRECT_EVENT_INVENTORY_ENABLED", "0")
    monkeypatch.setenv("PUBLIC_HEDGE_FETCH", "0")
    monkeypatch.setenv("PROXY_BASKET_BACKTEST_FETCH", "0")
    monkeypatch.setenv("IBKR_FORECAST_PROXY_QUOTE_FETCH", "0")
    _write_tsv(tmp_path / "positions.tsv", [{
        "ts": "1",
        "stage": "funded",
        "job_id": "13090",
        "surface": "S4",
        "instrument": "mock-001",
        "tx_hash": "0xabc",
    }])

    snap = state.snapshot()

    assert snap["positions"][0]["is_mock"] is True
    assert snap["positions"][0]["is_legacy_artifact"] is True
    assert snap["pnl"]["visible_positions"] == 0


def test_snapshot_fetches_missing_polymarket_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    _write_tsv(tmp_path / "judgements.tsv", [{
        "ts": "2",
        "surface": "polymarket",
        "instrument": "polymarket:32224",
        "direction": "short",
        "label": "EXECUTE",
        "reason_code": "all_gates_passed",
    }])
    monkeypatch.setattr(state, "_fetch_polymarket_event", lambda key: {
        "id": key,
        "slug": "fetched-event-slug",
        "title": "Will ERCOT issue a conservation appeal?",
        "description": "Fetched event description",
        "end_date": "2026-09-01T00:00:00Z",
    })

    snap = state.snapshot()

    assert snap["verdicts"][0]["display_label"] == "Will ERCOT issue a conservation appeal?"
    assert snap["verdicts"][0]["leg_slug"] == "fetched-event-slug"


def test_snapshot_hides_thesis_mismatched_prediction_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    _write_tsv(tmp_path / "judgements.tsv", [{
        "ts": "2",
        "surface": "polymarket",
        "instrument": "polymarket:32224",
        "direction": "short",
        "label": "EXECUTE",
        "reason_code": "all_gates_passed",
    }])
    monkeypatch.setattr(state, "_fetch_polymarket_event", lambda key: {
        "id": key,
        "slug": "which-party-will-win-the-senate-in-2026",
        "title": "Which party will win the Senate in 2026?",
        "description": "This market resolves based on party control of the Senate.",
        "end_date": "2026-11-03T00:00:00Z",
    })

    snap = state.snapshot()

    assert snap["verdicts"][0]["is_thesis_mismatch"] is True
    assert snap["pnl"]["executed_verdicts"] == 0


def test_snapshot_labels_ibkr_prediction_as_direct_event(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("DIRECT_EVENT_INVENTORY_ENABLED", "0")
    monkeypatch.setenv("PUBLIC_HEDGE_FETCH", "0")
    monkeypatch.setenv("PROXY_BASKET_BACKTEST_FETCH", "0")
    monkeypatch.setenv("IBKR_FORECAST_PROXY_QUOTE_FETCH", "0")
    _write_tsv(tmp_path / "judgements.tsv", [{
        "ts": "2",
        "surface": "ibkr_prediction",
        "instrument": "ibkr-prediction:fx-ercot",
        "leg_title": "Will ERCOT issue a conservation appeal?",
        "leg_description": "Energy event contract routed through IBKR ForecastTrader.",
        "direction": "short",
        "label": "EXECUTE",
        "reason_code": "all_gates_passed",
    }])

    snap = state.snapshot()

    assert snap["verdicts"][0]["leg_role"] == "direct_prediction_event"
    assert snap["verdicts"][0]["is_thesis_mismatch"] is False
    assert snap["pnl"]["executed_verdicts"] == 1


def test_snapshot_includes_direct_event_inventory_without_judge_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("IBKR_DIRECT_EVENT_SYMBOLS", "RETXC,ITNVD")
    monkeypatch.setenv("POLYMARKET_DIRECT_EVENT_SLUGS", "ai-data-center-moratorium-passed-before-2027")
    monkeypatch.setenv("POLYMARKET_DIRECT_EVENT_FETCH", "1")
    monkeypatch.setenv("PUBLIC_HEDGE_FETCH", "1")
    monkeypatch.setenv("PUBLIC_HEDGE_SYMBOLS", "NVDA")
    monkeypatch.setenv("IBKR_FORECAST_PROXY_QUOTE_FETCH", "0")
    monkeypatch.setattr(state, "_fetch_public_quote", lambda symbol, sources=None: {
        "symbol": symbol,
        "price": 180.25,
        "currency": "USD",
        "exchange": "NMS",
        "source": "yahoo_finance_chart",
    })
    (tmp_path / "ibkr_forecast_inventory.json").write_text(json.dumps({
        "generated_at": 123,
        "events": [{
            "symbol": "RETXC",
            "slug": "retxc-ec",
            "title": "Texas Commercial Electricity Generation Sales Revenue",
            "description": "Energy event contract discovered through IBKR ForecastTrader.",
            "pricing_status": "unpriced_snapshot",
            "sec_type": "EC",
            "yes_conid": "793085619",
        }],
    }))
    monkeypatch.setattr(state, "_fetch_polymarket_event", lambda key: {
        "id": "108522",
        "slug": "ai-data-center-moratorium-passed-before-2027",
        "title": "AI data center moratorium passed before 2027?",
        "description": "AI data center and grid-stress policy market.",
        "end_date": "2026-12-31T00:00:00Z",
        "yes_prices": [0.933],
        "active": True,
        "closed": False,
    })

    snap = state.snapshot()

    assert snap["packages"] == []
    assert len(snap["direct_inventory"]) == 3
    by_surface = {(row["surface"], row["leg_slug"]): row for row in snap["direct_inventory"]}
    assert by_surface[("ibkr_prediction", "retxc-ec")]["pricing_status"] == "unpriced_snapshot"
    assert by_surface[("ibkr_prediction", "retxc-ec")]["pricing_status_label"] == "Needs live venue price"
    assert by_surface[("ibkr_prediction", "itnvd-ec")]["direct_pair_role"] == "AI compute-demand leg"
    assert by_surface[("polymarket", "ai-data-center-moratorium-passed-before-2027")]["label"] == "WATCHLIST"
    assert all(not row["is_mock"] for row in snap["direct_inventory"])
    assert snap["public_hedges"][0]["leg_slug"] == "NVDA"
    assert snap["public_hedges"][0]["pricing_status"] == "priced_public_market"
    assert snap["public_hedges"][0]["pricing_status_label"] == "Public price available"
    proposal = snap["synthetic_instrument"]
    assert proposal["proposal_type"] == "compute_receivable_hedge_note"
    assert proposal["asset_backed"] is False
    assert proposal["collateral_status"] == "not_asset_backed_v0"
    assert proposal["outputs"]["direct_reference_legs"][0]["slug"] == "ai-data-center-moratorium-passed-before-2027"
    assert proposal["outputs"]["discovery_gaps"][0]["slug"] == "retxc-ec"
    assert proposal["outputs"]["priced_hedge_basket"][0]["slug"] == "NVDA"
    assert proposal["outputs"]["mock_hedge_construction"]["weighted_legs"][0]["last_price"] == 180.25
    assert proposal["outputs"]["mock_hedge_construction"]["weighted_legs"][0]["source"] == "yahoo_finance_chart"
    assert proposal["outputs"]["mock_hedge_construction"]["weighted_legs"][0]["description"] == "GPU supply and AI accelerator capex proxy."
    assert proposal["outputs"]["mock_hedge_construction"]["circle_testnet_usdc_request"] > 0
    assert "No Arc action unless verdict is EXECUTE." in proposal["outputs"]["guardrails"]


def test_snapshot_includes_kalshi_direct_ai_inventory(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("DIRECT_EVENT_INVENTORY_ENABLED", "1")
    monkeypatch.setenv("IBKR_DIRECT_EVENT_SYMBOLS", "")
    monkeypatch.setenv("POLYMARKET_DIRECT_EVENT_SLUGS", "")
    monkeypatch.setenv("KALSHI_DIRECT_EVENT_FETCH", "1")
    monkeypatch.setenv("PUBLIC_HEDGE_FETCH", "0")
    monkeypatch.setattr(state, "_ibkr_inventory_rows", lambda logs=None: [])
    monkeypatch.setattr(state, "_polymarket_inventory_rows", lambda: [])
    monkeypatch.setattr(state, "_fetch_kalshi_ai_events", lambda: [{
        "id": "KXOPENAI-26",
        "event_ticker": "KXOPENAI-26",
        "slug": "kxopenai-26",
        "title": "Will OpenAI release GPT-6 before 2027?",
        "description": "AI compute and frontier model capacity event.",
        "end_date": "2026-12-31T15:00:00Z",
        "yes_prices": [0.54, 0.50],
        "category": "Science and Technology",
        "series_ticker": "KXOPENAI",
        "market_tickers": ["KXOPENAI-26"],
        "mutually_exclusive": True,
        "volume": 150.0,
        "liquidity": 20.5,
    }])

    snap = state.snapshot()

    assert len(snap["direct_inventory"]) == 1
    row = snap["direct_inventory"][0]
    assert row["surface"] == "kalshi"
    assert row["leg_slug"] == "kxopenai-26"
    assert row["pricing_status"] == "priced_watchlist"
    assert row["pricing_status_label"] == "Live price available"
    assert row["direct_pair_role"] == "AI compute-demand leg"
    assert row["leg_role"] == "direct_prediction_event"
    assert row["mutually_exclusive"] is True
    assert row["is_thesis_mismatch"] is False
    direct_ref = snap["synthetic_instrument"]["outputs"]["direct_reference_legs"][0]
    assert direct_ref["surface"] == "kalshi"
    assert direct_ref["slug"] == "kxopenai-26"


def test_snapshot_labels_ibkr_quote_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("DIRECT_EVENT_INVENTORY_ENABLED", "1")
    monkeypatch.setenv("IBKR_DIRECT_EVENT_SYMBOLS", "RETXC")
    monkeypatch.setenv("POLYMARKET_DIRECT_EVENT_SLUGS", "")
    monkeypatch.setenv("PUBLIC_HEDGE_FETCH", "0")
    monkeypatch.setenv("IBKR_FORECAST_PROXY_QUOTE_FETCH", "0")
    (tmp_path / "ibkr_forecast_inventory.json").write_text(json.dumps({
        "events": [{
            "symbol": "RETXC",
            "slug": "retxc-ec",
            "title": "Texas Commercial Electricity Generation Sales Revenue",
            "pricing_status": "ibkr_quote_unavailable",
            "pricing_detail": "IBKR returned metadata but no bid/ask/last.",
        }],
    }))

    snap = state.snapshot()
    row = snap["direct_inventory"][0]

    assert row["pricing_status"] == "ibkr_quote_unavailable"
    assert row["pricing_status_label"] == "IBKR quote unavailable"
    gap = snap["synthetic_instrument"]["outputs"]["discovery_gaps"][0]
    assert gap["status_label"] == "IBKR quote unavailable"
    assert "ForecastTrader metadata" in gap["next_step"]


def test_snapshot_adds_external_proxy_price_for_ibkr_forecast_gap(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("DIRECT_EVENT_INVENTORY_ENABLED", "1")
    monkeypatch.setenv("IBKR_DIRECT_EVENT_SYMBOLS", "ITNVD")
    monkeypatch.setenv("POLYMARKET_DIRECT_EVENT_SLUGS", "")
    monkeypatch.setenv("PUBLIC_HEDGE_FETCH", "0")
    seen = {}

    def fake_public_quote(symbol, sources=None):
        seen["sources"] = sources
        return {
            "symbol": symbol,
            "price": 181.25,
            "currency": "USD",
            "exchange": "NMS",
            "source": "yahoo_finance_chart",
            "source_priority": "ibkr,yahoo",
        }

    monkeypatch.setattr(state, "_fetch_public_quote", fake_public_quote)
    (tmp_path / "ibkr_forecast_inventory.json").write_text(json.dumps({
        "events": [{
            "symbol": "ITNVD",
            "slug": "itnvd-ec",
            "title": "NVIDIA Inference vs. Training Revenue",
            "pricing_status": "ibkr_quote_unavailable",
        }],
    }))

    row = state.snapshot()["direct_inventory"][0]

    assert row["pricing_status"] == "ibkr_quote_unavailable"
    assert row["pricing_status_label"] == "IBKR quote unavailable; proxy price available"
    assert row["external_proxy_symbol"] == "NVDA"
    assert row["external_proxy_last_price"] == 181.25
    assert row["external_proxy_status"] == "priced_external_proxy"
    assert row["external_proxy_source"] == "yahoo_finance_chart"
    assert row["external_proxy_source_priority"] == "ibkr,yahoo"
    assert row["external_proxy_stale"] is False
    assert seen["sources"] == ["ibkr", "yahoo"]


def test_snapshot_marks_stale_ibkr_energy_history_proxy(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("DIRECT_EVENT_INVENTORY_ENABLED", "1")
    monkeypatch.setenv("IBKR_DIRECT_EVENT_SYMBOLS", "CRUDB")
    monkeypatch.setenv("POLYMARKET_DIRECT_EVENT_SLUGS", "")
    monkeypatch.setenv("PUBLIC_HEDGE_FETCH", "0")
    monkeypatch.setattr(state, "_fetch_public_quote", lambda symbol, sources=None: {
        "symbol": "BZ",
        "requested_symbol": symbol,
        "price": 102.58,
        "currency": "USD",
        "exchange": "NYMEX",
        "expiry": "20260529",
        "regular_market_time": "2026-05-21",
        "source": "ibkr_energy_history_csv",
        "source_priority": "ibkr,yahoo",
        "stale": True,
    })
    (tmp_path / "ibkr_forecast_inventory.json").write_text(json.dumps({
        "events": [{
            "symbol": "CRUDB",
            "slug": "crudb-ec",
            "title": "Brent Crude Oil Price",
            "pricing_status": "ibkr_quote_unavailable",
        }],
    }))

    row = state.snapshot()["direct_inventory"][0]

    assert row["external_proxy_source"] == "ibkr_energy_history_csv"
    assert row["external_proxy_last_price"] == 102.58
    assert row["external_proxy_stale"] is True
    assert row["external_proxy_regular_market_time"] == "2026-05-21"
    assert row["external_proxy_expiry"] == "20260529"


def test_snapshot_rolls_up_repeated_rejects_and_groups_package(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("DIRECT_EVENT_INVENTORY_ENABLED", "0")
    monkeypatch.setenv("PUBLIC_HEDGE_FETCH", "0")
    monkeypatch.setenv("PROXY_BASKET_BACKTEST_FETCH", "0")
    monkeypatch.setenv("IBKR_FORECAST_PROXY_QUOTE_FETCH", "0")
    _write_tsv(tmp_path / "judgements.tsv", [
        {
            "ts": "10",
            "arb_signal_id": "sig-1",
            "package_id": "pkg-1",
            "surface": "polymarket",
            "instrument": "polymarket:25009",
            "leg_title": "Will OpenAI launch a consumer hardware product?",
            "leg_slug": "will-openai-launch-a-consumer-hardware-product-by",
            "leg_description": "This market is about OpenAI consumer hardware.",
            "direction": "short",
            "sizing_usdc": "1",
            "est_pnl_per_dollar": "-0.85",
            "label": "REJECT",
            "reason_code": "premium_gate_fail",
        },
        {
            "ts": "20",
            "arb_signal_id": "sig-1",
            "package_id": "pkg-1",
            "surface": "polymarket",
            "instrument": "polymarket:25009",
            "leg_title": "Will OpenAI launch a consumer hardware product?",
            "leg_slug": "will-openai-launch-a-consumer-hardware-product-by",
            "leg_description": "This market is about OpenAI consumer hardware.",
            "direction": "short",
            "sizing_usdc": "1",
            "est_pnl_per_dollar": "-0.85",
            "label": "REJECT",
            "reason_code": "premium_gate_fail",
        },
    ])

    snap = state.snapshot()

    assert len(snap["verdicts"]) == 2
    assert len(snap["verdict_rollups"]) == 1
    assert snap["verdict_rollups"][0]["repeat_count"] == 2
    assert len(snap["packages"]) == 1
    assert snap["packages"][0]["label"] == "REJECT"
    assert snap["packages"][0]["direct_leg_count"] == 1
    assert snap["packages"][0]["repeat_count"] == 2
    assert snap["packages"][0]["direct_blocked_summary"] == "2 direct event scan rows blocked by premium_gate_fail"


def test_compact_snapshot_removes_duplicate_replay_blobs(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("DIRECT_EVENT_INVENTORY_ENABLED", "0")
    monkeypatch.setenv("PUBLIC_HEDGE_FETCH", "0")
    monkeypatch.setenv("PROXY_BASKET_BACKTEST_FETCH", "0")
    monkeypatch.setenv("IBKR_FORECAST_PROXY_QUOTE_FETCH", "0")

    snap = state.compact_snapshot(logs=tmp_path)

    outputs = snap["synthetic_instrument"]["outputs"]
    assert "spread_family_validation" not in outputs
    assert "proxy_basket_validation" not in outputs
    assert "recorded_history_replay" not in snap["spread_families"]
    assert "proxy_history_replay" not in snap["spread_families"]


def test_direct_inventory_degrades_when_one_surface_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(state, "_ibkr_inventory_rows", lambda logs=None: [{
        "surface": "ibkr_prediction",
        "instrument": "ibkr-prediction:RETXC",
        "leg_title": "Texas electricity generation revenue",
        "leg_description": "ERCOT power sales event contract.",
    }])
    monkeypatch.setattr(state, "_polymarket_inventory_rows", lambda: [{
        "surface": "polymarket",
        "instrument": "polymarket:ai-grid",
        "leg_title": "AI data center grid stress",
        "leg_description": "Direct power grid stress event.",
    }])
    monkeypatch.setattr(state, "_kalshi_inventory_rows", lambda: (_ for _ in ()).throw(RuntimeError("cache unavailable")))

    rows = state.direct_inventory_state(logs=tmp_path)

    assert {row["surface"] for row in rows} == {"ibkr_prediction", "polymarket"}


def test_snapshot_package_reason_prefers_execute_leg_over_rejected_direct_leg(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    _write_tsv(tmp_path / "judgements.tsv", [
        {
            "ts": "10",
            "arb_signal_id": "sig-1",
            "package_id": "pkg-1",
            "surface": "crypto",
            "instrument": "BTC/USD",
            "leg_title": "BTC/USD miner-margin proxy",
            "leg_role": "miner_margin_proxy",
            "leg_slug": "",
            "direction": "short",
            "sizing_usdc": "1",
            "est_pnl_per_dollar": "0.04",
            "label": "EXECUTE",
            "reason_code": "all_gates_passed",
        },
        {
            "ts": "20",
            "arb_signal_id": "sig-1",
            "package_id": "pkg-1",
            "surface": "polymarket",
            "instrument": "polymarket:25009",
            "leg_title": "Will OpenAI launch a consumer hardware product?",
            "leg_role": "direct_prediction_event",
            "leg_slug": "will-openai-launch-a-consumer-hardware-product-by",
            "direction": "short",
            "sizing_usdc": "1",
            "est_pnl_per_dollar": "-0.85",
            "label": "REJECT",
            "reason_code": "premium_gate_fail",
        },
    ])

    package = state.snapshot()["packages"][0]

    assert package["label"] == "EXECUTE"
    assert package["reason_code"] == "all_gates_passed"
    assert package["direct_leg_count"] == 1
    assert package["actionable_direct_leg_count"] == 0
    assert package["actionable_proxy_leg_count"] == 1
    assert package["direct_blocked_summary"] == "1 direct event scan row blocked by premium_gate_fail"
