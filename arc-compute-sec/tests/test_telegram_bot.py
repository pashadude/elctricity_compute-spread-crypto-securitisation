from integrations import telegram_bot
from services import scan_requests


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
        "verdicts": [{
            "action_payload_hash": "abc",
            "label": "EXECUTE",
            "surface": "crypto",
            "instrument": "BTC/USD",
            "reason_code": "all_gates_passed",
        }],
        "positions": [],
    })

    assert telegram_bot.notify_channel_once(logs=tmp_path) == 1
    assert telegram_bot.notify_channel_once(logs=tmp_path) == 0
    assert len(sent) == 1


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
        "direct_inventory": [{
            "surface": "ibkr_prediction",
            "leg_title": "Texas Commercial Electricity Generation Sales Revenue",
            "leg_slug": "retxc-ec",
            "direct_pair_role": "energy/grid-stress leg",
            "pricing_status": "unpriced_snapshot",
        }],
    })

    assert "direct watchlist:" in text
    assert "Texas Commercial Electricity Generation Sales Revenue" in text
    assert "unpriced_snapshot" in text


def test_channel_messages_group_execute_package():
    messages = telegram_bot.channel_messages({
        "runtime": {},
        "packages": [{
            "id": "pkg1",
            "package_id": "pkg1",
            "label": "EXECUTE",
            "direction": "electricity_expensive",
            "reason_code": "all_gates_passed",
            "legs": [
                {
                    "action_payload_hash": "abc",
                    "label": "EXECUTE",
                    "surface": "polymarket",
                    "side": "long",
                    "leg_role": "direct_prediction_event",
                    "leg_title": "Texas power price above threshold?",
                    "leg_slug": "texas-power-price-above-threshold",
                    "leg_end_date": "2026-06-30",
                },
                {
                    "action_payload_hash": "def",
                    "label": "EXECUTE",
                    "surface": "ibkr",
                    "side": "short",
                    "leg_role": "liquid_equity_proxy",
                    "instrument": "GOOGL",
                },
            ],
        }],
        "verdicts": [{
            "action_payload_hash": "abc",
            "label": "EXECUTE",
            "surface": "polymarket",
            "instrument": "texas-power-price-above-threshold",
            "reason_code": "all_gates_passed",
        }],
        "positions": [],
    })

    assert len(messages) == 1
    key, text = messages[0]
    assert key == "package:pkg1:EXECUTE"
    assert "EXECUTE spread package" in text
    assert "Texas power price above threshold?" in text
    assert "GOOGL" in text


def test_channel_package_message_excludes_reject_legs():
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

    assert len(messages) == 1
    assert "BTC/USD" in messages[0][1]
    assert "Rejected direct event" not in messages[0][1]


def test_channel_messages_include_runtime_errors():
    messages = telegram_bot.channel_messages({
        "runtime": {"last_error": "feed timeout", "last_failure_at": 123},
        "signal": {"latest": {}},
        "verdicts": [],
        "positions": [],
    })

    assert messages == [("runtime:error:123", "Runtime error: feed timeout")]


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
        "allowed_updates": ["message", "channel_post"],
        "secret_token": "abc",
    })]
