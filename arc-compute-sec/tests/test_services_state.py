import csv
import json
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
    (tmp_path / "runtime_status.json").write_text(json.dumps({
        "state": "idle",
        "last_error": "",
        "desk_wallet_id": "must-not-leak",
    }))

    assert state.snapshot()["runtime"] == {"state": "idle", "last_error": ""}


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
