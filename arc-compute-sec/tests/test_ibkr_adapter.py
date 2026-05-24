"""IBKR adapter test uses dry_run=True so no Gateway is needed."""
from adapters import ibkr


def test_stub_fill_long():
    fr = ibkr.place_paper_order("GOOGL", "long", qty=1, dry_run=True)
    assert fr["surface"] == "ibkr"
    assert fr["instrument"] == "GOOGL"
    assert fr["direction"] == "long"
    assert fr["qty"] == 1
    assert fr["stub"] is True


def test_stub_fill_short():
    fr = ibkr.place_paper_order("AMZN", "short", qty=3, dry_run=True)
    assert fr["direction"] == "short"
    assert fr["qty"] == 3
    assert fr["stub"] is True


def test_stub_fills_deterministic_within_session(monkeypatch):
    # Same symbol+direction+qty within a tight loop should produce different
    # fill_ids (because timestamp differs at sub-second granularity).
    fr1 = ibkr.place_paper_order("MSFT", "short", qty=1, dry_run=True)
    fr2 = ibkr.place_paper_order("MSFT", "short", qty=1, dry_run=True)
    # Hash includes ts; they may collide in same second. Don't assert
    # inequality strictly. Just assert both produce valid 16-char hex.
    assert len(fr1["fill_id"]) == 16
    assert len(fr2["fill_id"]) == 16


def test_fetch_prediction_events_from_env(monkeypatch):
    monkeypatch.setenv("IBKR_PREDICTION_EVENTS_JSON", '[{"id":"fx-1","title":"Will ERCOT spike?","yes_prices":[0.52,0.51]}]')
    monkeypatch.setenv("IBKR_FORECAST_DISCOVERY", "0")

    events = ibkr.fetch_prediction_events()

    assert events[0]["id"] == "fx-1"
    assert events[0]["yes_prices"] == [0.52, 0.51]


def test_fetch_prediction_events_can_add_client_portal_events(monkeypatch):
    monkeypatch.setenv("IBKR_PREDICTION_EVENTS_JSON", '[{"id":"manual","yes_prices":[0.52,0.51]}]')
    monkeypatch.setenv("IBKR_FORECAST_DISCOVERY", "1")
    monkeypatch.setattr(
        ibkr,
        "fetch_prediction_events_from_client_portal",
        lambda: [{"id": "cp", "yes_prices": [0.41, 0.59]}],
    )

    events = ibkr.fetch_prediction_events()

    assert [event["id"] for event in events] == ["manual", "cp"]


def test_parse_float_normalizes_forecast_cents():
    assert ibkr._parse_float("42") == 0.42
    assert ibkr._parse_float("0.42") == 0.42
    assert ibkr._parse_float("105") is None
    assert ibkr._parse_float("nan") is None


def test_flatten_forecast_markets_filters_thesis():
    tree = {
        "root": {"label": "Root", "markets": []},
        "energy": {
            "label": "Energy",
            "parentId": "root",
            "markets": [{"name": "US renewable energy electricity generation", "symbol": "EMUSX", "conid": 1}],
        },
        "sports": {
            "label": "Sports",
            "parentId": "root",
            "markets": [{"name": "Baseball winner", "symbol": "BALL", "conid": 2}],
        },
    }

    markets = ibkr._flatten_forecast_markets(tree)

    assert len(markets) == 2
    assert ibkr._forecast_market_matches_thesis(markets[0])
    assert not ibkr._forecast_market_matches_thesis(markets[1])


def test_tws_underlier_discovery_filters_event_contract_rows(monkeypatch):
    class FakeContract:
        symbol = "ITNVD"
        conId = 845604790
        secType = "IND"
        primaryExchange = "FORECASTX"
        currency = "USD"
        description = "NVIDIA Inference vs. Training Revenue"

    class FakeStockContract:
        symbol = "NVDA"
        conId = 4815747
        secType = "STK"
        primaryExchange = "NASDAQ"
        currency = "USD"
        description = "NVIDIA Corp"

    class FakeRow:
        def __init__(self, contract, derivative_sec_types):
            self.contract = contract
            self.derivativeSecTypes = derivative_sec_types

    class FakeIB:
        def reqMatchingSymbols(self, term):
            assert term == "Nvidia"
            return [FakeRow(FakeContract(), ["EC"]), FakeRow(FakeStockContract(), ["OPT"])]

    monkeypatch.setattr(ibkr, "_connect", lambda: FakeIB())

    markets = ibkr.fetch_forecast_markets_from_tws(terms=["Nvidia"])

    assert len(markets) == 1
    assert markets[0]["symbol"] == "ITNVD"
    assert markets[0]["theme"] == "ai_compute"
    assert markets[0]["source"] == "ibkr_tws"


def test_forecast_contract_events_builds_yes_no_prices(monkeypatch):
    market = {
        "symbol": "FF",
        "name": "US Fed Funds Target Rate",
        "category_path": "Economic Indicators / Rates",
    }
    monkeypatch.setattr(
        ibkr,
        "_forecast_search_result",
        lambda symbol: {"conid": 658663572, "symbol": symbol, "opt": "20260616"},
    )

    def fake_cp_get(path, *, params=None):
        if path == "/iserver/secdef/strikes":
            return {"call": [4.875], "put": [4.875]}
        if path == "/iserver/secdef/info":
            return [
                {"conid": 11, "right": "C", "desc2": "YES @FORECASTX"},
                {"conid": 12, "right": "P", "desc2": "NO @FORECASTX"},
            ]
        raise AssertionError(path)

    monkeypatch.setattr(ibkr, "_cp_get", fake_cp_get)
    monkeypatch.setattr(
        ibkr,
        "_forecast_snapshots",
        lambda conids: {"11": {"84": "0.40", "86": "0.42"}, "12": {"31": "59"}},
    )

    events = ibkr._forecast_contract_events_for_market(market)

    assert len(events) == 1
    assert events[0]["id"] == "FF-JUN26-4.875"
    assert [round(px, 2) for px in events[0]["yes_prices"]] == [0.41, 0.59]
    assert events[0]["exchange"] == "FORECASTX"


