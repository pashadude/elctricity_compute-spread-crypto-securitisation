"""Telegram bot and channel integration using the Bot API via requests."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
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
CHANNEL_INSTRUMENT_MENU_UPDATE_KEY = "channel-instrument-menu-update:v1"
CHANNEL_PROFITABILITY_UPDATE_KEY = "channel-profitability-update:v1"
CHANNEL_MINIAPP_UPDATE_KEY = "channel-miniapp-update:v3"
CHANNEL_MINIAPP_RELEASE_PREFIX = "channel-miniapp-release:v1"
CHANNEL_SIGNAL_DISCIPLINE_UPDATE_KEY = "channel-signal-discipline-update:v1"
CHANNEL_ORACLE_DISCIPLINE_UPDATE_KEY = "channel-oracle-discipline-update:v1"
CHANNEL_BASIS_SPREAD_UPDATE_KEY = "channel-basis-spread-update:v1"
CHANNEL_INDEX_TRADEABILITY_UPDATE_KEY = "channel-index-tradeability-update:v1"
CHANNEL_CAMPAIGN_PREFIX = "channel-campaign:v1"
CHANNEL_SCREENSHOT_FILES = {
    CHANNEL_ABOUT_KEY: "miniapp-home.png",
    CHANNEL_FEEDBACK_UPDATE_KEY: "miniapp-home.png",
    CHANNEL_MARKET_DATA_UPDATE_KEY: "venue-copy.png",
    CHANNEL_INSTRUMENT_MENU_UPDATE_KEY: "indexes-spreads.png",
    CHANNEL_PROFITABILITY_UPDATE_KEY: "profitability.png",
    CHANNEL_MINIAPP_UPDATE_KEY: "miniapp-updates.png",
    CHANNEL_SIGNAL_DISCIPLINE_UPDATE_KEY: "profitability.png",
    CHANNEL_ORACLE_DISCIPLINE_UPDATE_KEY: "venue-copy.png",
    CHANNEL_BASIS_SPREAD_UPDATE_KEY: "indexes-spreads.png",
    CHANNEL_INDEX_TRADEABILITY_UPDATE_KEY: "indexes-spreads.png",
    f"{CHANNEL_MINIAPP_RELEASE_PREFIX}:home": "miniapp-home.png",
    f"{CHANNEL_MINIAPP_RELEASE_PREFIX}:contract": "miniapp-contract.png",
    f"{CHANNEL_MINIAPP_RELEASE_PREFIX}:portfolio": "miniapp-portfolio.png",
    f"{CHANNEL_MINIAPP_RELEASE_PREFIX}:profitability": "profitability.png",
    f"{CHANNEL_MINIAPP_RELEASE_PREFIX}:scouting": "venue-copy.png",
    f"{CHANNEL_CAMPAIGN_PREFIX}:indexes-spreads": "indexes-spreads.png",
    f"{CHANNEL_CAMPAIGN_PREFIX}:profitability": "profitability.png",
    f"{CHANNEL_CAMPAIGN_PREFIX}:venue-copy": "venue-copy.png",
    f"{CHANNEL_CAMPAIGN_PREFIX}:arc-collateral": "miniapp-portfolio.png",
}


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
        "Polymarket/Kalshi/IBKR are scouting inputs, not the funnel. IBKR paper-terminal proxy marks are labelled separately.",
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


def _caption_text(text: str, *, max_len: int = 1000) -> str:
    clean = str(text or "").strip()
    if len(clean) <= max_len:
        return clean
    clipped = clean[:max_len - 44].rstrip()
    if "\n" in clipped:
        clipped = clipped.rsplit("\n", 1)[0].rstrip()
    return clipped + "\n\nOpen the dashboard for the full detail."


def screenshot_dir(*, logs: Path | str | None = None) -> Path:
    configured = os.environ.get("TELEGRAM_SCREENSHOT_DIR", "").strip()
    if configured:
        return Path(configured)
    return log_dir(logs) / "telegram_screenshots"


def screenshot_path_for_key(key: str, *, logs: Path | str | None = None) -> Path | None:
    filename = CHANNEL_SCREENSHOT_FILES.get(str(key or ""))
    if not filename:
        return None
    path = screenshot_dir(logs=logs) / filename
    return path if path.exists() and path.is_file() else None


def send_photo(chat_id: str | int, photo_path: Path | str, caption: str, *, reply_markup: dict[str, Any] | None = None) -> None:
    path = Path(photo_path)
    if not path.exists() or not path.is_file():
        send_message(chat_id, caption, reply_markup=reply_markup)
        return
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "caption": _caption_text(caption),
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    ctype = mimetypes.guess_type(str(path))[0] or "image/png"
    try:
        with path.open("rb") as fh:
            resp = requests.post(
                TELEGRAM_API.format(token=bot_token(), method="sendPhoto"),
                data=payload,
                files={"photo": (path.name, fh, ctype)},
                timeout=30,
            )
        resp.raise_for_status()
    except requests.HTTPError as exc:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", "unknown")
        detail = str(getattr(response, "text", "") or "")[:300]
        raise RuntimeError(f"Telegram sendPhoto HTTP {status}: {detail}") from None
    except requests.RequestException as exc:
        raise RuntimeError(f"Telegram sendPhoto request failed: {exc.__class__.__name__}") from None
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram sendPhoto failed: {data}")


def send_channel_post(chat_id: str | int, key: str, text: str, *, logs: Path | str | None = None) -> None:
    image = screenshot_path_for_key(key, logs=logs)
    if image:
        caption = _caption_text(text)
        send_photo(chat_id, image, caption)
        if caption != str(text or "").strip():
            send_message(chat_id, text)
        return
    send_message(chat_id, text)


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
        "ibkr_forecast_inventory": "IBKR ForecastTrader inventory",
        "polymarket_direct_watchlist": "Polymarket Gamma",
        "kalshi_direct_ai_watchlist": "Kalshi public API",
        "yahoo_finance_chart": "Yahoo fallback",
        "yahoo_close_history": "Yahoo close-history replay",
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


def _spread_replay_line(snap: dict[str, Any]) -> str:
    replay = snap.get("spread_families") if isinstance(snap.get("spread_families"), dict) else {}
    primary = replay.get("primary_family") if isinstance(replay.get("primary_family"), dict) else {}
    if not primary:
        return ""
    status = primary.get("status") or "UNKNOWN"
    label = primary.get("label") or primary.get("family_id") or "spread family"
    raw = int(float(primary.get("raw_observations") or primary.get("observations") or 0))
    obs = int(float(primary.get("observations") or 0))
    collapsed = int(float(primary.get("collapsed_repeated_marks") or 0))
    oos_status = primary.get("oos_status") or ""
    oos_pnl = _fmt_operator_float(primary.get("oos_test_pnl_per_unit"), places=4)
    oos = f" | OOS {oos_status}" + (f" {oos_pnl}" if oos_pnl else "") if oos_status else ""
    return f"spread replay: {status} | {label} | {obs}/{raw} mark changes, {collapsed} repeated polls collapsed{oos}"


def _index_coverage_line(snap: dict[str, Any]) -> str:
    replay = snap.get("spread_families") if isinstance(snap.get("spread_families"), dict) else {}
    coverage = replay.get("index_coverage") if isinstance(replay.get("index_coverage"), dict) else {}
    if not coverage:
        return ""
    electricity = coverage.get("electricity") if isinstance(coverage.get("electricity"), dict) else {}
    compute = coverage.get("compute") if isinstance(coverage.get("compute"), dict) else {}
    archetypes = coverage.get("spread_archetypes") if isinstance(coverage.get("spread_archetypes"), dict) else {}
    summary = coverage.get("summary") or (
        f"{electricity.get('usable', 0)}/{electricity.get('total', 0)} electricity indexes usable, "
        f"{compute.get('usable', 0)}/{compute.get('total', 0)} compute indexes usable, "
        f"{archetypes.get('replayed', 0)}/{archetypes.get('total', 0)} spread forms replayed."
    )
    needs_history = archetypes.get("needs_history") if isinstance(archetypes.get("needs_history"), list) else []
    suffix = ""
    if needs_history:
        suffix = " | needs history: " + ", ".join(
            str(row.get("label") or row.get("archetype_id"))
            for row in needs_history[:3]
            if isinstance(row, dict)
        )
    return f"index coverage: {summary}{suffix}"


def _spread_archetype_line(snap: dict[str, Any]) -> str:
    replay = snap.get("spread_families") if isinstance(snap.get("spread_families"), dict) else {}
    rows = replay.get("archetype_scoreboard") if isinstance(replay.get("archetype_scoreboard"), list) else []
    if not rows:
        return ""
    parts = []
    for row in rows[:4]:
        label = row.get("label") or row.get("archetype_id") or "spread"
        status = row.get("replay_status") or "UNKNOWN"
        evidence = row.get("evidence_level") or "planned"
        oos = row.get("oos_status") or ""
        oos_text = f"/OOS {oos}" if oos else ""
        parts.append(f"{label}:{status}/{evidence}{oos_text}")
    return "spread archetypes: " + "; ".join(parts)


def _proxy_replay_line(snap: dict[str, Any]) -> str:
    replay = snap.get("proxy_baskets") if isinstance(snap.get("proxy_baskets"), dict) else {}
    primary = replay.get("active_basket") if isinstance(replay.get("active_basket"), dict) else {}
    if not primary:
        primary = replay.get("primary_basket") if isinstance(replay.get("primary_basket"), dict) else {}
    if not primary:
        return ""
    label = primary.get("label") or primary.get("basket_id") or "proxy basket"
    direction = primary.get("direction") or replay.get("active_direction") or ""
    status = primary.get("status") or "UNKNOWN"
    recommendation = primary.get("recommendation") or "MONITOR_ONLY"
    latest_signal = primary.get("latest_signal") or "MONITOR"
    trailing = primary.get("trailing_returns") if isinstance(primary.get("trailing_returns"), dict) else {}
    five_day = (trailing.get("5d") or {}).get("return_pct")
    one_month = (trailing.get("1m") or {}).get("return_pct")
    ret = float(primary.get("total_return_pct") or 0)
    wr = float(primary.get("win_rate") or 0)
    days = int(float(primary.get("observations") or 0))
    recent = []
    if five_day is not None:
        recent.append(f"5d {float(five_day):+.2f}%")
    if one_month is not None:
        recent.append(f"1m {float(one_month):+.2f}%")
    recent_text = ", ".join(recent) if recent else f"{ret:+.2f}% over {days} days"
    direction_text = f" | {direction}" if direction else ""
    return f"proxy replay: {latest_signal}/{status}/{recommendation} | {label}{direction_text} | {recent_text}, WR {wr:.0f}%"


def _operator_signal_sheet(snap: dict[str, Any]) -> dict[str, Any]:
    proposal = snap.get("synthetic_instrument") if isinstance(snap.get("synthetic_instrument"), dict) else {}
    outputs = proposal.get("outputs") if isinstance(proposal.get("outputs"), dict) else {}
    sheet = outputs.get("operator_signal_sheet") if isinstance(outputs.get("operator_signal_sheet"), dict) else {}
    return sheet


def _fmt_operator_pct(value: Any) -> str:
    if value in ("", None):
        return ""
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return ""


def _fmt_operator_float(value: Any, *, places: int = 4) -> str:
    if value in ("", None):
        return ""
    try:
        return f"{float(value):+,.{places}f}"
    except (TypeError, ValueError):
        return ""


def _fmt_operator_usd(value: Any) -> str:
    if value in ("", None):
        return ""
    try:
        return f"${float(value):+,.2f}"
    except (TypeError, ValueError):
        return ""


def _operator_row_line(row: dict[str, Any]) -> str:
    label = str(row.get("label") or row.get("key") or "signal row")
    action = str(row.get("action") or row.get("signal") or "MONITOR")
    signal = str(row.get("signal") or "").strip()
    status = str(row.get("status") or "").strip()
    head = f"{label}: {action}"
    if signal and signal != action:
        head += f"/{signal}"
    if status:
        head += f"/{status}"
    metrics: list[str] = []
    if row.get("return_5d_pct") not in ("", None):
        metrics.append(f"5d {_fmt_operator_pct(row.get('return_5d_pct'))}")
    if row.get("return_1m_pct") not in ("", None):
        metrics.append(f"1m {_fmt_operator_pct(row.get('return_1m_pct'))}")
    if row.get("power_share_pct") not in ("", None):
        try:
            metrics.append(f"power share {float(row.get('power_share_pct')):.2f}%")
        except (TypeError, ValueError):
            pass
    if row.get("win_rate") not in ("", None):
        try:
            metrics.append(f"WR {float(row.get('win_rate')):.0f}%")
        except (TypeError, ValueError):
            pass
    score = row.get("score")
    if score not in ("", None) and not metrics:
        try:
            metrics.append(f"score {float(score):.2f}")
        except (TypeError, ValueError):
            pass
    return f"{head}" + (f" | {', '.join(metrics)}" if metrics else "")


def _operator_signal_lines(snap: dict[str, Any], *, row_limit: int = 3) -> list[str]:
    sheet = _operator_signal_sheet(snap)
    if not sheet:
        return []
    action = str(sheet.get("overall_action") or "MONITOR")
    headline = str(sheet.get("headline") or "").strip()
    reason = str(sheet.get("reason") or "").strip()
    direction = str(sheet.get("direction") or "").strip()
    active = str(sheet.get("active_proxy_basket_id") or "").strip()
    prefix = f"operator signal: {action}"
    context = " | ".join(part for part in [direction, active] if part)
    first = prefix + (f" | {context}" if context else "")
    if headline:
        first += f" | {headline}"
    if reason and reason not in headline:
        first += f" Reason: {reason}"
    lines = [first]
    rows = [row for row in (sheet.get("rows") or []) if isinstance(row, dict)]
    preferred = [
        "active_proxy_basket",
        "active_syndicated_structure",
        "best_collateral_profile",
        "current_collateral_profile",
        "spread_replay",
    ]
    ordered: list[dict[str, Any]] = []
    for key in preferred:
        for row in rows:
            if row.get("key") == key and row not in ordered:
                ordered.append(row)
    for row in rows:
        if row not in ordered:
            ordered.append(row)
    for row in ordered[:row_limit]:
        lines.append("- " + _operator_row_line(row))
    guardrail = str(sheet.get("guardrail") or "").strip()
    if guardrail:
        lines.append(guardrail)
    return lines


def _spread_trade_map_line(snap: dict[str, Any], *, limit: int = 3) -> str:
    proposal = snap.get("synthetic_instrument") if isinstance(snap.get("synthetic_instrument"), dict) else {}
    outputs = proposal.get("outputs") if isinstance(proposal.get("outputs"), dict) else {}
    rows = [row for row in (outputs.get("spread_archetype_trade_map") or []) if isinstance(row, dict)]
    if not rows:
        return ""
    parts = []
    for row in rows[:limit]:
        selected = row.get("selected_expression") if isinstance(row.get("selected_expression"), dict) else {}
        label = row.get("label") or row.get("archetype_id") or "spread"
        action = row.get("tradability_action") or "MONITOR"
        basket = selected.get("basket_id") or selected.get("title") or "no expression"
        signal = selected.get("latest_signal") or "MONITOR"
        parts.append(f"{label}:{action}/{signal} via {basket}")
    return "spread trade map: " + "; ".join(parts)


def _profitability_ledger_line(snap: dict[str, Any], *, limit: int = 3) -> str:
    proposal = snap.get("synthetic_instrument") if isinstance(snap.get("synthetic_instrument"), dict) else {}
    outputs = proposal.get("outputs") if isinstance(proposal.get("outputs"), dict) else {}
    ledger = outputs.get("spread_profitability_ledger") if isinstance(outputs.get("spread_profitability_ledger"), dict) else {}
    rows = [row for row in (ledger.get("rows") or []) if isinstance(row, dict)]
    if not rows:
        return ""
    parts = []
    for row in rows[:limit]:
        label = row.get("label") or row.get("archetype_id") or "spread"
        status = row.get("profitability_status") or "MONITOR"
        five_day = _fmt_operator_pct(row.get("paper_5d_return_pct"))
        one_month = _fmt_operator_pct(row.get("paper_1m_return_pct"))
        signal = row.get("latest_signal") or "MONITOR"
        metrics = []
        if five_day:
            metrics.append(f"5d {five_day}")
        if one_month:
            metrics.append(f"1m {one_month}")
        latest_pnl = _fmt_operator_usd(row.get("latest_paper_pnl_usdc"))
        latest_ret = _fmt_operator_pct(row.get("latest_paper_return_pct"))
        if latest_pnl:
            metrics.append(f"mark {latest_pnl}" + (f" / {latest_ret}" if latest_ret else ""))
        ticket_pnl = _fmt_operator_usd(row.get("paper_trade_total_pnl_usdc"))
        ticket_action = row.get("paper_trade_action") or ""
        ticket_hit = _fmt_operator_pct(row.get("paper_trade_hit_rate"))
        if ticket_pnl:
            ticket_text = f"tickets {ticket_pnl}"
            if ticket_action:
                ticket_text += f" {ticket_action}"
            if ticket_hit:
                ticket_text += f" hit {ticket_hit}"
            metrics.append(ticket_text)
        oos_status = str(row.get("oos_status") or "")
        oos_return = _fmt_operator_pct(row.get("oos_test_return_pct"))
        if oos_status and oos_status != "NO_OOS_REPLAY":
            oos_text = f"OOS {oos_status}"
            if oos_return:
                oos_text += f" {oos_return}"
            metrics.append(oos_text)
        signal_reason = str(row.get("signal_reason") or row.get("current_action_reason") or "").strip()
        if signal_reason:
            metrics.append(f"why {signal_reason[:120]}")
        metric_text = ", ".join(metrics) if metrics else "paper replay"
        parts.append(f"{label}:{status}/{signal} ({metric_text})")
    note = "not realized PnL" if ledger.get("realized") is False else "ledger"
    return "profitability ledger: " + "; ".join(parts) + f" | {note}"


def _portfolio_signal_line(snap: dict[str, Any]) -> str:
    proposal = snap.get("synthetic_instrument") if isinstance(snap.get("synthetic_instrument"), dict) else {}
    outputs = proposal.get("outputs") if isinstance(proposal.get("outputs"), dict) else {}
    summary = outputs.get("portfolio_signal_summary") if isinstance(outputs.get("portfolio_signal_summary"), dict) else {}
    if not summary:
        return ""
    ticket_pnl = _fmt_operator_usd(summary.get("paper_ticket_total_pnl_usdc")) or "n/a"
    mark_pnl = _fmt_operator_usd(summary.get("latest_mark_total_pnl_usdc")) or "n/a"
    action = summary.get("action") or "MONITOR"
    counts = f"{summary.get('buy_count', 0)} buy/{summary.get('close_or_avoid_count', 0)} close/{summary.get('wait_count', 0)} wait"
    return f"portfolio signal: {action} | tickets {ticket_pnl}, marks {mark_pnl} | {counts}"


def _pnl_line(snap: dict[str, Any]) -> str:
    pnl = snap.get("pnl") if isinstance(snap.get("pnl"), dict) else {}
    if not pnl:
        return ""
    label = pnl.get("status_label") or "PnL unavailable"
    trades = pnl.get("display_trades") or "0 settled"
    total = pnl.get("display_total") or label
    return f"settled PnL: {total} | trades {trades} | replay/local tickets are separate"


def _venue_evidence_line(snap: dict[str, Any]) -> str:
    matrix = snap.get("venue_evidence") if isinstance(snap.get("venue_evidence"), dict) else {}
    rows = [row for row in (matrix.get("rows") or []) if isinstance(row, dict)]
    if not rows:
        return ""
    compact = []
    for row in rows[:5]:
        surface = row.get("surface") or "surface"
        status = str(row.get("status") or "UNKNOWN").replace("_", " ")
        priced = int(float(row.get("priced_count") or 0))
        proxy = int(float(row.get("external_proxy_count") or 0))
        suffix = f"{priced} priced"
        if proxy:
            suffix += f", {proxy} proxy"
        auth = str(row.get("auth_status") or "").strip()
        auth_text = f", auth {auth.replace('_', ' ')}" if auth else ""
        sources = _quote_source_list(row.get("quote_sources") or [], limit=2)
        source_text = f", source {'/'.join(sources)}" if sources else ""
        compact.append(f"{surface}:{status} ({suffix}){auth_text}{source_text}")
    return "venue evidence: " + "; ".join(compact) + "; Arc-ready 0 before judge EXECUTE"


def _venue_copy_matrix_line(snap: dict[str, Any], *, limit: int = 4) -> str:
    proposal = snap.get("synthetic_instrument") if isinstance(snap.get("synthetic_instrument"), dict) else {}
    outputs = proposal.get("outputs") if isinstance(proposal.get("outputs"), dict) else {}
    matrix = outputs.get("real_venue_copy_matrix") if isinstance(outputs.get("real_venue_copy_matrix"), dict) else {}
    rows = [row for row in (matrix.get("rows") or []) if isinstance(row, dict)]
    if not rows:
        return ""
    parts = []
    for row in rows[:limit]:
        surface = row.get("surface") or "surface"
        role = str(row.get("copy_role") or "watch").replace("_", " ")
        status = str(row.get("copy_status") or "UNKNOWN").replace("_", " ")
        links = row.get("spread_links") if isinstance(row.get("spread_links"), list) else []
        link_text = ""
        if links:
            link_text = " -> " + ",".join(str(link.get("archetype_id") or "spread") for link in links[:2])
        parts.append(f"{surface}:{role}/{status}{link_text}")
    return "venue copy matrix: " + "; ".join(parts) + "; judge before Arc"


def _campaign_venue_health_line(snap: dict[str, Any]) -> str:
    if not _campaign_snapshot_ready(snap) and _campaign_snapshot_quality_score(snap) < 45.0:
        return (
            "Current venue evidence: draft snapshot is replay/local-fallback quality; "
            "open the Mini App for live Polymarket, Kalshi, IBKR auth, public quote, and crypto pricing state."
        )
    line = _venue_evidence_line(snap)
    if not line:
        return "Current venue health: open the Mini App for live auth/pricing state."
    return "Current " + line


def _direct_event_pair_line(snap: dict[str, Any], *, limit: int = 3) -> str:
    proposal = snap.get("synthetic_instrument") if isinstance(snap.get("synthetic_instrument"), dict) else {}
    outputs = proposal.get("outputs") if isinstance(proposal.get("outputs"), dict) else {}
    pairs = outputs.get("direct_event_pair_candidates") if isinstance(outputs.get("direct_event_pair_candidates"), dict) else {}
    rows = [row for row in (pairs.get("rows") or []) if isinstance(row, dict)]
    if not rows:
        return ""
    parts = []
    for row in rows[:limit]:
        energy = row.get("energy_leg") if isinstance(row.get("energy_leg"), dict) else {}
        compute = row.get("compute_leg") if isinstance(row.get("compute_leg"), dict) else {}
        energy_ref = energy.get("slug") or energy.get("title") or "energy leg"
        compute_ref = compute.get("slug") or compute.get("title") or "compute leg"
        energy_side = energy.get("pair_side") or "watch"
        compute_side = compute.get("pair_side") or "watch"
        readiness = str(row.get("readiness") or "WATCH").replace("_", " ")
        oracle = row.get("oracle_evidence") if isinstance(row.get("oracle_evidence"), dict) else {}
        oracle_gate = str(oracle.get("gate") or "NO_ORACLE_RECEIPTS").replace("_", " ")
        receipts = int(float(oracle.get("receipts") or 0))
        parts.append(f"{readiness} {energy_side} {energy_ref} vs {compute_side} {compute_ref} (oracle {oracle_gate}, {receipts} receipts)")
    ready = int(float(pairs.get("ready_for_judge_count") or 0))
    total = int(float(pairs.get("pair_count") or len(rows)))
    return f"direct event pairs: {ready}/{total} ready | " + "; ".join(parts) + "; premium/judge before Arc"


def _oracle_line(snap: dict[str, Any]) -> str:
    oracle = snap.get("oracle") if isinstance(snap.get("oracle"), dict) else {}
    if not oracle:
        return ""
    status = str(oracle.get("status") or "NO_RECEIPTS")
    row_count = int(float(oracle.get("row_count") or 0))
    verdict_counts = oracle.get("verdict_counts") if isinstance(oracle.get("verdict_counts"), dict) else {}
    verdict_text = ", ".join(f"{key}:{value}" for key, value in sorted(verdict_counts.items())) or "none"
    reason = oracle.get("latest_reason_code") or "none"
    return f"oracle evidence: {status} | receipts {row_count} | verdicts {verdict_text} | latest {reason} | evidence only"


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
    parts.extend(_operator_signal_lines(snap, row_limit=3))
    spread_line = _spread_replay_line(snap)
    if spread_line:
        parts.append(spread_line)
    index_line = _index_coverage_line(snap)
    if index_line:
        parts.append(index_line)
    archetype_line = _spread_archetype_line(snap)
    if archetype_line:
        parts.append(archetype_line)
    proxy_line = _proxy_replay_line(snap)
    if proxy_line:
        parts.append(proxy_line)
    profitability_line = _profitability_ledger_line(snap)
    if profitability_line:
        parts.append(profitability_line)
    trade_map_line = _spread_trade_map_line(snap)
    if trade_map_line:
        parts.append(trade_map_line)
    pnl_line = _pnl_line(snap)
    if pnl_line:
        parts.append(pnl_line)
    venue_copy_line = _venue_copy_matrix_line(snap)
    if venue_copy_line:
        parts.append(venue_copy_line)
    direct_pair_line = _direct_event_pair_line(snap)
    if direct_pair_line:
        parts.append(direct_pair_line)
    venue_line = _venue_evidence_line(snap)
    if venue_line:
        parts.append(venue_line)
    oracle_line = _oracle_line(snap)
    if oracle_line:
        parts.append(oracle_line)
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
        operator_lines = _operator_signal_lines(snap, row_limit=4)
        if operator_lines:
            lines.append("operator signal sheet:")
            lines.extend(operator_lines)
        spread_line = _spread_replay_line(snap)
        if spread_line:
            lines.append(spread_line)
        index_line = _index_coverage_line(snap)
        if index_line:
            lines.append(index_line)
        archetype_line = _spread_archetype_line(snap)
        if archetype_line:
            lines.append(archetype_line)
        proxy_line = _proxy_replay_line(snap)
        if proxy_line:
            lines.append(proxy_line)
        portfolio_line = _portfolio_signal_line(snap)
        if portfolio_line:
            lines.append(portfolio_line)
        profitability_line = _profitability_ledger_line(snap, limit=4)
        if profitability_line:
            lines.append(profitability_line)
        trade_map_line = _spread_trade_map_line(snap, limit=4)
        if trade_map_line:
            lines.append(trade_map_line)
        pnl_line = _pnl_line(snap)
        if pnl_line:
            lines.append(pnl_line)
        venue_copy_line = _venue_copy_matrix_line(snap)
        if venue_copy_line:
            lines.append(venue_copy_line)
        direct_pair_line = _direct_event_pair_line(snap)
        if direct_pair_line:
            lines.append(direct_pair_line)
        venue_line = _venue_evidence_line(snap)
        if venue_line:
            lines.append(venue_line)
        oracle_line = _oracle_line(snap)
        if oracle_line:
            lines.append(oracle_line)
        if search_plan:
            lines.append("agent scouting: " + ", ".join(
                f"{item.get('surface')}:{item.get('target')}"
                for item in search_plan[:3]
            ))
        if actions:
            lines.append(f"next: {actions[0]}")
        instrument_menu = (((proposal.get("outputs") or {}).get("syndicated_instrument_menu")) or [])
        if instrument_menu:
            lines.append("syndicated structures:")
            for item in instrument_menu[:4]:
                trailing = item.get("trailing_returns") if isinstance(item.get("trailing_returns"), dict) else {}
                ret_5d = (trailing.get("5d") or {}).get("return_pct")
                ret_1m = (trailing.get("1m") or {}).get("return_pct")
                active = "ACTIVE " if item.get("direction_aligned") else ""
                direction = item.get("basket_direction") or item.get("active_signal_direction") or ""
                direction_part = f"{direction} | " if direction else ""
                lines.append(
                    "- "
                    f"{active}{item.get('latest_signal', 'MONITOR')} | {item.get('title', item.get('instrument_type'))} | "
                    f"{item.get('status', 'MONITOR_ONLY')} | "
                    f"{direction_part}"
                    f"5d {float(ret_5d or 0):+.2f}% / 1m {float(ret_1m or 0):+.2f}%"
                )
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
        "- Spread replay collapses repeated worker polls before PnL; proxy replay uses public close history for the liquid expression.",
        "- Settled PnL stays \"No settled PnL\" until reconciliation rows exist; replay and local tickets are labelled separately.",
        "- Venue evidence matrix shows Polymarket, Kalshi, IBKR, public quotes, crypto, and Opoint/Nebius as feeds or evidence only.",
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
        "The spread replay collapses repeated worker polls before PnL, and the proxy replay separately checks public close-history PnL.",
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
        "Screenshot attached when refreshed: Mini App home with the account state, walkthrough, and links to the bot/channel/web surfaces.",
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
        "Screenshot attached when refreshed: venue-copy matrix showing which surfaces are direct legs, which are liquid proxies, and which are evidence-only.",
        "",
        "Mini App: https://power.botozen.com/tg",
        "Dashboard: https://power.botozen.com/dashboard",
    ])


def channel_instrument_menu_update_message() -> str:
    return "\n".join([
        "Product update: spread menu shipped",
        "",
        "Power by Botozen now tracks more than one compute/energy expression.",
        "",
        "New index universe:",
        "- electricity: EIA regional power, IBKR ForecastTrader power indexes, Henry Hub, Brent/WTI, merchant power proxies",
        "- compute: AWS GPU spot, H100 rental marks, cloud GPU providers, AI event contracts, NVDA/VRT/ETN, BTC/ETH miner-margin proxies",
        "- spread archetypes: compute spark, power-cost share, regional compute basis, regional power basis, regional compute-power basis, compute calendar, fuel-stack compute",
        "",
        "New syndicated structures:",
        "- compute scarcity receivable hedge note",
        "- power-stress compute receivable hedge",
        "- grid load-growth basket note",
        "- miner-margin power pair",
        "- fuel-stack compute input hedge",
        "- regional compute capacity basis note",
        "- regional power congestion basis note",
        "",
        "Each structure now carries a replay signal: BUY, HOLD, SELL, or MONITOR, with 5d and 1m public proxy PnL. Still no Arc action before judge.classify() returns EXECUTE, and these are not asset-backed until collateral is attached.",
        "",
        "Screenshot attached when refreshed: the index catalog and spread menu inside the Mini App.",
        "",
        "Mini App: https://power.botozen.com/tg",
        "Dashboard: https://power.botozen.com/dashboard",
    ])


def channel_profitability_update_message() -> str:
    return "\n".join([
        "Product update: profitability ledger shipped",
        "",
        "Power by Botozen now ranks the compute/energy spread menu by paper profitability instead of showing disconnected replay rows.",
        "",
        "What changed:",
        "- each oil-style spread maps to a tradable expression basket",
        "- each expression shows PAPER_BUY, SELL_OR_AVOID, MONITOR, or needs-data status",
        "- 5d and 1m public proxy PnL are shown next to the spread replay",
        "- realized PnL remains separate and stays empty until reconciled fills or settlements exist",
        "- Kalshi, Polymarket, IBKR ForecastTrader, Yahoo/public quotes, and crypto are labelled by venue role",
        "",
        "Current interpretation: a spread can be PROMOTABLE as an index replay and still be SELL_OR_AVOID if the mapped proxy basket's current signal says sell. That is intentional.",
        "",
        "Screenshot attached when refreshed: profitability ledger with paper-ticket PnL, latest mark PnL, OOS gate, and buy/avoid labels.",
        "",
        "No Arc action can happen unless judge.classify() returns EXECUTE.",
        "",
        "Mini App: https://power.botozen.com/tg",
        "Dashboard: https://power.botozen.com/dashboard",
    ])


def channel_miniapp_update_message() -> str:
    return "\n".join([
        "Product update: Telegram Mini App walkthrough shipped",
        "",
        "The Mini App now mirrors the web desk and has its own release-notes screen so users can see what changed without reading operator docs.",
        "",
        "New in Telegram:",
        "- home screen now has a four-step walkthrough: read signal, create account/open ticket, track PnL, check venue scouting",
        "- What Changed screen explains the Mini App release and maps channel screenshots to product sections",
        "- My Portfolio screen with server-side Operator account, wallet label, open paper tickets, realized ledger, and net paper PnL",
        "- Open Paper Ticket from the mock contract screen after Operator setup",
        "- Close buttons for paper tickets, with backend NAV refresh after every action",
        "- clear labels separating paper ticket PnL from settled venue PnL and Arc escrow PnL",
        "- direct links to the bot, channel, web account, and live dashboard",
        "",
        "Screenshot attached when refreshed: the What Changed screen. Other channel posts attach the portfolio ledger, spread menu, profitability ledger, and venue-copy matrix.",
        "",
        "Still unchanged: no IBKR, Polymarket, Circle, or Arc execution happens from a Mini App tap. It only saves a paper ticket unless judge.classify() later returns EXECUTE and the operator runs the gated Arc path.",
        "",
        "Mini App: https://power.botozen.com/tg",
        "Dashboard: https://power.botozen.com/dashboard",
    ])


def channel_miniapp_release_messages() -> list[tuple[str, str]]:
    return [
        (
            f"{CHANNEL_MINIAPP_RELEASE_PREFIX}:home",
            "\n".join([
                "Mini App release 1/5: user path",
                "",
                "The Telegram Mini App is now the same product flow as the web desk, not a separate bot demo.",
                "",
                "Screenshot: home screen with system status, notional, Circle test-USDC ask, Operator account state, and the four-step walkthrough.",
                "",
                "What changed:",
                "- read the live compute/energy spread signal",
                "- create or restore the Operator account",
                "- open the mock contract screen",
                "- track PnL and venue scouting without channel reject spam",
                "",
                "Mini App: https://power.botozen.com/tg",
            ]),
        ),
        (
            f"{CHANNEL_MINIAPP_RELEASE_PREFIX}:contract",
            "\n".join([
                "Mini App release 2/5: mock contract",
                "",
                "This is the user-facing trade surface. It shows electricity, compute, S_t, z-score, notional, Circle ask, weighted legs, and the buy/monitor/sell recommendation.",
                "",
                "Screenshot: Mock Contract screen. BTC, ETH, equities, IBKR, Kalshi, and Polymarket are labelled by role: proxy hedge, direct event leg, or research-only scouting input.",
                "",
                "A tap only saves a local paper ticket. It is not an IBKR, Polymarket, Circle, or Arc order.",
                "",
                "Guardrail: judge.classify() first, Arc second.",
            ]),
        ),
        (
            f"{CHANNEL_MINIAPP_RELEASE_PREFIX}:portfolio",
            "\n".join([
                "Mini App release 3/5: account and PnL",
                "",
                "The Mini App now has a real backend Operator account surface. Paper positions and PnL are restored from the signed session instead of disappearing after a browser refresh.",
                "",
                "Screenshot: My Portfolio screen with account id, wallet label, open paper tickets, realized ledger, unrealized PnL, realized PnL, and net PnL.",
                "",
                "Important label: paper PnL is NAV versus entry. Settled venue PnL and Arc escrow PnL remain separate.",
            ]),
        ),
        (
            f"{CHANNEL_MINIAPP_RELEASE_PREFIX}:profitability",
            "\n".join([
                "Mini App release 4/5: profitability discipline",
                "",
                "The app no longer shows isolated BUY labels without context. Each syndicated spread has replay status, latest mark PnL, paper-ticket PnL, OOS state, and a current action.",
                "",
                "Screenshot: profitability ledger. Entry-day $0 is expected because it is the baseline; subsequent marks show whether the proposed arb made or lost money.",
                "",
                "A spread can be interesting but still be WAIT or SELL_OR_AVOID if replay and proxy marks disagree.",
            ]),
        ),
        (
            f"{CHANNEL_MINIAPP_RELEASE_PREFIX}:scouting",
            "\n".join([
                "Mini App release 5/5: venue scouting",
                "",
                "The scouting screen explains what each venue contributes before anything is promoted into the user funnel.",
                "",
                "Screenshot: venue matrix with Polymarket, Kalshi, IBKR ForecastTrader, public quotes, crypto proxies, and Opoint/Nebius evidence roles.",
                "",
                "Opoint/Nebius is evidence only. IBKR/Polymarket/Kalshi are direct-leg candidates only when priced, thesis-matched, and judged. The public channel stays sparse: no repeated REJECT/DEFER/watchlist rows.",
                "",
                "Mini App: https://power.botozen.com/tg?screen=scouting",
            ]),
        ),
    ]


def channel_miniapp_release_draft_text() -> str:
    return "\n\n---\n\n".join(text for _key, text in channel_miniapp_release_messages())


def channel_signal_discipline_update_message() -> str:
    return "\n".join([
        "Product update: signal discipline tightened",
        "",
        "We fixed the confusing case where a syndicated note could show BUY in the menu while the profitability ledger still said wait.",
        "",
        "New rule:",
        "- a proxy basket BUY is not enough for a fresh paper-buy label",
        "- the matching oil-style spread replay must also clear its promotion gate",
        "- if spread replay or OOS replay fails, the note is downgraded to WAIT_FOR_SPREAD_REPLAY",
        "- SELL and CLOSE/AVOID signals stay explicit when current proxy marks deteriorate",
        "",
        "Current live interpretation: some proxy baskets still mark BUY, but the portfolio action is CLOSE_OR_AVOID because the matching spread/OOS evidence is not strong enough for a user-facing fresh buy.",
        "",
        "Screenshot attached when refreshed: profitability ledger proving the buy label is suppressed until spread replay and proxy replay agree.",
        "",
        "This keeps the product honest: real venues and liquid proxies can mark the package, but profitability discipline decides whether a user should open, hold, or close a paper ticket. Arc remains locked unless judge.classify() returns EXECUTE.",
        "",
        "Mini App: https://power.botozen.com/tg",
        "Dashboard: https://power.botozen.com/dashboard",
    ])


def channel_oracle_discipline_update_message() -> str:
    return "\n".join([
        "Product update: Opoint/Nebius evidence discipline shipped",
        "",
        "We tightened the news/LLM layer so the current desk summary prefers compute-power receipts instead of whichever generic energy receipt was newest.",
        "",
        "New rule:",
        "- data-center moratorium, grid interconnection, AI capex, GPU capacity, and nuclear/data-center candidates use compute-power query templates",
        "- Opoint topic filters still use working numeric topic ids, not scraped medtop URIs",
        "- Hormuz/tanker/oil-shipping false positives are rejected for compute-power evidence",
        "- Mini App scouting now shows total receipts, current-desk receipts, latest scope, query label, verdict counts, and article coverage",
        "",
        "This remains evidence only. Opoint/Nebius can support or criticize a direct leg, but it cannot replace the premium scorer or judge.classify(), and it cannot trigger Circle or Arc.",
        "",
        "Screenshot attached when refreshed: Mini App venue/scouting matrix with oracle scope and venue-role labels.",
        "",
        "Mini App: https://power.botozen.com/tg?screen=scouting",
        "Dashboard: https://power.botozen.com/dashboard",
    ])


def channel_basis_spread_update_message() -> str:
    return "\n".join([
        "Product update: regional basis spreads shipped",
        "",
        "Power by Botozen now splits the old combined regional compute/power basis into two cleaner oil-style basis legs.",
        "",
        "New spread forms:",
        "- Regional compute rental basis: Region A GPU rental minus Region B GPU rental",
        "- Regional power basis: Region A electricity $/MWh minus Region B electricity $/MWh",
        "",
        "New syndicated copies:",
        "- Regional compute capacity basis note",
        "- Regional power congestion basis note",
        "",
        "Why this matters: this is closer to WTI-Brent or regional power hub basis trading. The desk can now ask whether compute-region dislocation and power-region congestion are separate opportunities before combining them into a compute-power package.",
        "",
        "Both forms go through the same replay path: no-lookahead spread replay, proxy-basket replay, paper-ticket PnL, OOS check, and judge-before-Arc guardrail.",
        "",
        "Screenshot attached when refreshed: Mini App index catalog and spread menu with the new basis forms.",
        "",
        "Mini App: https://power.botozen.com/tg?screen=dashboard",
        "Dashboard: https://power.botozen.com/dashboard",
    ])


def _format_count_map(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "none"
    items = sorted(value.items(), key=lambda item: (-int(float(item[1] or 0)), str(item[0])))
    return ", ".join(
        f"{str(key).replace('_', ' ')} {int(float(count or 0))}"
        for key, count in items
    )


def channel_index_tradeability_update_message(snap: dict[str, Any]) -> str:
    spread_families = snap.get("spread_families") if isinstance(snap.get("spread_families"), dict) else {}
    coverage = spread_families.get("index_coverage") if isinstance(spread_families.get("index_coverage"), dict) else {}
    electricity = coverage.get("electricity") if isinstance(coverage.get("electricity"), dict) else {}
    compute = coverage.get("compute") if isinstance(coverage.get("compute"), dict) else {}
    archetypes = coverage.get("spread_archetypes") if isinstance(coverage.get("spread_archetypes"), dict) else {}
    return "\n".join([
        "Product update: index tradeability labels shipped",
        "",
        "The index catalog now says what each row can actually do in the desk.",
        "",
        "Power index tradeability:",
        _format_count_map(electricity.get("tradeability_counts")),
        "",
        "Compute index tradeability:",
        _format_count_map(compute.get("tradeability_counts")),
        "",
        "Family buckets:",
        f"- power: {_format_count_map(electricity.get('family_counts'))}",
        f"- compute: {_format_count_map(compute.get('family_counts'))}",
        "",
        f"Spread forms replayed: {int(float(archetypes.get('replayed') or 0))}/{int(float(archetypes.get('total') or 0))}; OOS passed: {int(float(archetypes.get('oos_passed') or archetypes.get('oos_pass') or 0))}.",
        "",
        "How to read the labels:",
        "- live/derived marks can support the spread index directly",
        "- priced proxies can mark paper syndicated baskets after replay gates pass",
        "- labelled proxies like BTC/ETH stay miner-margin proxies, not the securitized asset",
        "- direct-event watchlists can become Polymarket/Kalshi/IBKR legs only after venue price, premium gate where required, and judge.classify()",
        "- planned gaps are visible research gaps, not tradable marks",
        "",
        "This prevents the old confusion where a real feed, a proxy, and a future research target looked equivalent.",
        "",
        "Screenshot attached when refreshed: Mini App index/scouting surface with family and tradeability labels.",
        "",
        "Mini App: https://power.botozen.com/tg?screen=scouting",
        "Dashboard: https://power.botozen.com/dashboard",
    ])


def _index_catalog_counts(snap: dict[str, Any]) -> dict[str, int]:
    spread_families = snap.get("spread_families") if isinstance(snap.get("spread_families"), dict) else {}
    catalog = spread_families.get("index_catalog") if isinstance(spread_families.get("index_catalog"), dict) else {}
    coverage = spread_families.get("index_coverage") if isinstance(spread_families.get("index_coverage"), dict) else {}
    electricity = coverage.get("electricity") if isinstance(coverage.get("electricity"), dict) else {}
    compute = coverage.get("compute") if isinstance(coverage.get("compute"), dict) else {}
    spread_archetypes = coverage.get("spread_archetypes") if isinstance(coverage.get("spread_archetypes"), dict) else {}
    return {
        "electricity": len(catalog.get("electricity") or []),
        "compute": len(catalog.get("compute") or []),
        "spreads": len(catalog.get("spread_archetypes") or []),
        "electricity_usable": int(float(electricity.get("usable") or 0)),
        "compute_usable": int(float(compute.get("usable") or 0)),
        "spreads_replayed": int(float(spread_archetypes.get("replayed") or 0)),
    }


def _profitability_rows(snap: dict[str, Any]) -> list[dict[str, Any]]:
    proposal = snap.get("synthetic_instrument") if isinstance(snap.get("synthetic_instrument"), dict) else {}
    outputs = proposal.get("outputs") if isinstance(proposal.get("outputs"), dict) else {}
    ledger = outputs.get("spread_profitability_ledger") if isinstance(outputs.get("spread_profitability_ledger"), dict) else {}
    return [row for row in (ledger.get("rows") or []) if isinstance(row, dict)]


def _venue_copy_rows(snap: dict[str, Any]) -> list[dict[str, Any]]:
    proposal = snap.get("synthetic_instrument") if isinstance(snap.get("synthetic_instrument"), dict) else {}
    outputs = proposal.get("outputs") if isinstance(proposal.get("outputs"), dict) else {}
    matrix = outputs.get("real_venue_copy_matrix") if isinstance(outputs.get("real_venue_copy_matrix"), dict) else {}
    return [row for row in (matrix.get("rows") or []) if isinstance(row, dict)]


def _campaign_outputs(snap: dict[str, Any]) -> dict[str, Any]:
    proposal = snap.get("synthetic_instrument") if isinstance(snap.get("synthetic_instrument"), dict) else {}
    return proposal.get("outputs") if isinstance(proposal.get("outputs"), dict) else {}


def _campaign_portfolio_line(snap: dict[str, Any], ledger_rows: list[dict[str, Any]]) -> str:
    outputs = _campaign_outputs(snap)
    summary = outputs.get("portfolio_signal_summary") if isinstance(outputs.get("portfolio_signal_summary"), dict) else {}
    action = summary.get("action") or "MONITOR"
    top_buy = summary.get("top_buy") if isinstance(summary.get("top_buy"), dict) else {}
    if top_buy:
        reason = str(top_buy.get("signal_reason") or top_buy.get("current_action_reason") or top_buy.get("reason") or "").strip()
        return (
            f"Current buy signal: {top_buy.get('label') or top_buy.get('archetype_id')} "
            f"({top_buy.get('profitability_status') or 'PAPER_BUY'} / {top_buy.get('latest_signal') or 'BUY'})."
            + (f" Why: {reason}" if reason else "")
        )
    close_row = summary.get("top_close_or_avoid") if isinstance(summary.get("top_close_or_avoid"), dict) else {}
    if summary and (str(action).startswith("CLOSE") or str(action).startswith("AVOID") or close_row):
        if close_row:
            reason = str(close_row.get("signal_reason") or close_row.get("current_action_reason") or close_row.get("reason") or "").strip()
            return (
                f"Current buy signal: none. Portfolio action is {action}; "
                f"avoid/close {close_row.get('label') or close_row.get('archetype_id')}."
                + (f" Why: {reason}" if reason else "")
            )
        return f"Current buy signal: none. Portfolio action is {action}."
    buy_row = next((row for row in ledger_rows if row.get("profitability_status") == "PAPER_BUY"), {})
    if buy_row:
        reason = str(buy_row.get("signal_reason") or buy_row.get("current_action_reason") or buy_row.get("reason") or "").strip()
        return (
            f"Current buy signal: {buy_row.get('label') or buy_row.get('archetype_id')} "
            f"({buy_row.get('profitability_status')} / {buy_row.get('latest_signal') or 'BUY'})."
            + (f" Why: {reason}" if reason else "")
        )
    return f"Current buy signal: none. Portfolio action is {action}."


def _campaign_direct_pair_line(snap: dict[str, Any]) -> str:
    if not _campaign_snapshot_ready(snap) and _campaign_snapshot_quality_score(snap) < 45.0:
        return (
            "Direct event pairs: draft snapshot is replay/local-fallback quality; "
            "open the Mini App for live thesis-matched pair readiness."
        )
    outputs = _campaign_outputs(snap)
    pairs = outputs.get("direct_event_pair_candidates") if isinstance(outputs.get("direct_event_pair_candidates"), dict) else {}
    rows = [row for row in (pairs.get("rows") or []) if isinstance(row, dict)]
    if rows:
        first = rows[0]
        oracle = first.get("oracle_evidence") if isinstance(first.get("oracle_evidence"), dict) else {}
        energy = first.get("energy_leg") if isinstance(first.get("energy_leg"), dict) else {}
        compute = first.get("compute_leg") if isinstance(first.get("compute_leg"), dict) else {}
        return (
            f"Direct event pairs: {pairs.get('ready_for_judge_count', 0)}/{pairs.get('pair_count', len(rows))} ready; "
            f"top pair {energy.get('surface') or 'energy'}:{energy.get('slug') or 'energy-leg'} vs "
            f"{compute.get('surface') or 'compute'}:{compute.get('slug') or 'compute-leg'}; "
            f"gate {first.get('readiness') or 'WATCH'}; "
            f"oracle {oracle.get('gate') or 'NO_ORACLE_RECEIPTS'} with {int(float(oracle.get('receipts') or 0))} receipts."
        )
    inventory = [row for row in (snap.get("direct_inventory") or []) if isinstance(row, dict)]
    if not inventory:
        return "Direct event pairs: loading."
    def bucket(row: dict[str, Any]) -> str:
        role = str(row.get("direct_pair_role") or row.get("role") or row.get("leg_role") or "").lower()
        title = str(row.get("leg_title") or row.get("title") or row.get("instrument") or "").lower()
        if any(term in role for term in ("compute", "ai", "gpu", "nvidia", "openai", "anthropic", "data center", "datacenter")):
            return "compute"
        if any(term in role for term in ("energy", "electricity", "power", "grid", "gas", "oil", "brent", "crude", "generation")):
            return "energy"
        text = f"{role} {title}"
        if any(term in text for term in ("energy", "electricity", "power", "grid", "gas", "oil", "brent", "crude", "generation")):
            return "energy"
        if any(term in text for term in ("compute", "ai", "gpu", "nvidia", "openai", "anthropic", "data center", "datacenter")):
            return "compute"
        return ""
    energy_rows = [row for row in inventory if bucket(row) == "energy"]
    compute_rows = [row for row in inventory if bucket(row) == "compute"]
    if not energy_rows or not compute_rows:
        return "Direct event pairs: loading."

    def is_priced(row: dict[str, Any]) -> bool:
        status = str(row.get("pricing_status") or row.get("reason_code") or "").lower()
        label = str(row.get("pricing_status_label") or row.get("status_label") or "").lower()
        prices = row.get("yes_prices") if isinstance(row.get("yes_prices"), list) else []
        return (
            status in {"priced_watchlist", "priced_public_market", "live_priced"}
            or label in {"live price available", "public price available"}
            or bool(prices)
        )

    def readiness(energy: dict[str, Any], compute: dict[str, Any]) -> str:
        both_priced = is_priced(energy) and is_priced(compute)
        surfaces = {str(energy.get("surface") or ""), str(compute.get("surface") or "")}
        if both_priced and "polymarket" in surfaces:
            return "NEEDS_PREMIUM_AND_JUDGE"
        if both_priced:
            return "NEEDS_JUDGE"
        return "NEEDS_PRICE"

    reconstructed = []
    for energy_row in energy_rows:
        for compute_row in compute_rows:
            reconstructed.append((readiness(energy_row, compute_row), energy_row, compute_row))
    reconstructed.sort(key=lambda item: (
        0 if item[0] in {"NEEDS_PREMIUM_AND_JUDGE", "NEEDS_JUDGE"} else 1,
        0 if len({str(item[1].get("surface") or ""), str(item[2].get("surface") or "")}) > 1 else 1,
        str(item[1].get("surface") or ""),
        str(item[2].get("surface") or ""),
    ))
    readiness_label, energy, compute = reconstructed[0]
    oracle = snap.get("oracle") if isinstance(snap.get("oracle"), dict) else {}
    pair_count = len(energy_rows) * len(compute_rows)
    ready = sum(1 for label, _energy, _compute in reconstructed if label in {"NEEDS_PREMIUM_AND_JUDGE", "NEEDS_JUDGE"})
    return (
        f"Direct event pairs: {ready}/{pair_count} ready; "
        f"top pair {energy.get('surface') or 'energy'}:{energy.get('leg_slug') or energy.get('slug') or 'energy-leg'} vs "
        f"{compute.get('surface') or 'compute'}:{compute.get('leg_slug') or compute.get('slug') or 'compute-leg'}; "
        f"gate {readiness_label}; "
        f"oracle {oracle.get('latest_pricing_status') or oracle.get('status') or 'NO_ORACLE_RECEIPTS'} with {int(float(oracle.get('row_count') or 0))} receipts."
    )


def channel_campaign_messages(snap: dict[str, Any]) -> list[tuple[str, str]]:
    """Return the operator-reviewed campaign posts without sending them."""
    counts = _index_catalog_counts(snap)
    ledger_rows = _profitability_rows(snap)
    best = next((row for row in ledger_rows if row.get("profitability_status") == "PAPER_BUY"), ledger_rows[0] if ledger_rows else {})
    avoid = next((row for row in ledger_rows if str(row.get("profitability_status")).upper().startswith("SELL")), {})
    venue_rows = _venue_copy_rows(snap)
    venue_line = "; ".join(
        f"{row.get('surface')}={str(row.get('copy_role') or '').replace('_', ' ')}"
        for row in venue_rows[:6]
    ) or "venue roles loading"
    best_ticket = _fmt_operator_usd(best.get("paper_trade_total_pnl_usdc")) or "ticket replay loading"
    best_mark = _fmt_operator_usd(best.get("latest_paper_pnl_usdc")) or "mark loading"
    best_reason = str(best.get("signal_reason") or best.get("current_action_reason") or best.get("reason") or "").strip()
    portfolio_line = _campaign_portfolio_line(snap, ledger_rows)
    direct_pair_line = _campaign_direct_pair_line(snap)
    venue_health_line = _campaign_venue_health_line(snap)
    avoid_text = ""
    if avoid:
        avoid_text = (
            f"\nAvoid/close example: {avoid.get('label') or avoid.get('archetype_id')} is "
            f"{avoid.get('profitability_status')} with ticket action {avoid.get('paper_trade_action') or 'WAIT'}."
        )
    return [
        (
            f"{CHANNEL_CAMPAIGN_PREFIX}:indexes-spreads",
            "\n".join([
                "Power by Botozen campaign 1/4: the index layer",
                "",
                "We are not pretending BTC, NVDA, or one prediction market is the product.",
                "",
                f"The desk tracks {counts['electricity']} electricity indexes, {counts['compute']} compute indexes, and {counts['spreads']} oil-style spread forms.",
                f"Currently usable/replayed: {counts['electricity_usable']} electricity indexes, {counts['compute_usable']} compute indexes, {counts['spreads_replayed']} spread forms.",
                "",
                "Core idea: all is compute, compute is energy, and the tradable object is the judged compute/energy spread package.",
                "",
                "Examples: compute spark spread, power-cost share, regional compute basis, regional power basis, regional compute-power basis, compute calendar, electricity calendar, fuel-stack/miner-margin spread.",
                "New syndicated copies include compute calendar forward hedge, electricity calendar power hedge, compute-power calendar basis note, regional compute capacity basis note, and regional power congestion basis note.",
                "",
                "Screenshot attached when refreshed: Mini App index catalog and oil-style spread menu.",
                "",
                "Mini App: https://power.botozen.com/tg",
            ]),
        ),
        (
            f"{CHANNEL_CAMPAIGN_PREFIX}:profitability",
            "\n".join([
                "Power by Botozen campaign 2/4: profitability discipline",
                "",
                "Each spread has two checks before it becomes a user-facing signal:",
                "1. no-lookahead spread-family replay",
                "2. public proxy basket replay with simulated paper tickets",
                "",
                portfolio_line,
                f"Reference row: {best.get('label') or best.get('archetype_id') or 'loading'}",
                f"row status: {best.get('profitability_status') or 'loading'} / {best.get('latest_signal') or 'MONITOR'}",
                f"paper ticket PnL: {best_ticket}; latest mark PnL: {best_mark}",
                f"ticket action: {best.get('paper_trade_action') or 'WAIT'}",
                f"why: {best_reason or 'waiting for replay reason'}",
                avoid_text,
                "",
                "An entry-day $0.00 mark is not a broken spread. It is just the entry mark; ticket replay shows what the proposed arb would have made after entry.",
                "",
                "Screenshot attached when refreshed: Mini App profitability ledger with paper-ticket PnL, latest mark PnL, and OOS status.",
                "",
                "Dashboard: https://power.botozen.com/dashboard",
            ]),
        ),
        (
            f"{CHANNEL_CAMPAIGN_PREFIX}:venue-copy",
            "\n".join([
                "Power by Botozen campaign 3/4: real venue roles",
                "",
                "The same spread package can be copied across several real surfaces, but the roles are different:",
                venue_line,
                "",
                direct_pair_line,
                "",
                venue_health_line,
                "",
                "Polymarket, Kalshi, and IBKR ForecastTrader are direct event/forecast-leg candidates when they are priced, thesis-matched, and judged.",
                "Yahoo/IBKR public quotes and equities are liquid proxy hedges for sizing and mark-to-market.",
                "BTC/ETH are only miner-margin proxies when power cost matters.",
                "Opoint/Nebius is evidence only: news and LLM receipts can support, defer, or criticize a pair but cannot execute it.",
                "Live gate labels and IBKR auth hints stay in the Mini App so operators can see exactly why a venue leg is or is not usable.",
                "",
                "No raw REJECT/DEFER/watchlist spam belongs in this channel.",
                "",
                "Screenshot attached when refreshed: Mini App venue-copy matrix.",
            ]),
        ),
        (
            f"{CHANNEL_CAMPAIGN_PREFIX}:arc-collateral",
            "\n".join([
                "Power by Botozen campaign 4/4: what is securitized",
                "",
                "The securitized object is not BTC or a generic compute index.",
                "",
                "The product starts from a commercial exposure: a forward compute sale, GPU-hour receivable, power hedge, PPA, or metered delivery claim.",
                "The agent then attaches direct event legs and liquid proxy hedges that are tested against the compute/energy spread.",
                "",
                "Arc is the wrapper: ERC-8004 identity, ERC-8183 job escrow, USDC budget, completion, reputation, and audit trail.",
                "",
                "Guardrail: judge.classify() first, Arc second. If the verdict is not EXECUTE, Circle and Arc stay locked.",
                "",
                "Screenshot attached when refreshed: Mini App portfolio/account ledger, where user tickets and PnL are tracked separately from Arc escrow.",
                "",
                "Repo: https://github.com/pashadude/elctricity_compute-spread-crypto-securitisation",
            ]),
        ),
    ]


def channel_campaign_draft_text(snap: dict[str, Any]) -> str:
    return "\n\n---\n\n".join(text for _key, text in channel_campaign_messages(snap))


def _campaign_snapshot_ready(data: dict[str, Any]) -> bool:
    """Avoid accepting a cold API snapshot with empty liquid-proxy evidence."""
    matrix = data.get("venue_evidence") if isinstance(data.get("venue_evidence"), dict) else {}
    rows = [row for row in (matrix.get("rows") or []) if isinstance(row, dict)]
    if not rows:
        return True
    by_surface = {str(row.get("surface") or ""): row for row in rows}
    for surface in ("public_market", "crypto"):
        row = by_surface.get(surface)
        if not row:
            continue
        if str(row.get("status") or "").upper() in {"NEEDS_PRICE", "NEEDS_QUOTES"} and int(float(row.get("priced_count") or 0)) == 0:
            return False
    polymarket = by_surface.get("polymarket")
    if polymarket:
        sources = {str(src) for src in (polymarket.get("quote_sources") or [])}
        if (
            str(polymarket.get("status") or "").upper() == "NEEDS_PRICE"
            and int(float(polymarket.get("priced_count") or 0)) == 0
            and "polymarket_direct_watchlist" in sources
        ):
            return False
    ibkr = by_surface.get("ibkr_prediction")
    if ibkr:
        sources = {str(src) for src in (ibkr.get("quote_sources") or [])}
        if (
            str(ibkr.get("status") or "").upper() == "NEEDS_PRICE"
            and int(float(ibkr.get("priced_count") or 0)) == 0
            and int(float(ibkr.get("external_proxy_count") or 0)) == 0
            and "ibkr_forecast_inventory" in sources
            and ("yahoo_finance_chart" in sources or "ibkr_energy_history_csv" in sources)
        ):
            return False
    return True


def _campaign_snapshot_from_url(url: str, *, timeout: float) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme in {"http", "https"} and not host.endswith(".test"):
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data
        raise ValueError("campaign snapshot API did not return a JSON object")
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if isinstance(data, dict):
        return data
    raise ValueError("campaign snapshot API did not return a JSON object")


def campaign_snapshot(*, logs: Path | str | None = None) -> dict[str, Any]:
    """Build a campaign snapshot without forcing heavy proxy refreshes."""
    url = os.environ.get("TELEGRAM_CAMPAIGN_SNAPSHOT_URL", "http://127.0.0.1:8080/api/snapshot").strip()
    if os.environ.get("TELEGRAM_CAMPAIGN_DEBUG", "").strip():
        print(f"[campaign-snapshot] url={url or '<empty>'}", file=sys.stderr)
    if url and url not in {"0", "false", "False"}:
        timeout = float(os.environ.get("TELEGRAM_CAMPAIGN_SNAPSHOT_TIMEOUT", "15") or 15)
        attempts = max(1, int(float(os.environ.get("TELEGRAM_CAMPAIGN_SNAPSHOT_ATTEMPTS", "4") or 4)))
        delay = max(0.0, float(os.environ.get("TELEGRAM_CAMPAIGN_SNAPSHOT_RETRY_DELAY", "1.0") or 1.0))
        for attempt in range(attempts):
            try:
                data = _campaign_snapshot_from_url(url, timeout=timeout)
                if isinstance(data, dict) and data.get("ok") is not False:
                    if _campaign_snapshot_ready(data):
                        return data
                    if attempt + 1 < attempts and delay:
                        time.sleep(delay)
            except (requests.RequestException, urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
                if attempt + 1 < attempts and delay:
                    time.sleep(delay)

    disabled = {
        "PUBLIC_HEDGE_FETCH": "0",
        "IBKR_FORECAST_PROXY_QUOTE_FETCH": "0",
        "PROXY_BASKET_BACKTEST_FETCH": "0",
    }
    prior = {name: os.environ.get(name) for name in disabled}
    os.environ.update(disabled)
    try:
        return snapshot(logs=logs)
    finally:
        for name, value in prior.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _campaign_snapshot_quality_score(data: dict[str, Any]) -> float:
    matrix = data.get("venue_evidence") if isinstance(data.get("venue_evidence"), dict) else {}
    rows = [row for row in (matrix.get("rows") or []) if isinstance(row, dict)]
    score = 0.0
    for row in rows:
        surface = str(row.get("surface") or "")
        status = str(row.get("status") or "").upper()
        priced = int(float(row.get("priced_count") or 0))
        proxy = int(float(row.get("external_proxy_count") or 0))
        if status == "LIVE_PRICED":
            score += 10.0 + priced
        elif status == "PROXY_PRICED":
            score += 6.0 + proxy
        elif status == "REPLAY_PRICED":
            score += 3.0 + priced * 0.5
        elif status == "EVIDENCE_LOGGED":
            score += 1.0
        if surface == "polymarket" and status == "LIVE_PRICED":
            score += 8.0
        if surface == "kalshi" and status == "LIVE_PRICED":
            score += 5.0
        if surface == "public_market" and status == "LIVE_PRICED":
            score += 4.0
        if surface == "crypto" and status == "LIVE_PRICED":
            score += 2.0
    return score


def campaign_snapshot_for_messaging(*, logs: Path | str | None = None) -> dict[str, Any]:
    """Prefer the warmest snapshot for public campaign text.

    The API and local fallback can both be valid, but channel copy should not
    understate live venue pricing when the running API is reachable.
    """
    attempts = max(1, int(float(os.environ.get("TELEGRAM_CAMPAIGN_MESSAGE_ATTEMPTS", "2") or 2)))
    delay = max(0.0, float(os.environ.get("TELEGRAM_CAMPAIGN_MESSAGE_RETRY_DELAY", "0.25") or 0.25))
    best: dict[str, Any] = {}
    best_score = -1.0
    for attempt in range(attempts):
        data = campaign_snapshot(logs=logs)
        score = _campaign_snapshot_quality_score(data)
        if os.environ.get("TELEGRAM_CAMPAIGN_DEBUG", "").strip():
            rows = [
                (row.get("surface"), row.get("status"), row.get("priced_count"), row.get("external_proxy_count"))
                for row in (((data.get("venue_evidence") or {}).get("rows") or []))
                if isinstance(row, dict)
            ]
            print(f"[campaign-snapshot] attempt={attempt + 1} score={score:.1f} rows={rows}", file=sys.stderr)
        if score > best_score:
            best = data
            best_score = score
        if score >= 45.0:
            return data
        if attempt + 1 < attempts and delay:
            time.sleep(delay)
    if os.environ.get("TELEGRAM_CAMPAIGN_MESSAGE_DIRECT_REFRESH", "1").strip() not in {"0", "false", "False"}:
        urls: list[str] = []
        configured = os.environ.get("TELEGRAM_CAMPAIGN_SNAPSHOT_URL", "").strip()
        if configured and configured not in {"0", "false", "False"}:
            urls.append(configured)
        else:
            urls.append("http://127.0.0.1:8080/api/snapshot")
        public_base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
        if public_base:
            urls.append(f"{public_base}/api/snapshot")
        for url in dict.fromkeys(urls):
            try:
                data = _campaign_snapshot_from_url(url, timeout=8.0)
            except (requests.RequestException, urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
                continue
            score = _campaign_snapshot_quality_score(data)
            if score > best_score:
                best = data
                best_score = score
            if score >= 45.0:
                return data
    return best


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


def _operator_signal_message(snap: dict[str, Any]) -> tuple[str, str] | None:
    sheet = _operator_signal_sheet(snap)
    if not sheet:
        return None
    action = str(sheet.get("overall_action") or "MONITOR").upper()
    if action not in {"BUY", "BUY_OR_HOLD", "AVOID", "AVOID_OR_CLOSE", "AVOID_OR_SELL", "SELL"}:
        return None
    proposal = snap.get("synthetic_instrument") if isinstance(snap.get("synthetic_instrument"), dict) else {}
    proposal_id = str(proposal.get("proposal_id") or proposal.get("reference_package_id") or proposal.get("instrument_name") or "operator")
    proxy = snap.get("proxy_baskets") if isinstance(snap.get("proxy_baskets"), dict) else {}
    active = proxy.get("active_basket") if isinstance(proxy.get("active_basket"), dict) else {}
    bucket = str(active.get("end_date") or int(time.time() // 86400))
    active_id = str(sheet.get("active_proxy_basket_id") or active.get("basket_id") or "basket")
    key = f"operator-signal:{proposal_id}:{bucket}:{action}:{active_id}"
    lines = [
        "Operator signal update",
        *_operator_signal_lines(snap, row_limit=4),
        "No raw REJECT/DEFER/watchlist rows are included in this channel update.",
        "Mini App: https://power.botozen.com/tg",
    ]
    return key, "\n".join(line for line in lines if line)


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
    operator_message = _operator_signal_message(snap)
    operator_action = str(_operator_signal_sheet(snap).get("overall_action") or "").upper()
    if operator_message and not (mock_message and operator_action.startswith("BUY")):
        out.append(operator_message)
    return out


def notify_channel_about_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    if CHANNEL_ABOUT_KEY in sent:
        return 0
    send_channel_post(channel_id, CHANNEL_ABOUT_KEY, channel_about_message(), logs=logs)
    _mark_sent(CHANNEL_ABOUT_KEY, logs=logs)
    return 1


def notify_channel_feedback_update_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    if CHANNEL_FEEDBACK_UPDATE_KEY in sent:
        return 0
    send_channel_post(channel_id, CHANNEL_FEEDBACK_UPDATE_KEY, channel_feedback_update_message(), logs=logs)
    _mark_sent(CHANNEL_FEEDBACK_UPDATE_KEY, logs=logs)
    return 1


def notify_channel_market_data_update_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    if CHANNEL_MARKET_DATA_UPDATE_KEY in sent:
        return 0
    send_channel_post(channel_id, CHANNEL_MARKET_DATA_UPDATE_KEY, channel_market_data_update_message(), logs=logs)
    _mark_sent(CHANNEL_MARKET_DATA_UPDATE_KEY, logs=logs)
    return 1


def notify_channel_instrument_menu_update_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    if CHANNEL_INSTRUMENT_MENU_UPDATE_KEY in sent:
        return 0
    send_channel_post(channel_id, CHANNEL_INSTRUMENT_MENU_UPDATE_KEY, channel_instrument_menu_update_message(), logs=logs)
    _mark_sent(CHANNEL_INSTRUMENT_MENU_UPDATE_KEY, logs=logs)
    return 1


def notify_channel_profitability_update_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    if CHANNEL_PROFITABILITY_UPDATE_KEY in sent:
        return 0
    send_channel_post(channel_id, CHANNEL_PROFITABILITY_UPDATE_KEY, channel_profitability_update_message(), logs=logs)
    _mark_sent(CHANNEL_PROFITABILITY_UPDATE_KEY, logs=logs)
    return 1


def notify_channel_miniapp_update_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    if CHANNEL_MINIAPP_UPDATE_KEY in sent:
        return 0
    send_channel_post(channel_id, CHANNEL_MINIAPP_UPDATE_KEY, channel_miniapp_update_message(), logs=logs)
    _mark_sent(CHANNEL_MINIAPP_UPDATE_KEY, logs=logs)
    return 1


def notify_channel_miniapp_release_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    posted = 0
    for key, text in channel_miniapp_release_messages():
        if key in sent:
            continue
        send_channel_post(channel_id, key, text, logs=logs)
        _mark_sent(key, logs=logs)
        posted += 1
    return posted


def notify_channel_signal_discipline_update_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    if CHANNEL_SIGNAL_DISCIPLINE_UPDATE_KEY in sent:
        return 0
    send_channel_post(channel_id, CHANNEL_SIGNAL_DISCIPLINE_UPDATE_KEY, channel_signal_discipline_update_message(), logs=logs)
    _mark_sent(CHANNEL_SIGNAL_DISCIPLINE_UPDATE_KEY, logs=logs)
    return 1


def notify_channel_oracle_discipline_update_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    if CHANNEL_ORACLE_DISCIPLINE_UPDATE_KEY in sent:
        return 0
    send_channel_post(channel_id, CHANNEL_ORACLE_DISCIPLINE_UPDATE_KEY, channel_oracle_discipline_update_message(), logs=logs)
    _mark_sent(CHANNEL_ORACLE_DISCIPLINE_UPDATE_KEY, logs=logs)
    return 1


def notify_channel_basis_spread_update_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    if CHANNEL_BASIS_SPREAD_UPDATE_KEY in sent:
        return 0
    send_channel_post(channel_id, CHANNEL_BASIS_SPREAD_UPDATE_KEY, channel_basis_spread_update_message(), logs=logs)
    _mark_sent(CHANNEL_BASIS_SPREAD_UPDATE_KEY, logs=logs)
    return 1


def notify_channel_index_tradeability_update_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    if CHANNEL_INDEX_TRADEABILITY_UPDATE_KEY in sent:
        return 0
    snap = campaign_snapshot_for_messaging(logs=logs)
    send_channel_post(channel_id, CHANNEL_INDEX_TRADEABILITY_UPDATE_KEY, channel_index_tradeability_update_message(snap), logs=logs)
    _mark_sent(CHANNEL_INDEX_TRADEABILITY_UPDATE_KEY, logs=logs)
    return 1


def notify_channel_campaign_once(*, logs: Path | str | None = None) -> int:
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        return 0
    sent = _sent_keys(logs=logs)
    count = 0
    snap = campaign_snapshot_for_messaging(logs=logs)
    for key, text in channel_campaign_messages(snap):
        if key in sent:
            continue
        send_channel_post(channel_id, key, text, logs=logs)
        _mark_sent(key, logs=logs)
        count += 1
    return count


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
        send_channel_post(channel_id, key, text, logs=logs)
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
    parser.add_argument("--post-instrument-menu-update", action="store_true", help="Post the deduped index/spread/instrument menu update")
    parser.add_argument("--post-profitability-update", action="store_true", help="Post the deduped profitability-ledger channel update")
    parser.add_argument("--post-miniapp-update", action="store_true", help="Post the deduped Telegram Mini App account/portfolio update")
    parser.add_argument("--draft-miniapp-release", action="store_true", help="Print the five-post Mini App screenshot release deck")
    parser.add_argument("--post-miniapp-release", action="store_true", help="Post the deduped five-post Mini App screenshot release deck")
    parser.add_argument("--post-signal-discipline-update", action="store_true", help="Post the deduped signal-discipline/profitability update")
    parser.add_argument("--post-oracle-discipline-update", action="store_true", help="Post the deduped Opoint/Nebius evidence-discipline update")
    parser.add_argument("--post-basis-spread-update", action="store_true", help="Post the deduped regional basis spread update")
    parser.add_argument("--post-index-tradeability-update", action="store_true", help="Post the deduped index-tradeability update")
    parser.add_argument("--draft-campaign", action="store_true", help="Print the four-post Telegram campaign draft without sending")
    parser.add_argument("--post-campaign", action="store_true", help="Post the deduped four-post Telegram campaign")
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
    if args.post_instrument_menu_update:
        print(notify_channel_instrument_menu_update_once())
        return 0
    if args.post_profitability_update:
        print(notify_channel_profitability_update_once())
        return 0
    if args.post_miniapp_update:
        print(notify_channel_miniapp_update_once())
        return 0
    if args.draft_miniapp_release:
        print(channel_miniapp_release_draft_text())
        return 0
    if args.post_miniapp_release:
        print(notify_channel_miniapp_release_once())
        return 0
    if args.post_signal_discipline_update:
        print(notify_channel_signal_discipline_update_once())
        return 0
    if args.post_oracle_discipline_update:
        print(notify_channel_oracle_discipline_update_once())
        return 0
    if args.post_basis_spread_update:
        print(notify_channel_basis_spread_update_once())
        return 0
    if args.post_index_tradeability_update:
        print(notify_channel_index_tradeability_update_once())
        return 0
    if args.draft_campaign:
        snap = campaign_snapshot_for_messaging()
        text = channel_campaign_draft_text(snap)
        print(text)
        return 0
    if args.post_campaign:
        print(notify_channel_campaign_once())
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
