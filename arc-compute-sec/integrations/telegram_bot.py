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
CHANNEL_ABOUT_KEY = "channel-about:v1"


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
    return "Compute/energy spread desk. Watchlist in /latest; channel posts only EXECUTE packages/jobs."


def bot_description() -> str:
    return "\n".join([
        "Power by Botozen wraps judged compute/energy spread packages on Arc.",
        "",
        "/latest and the Mini App show direct IBKR ForecastTrader and Polymarket watchlist slugs.",
        "The public channel posts only EXECUTE packages, Arc job updates, and runtime errors.",
        "Commands are private-chat only; the channel ignores inbound /status or /scan commands.",
        "REJECT, DEFER, and premium_gate_fail rows are intentionally muted.",
        "",
        "No Arc action can happen unless judge.classify() returns EXECUTE.",
    ])


def configure_bot_profile() -> dict[str, Any]:
    calls = [
        ("setMyShortDescription", {"short_description": bot_short_description()}),
        ("setMyDescription", {"description": bot_description()}),
        ("setMyCommands", {"commands": [
            {"command": "start", "description": "Open desk policy and commands"},
            {"command": "about", "description": "Explain watchlist vs channel posts"},
            {"command": "latest", "description": "Show signal and watchlist slugs"},
            {"command": "status", "description": "Show worker and judge status"},
            {"command": "positions", "description": "Show recent Arc jobs"},
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


def format_status(snap: dict[str, Any]) -> str:
    runtime = snap.get("runtime") or {}
    mode = snap.get("mode") or {}
    verdict = _latest_verdict(snap)
    parts = [
        "Arc Compute Sec",
        f"state: {runtime.get('state', 'unknown')}",
        f"live_chain: {'enabled' if mode.get('live_chain_enabled') else 'disabled'}",
    ]
    if runtime.get("last_success_at"):
        parts.append(f"last_success: {int(float(runtime['last_success_at']))}")
    if runtime.get("last_error"):
        parts.append(f"last_error: {runtime['last_error']}")
    if verdict:
        parts.append(
            f"latest: {verdict.get('label', '?')} {verdict.get('surface', '')}/{verdict.get('instrument', '')}"
        )
    return "\n".join(parts)


def format_latest(snap: dict[str, Any]) -> str:
    signal = (snap.get("signal") or {}).get("latest") or {}
    verdict = _latest_verdict(snap) or {}
    position = (snap.get("positions") or [{}])[0] if snap.get("positions") else {}
    lines = [
        "Latest desk state",
        f"signal: {signal.get('direction', 'none')} z={signal.get('z', '')}",
        f"verdict: {verdict.get('label', 'none')} {verdict.get('reason_code', '')}",
        f"position: #{position.get('job_id', '')} {position.get('surface', '')}/{position.get('instrument', '')}".strip(),
    ]
    proposal = snap.get("synthetic_instrument") if isinstance(snap.get("synthetic_instrument"), dict) else {}
    if proposal:
        lines.append(
            f"proposal: {proposal.get('instrument_name', 'synthetic spread note')} "
            f"({proposal.get('collateral_status', 'not_asset_backed_v0')})"
        )
        actions = (((proposal.get("outputs") or {}).get("agent_next_actions")) or [])
        hedges = (((proposal.get("outputs") or {}).get("priced_hedge_basket")) or [])
        gaps = (((proposal.get("outputs") or {}).get("discovery_gaps")) or [])
        if hedges:
            lines.append("priced hedges: " + ", ".join(str(leg.get("slug") or leg.get("title")) for leg in hedges[:4]))
        if gaps:
            lines.append("unpriced discovery: " + ", ".join(str(leg.get("slug") or leg.get("title")) for leg in gaps[:4]))
        if actions:
            lines.append(f"next: {actions[0]}")
    inventory = [row for row in (snap.get("direct_inventory") or []) if isinstance(row, dict)]
    if inventory:
        lines.append("direct watchlist:")
        for row in inventory[:6]:
            title = _leg_name(row)
            surface = row.get("surface", "")
            role = row.get("direct_pair_role") or row.get("leg_role") or "direct leg"
            status = row.get("pricing_status") or row.get("reason_code") or "watchlist"
            slug = row.get("leg_slug") or row.get("slug") or ""
            lines.append(f"- {surface} | {role} | {title} | {status}{f' | {slug}' if slug else ''}")
    return "\n".join(lines)


def format_about() -> str:
    return "\n".join([
        "Power by Botozen",
        "Arc-wrapped compute/energy spread desk.",
        "",
        "How to read the feed:",
        "- /latest and the Mini App show IBKR ForecastTrader and Polymarket slugs as direct watchlist inventory.",
        "- Watchlist rows are research surfaces, not public channel alerts.",
        "- The agent proposes a synthetic instrument from the latest spread, legs, collateral status, and next actions.",
        "- The channel posts only EXECUTE spread packages, Arc job updates, and runtime errors.",
        "- REJECT, DEFER, and premium_gate_fail rows stay out of the channel.",
        "- Commands work in the private bot chat only; channel commands are ignored.",
        "- BTC/ETH are miner-margin proxies; the securitized object is the judged spread package.",
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
        "Power by Botozen tracks electricity stress against GPU compute demand, then packages only judge-approved legs for Arc settlement.",
        "",
        "This channel posts:",
        "- EXECUTE spread packages with grouped IBKR/Polymarket/crypto legs",
        "- Arc ERC-8183 job updates",
        "- runtime errors that need operator attention",
        "",
        "This channel does not post repeated REJECT/DEFER rows or watchlist-only slugs. Use /latest in the bot or the Mini App for the live watchlist.",
        "",
        "BTC/ETH are labelled miner-margin proxies. The securitized object is the judged spread package, and no Arc action can happen unless judge.classify() returns EXECUTE.",
    ])


def channel_messages(snap: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    runtime = snap.get("runtime") or {}
    if runtime.get("last_error"):
        key_tail = runtime.get("last_failure_at") or runtime.get("updated_at") or runtime.get("last_error")
        out.append((
            f"runtime:error:{key_tail}",
            f"Runtime error: {runtime.get('last_error')}",
        ))

    packages = [pkg for pkg in (snap.get("packages") or []) if isinstance(pkg, dict)]
    for pkg in packages:
        label = str(pkg.get("label") or "")
        if label != "EXECUTE":
            continue
        key = f"package:{pkg.get('package_id') or pkg.get('id') or pkg.get('arb_signal_id')}:{label}"
        out.append((key, _package_message(pkg)))

    packaged_leg_hashes = {
        str(leg.get("action_payload_hash") or "")
        for pkg in packages
        for leg in (pkg.get("legs") or [])
        if isinstance(leg, dict) and leg.get("action_payload_hash")
    }
    for verdict in snap.get("verdicts") or []:
        label = verdict.get("label")
        if label != "EXECUTE":
            continue
        if str(verdict.get("action_payload_hash") or "") in packaged_leg_hashes:
            continue
        key = f"verdict:{verdict.get('action_payload_hash', '')}:{label}"
        text = f"{label} {verdict.get('surface', '')}/{verdict.get('instrument', '')}: {verdict.get('reason_code', '')}"
        out.append((key, text))
    for pos in snap.get("positions") or []:
        if pos.get("job_id"):
            text = f"Arc job #{pos.get('job_id')} {pos.get('status', pos.get('stage', ''))} {pos.get('surface', '')}/{pos.get('instrument', '')}"
            if pos.get("arcscan_url"):
                text += f"\n{pos['arcscan_url']}"
            out.append((f"position:{pos.get('job_id')}:{pos.get('stage', '')}", text))
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