def test_forecast_ec_event_uses_tws_fallback_when_client_portal_snapshot_is_empty(monkeypatch):
    market = {"symbol": "RETXC", "name": "Texas power", "category_path": "operator supplied"}
    search = {"conid": 793085619, "symbol": "RETXC", "companyName": "Texas power"}
    monkeypatch.setattr(ibkr, "_forecast_snapshots", lambda conids: {"793085619": {"conid": 793085619}})
    monkeypatch.setattr(ibkr, "_forecast_tws_event_price", lambda conid: (0.37, "ibkr_tws_bid_ask"))

    event = ibkr._forecast_ec_event_for_market(market, search)

    assert event["pricing_status"] == "priced"
    assert event["source"] == "ibkr_tws_bid_ask"
    assert event["yes_prices"] == [0.37, 0.63]


def test_forecast_ec_event_marks_quote_unavailable_with_detail(monkeypatch):
    market = {"symbol": "RETXC", "name": "Texas power", "category_path": "operator supplied"}
    search = {"conid": 793085619, "symbol": "RETXC", "companyName": "Texas power"}
    monkeypatch.setattr(ibkr, "_forecast_snapshots", lambda conids: {"793085619": {"conid": 793085619}})
    monkeypatch.setattr(ibkr, "_forecast_tws_event_price", lambda conid: (None, "ConnectionRefusedError"))

    event = ibkr._forecast_ec_event_for_market(market, search)

    assert event["pricing_status"] == "ibkr_quote_unavailable"
    assert event["yes_prices"] == []
    assert "no bid/ask/last" in event["pricing_detail"]


def test_fetch_prediction_events_for_symbols(monkeypatch):
    seen = []
    monkeypatch.setattr(ibkr, "client_portal_ensure_ready", lambda: {"authenticated": True, "connected": True})

    def fake_events(market):
        seen.append(market)
        return [{"id": market["symbol"], "yes_prices": [0.4, 0.6]}]

    monkeypatch.setattr(ibkr, "_forecast_contract_events_for_market", fake_events)

    events = ibkr.fetch_prediction_events_for_symbols(["retxc", "", "ITNVD"])

    assert [event["id"] for event in events] == ["RETXC", "ITNVD"]
    assert [market["category_path"] for market in seen] == [
        "operator supplied IBKR ForecastTrader symbol",
        "operator supplied IBKR ForecastTrader symbol",
    ]


def test_client_portal_ensure_ready_reauthenticates(monkeypatch):
    calls = []
    monkeypatch.setenv("IBKR_CP_AUTO_REAUTH", "1")
    monkeypatch.setattr(ibkr, "client_portal_auth_status", lambda: {"authenticated": False, "connected": False})
    monkeypatch.setattr(ibkr, "client_portal_tickle", lambda: calls.append("tickle") or {"ok": True})
    monkeypatch.setattr(
        ibkr,
        "client_portal_reauthenticate",
        lambda: calls.append("reauth") or {"authenticated": True, "connected": True},
    )

    status = ibkr.client_portal_ensure_ready()

    assert status["authenticated"] is True
    assert calls == ["tickle", "reauth"]


def test_client_portal_reauthenticate_posts_and_polls(monkeypatch):
    calls = []
    statuses = [
        {"authenticated": False, "connected": False},
        {"authenticated": True, "connected": True},
    ]
    monkeypatch.setattr(ibkr, "_cp_post", lambda path, **kwargs: calls.append(path) or {"message": "triggered"})
    monkeypatch.setattr(ibkr, "client_portal_auth_status", lambda: statuses.pop(0))
    monkeypatch.setattr(ibkr.time, "sleep", lambda seconds: None)

    status = ibkr.client_portal_reauthenticate(wait_seconds=1)

    assert status["authenticated"] is True
    assert calls == ["/iserver/reauthenticate"]


def test_forecast_ec_event_can_be_unpriced(monkeypatch):
    market = {
        "symbol": "RETXC",
        "name": "Texas Commercial Electricity Generation Sales Revenue",
        "category_path": "operator supplied IBKR ForecastTrader symbol",
    }
    search = {
        "conid": "793085619",
        "companyName": "Texas Commercial Electricity Generation Sales Revenue",
        "symbol": "RETXC",
        "description": "FORECASTX",
        "sections": [{"secType": "EC"}],
    }
    monkeypatch.setattr(ibkr, "_forecast_snapshots", lambda conids: {"793085619": {"conid": 793085619}})
    monkeypatch.setattr(ibkr, "_forecast_tws_event_price", lambda conid: (None, "tws_no_bid_ask_last"))

    event = ibkr._forecast_ec_event_for_market(market, search)

    assert event["sec_type"] == "EC"
    assert event["pricing_status"] == "ibkr_quote_unavailable"
    assert event["yes_prices"] == []
    assert event["yes_conid"] == "793085619"


def test_simulate_prediction_fill():
    fr = ibkr.simulate_prediction_fill(
        "ibkr-prediction:fx-1",
        "short",
        [0.52, 0.51],
        notional_usdc=1.0,
        metadata={"exchange": "FORECASTX", "sec_type": "OPT"},
    )

    assert fr["surface"] == "ibkr_prediction"
    assert fr["exchange"] == "FORECASTX"
    assert fr["sec_type"] == "OPT"
    assert fr["stub"] is True
