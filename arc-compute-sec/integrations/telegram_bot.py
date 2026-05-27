"""Telegram bot and channel integration using the Bot API via requests."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from services import scan_requests
from services.state import log_dir, snapshot

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
SENT_NAME = "telegram_sent.jsonl"
DEFAULT_NOTIFY_MAX_PER_PASS = 3
DEFAULT_IBKR_REAUTH_REMINDER_HOURS = 4.0
CHANNEL_ABOUT_KEY = "channel-about:v2"
CHANNEL_FEEDBACK_UPDATE_KEY = "channel-feedback-update:v1"
CHANNEL_MARKET_DATA_UPDATE_KEY = "channel-market-data-update:v1"


def admin_ids() -> set[str]:
    raw = os.environ.get("TELEGRAM_ADMIN_USER_IDS", "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def is_admin(user_id: str | int | None) -> bool:
    admins = admin_ids()
    return bool(admins) and str(user_id or "") in admins


def bot_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required for Telegram integration")
    return token


def telegram_call(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        resp = requests.post(TELEGRAM_API.format(token=bot_token(), method=method), json=payload, timeout=20)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", "unknown")
        detail = str(getattr(response, "text", "") or "")[:300]
        raise RuntimeError(f"Telegram {method} HTTP {status}: {detail}") from None
    except requests.RequestException as exc:
        raise RuntimeError(f"Telegram {method} request failed: {exc.__class__.__name__}") from None
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data}")
    return data


def webhook_url() -> str:
    explicit = os.environ.get("TELEGRAM_WEBHOOK_URL", "").strip()
    if explicit:
        return explicit
    base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise RuntimeError("Set PUBLIC_BASE_URL or TELEGRAM_WEBHOOK_URL before configuring webhook mode")
    return base + "/api/telegram/webhook"


def set_webhook() -> dict[str, Any]:
    payload: dict[str, Any] = {"url": webhook_url(), "allowed_updates": ["message"]}
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if secret:
        payload["secret_token"] = secret
    return telegram_call("setWebhook", payload)


def delete_webhook() -> dict[str, Any]:
    return telegram_call("deleteWebhook", {"drop_pending_updates": False})


def bot_short_description() -> str:
    return "Compute/energy spread desk. Live-priced mock contract, buy/monitor/sell, Arc-gated."


def bot_description() -> str:
    return "\n".join([
        "Power by Botozen: live-priced compute/energy mock contract.",
        "/latest + Mini App show notional, Circle test USDC ask, live weights, and buy/monitor recommendation.",
        "IBKR/Polymarket are scouting inputs, not the funnel. IBKR paper-terminal proxy marks are labelled separately.",
        "Channel posts mock-contract updates, operator notes, and runtime errors. Raw REJECT/DEFER/premium_gate/watchlist noise is muted.",
        "No Arc action unless judge.classify() returns EXECUTE.",
    ])


def configure_bot_profile() -> dict[str, Any]:
    calls = [
        ("setMyShortDescription", {"short_description": bot_short_description()}),
        ("setMyDescription", {"description": bot_description()}),
        ("setMyCommands", {"commands": [
            {"command": "start", "description": "Open desk policy and commands"},
            {"command": "about", "description": "Explain the mock contract workflow"},
            {"command": "latest", "description": "Show mock contract and weights"},
            {"command": "status", "description": "Show worker and quote status"},
            {"command": "positions", "description": "Show audit-only Arc jobs"},
        ]}),
    ]
    base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if base:
        calls.append(("setChatMenuButton", {"menu_button": {
            "type": "web_app",
            "text": "Open Power",
            "web_app": {"url": base + "/tg"},
        }}))
    results = {}
    for method, payload in calls:
        results[method] = telegram_call(method, payload).get("ok", False)
    return results


def send_message(chat_id: str | int, text: str, *, reply_markup: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    telegram_call("sendMessage", payload)


def _latest_verdict(snap: dict[str, Any]) -> dict[str, Any] | None:
    verdicts = snap.get("verdicts") or []
    return verdicts[0] if verdicts else None


def _quote_source_label(source: Any) -> str:
    low = str(source or "").strip().lower()
    labels = {
        "public_quote": "public quote adapter",
        "ibkr_energy_history_csv": "IBKR paper CSV",
        "ibkr_tws_front_future": "IBKR paper TWS front future",
        "ibkr_tws_stock": "IBKR paper TWS stock",
        "ibkr_tws": "IBKR paper TWS",
        "yahoo_finance_chart": "Yahoo fallback",
        "alpaca_market_data": "Alpaca fallback",
    }
    return labels.get(low, str(source or "public quotes"))


def _quote_source_list(sources: Any, *, limit: int = 3) -> list[str]:
    out: list[str] = []
    for source in sources or []:
        label = _quote_source_label(source)
        if label and label not in out:
            out.append(label)
        if len(out) >= limit:
            break
    return out


def format_status(snap: dict[str, Any]) -> str:
    runtime = snap.get("runtime") or {}
    mode = snap.get("mode") or {}
    proposal = snap.get("synthetic_instrument") if isinstance(snap.get("synthetic_instrument"), dict) else {}
    construction = (((proposal.get("outputs") or {}).get("mock_hedge_construction")) or {}) if proposal else {}
    parts = [
        "Power by Botozen",
        f"state: {runtime.get('state', 'unknown')}",
        f"live_chain: {'enabled' if mode.get('live_chain_enabled') else 'disabled'}; no Arc before EXECUTE",
    ]
    if construction:
        label = construction.get("recommendation_label") or construction.get("recommended_action", "MONITOR_ONLY")
        parts.append(f"mock_contract: {label}")
        parts.append(
            f"notional: {float(construction.get('hedge_notional_usdc') or 0):.2f} USDC; "
            f"Circle ask: {float(construction.get('circle_testnet_usdc_request') or 0):.2f} test USDC"
        )
        if construction.get("entry_signal_score") not in ("", None):
            threshold = float(construction.get("entry_threshold_score") or 70)
            parts.append(f"entry score: {float(construction.get('entry_signal_score') or 0):.0f}/100 (threshold {threshold:.0f})")
        judge_verdict = construction.get("judge_verdict") if isinstance(construction.get("judge_verdict"), dict) else {}
        if judge_verdict.get("label"):
            parts.append(f"judge: {judge_verdict.get('label')}/{judge_verdict.get('reason_code', 'checked')}")
        sources = construction.get("quote_sources") or []
        if sources:
            parts.append("quotes: " + ", ".join(_quote_source_list(sources)))
    if runtime.get("last_success_at"):
        parts.append(f"last_success: {int(float(runtime['last_success_at']))}")
    if runtime.get("last_error"):
        parts.append(f"last_error: {runtime['last_error']}")
    return "\n".join(parts)


def format_latest(snap: dict[str, Any]) -> str:
    signal = (snap.get("signal") or {}).get("latest") or {}
    lines = [
        "Latest mock contract",
        f"signal: {signal.get('direction', 'none')} z={signal.get('z', '')}",
    ]
    proposal = snap.get("synthetic_instrument") if isinstance(snap.get("synthetic_instrument"), dict) else {}
    if proposal:
        lines.append(f"contract: {proposal.get('instrument_name', 'compute/energy mock contract')}")
        actions = (((proposal.get("outputs") or {}).get("agent_next_actions")) or [])
        hedges = (((proposal.get("outputs") or {}).get("priced_hedge_basket")) or [])
        search_plan = (((proposal.get("outputs") or {}).get("agent_search_plan")) or [])
        construction = (((proposal.get("outputs") or {}).get("mock_hedge_construction")) or {})
        if hedges:
            lines.append("live-priced basket: " + ", ".join(str(leg.get("slug") or leg.get("title")) for leg in hedges[:4]))
        if construction:
            lines.append(
                "funding: "
                f"{float(construction.get('hedge_notional_usdc') or 0):.2f} USDC notional, "
                f"Circle ask {float(construction.get('circle_testnet_usdc_request') or 0):.2f} test USDC"
            )
            if construction.get("recommended_action"):
                label = construction.get("recommendation_label") or construction.get("recommended_action")
                summary = construction.get("recommendation_summary") or "Arc stays gated by judge.classify()."
                lines.append(f"agent recommendation: {label} — {summary}")
                if construction.get("entry_signal_score") not in ("", None):
                    threshold = float(construction.get("entry_threshold_score") or 70)
                    lines.append(f"entry score: {float(construction.get('entry_signal_score') or 0):.0f}/100 (threshold {threshold:.0f})")
                judge_verdict = construction.get("judge_verdict") if isinstance(construction.get("judge_verdict"), dict) else {}
                if judge_verdict.get("label"):
                    lines.append(f"judge: {judge_verdict.get('label')}/{judge_verdict.get('reason_code', 'checked')}")
            sources = construction.get("quote_sources") or []
            if sources:
                lines.append("quote source: " + ", ".join(_quote_source_list(sources)))
            weighted = construction.get("weighted_legs") or []
            if weighted:
                lines.append("weights: " + ", ".join(
                    f"{leg.get('side')} {leg.get('slug')} {float(leg.get('weight') or 0):+.1%}"
                    for leg in weighted[:4]
                ))
        if search_plan:
            lines.append("agent scouting: " + ", ".join(
                f"{item.get('surface')}:{item.get('target')}"
                for item in search_plan[:3]
            ))
        if actions:
            lines.append(f"next: {actions[0]}")
    inventory = [row for row in (snap.get("direct_inventory") or []) if isinstance(row, dict)]
    if inventory:
        lines.append("research watchlist:")
        for row in inventory[:6]:
            title = _leg_name(row)
            surface = row.get("surface", "")
            role = row.get("direct_pair_role") or row.get("leg_role") or "direct leg"
            status = row.get("pricing_status_label") or row.get("pricing_status") or row.get("reason_code") or "watchlist"
            slug = row.get("leg_slug") or row.get("slug") or ""
            lines.append(f"- {surface} | {role} | {title} | {status}{f' | {slug}' if slug else ''}")
    return "\n".join(lines)


def format_about() -> str:
    return "\n".join([
        "Power by Botozen",
        "Live-priced compute/energy mock contract desk.",
        "",
        "How to read the feed:",
        "- /latest and the Mini App show the mock contract, live-priced weights, Circle test USDC ask, and buy/monitor recommendation.",
        "- Buy Contract freezes a local testnet entry ticket; Monitor tracks live leg marks; Sell Mock explains the worst drag if PnL turns red.",
        "- IBKR ForecastTrader, Polymarket, and future venues are agent scouting inputs until priced and thesis-matched.",
        "- The channel posts mock-contract updates, product updates, and runtime errors.",
        "- Raw REJECT, DEFER, premium_gate_fail, and watchlist-only rows stay out of the channel.",
        "- Commands work in the private bot chat only; channel commands are ignored.",
        "- BTC/ETH are labelled proxies inside the weighted basket, not the securitized object.",
        "- No Arc action can happen unless judge.classify() returns EXECUTE.",
        "",
        "Commands: /latest, /status, /positions, /about, /scan",
    ])


def format_positions(snap: dict[str, Any], limit: int = 5) -> str:
    positions = snap.get("positions") or []
    if not positions:
        return "No Arc positions recorded yet."
    lines = ["Recent Arc positions"]
    for pos in positions[:limit]:
        line = f"#{pos.get('job_id', '')} {pos.get('status', pos.get('stage', ''))} {pos.get('surface', '')}/{pos.get('instrument', '')}"
        if pos.get("arcscan_url"):
            line += f"\n{pos['arcscan_url']}"
        lines.append(line)
    return "\n\n".join(lines)


def mini_app_markup() -> dict[str, Any] | None:
    base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base:
        return None
    return {"inline_keyboard": [[{"text": "Open Dashboard", "web_app": {"url": base + "/"}}]]}


def handle_command(text: str, user_id: str | int | None, *, logs: Path | str | None = None) -> str:
    command = (text or "").strip().split(maxsplit=1)[0].lower()
    snap = snapshot(logs=logs)
    if command in {"/start", "/help"}:
        return format_about()
    if command == "/about":
        return format_about()
    if command == "/status":
        return format_status(snap)
    if command == "/latest":
        return format_latest(snap)
    if command == "/positions":
        return format_positions(snap)
    if command == "/scan":
        if not is_admin(user_id):
            return "Not authorized."
        request = scan_requests.enqueue_scan(source="telegram", live=False, logs=logs, user_id=user_id)
        return f"Dry-run scan queued: {request['request_id']}"
    if command == "/scan_live":
        if not is_admin(user_id):
            return "Not authorized."
        if os.environ.get("ENABLE_LIVE_CHAIN", "").strip() != "1":
            return "Live chain mode is disabled."
        request = scan_requests.enqueue_scan(source="telegram", live=True, settle=True, logs=logs, user_id=user_id)
        return f"Live scan queued: {request['request_id']}"
    return "Unknown command. Use /status, /latest, /positions, /about, or /scan."


def process_update(update: dict[str, Any], *, logs: Path | str | None = None) -> None:
    if update.get("channel_post"):
        return
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    text = message.get("text") or ""
    if not text.startswith("/"):
        return
    if "id" not in chat:
        return
    if chat.get("type") != "private":
        return
    reply = handle_command(text, sender.get("id"), logs=logs)
    send_message(chat["id"], reply, reply_markup=mini_app_markup() if text.startswith("/start") else None)


def sent_path(logs: Path | str | None = None) -> Path:
    return log_dir(logs) / SENT_NAME


def _sent_keys(*, logs: Path | str | None = None) -> set[str]:
    path = sent_path(logs)
    if not path.exists():
        return set()
    out: set[str] = set()
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and record.get("key"):
                out.add(str(record["key"]))
    return out


def _mark_sent(key: str, *, logs: Path | str | None = None) -> None:
    path = sent_path(logs)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": time.time(), "key": key}, sort_keys=True) + "\n")


def _notify_max_per_pass() -> int:
    raw = os.environ.get("TELEGRAM_NOTIFY_MAX_PER_PASS", "").strip()
    if not raw:
        return DEFAULT_NOTIFY_MAX_PER_PASS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_NOTIFY_MAX_PER_PASS


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _ibkr_reauth_chat_id() -> str:
    explicit = os.environ.get("IBKR_REAUTH_REMINDER_CHAT_ID", "").strip()
    if explicit:
        return explicit
    admins = sorted(admin_ids())
    return admins[0] if admins else ""


def _ibkr_reauth_interval_seconds() -> int:
    hours = _float_env("IBKR_REAUTH_REMINDER_INTERVAL_HOURS", DEFAULT_IBKR_REAUTH_REMINDER_HOURS)
    return max(900, int(hours * 3600))


def _ibkr_reauth_message() -> str:
    return "\n".join([
        "IBKR Client Portal reauth reminder",
        "1. Open https://localhost:5055",
        "2. Complete paper login/2FA until the browser says Client login succeeds.",
        "3. Run: npm run ibkr:cp-watchdog-once",
        "4. Keep it warm: npm run ibkr:cp-watchdog",
        "5. Refresh event-contract inventory:",
        "IBKR_CP_BASE_URL=https://localhost:5055/v1/api .venv/bin/python scripts/ibkr_forecast_smoke.py --priced --symbols RETXC,ITNVD,CRUDB,NGP,FF",
    ])


def notify_ibkr_reauth_reminder_once(*, logs: Path | str | None = None) -> int:
    if not _bool_env("IBKR_REAUTH_REMINDER_ENABLED", True):
        return 0
    chat_id = _ibkr_reauth_chat_id()
    if not chat_id:
        return 0
    interval = _ibkr_reauth_interval_seconds()
    bucket = int(time.time() // interval)
    key = f"ibkr-reauth-reminder:{bucket}"
    sent = _sent_keys(logs=logs)
    if key in sent:
        return 0
    send_message(chat_id, _ibkr_reauth_message())
    _mark_sent(key, logs=logs)
    return 1


def _leg_name(leg: dict[str, Any]) -> str:
    return str(
        leg.get("leg_title")
        or leg.get("title")
        or leg.get("instrument")
        or leg.get("slug")
        or "unknown leg"
    )


def _leg_line(leg: dict[str, Any]) -> str:
    surface = str(leg.get("surface") or "?")
    side = str(leg.get("side") or leg.get("direction") or "").strip()
    role = str(leg.get("direct_pair_role") or leg.get("leg_role") or "leg").replace("_", " ")
    parts = [surface]
    if side:
        parts.append(side)
    parts.append(_leg_name(leg))
    line = " - " + " | ".join(parts)
    slug = str(leg.get("leg_slug") or leg.get("slug") or "").strip()
    end_date = str(leg.get("leg_end_date") or leg.get("end_date") or "").strip()
    suffix = []
    if slug:
        suffix.append(slug)
    if end_date:
        suffix.append(f"resolves {end_date}")
    if suffix:
        line += f" ({'; '.join(suffix)})"
    status = str(leg.get("pricing_status") or "").strip()
    if status:
        return f"{line}\n   role: {role}; status: {status}"
    return f"{line}\n   role: {role}"


def _package_message(pkg: dict[str, Any]) -> str:
    package_id = str(pkg.get("package_id") or pkg.get("arb_signal_id") or pkg.get("id") or "package")
    label = str(pkg.get("label") or "PENDING")
    direction = str(pkg.get("direction") or "unknown")
    reason = str(pkg.get("reason_code") or "")
    legs = [
        leg for leg in (pkg.get("legs") or [])
        if isinstance(leg, dict) and str(leg.get("label") or "") != "REJECT"
    ]
    lines = [
        f"{label} spread package",
        f"id: {package_id}",
        f"direction: {direction}",
    ]
    if reason:
        lines.append(f"judge: {reason}")
    if legs:
        lines.append("legs:")
        lines.extend(_leg_line(leg) for leg in legs[:6])
        if len(legs) > 6:
            lines.append(f" - plus {len(legs) - 6} more legs")
    return "\n".join(lines)


def channel_about_message() -> str:
    return "\n".join([
        "How this channel works",
        "",
        "Power by Botozen now centers the live-priced compute/energy mock contract.",
        "",
        "This channel posts:",
        "- buy/monitor recommendations for the mock contract",
        "- product updates and operator notes",
        "- runtime errors that need operator attention",
        "",
        "This channel does not post repeated REJECT/DEFER rows, premium_gate_fail rows, raw judge tables, or watchlist-only slugs. Use /latest in the bot or the Mini App for research scouting details.",
        "",
        "The Mini App shows live-priced weights, Circle test USDC ask, local Buy Contract / Monitor Price / Sell Mock controls, and the leg that drags PnL red.",
        "",
        "No Arc action can happen unless judge.classify() returns EXECUTE.",
    ])


def channel_feedback_update_message() -> str:
    return "\n".join([
        "Product update: feedback shipped",
        "",
        "Thank you for the sharp feedback on the previous dashboard. You were right: raw Direct Event / Forecast Legs, repeated rejects, and isolated BTC rows did not explain the product.",
        "",
        "New in Power by Botozen:",
        "- live-priced mock contract is now the main surface",
        "- Buy Contract freezes a local testnet entry ticket",
        "- Monitor Price tracks refreshed leg marks",
        "- Sell Mock explains which leg makes the package unprofitable",
        "- weights now describe NVDA, VRT, ETN, CEG, NRG, BTC, and ETH in plain English",
        "- IBKR/Polymarket are now agent scouting inputs, not the main product funnel",
        "- channel and bot mute raw REJECT/DEFER/watchlist noise",
        "",
        "Open Mini App: https://power.botozen.com/tg",
        "Dashboard: https://power.botozen.com/dashboard",
    ])


def channel_market_data_update_message() -> str:
    return "\n".join([
        "Product update: IBKR paper-terminal marks shipped",
        "",
        "The scouting panel now separates three things that were easy to confuse:",
        "- IBKR ForecastTrader EC contract status",
        "- IBKR paper-terminal proxy marks for public futures/stocks",
        "- Yahoo/Alpaca fallback marks when IBKR market data is blocked",
        "",
        "If IBKR blocks live market data because another session owns the data bridge, Power can still show Brent and gas marks from the local Brent strategy IBKR history file. Those rows are labelled IBKR paper CSV / stale, not live EC prices.",
        "",
        "This keeps the story honest: the contract is the judged compute/energy package; IBKR and Polymarket are scouting surfaces until priced, thesis-matched, and approved by the judge.",
        "",
        "Mini App: https://power.botozen.com/tg",
        "Dashboard: https://power.botozen.com/dashboard",
    ])


def _mock_contract_message(snap: dict[str, Any]) -> tuple[str, str] | None:
    proposal = snap.get("synthetic_instrument") if isinstance(snap.get("synthetic_instrument"), dict) else {}
    if not proposal:
        return None
    construction = (((proposal.get("outputs") or {}).get("mock_hedge_construction")) or {})
    if not construction:
        return None
    action = str(construction.get("recommended_action") or "MONITOR_ONLY")
    score = float(construction.get("entry_signal_score") or construction.get("profitability_score") or 0)
    threshold = float(construction.get("entry_threshold_score") or 70)
    judge_verdict = construction.get("judge_verdict") if isinstance(construction.get("judge_verdict"), dict) else {}
    if action != "BUY_CONTRACT" or score < threshold or judge_verdict.get("label") != "EXECUTE":
        return None
    label = str(construction.get("recommendation_label") or action)
    proposal_id = str(proposal.get("proposal_id") or proposal.get("reference_package_id") or proposal.get("instrument_name") or "mock")
    circle = float(construction.get("circle_testnet_usdc_request") or 0)
    notional = float(construction.get("hedge_notional_usdc") or 0)
    weighted = construction.get("weighted_legs") or []
    weights = ", ".join(
        f"{leg.get('side')} {leg.get('slug')} {float(leg.get('weight') or 0):+.0%}"
        for leg in weighted[:5]
        if isinstance(leg, dict)
    )
    sources = ", ".join(_quote_source_list(construction.get("quote_sources") or [])) or "public quotes"
    key = f"mock-contract:{proposal_id}:{action}:{round(circle, 2)}"
    text = "\n".join([
        f"{label} mock compute/energy contract",
        f"instrument: {proposal.get('instrument_name', 'compute/energy hedge note')}",
        f"notional: {notional:.2f} USDC",
        f"Circle ask: {circle:.2f} test USDC",
        f"entry score: {score:.0f}/100 (threshold {threshold:.0f})",
        f"judge: {judge_verdict.get('label')}/{judge_verdict.get('reason_code', 'checked')}",
        f"weights: {weights or 'waiting for live prices'}",
        f"quotes: {sources}",
        f"reason: {construction.get('recommendation_summary') or 'Arc stays gated by judge.classify().'}",
        "Open Mini App to open, monitor, or close the local paper/testnet ticket.",
    ])
    return key, text


def channel_messages(snap: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    runtime = snap.get("runtime") or {}
    if runtime.get("last_error"):
        key_tail = runtime.get("last_failure_at") or runtime.get("updated_at") or runtime.get("last_error")
        out.append((
            f"runtime:error:{key_tail}",
            f"Runtime error: {runtime.get('last_error')}",
        ))

    mock_message = _mock_contract_message(snap)
    if mock_message:
        out.append(mock_message)
    return out


def notify_channel_about_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    if CHANNEL_ABOUT_KEY in sent:
        return 0
    send_message(channel_id, channel_about_message())
    _mark_sent(CHANNEL_ABOUT_KEY, logs=logs)
    return 1


def notify_channel_feedback_update_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    if CHANNEL_FEEDBACK_UPDATE_KEY in sent:
        return 0
    send_message(channel_id, channel_feedback_update_message())
    _mark_sent(CHANNEL_FEEDBACK_UPDATE_KEY, logs=logs)
    return 1


def notify_channel_market_data_update_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    if CHANNEL_MARKET_DATA_UPDATE_KEY in sent:
        return 0
    send_message(channel_id, channel_market_data_update_message())
    _mark_sent(CHANNEL_MARKET_DATA_UPDATE_KEY, logs=logs)
    return 1


def notify_channel_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    count = 0
    for key, text in channel_messages(snapshot(logs=logs)):
        if count >= _notify_max_per_pass():
            break
        if not key or key in sent:
            continue
        send_message(channel_id, text)
        _mark_sent(key, logs=logs)
        count += 1
    return count


def poll_once(offset: int | None = None, *, logs: Path | str | None = None) -> int | None:
    payload: dict[str, Any] = {"timeout": 20, "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = offset
    data = telegram_call("getUpdates", payload)
    next_offset = offset
    for update in data.get("result", []):
        process_update(update, logs=logs)
        next_offset = int(update["update_id"]) + 1
    notify_channel_once(logs=logs)
    notify_ibkr_reauth_reminder_once(logs=logs)
    return next_offset


def polling_loop() -> None:
    offset: int | None = None
    while True:
        try:
            offset = poll_once(offset)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"[telegram] {exc}")
            time.sleep(10)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Arc Compute Sec Telegram bot")
    parser.add_argument("--notify-once", action="store_true", help="Send one deduped channel notification pass")
    parser.add_argument("--poll-once", action="store_true", help="Run one getUpdates poll")
    parser.add_argument("--set-webhook", action="store_true", help="Configure Telegram webhook from PUBLIC_BASE_URL")
    parser.add_argument("--delete-webhook", action="store_true", help="Delete Telegram webhook")
    parser.add_argument("--configure-bot-profile", action="store_true", help="Configure bot description, commands, and menu")
    parser.add_argument("--post-channel-about", action="store_true", help="Post the deduped channel explainer")
    parser.add_argument("--post-feedback-update", action="store_true", help="Post the deduped feedback/new-features channel update")
    parser.add_argument("--post-market-data-update", action="store_true", help="Post the deduped IBKR/proxy market-data update")
    args = parser.parse_args(argv)
    if args.set_webhook:
        print(json.dumps(set_webhook(), sort_keys=True))
        return 0
    if args.delete_webhook:
        print(json.dumps(delete_webhook(), sort_keys=True))
        return 0
    if args.configure_bot_profile:
        print(json.dumps(configure_bot_profile(), sort_keys=True))
        return 0
    if args.post_channel_about:
        print(notify_channel_about_once())
        return 0
    if args.post_feedback_update:
        print(notify_channel_feedback_update_once())
        return 0
    if args.post_market_data_update:
        print(notify_channel_market_data_update_once())
        return 0
    if args.notify_once:
        print(notify_channel_once() + notify_ibkr_reauth_reminder_once())
        return 0
    if args.poll_once:
        poll_once()
        return 0
    polling_loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
