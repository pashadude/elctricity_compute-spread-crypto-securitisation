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
                    "recommendation_label": "Hedge now",
                    "recommendation_summary": "Hedge now, then monitor leg PnL.",
                    "entry_signal_score": 83.0,
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
    assert "Hedge now mock compute/energy contract" in sent[0][1]
    assert "edge: 83/100" in sent[0][1]
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
                    "recommendation_label": "Hedge now",
                    "recommendation_summary": "Hedge now, then monitor leg PnL.",
                    "entry_signal_score": 83.0,
                    "judge_verdict": {"label": "EXECUTE", "reason_code": "all_gates_passed", "confidence": 0.95},
                    "weighted_legs": [
                        {"slug": "NVDA", "side": "short", "weight": -0.2},
                        {"slug": "CEG", "side": "long", "weight": 0.2},
                    ],
                },
                "discovery_gaps": [{"slug": "retxc-ec", "status_label": "Needs live venue price"}],
                "agent_search_plan": [{"surface": "opoint_nebius", "target": "news-grounded spread drivers"}],
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
    })

    assert "Latest mock contract" in text
    assert "research watchlist:" in text
    assert "contract: ERCOT power compute receivable hedge note abc123" in text
    assert "live-priced basket: NVDA, CEG" in text
    assert "funding: 1500.00 USDC notional, Circle ask 1630.00 test USDC" in text
    assert "agent recommendation: Hedge now — Hedge now, then monitor leg PnL." in text
    assert "edge: 83/100" in text
    assert "judge: EXECUTE/all_gates_passed" in text
    assert "weights: short NVDA -20.0%, long CEG +20.0%" in text
    assert "pricing gaps:" not in text
    assert "agent scouting: opoint_nebius:news-grounded spread drivers" in text
    assert "next: Find one direct regional energy/grid-stress leg." in text
    assert "Texas Commercial Electricity Generation Sales Revenue" in text
    assert "Needs live venue price" in text
    assert "unpriced_snapshot" not in text


def test_about_explains_watchlist_and_channel_policy(tmp_path):
    text = telegram_bot.handle_command("/start", 7, logs=tmp_path)

    assert "/latest and the Mini App show the mock contract" in text
    assert "Buy Contract freezes a local testnet entry ticket" in text
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
                    "recommendation_label": "Hedge now",
                    "recommendation_summary": "Hedge now, then monitor leg PnL.",
                    "entry_signal_score": 83.0,
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
    assert "Hedge now mock compute/energy contract" in text
    assert "Circle ask: 1630.00 test USDC" in text
    assert "edge: 83/100" in text
    assert "judge: EXECUTE/all_gates_passed" in text
    assert "weights: short NVDA -20%, long CEG +20%" in text


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
