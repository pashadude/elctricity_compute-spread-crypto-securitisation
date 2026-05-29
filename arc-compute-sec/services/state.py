"""Read-only, sanitized backend state for API, worker, and Telegram.

This module intentionally reads only public runtime artifacts. It never exposes
`logs/identity.tsv`, wallet IDs, entity secrets, or `.env` values.
"""
from __future__ import annotations

import csv
import concurrent.futures
import copy
import functools
import json
import os
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from services.env import load_project_env
from agent.synthetic_instrument import propose_synthetic_instrument
from agent import spread_family_backtest
from agent import proxy_basket_backtest
from adapters.yahoo_finance import fetch_chart_quote, fetch_chart_history
from contracts.arc_addresses import EXPLORER
from feeds import cache
from templates.energy.classifier import classify_energy

load_project_env()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_FRONTEND_DIR = REPO_ROOT / "frontend"
KNOWN_PUBLIC_SURFACES = {"polymarket", "ibkr_prediction", "ibkr", "crypto", "kalshi"}
DEFAULT_IBKR_DIRECT_EVENT_SYMBOLS = ("RETXC", "ITNVD", "CRUDB", "NGP")
DEFAULT_POLYMARKET_DIRECT_EVENT_SLUGS = (
    "ai-data-center-moratorium-passed-before-2027",
    "ai-bubble-burst-by",
)
DEFAULT_KALSHI_DIRECT_EVENT_TERMS = (
    "ai",
    "artificial intelligence",
    "openai",
    "anthropic",
    "nvidia",
    "gpu",
    "llm",
    "agi",
    "data center",
    "compute",
)
DEFAULT_PUBLIC_HEDGE_SYMBOLS = ("NVDA", "VRT", "ETN", "CEG", "NRG", "BTC-USD", "ETH-USD")
DEFAULT_PUBLIC_HEDGE_PRICE_SOURCES = ("yahoo",)
PRICED_STATUS_VALUES = {"priced_watchlist", "priced_public_market", "priced_close_history"}
DEFAULT_IBKR_FORECAST_PROXY_PRICE_SOURCES = ("ibkr", "yahoo")
DEFAULT_PROXY_BASKET_HISTORY_RANGE = "6mo"
DEFAULT_PROXY_BASKET_HISTORY_INTERVAL = "1d"
TELEGRAM_SENT_NAME = "telegram_sent.jsonl"
TELEGRAM_CAMPAIGN_POSTS = (
    ("channel-campaign:v1:indexes-spreads", "Index layer", "Electricity/compute indexes and oil-style spread forms."),
    ("channel-campaign:v1:profitability", "Profitability discipline", "Backtested spread replay and paper-ticket PnL."),
    ("channel-campaign:v1:venue-copy", "Real venue roles", "Polymarket/Kalshi/IBKR/direct legs versus public/crypto proxies."),
    ("channel-campaign:v1:arc-collateral", "Securitization shape", "Collateral, Arc wrapper, and judge-before-Arc guardrail."),
)
TELEGRAM_MINIAPP_RELEASE_POSTS = (
    ("channel-miniapp-release:v1:home", "User path", "Home screen with status, notional, Circle ask, Operator account state, and walkthrough."),
    ("channel-miniapp-release:v1:contract", "Mock contract", "Trade surface with spread metrics, weighted legs, buy/monitor/sell recommendation, and judge gate."),
    ("channel-miniapp-release:v1:portfolio", "Account and PnL", "Server-side account, wallet label, open tickets, realized ledger, and net paper PnL."),
    ("channel-miniapp-release:v1:profitability", "Profitability discipline", "Paper-ticket replay, latest mark PnL, OOS state, and buy/avoid labels."),
    ("channel-miniapp-release:v1:scouting", "Venue scouting", "Venue role matrix for Polymarket, Kalshi, IBKR, public quotes, crypto, and Opoint/Nebius evidence."),
)
IBKR_FORECAST_SYMBOL_META: dict[str, dict[str, str]] = {
    "RETXC": {
        "title": "Texas Commercial Electricity Generation Sales Revenue",
        "description": "IBKR ForecastTrader electricity revenue contract used as an energy/grid-stress leg.",
        "pair_role": "energy/grid-stress leg",
        "direction": "long",
    },
    "ITNVD": {
        "title": "NVIDIA Inference vs. Training Revenue",
        "description": "IBKR ForecastTrader AI infrastructure contract used as the compute-demand leg.",
        "pair_role": "AI compute-demand leg",
        "direction": "short",
    },
    "CRUDB": {
        "title": "Brent Crude Oil Price",
        "description": "IBKR ForecastTrader crude contract used as an energy input-cost leg.",
        "pair_role": "energy input-cost leg",
        "direction": "long",
    },
    "NGP": {
        "title": "US Natural Gas Production",
        "description": "IBKR ForecastTrader natural-gas contract used as a power-stack supply leg.",
        "pair_role": "power fuel-supply leg",
        "direction": "long",
    },
    "FF": {
        "title": "US Fed Funds Target Rate",
        "description": "IBKR ForecastTrader macro-rate contract. This is context, not a direct compute/energy leg.",
        "pair_role": "macro context",
        "direction": "watch",
        "leg_role": "macro_context_forecast",
    },
}
IBKR_FORECAST_PROXY_META: dict[str, dict[str, str]] = {
    "RETXC": {
        "symbol": "NRG",
        "title": "NRG Energy",
        "role": "merchant power external proxy",
    },
    "ITNVD": {
        "symbol": "NVDA",
        "title": "NVIDIA",
        "role": "AI compute-demand external proxy",
    },
    "CRUDB": {
        "symbol": "BZ=F",
        "title": "Brent crude futures",
        "role": "energy input-cost external proxy",
    },
    "NGP": {
        "symbol": "NG=F",
        "title": "Henry Hub natural gas futures",
        "role": "power-stack fuel external proxy",
    },
    "FF": {
        "symbol": "ZQ=F",
        "title": "30-day Fed Funds futures",
        "role": "macro-rate external proxy",
    },
}
POLYMARKET_WATCHLIST_META: dict[str, dict[str, str]] = {
    "ai-data-center-moratorium-passed-before-2027": {
        "title": "AI data center moratorium passed before 2027?",
        "description": (
            "Polymarket event on whether US AI data-center construction or expansion "
            "is blocked by a qualifying moratorium before 2027. Used as a grid-stress "
            "and power-siting policy leg."
        ),
        "end_date": "2026-12-31T00:00:00Z",
        "pair_role": "energy/grid-stress leg",
        "direction": "long",
    },
    "ai-bubble-burst-by": {
        "title": "AI bubble burst by...?",
        "description": (
            "Polymarket event on AI-industry downturn conditions, including NVIDIA, "
            "H100 rental prices, and major AI hardware suppliers. Used as a "
            "compute-demand stress leg."
        ),
        "end_date": "2026-12-31T00:00:00Z",
        "pair_role": "AI compute-demand leg",
        "direction": "short",
    },
}
PUBLIC_HEDGE_META: dict[str, dict[str, str]] = {
    "NVDA": {
        "title": "NVIDIA",
        "role": "AI compute-demand equity proxy",
        "direction": "long_compute_short_power",
        "description": "Public equity proxy for GPU demand and AI infrastructure capex.",
    },
    "VRT": {
        "title": "Vertiv",
        "role": "data-center power/cooling infrastructure proxy",
        "direction": "long_compute_load_growth",
        "description": "Public equity proxy for data-center power, cooling, and electrical infrastructure demand.",
    },
    "ETN": {
        "title": "Eaton",
        "role": "grid/electrification equipment proxy",
        "direction": "long_grid_upgrade_demand",
        "description": "Public equity proxy for electrification and grid equipment demand.",
    },
    "CEG": {
        "title": "Constellation Energy",
        "role": "nuclear baseload power proxy",
        "direction": "long_clean_baseload_power",
        "description": "Public equity proxy for nuclear-heavy baseload power exposed to data-center procurement.",
    },
    "NRG": {
        "title": "NRG Energy",
        "role": "merchant power proxy",
        "direction": "long_power_price_exposure",
        "description": "Public equity proxy for merchant power exposure and retail load sensitivity.",
    },
    "BTC-USD": {
        "title": "Bitcoin",
        "role": "miner-margin proxy",
        "direction": "short_when_power_expensive",
        "description": "Liquid proxy for proof-of-work miner margin sensitivity to electricity costs.",
    },
    "ETH-USD": {
        "title": "Ether",
        "role": "crypto beta proxy",
        "direction": "watch",
        "description": "Liquid crypto proxy retained for beta context; not a direct power claim.",
    },
}

SENSITIVE_FIELD_MARKERS = (
    "wallet",
    "secret",
    "entity",
    "api_key",
    "apikey",
    "token",
    "user_id",
    "private",
    "mnemonic",
    "seed",
)
_COMPACT_SNAPSHOT_LOCK = threading.RLock()
_COMPACT_SNAPSHOT_BUILD_LOCK = threading.Lock()
_COMPACT_SNAPSHOT_CACHE: tuple[float, str, dict[str, Any]] | None = None


def log_dir(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return Path(os.environ.get("ARC_LOG_DIR") or os.environ.get("LOG_DIR") or DEFAULT_LOG_DIR)


def frontend_dir(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return Path(os.environ.get("FRONTEND_DIR") or DEFAULT_FRONTEND_DIR)


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _is_sensitive_key(key: str) -> bool:
    low = key.lower()
    return any(marker in low for marker in SENSITIVE_FIELD_MARKERS)


def _coerce_value(value: str) -> Any:
    if value == "":
        return ""
    text = value.strip()
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return value


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_value(inner)
            for key, inner in value.items()
            if key is not None and not _is_sensitive_key(str(key))
        }
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _coerce_value(value)
    return value


def sanitize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key is None or _is_sensitive_key(str(key)):
            continue
        out[str(key)] = _sanitize_value(value)
    tx_hash = out.get("tx_hash")
    if isinstance(tx_hash, str) and tx_hash.startswith("0x"):
        out["arcscan_url"] = f"{EXPLORER}/tx/{tx_hash}"
    return out


def read_tsv(name: str, *, limit: int | None = None, logs: Path | str | None = None) -> list[dict[str, Any]]:
    if "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"invalid log name: {name!r}")
    if name == "identity.tsv":
        raise ValueError("identity.tsv is private runtime state and is not API-readable")
    path = log_dir(logs) / name
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as fh:
        rows = [sanitize_row(row) for row in csv.DictReader(fh, delimiter="\t")]
    if limit is None:
        return rows
    return rows[-limit:]


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def read_jsonl(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                text = line.strip()
                if not text:
                    continue
                try:
                    decoded = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(decoded, dict):
                    rows.append(sanitize_row(decoded))
    except OSError:
        return []
    if limit is None:
        return rows
    return rows[-limit:]


def latest_row(name: str, *, logs: Path | str | None = None) -> dict[str, Any] | None:
    rows = read_tsv(name, limit=1, logs=logs)
    return rows[-1] if rows else None


def _latest_first(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list(reversed(rows))


def _maybe_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return []
        return decoded if isinstance(decoded, list) else []
    return []


def _as_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:
        return None
    return out


def _coerce_price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if 0.0 <= price <= 1.0:
        return price
    return None


def _event_yes_prices(event: dict[str, Any]) -> list[float]:
    prices: list[float] = []
    for raw in event.get("markets") or []:
        if not isinstance(raw, dict):
            continue
        price = None
        for key in ("outcomePrice", "lastPrice", "price", "bestBid", "lastTradePrice"):
            price = _coerce_price(raw.get(key))
            if price is not None:
                break
        if price is None:
            outcome_prices = _maybe_json_list(raw.get("outcomePrices"))
            outcomes = _maybe_json_list(raw.get("outcomes"))
            yes_idx = 0
            for idx, outcome in enumerate(outcomes):
                if str(outcome).strip().lower() == "yes":
                    yes_idx = idx
                    break
            if yes_idx < len(outcome_prices):
                price = _coerce_price(outcome_prices[yes_idx])
        if price is not None:
            prices.append(price)
    return prices


def _polymarket_event_summary(event: dict[str, Any]) -> dict[str, Any]:
    event_id = str(event.get("id") or "")
    slug = str(event.get("slug") or "")
    return {
        "id": event_id,
        "slug": slug,
        "title": str(event.get("title") or event.get("question") or slug or event_id),
        "description": str(event.get("description") or ""),
        "start_date": str(event.get("startDate") or event.get("start_date") or ""),
        "end_date": str(event.get("endDate") or event.get("end_date") or ""),
        "active": bool(event.get("active", False)),
        "closed": bool(event.get("closed", False)),
        "volume": event.get("volume") or event.get("volumeNum") or "",
        "liquidity": event.get("liquidity") or event.get("liquidityNum") or "",
        "yes_prices": _event_yes_prices(event),
    }


@functools.lru_cache(maxsize=256)
def _fetch_polymarket_event(key: str) -> dict[str, Any] | None:
    key = str(key or "").strip()
    if not key or key.startswith("mock"):
        return None
    if key.isdigit():
        path = key
    else:
        path = f"slug/{urllib.parse.quote(key, safe='')}"
    url = f"https://gamma-api.polymarket.com/events/{path}"
    req = urllib.request.Request(
        url,
        headers={"accept": "application/json", "user-agent": "arc-compute-sec/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            event = json.loads(resp.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    if isinstance(event, dict):
        return _polymarket_event_summary(event)
    return None


def _polymarket_cache_event_index(*, logs: Path | str | None = None) -> dict[str, dict[str, Any]]:
    path = log_dir(logs) / "_feed_cache.sqlite"
    if not path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(path))
        rows = conn.execute(
            "SELECT value FROM cache WHERE ns = ? ORDER BY expires_at DESC",
            ("polymarket_events",),
        ).fetchall()
        conn.close()
    except sqlite3.DatabaseError:
        return {}
    index: dict[str, dict[str, Any]] = {}
    for (raw_value,) in rows:
        try:
            events = json.loads(raw_value)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            summary = _polymarket_event_summary(event)
            event_id = summary["id"]
            slug = summary["slug"]
            for key in (event_id, slug, f"polymarket:{event_id}" if event_id else ""):
                if key and key not in index:
                    index[key] = summary
    return index


def _instrument_lookup_key(row: dict[str, Any]) -> str:
    instrument = str(row.get("instrument") or "")
    if instrument.startswith("polymarket:"):
        return instrument.split(":", 2)[1]
    if instrument.startswith("kalshi:"):
        return instrument.split(":", 2)[1]
    return instrument


def _fallback_leg_role(surface: str) -> str:
    return {
        "polymarket": "direct_prediction_event",
        "ibkr_prediction": "direct_prediction_event",
        "kalshi": "direct_prediction_event",
        "crypto": "miner_margin_proxy",
        "ibkr": "liquid_equity_proxy",
    }.get(surface, "expression_leg")


def _leg_connection(surface: str, role: str) -> str:
    if surface in {"polymarket", "ibkr_prediction", "kalshi"} or role == "direct_prediction_event":
        return (
            "Direct event leg: the package pairs energy/grid-stress outcomes "
            "against AI compute-demand outcomes, so this event is one side of "
            "the judged spread expression."
        )
    if role == "macro_context_forecast":
        return (
            "Context forecast only: macro event contracts can condition sizing "
            "or risk review, but they are not the securitized compute/energy leg."
        )
    if surface == "crypto" or role == "miner_margin_proxy":
        return (
            "Proxy leg only: BTC/ETH are used for miner-margin stress because "
            "mining revenue is crypto-linked while electricity is the main "
            "variable cost."
        )
    if surface == "ibkr" or role == "liquid_equity_proxy":
        return (
            "Proxy leg only: the equity leg reflects compute/energy margin "
            "sensitivity and is not the direct securitized outcome."
        )
    return "Expression leg in the canonical compute/energy spread package."


def _is_mock_leg(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(key) or "").lower()
        for key in ("instrument", "leg_title", "leg_slug", "display_label")
    )
    return "mock" in text


def _is_legacy_artifact(row: dict[str, Any]) -> bool:
    surface = str(row.get("surface") or "")
    display = str(row.get("display_label") or "")
    return surface not in KNOWN_PUBLIC_SURFACES or display == "unknown leg"


def _is_thesis_mismatch(row: dict[str, Any]) -> bool:
    surface = str(row.get("surface") or "")
    role = str(row.get("leg_role") or "")
    if row.get("is_mock") or role != "direct_prediction_event":
        return False
    if surface not in {"polymarket", "ibkr_prediction", "kalshi"}:
        return False
    title = str(row.get("leg_title") or row.get("display_label") or row.get("instrument") or "")
    description = str(row.get("leg_description") or "")
    return classify_energy(title, description) is None


def _enrich_leg_rows(rows: list[dict[str, Any]], *, logs: Path | str | None = None) -> list[dict[str, Any]]:
    event_index = _polymarket_cache_event_index(logs=logs)
    for row in rows:
        surface = str(row.get("surface") or "")
        event = None
        if surface == "polymarket":
            for key in (
                str(row.get("leg_slug") or ""),
                _instrument_lookup_key(row),
                str(row.get("instrument") or ""),
            ):
                event = event_index.get(key)
                if event:
                    break
            if not event:
                should_fetch = not row.get("inventory") or bool_env("POLYMARKET_DIRECT_EVENT_FETCH", False)
                if should_fetch:
                    event = _fetch_polymarket_event(_instrument_lookup_key(row))
        if event:
            row["leg_title"] = row.get("leg_title") or event.get("title", "")
            row["leg_slug"] = row.get("leg_slug") or event.get("slug", "")
            row["leg_description"] = row.get("leg_description") or event.get("description", "")
            row["leg_end_date"] = row.get("leg_end_date") or event.get("end_date", "")
        role = str(row.get("leg_role") or _fallback_leg_role(surface))
        row["leg_role"] = role
        row["leg_connection"] = _leg_connection(surface, role)
        row["display_label"] = row.get("leg_title") or row.get("instrument") or "unknown leg"
        row["is_mock"] = _is_mock_leg(row)
        row["is_legacy_artifact"] = _is_legacy_artifact(row)
        row["is_thesis_mismatch"] = _is_thesis_mismatch(row)
    return rows


def spread_state(*, logs: Path | str | None = None, limit: int = 120) -> dict[str, Any]:
    rows = read_tsv("spread_history.tsv", limit=limit, logs=logs)
    latest = dict(rows[-1]) if rows else None
    history: list[float] = []
    for row in rows:
        try:
            history.append(float(row.get("S_t", 0.0)))
        except (TypeError, ValueError):
            continue
    source_rows = read_jsonl(log_dir(logs) / "spread_mark_sources.jsonl", limit=1)
    source = source_rows[-1] if source_rows else {}
    if latest and source:
        latest.update({
            "electricity_source": source.get("electricity_source", ""),
            "electricity_source_status": source.get("electricity_source_status", ""),
            "electricity_base_per_mwh": source.get("electricity_base_per_mwh", ""),
            "electricity_proxy_weighted_return_pct": source.get("electricity_proxy_weighted_return_pct", ""),
            "electricity_proxy_symbols": source.get("electricity_proxy_symbols", []),
            "electricity_proxy_used_quotes": source.get("electricity_proxy_used_quotes", ""),
            "electricity_proxy_quote_sources": source.get("electricity_proxy_quote_sources", []),
            "electricity_proxy_formula": source.get("electricity_proxy_formula", ""),
            "eia_period": source.get("eia_period", ""),
            "compute_source": source.get("compute_source", ""),
            "compute_instance": source.get("compute_instance", ""),
            "compute_region": source.get("compute_region", ""),
            "power_cost_per_gpu_hr": source.get("power_cost_per_gpu_hr", latest.get("power_cost_per_gpu_hr", "")),
            "power_cost_share": source.get("power_cost_share", latest.get("power_cost_share", "")),
            "power_cost_share_pct": source.get("power_cost_share_pct", latest.get("power_cost_share_pct", "")),
        })
    if latest:
        compute = _as_float(latest.get("compute_per_gpu_hr"))
        elec = _as_float(latest.get("electricity_per_mwh"))
        k = _as_float(latest.get("k"))
        kwh = _as_float(latest.get("kwh_per_gpu_hr") or latest.get("kWh_per_gpu_hr"))
        if compute and elec and k and kwh and not latest.get("power_cost_per_gpu_hr"):
            power_cost = k * (elec / 1000.0) * kwh
            latest["power_cost_per_gpu_hr"] = round(power_cost, 6)
            latest["power_cost_share"] = round(power_cost / compute, 6) if compute > 0 else 0.0
            latest["power_cost_share_pct"] = round((power_cost / compute) * 100.0, 4) if compute > 0 else 0.0
        elif latest.get("power_cost_share") and not latest.get("power_cost_share_pct"):
            latest["power_cost_share_pct"] = round(_as_float(latest.get("power_cost_share")) * 100.0, 4)
    return {"latest": latest, "history": history, "mark_source": source}


def spread_family_state(*, logs: Path | str | None = None, limit: int = 720) -> dict[str, Any]:
    rows = read_tsv("spread_history.tsv", limit=limit, logs=logs)
    strategies = (
        spread_family_backtest.STRATEGY_MEAN_REVERSION,
        spread_family_backtest.STRATEGY_MOMENTUM,
    )
    recorded = spread_family_backtest.summarize(rows, strategy_modes=strategies)
    proxy_rows = read_tsv("spread_proxy_history.tsv", limit=limit, logs=logs)
    proxy = spread_family_backtest.summarize(proxy_rows, strategy_modes=strategies) if proxy_rows else None
    recorded_primary = recorded.get("primary_family") or {}
    proxy_primary = (proxy or {}).get("primary_family") or {}
    proxy_has_stronger_sample = (
        proxy
        and proxy.get("entry_gate_pass")
        and (
            not recorded.get("entry_gate_pass")
            or int(_as_float(proxy_primary.get("tested_trades")) or 0)
            > int(_as_float(recorded_primary.get("tested_trades")) or 0)
        )
    )
    chosen = proxy if proxy_has_stronger_sample else recorded
    source = "proxy_history" if chosen is proxy else "recorded_runtime_marks"
    out = dict(chosen)
    out["primary_source"] = source
    out["recorded_history_replay"] = recorded
    if proxy is not None:
        out["proxy_history_replay"] = proxy
    out["source_status"] = (
        "using public proxy history because recorded runtime marks are too flat"
        if source == "proxy_history"
        else "using recorded runtime marks"
    )
    return out


def _proxy_basket_report_path(*, logs: Path | str | None = None) -> Path:
    return log_dir(logs) / "proxy_basket_backtest.json"


def _fetch_yahoo_history_cached(
    symbol: str,
    *,
    range_name: str = DEFAULT_PROXY_BASKET_HISTORY_RANGE,
    interval: str = DEFAULT_PROXY_BASKET_HISTORY_INTERVAL,
) -> dict[str, Any] | None:
    clean = str(symbol or "").strip().upper()
    if not clean:
        return None
    key = f"{range_name}|{interval}|{clean}"
    cached = cache.get("yahoo_history", key)
    if isinstance(cached, dict):
        return cached
    timeout = _num_env("PROXY_BASKET_HISTORY_TIMEOUT", 2.5)
    try:
        history = fetch_chart_history(clean, range=range_name, interval=interval, timeout=timeout)
    except Exception as exc:
        history = {"symbol": clean, "points": [], "source": "yahoo_finance_chart", "error": exc.__class__.__name__}
    if isinstance(history, dict):
        cache.put("yahoo_history", key, history, ttl_seconds=int(_num_env("PROXY_BASKET_HISTORY_CACHE_SECONDS", 21_600)))
        return history
    return None


def _num_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def proxy_basket_state(*, logs: Path | str | None = None) -> dict[str, Any]:
    saved = read_json(_proxy_basket_report_path(logs=logs), default={})
    if isinstance(saved, dict) and saved.get("version") == "proxy_basket_replay_v1":
        return saved
    if not bool_env("PROXY_BASKET_BACKTEST_FETCH", False):
        out = proxy_basket_backtest.summarize({})
        out["fetch_enabled"] = False
        out["status_reason"] = "Set PROXY_BASKET_BACKTEST_FETCH=1 or run npm run proxy:backtest to load Yahoo close-history replay."
        return out
    range_name = os.environ.get("PROXY_BASKET_HISTORY_RANGE", DEFAULT_PROXY_BASKET_HISTORY_RANGE)
    interval = os.environ.get("PROXY_BASKET_HISTORY_INTERVAL", DEFAULT_PROXY_BASKET_HISTORY_INTERVAL)
    histories = {
        symbol: history
        for symbol in proxy_basket_backtest.required_symbols()
        if (history := _fetch_yahoo_history_cached(symbol, range_name=range_name, interval=interval))
    }
    out = proxy_basket_backtest.summarize(histories)
    out["fetch_enabled"] = True
    out["history_range"] = range_name
    out["history_interval"] = interval
    return out


def _proxy_basket_entry_gate(basket: dict[str, Any], fallback: Any = None) -> bool | None:
    if not basket:
        return bool(fallback) if fallback is not None else None
    if "is_promotable" in basket:
        return bool(basket.get("is_promotable"))
    status = str(basket.get("status") or "")
    if status:
        return status == "PROMOTABLE"
    return bool(fallback) if fallback is not None else None


def select_proxy_basket_for_direction(proxy_baskets: dict[str, Any], direction: str) -> tuple[dict[str, Any], bool | None]:
    validation = proxy_baskets if isinstance(proxy_baskets, dict) else {}
    primary = validation.get("primary_basket") if isinstance(validation.get("primary_basket"), dict) else {}
    baskets = [basket for basket in validation.get("baskets") or [] if isinstance(basket, dict)]
    if primary and all(basket.get("basket_id") != primary.get("basket_id") for basket in baskets):
        baskets.append(primary)

    clean_direction = str(direction or "").strip()
    if clean_direction and clean_direction != "no_signal":
        for basket in baskets:
            if str(basket.get("direction") or "").strip() == clean_direction:
                return basket, _proxy_basket_entry_gate(basket)
        if primary and not str(primary.get("direction") or "").strip():
            return primary, _proxy_basket_entry_gate(primary, validation.get("entry_gate_pass"))
        if baskets or primary:
            return {
                "basket_id": "no_direction_matched_proxy_basket",
                "direction": clean_direction,
                "label": "No direction-matched proxy basket",
                "status": "DIRECTION_MISMATCH",
                "status_reason": f"No proxy basket replay matched the active {clean_direction} signal.",
                "recommendation": "MONITOR_ONLY",
                "latest_signal": "MONITOR",
                "signal_reason": "Proxy replay is available, but not for the active spread direction.",
                "trailing_returns": {},
                "total_return_pct": 0,
                "win_rate": 0,
                "max_drawdown_pct": 0,
            }, False
    return primary, _proxy_basket_entry_gate(primary, validation.get("entry_gate_pass"))


def signal_state(*, logs: Path | str | None = None, limit: int = 25) -> dict[str, Any]:
    rows = read_tsv("arb_signals.tsv", limit=limit, logs=logs)
    return {"latest": rows[-1] if rows else None, "recent": _latest_first(rows)}


def verdict_state(*, logs: Path | str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    rows = read_tsv("judgements.tsv", limit=limit, logs=logs)
    return _latest_first(_enrich_leg_rows(rows, logs=logs))


def position_state(*, logs: Path | str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    rows = read_tsv("positions.tsv", limit=limit, logs=logs)
    for row in rows:
        stage = str(row.get("stage", ""))
        if "status" not in row:
            row["status"] = "completed" if stage == "settled" else stage or "unknown"
    return _latest_first(_enrich_leg_rows(rows, logs=logs))


def _env_csv(name: str, default: tuple[str, ...] = ()) -> list[str]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return list(default)
    return [part.strip() for part in raw.split(",") if part.strip()]


def _pricing_status_label(status: Any) -> str:
    low = str(status or "").strip().lower()
    if low == "unpriced_snapshot":
        return "Needs live venue price"
    if low == "ibkr_quote_unavailable":
        return "IBKR quote unavailable"
    if low == "metadata_watchlist":
        return "Metadata only"
    if low == "priced_watchlist":
        return "Live price available"
    if low == "priced_public_market":
        return "Public price available"
    if low == "priced_close_history":
        return "Close-history replay available"
    if low == "price_unavailable":
        return "Price unavailable"
    if low == "closed_watchlist":
        return "Closed"
    return str(status or "Needs review").replace("_", " ")


def _fetch_ibkr_public_quote(symbol: str) -> dict[str, Any] | None:
    clean = str(symbol or "").strip().upper()
    if not clean:
        return None
    if _docker_local_ibkr_host_misconfigured():
        return {
            "symbol": clean,
            "price": None,
            "source": "ibkr_tws",
            "error": "ibkr_host_points_to_container",
            "action": "Set IBKR_HOST=host.docker.internal for Docker, or remove ibkr from PUBLIC_HEDGE_PRICE_SOURCES.",
        }
    if not _ibkr_tws_socket_reachable():
        host, port = _ibkr_socket_target()
        return {
            "symbol": clean,
            "price": None,
            "source": "ibkr_tws",
            "error": "ibkr_tws_unreachable",
            "action": f"Start IBKR Gateway/TWS at {host}:{port}, or remove ibkr from PUBLIC_HEDGE_PRICE_SOURCES.",
        }
    try:
        from adapters.ibkr import fetch_public_quote

        quote = fetch_public_quote(clean)
    except Exception as exc:
        return {
            "symbol": clean,
            "price": None,
            "source": "ibkr_tws",
            "error": exc.__class__.__name__,
        }
    if not isinstance(quote, dict) or quote.get("price") is None:
        return None
    return quote


def _running_in_docker() -> bool:
    return Path("/.dockerenv").exists()


def _docker_local_ibkr_host_misconfigured() -> bool:
    host = os.environ.get("IBKR_HOST", "127.0.0.1").strip().lower()
    return _running_in_docker() and host in {"", "127.0.0.1", "localhost", "::1"}


def _ibkr_socket_target() -> tuple[str, int]:
    host = os.environ.get("IBKR_HOST", "127.0.0.1").strip() or "127.0.0.1"
    raw_port = os.environ.get("IBKR_GATEWAY_PORT") or os.environ.get("IBKR_PORT") or "4002"
    try:
        port = int(raw_port)
    except ValueError:
        port = 4002
    return host, port


def _ibkr_tws_socket_reachable() -> bool:
    host, port = _ibkr_socket_target()
    timeout = _num_env("IBKR_PUBLIC_QUOTE_CONNECT_TIMEOUT", 0.4)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _fetch_alpaca_public_quote(symbol: str) -> dict[str, Any] | None:
    clean = str(symbol or "").strip().upper()
    if not clean or "-" in clean:
        return None
    key = os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET")
    if not key or not secret:
        return None
    url = f"https://data.alpaca.markets/v2/stocks/{urllib.parse.quote(clean, safe='')}/trades/latest"
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "User-Agent": "arc-compute-sec/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        trade = data.get("trade") if isinstance(data, dict) else {}
        price = trade.get("p") if isinstance(trade, dict) else None
        if price is None:
            return None
        return {
            "symbol": clean,
            "price": float(price),
            "currency": "USD",
            "exchange": str(trade.get("x") or "alpaca"),
            "regular_market_time": str(trade.get("t") or ""),
            "source": "alpaca_market_data",
        }
    except Exception as exc:
        return {
            "symbol": clean,
            "price": None,
            "source": "alpaca_market_data",
            "error": exc.__class__.__name__,
        }


def _fetch_yahoo_public_quote(symbol: str) -> dict[str, Any] | None:
    try:
        return fetch_chart_quote(symbol, timeout=_num_env("PUBLIC_HEDGE_QUOTE_TIMEOUT", 2.0))
    except Exception as exc:
        return {
            "symbol": str(symbol or "").strip().upper(),
            "price": None,
            "source": "yahoo_finance_chart",
            "error": exc.__class__.__name__,
        }


def _fetch_public_quote(symbol: str, sources: list[str] | tuple[str, ...] | None = None) -> dict[str, Any] | None:
    cache_key = str(symbol or "").strip().upper()
    if not cache_key:
        return None
    selected_sources = [
        item.lower()
        for item in (
            list(sources)
            if sources is not None
            else _env_csv("PUBLIC_HEDGE_PRICE_SOURCES", DEFAULT_PUBLIC_HEDGE_PRICE_SOURCES)
        )
    ]
    source_key = ",".join(selected_sources) or "yahoo"
    cached = cache.get("public_quote", f"{source_key}|{cache_key}")
    if isinstance(cached, dict):
        return cached
    quote: dict[str, Any] | None = None
    errors: list[str] = []
    for source in selected_sources:
        if source == "ibkr":
            quote = _fetch_ibkr_public_quote(cache_key)
        elif source == "alpaca":
            quote = _fetch_alpaca_public_quote(cache_key)
        elif source == "yahoo":
            quote = _fetch_yahoo_public_quote(cache_key)
        else:
            errors.append(f"{source}:unsupported")
            quote = None
        if isinstance(quote, dict) and quote.get("price") is not None:
            quote["source_priority"] = source_key
            if errors:
                quote["fallback_errors"] = errors[:4]
            cache.put("public_quote", f"{source_key}|{cache_key}", quote, ttl_seconds=900)
            return quote
        if isinstance(quote, dict) and quote.get("error"):
            errors.append(f"{quote.get('source')}:{quote.get('error')}")
    if quote is None:
        quote = {"symbol": cache_key, "price": None, "source": source_key}
    if errors:
        quote["fallback_errors"] = errors[:4]
    cache.put("public_quote", f"{source_key}|{cache_key}", quote, ttl_seconds=300)
    return quote


def _worker_count(name: str, default: int, item_count: int) -> int:
    if item_count <= 1:
        return 1
    raw = os.environ.get(name, "").strip()
    try:
        configured = int(raw) if raw else default
    except ValueError:
        configured = default
    return max(1, min(item_count, configured))


def public_hedge_state(*, logs: Path | str | None = None) -> list[dict[str, Any]]:
    """Priced public-market proxies used when direct event contracts are unpriced.

    These are not direct claims on compute or electricity. They are liquid,
    priced hedge references for the commercial compute-sale package.
    """
    fetch_live = bool_env("PUBLIC_HEDGE_FETCH", True)
    symbols = [symbol.strip().upper() for symbol in _env_csv("PUBLIC_HEDGE_SYMBOLS", DEFAULT_PUBLIC_HEDGE_SYMBOLS)]
    symbols = [symbol for symbol in symbols if symbol]

    def build_row(clean: str) -> dict[str, Any]:
        now = time.time()
        meta = PUBLIC_HEDGE_META.get(clean, {})
        quote = _fetch_public_quote(clean) if fetch_live else None
        price = quote.get("price") if isinstance(quote, dict) else None
        return sanitize_row({
            "ts": now,
            "surface": "public_market",
            "instrument": clean,
            "leg_slug": clean,
            "leg_title": meta.get("title") or clean,
            "display_label": meta.get("title") or clean,
            "leg_role": "priced_public_hedge",
            "direct_pair_role": meta.get("role") or "public hedge proxy",
            "direction": meta.get("direction") or "watch",
            "label": "PRICED" if price is not None else "PRICE_MISSING",
            "pricing_status": "priced_public_market" if price is not None else "price_unavailable",
            "pricing_status_label": _pricing_status_label("priced_public_market" if price is not None else "price_unavailable"),
            "last_price": price if price is not None else "",
            "currency": quote.get("currency", "") if isinstance(quote, dict) else "",
            "exchange": quote.get("exchange", "") if isinstance(quote, dict) else "",
            "source": quote.get("source", "yahoo_finance_chart") if isinstance(quote, dict) else "yahoo_finance_chart",
            "source_priority": quote.get("source_priority", "") if isinstance(quote, dict) else "",
            "leg_description": meta.get("description") or "",
            "inventory": True,
        })

    if not symbols:
        return []
    if fetch_live:
        workers = _worker_count("PUBLIC_HEDGE_FETCH_WORKERS", 6, len(symbols))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(build_row, symbols))
    return [build_row(symbol) for symbol in symbols]


def _forecast_inventory_path(*, logs: Path | str | None = None) -> Path:
    return log_dir(logs) / "ibkr_forecast_inventory.json"


def _read_ibkr_forecast_inventory(*, logs: Path | str | None = None) -> dict[str, dict[str, Any]]:
    data = read_json(_forecast_inventory_path(logs=logs), default={})
    if isinstance(data, dict):
        raw_events = data.get("events") or []
    elif isinstance(data, list):
        raw_events = data
    else:
        raw_events = []
    out: dict[str, dict[str, Any]] = {}
    for event in raw_events:
        if not isinstance(event, dict):
            continue
        symbol = str(event.get("symbol") or "").strip().upper()
        if not symbol:
            slug = str(event.get("slug") or "")
            symbol = slug.split("-", 1)[0].upper()
        if symbol and symbol not in out:
            out[symbol] = event
    return out


def _inventory_sizing(surface: str) -> str:
    if surface == "ibkr_prediction":
        env_name = "SIZING_IBKR_PREDICTION_USDC"
    elif surface == "kalshi":
        env_name = "SIZING_KALSHI_USDC"
    else:
        env_name = "SIZING_POLYMARKET_USDC"
    return str(os.environ.get(env_name, "1.0"))


def _ibkr_forecast_proxy_meta(symbol: str) -> dict[str, str]:
    clean = str(symbol or "").strip().upper()
    meta = dict(IBKR_FORECAST_PROXY_META.get(clean, {}))
    raw = os.environ.get("IBKR_FORECAST_PROXY_SYMBOLS_JSON", "").strip()
    if not raw:
        return meta
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return meta
    if not isinstance(decoded, dict):
        return meta
    override = decoded.get(clean)
    if isinstance(override, str):
        meta["symbol"] = override.strip().upper()
    elif isinstance(override, dict):
        for key in ("symbol", "title", "role"):
            if override.get(key):
                meta[key] = str(override[key])
    return meta


def _ibkr_external_proxy_quote_fields(symbol: str, pricing_status: str) -> dict[str, Any]:
    if not bool_env("IBKR_FORECAST_PROXY_QUOTE_FETCH", True):
        return {}
    if str(pricing_status or "").strip().lower() in {"priced", "priced_watchlist"}:
        return {}
    meta = _ibkr_forecast_proxy_meta(symbol)
    proxy_symbol = str(meta.get("symbol") or "").strip().upper()
    if not proxy_symbol:
        return {}
    sources = _env_csv("IBKR_FORECAST_PROXY_PRICE_SOURCES", DEFAULT_IBKR_FORECAST_PROXY_PRICE_SOURCES)
    quote = _fetch_public_quote(proxy_symbol, sources=sources)
    price = quote.get("price") if isinstance(quote, dict) else None
    base = {
        "external_proxy_symbol": proxy_symbol,
        "external_proxy_title": meta.get("title") or proxy_symbol,
        "external_proxy_role": meta.get("role") or "external proxy quote",
        "external_proxy_status": "priced_external_proxy" if price is not None else "external_proxy_price_unavailable",
        "external_proxy_status_label": "External proxy price available" if price is not None else "External proxy price unavailable",
    }
    if isinstance(quote, dict):
        base.update({
            "external_proxy_last_price": float(price) if price is not None else "",
            "external_proxy_currency": quote.get("currency", ""),
            "external_proxy_exchange": quote.get("exchange", ""),
            "external_proxy_source": quote.get("source", ""),
            "external_proxy_source_priority": quote.get("source_priority", ""),
            "external_proxy_regular_market_time": quote.get("regular_market_time", ""),
            "external_proxy_expiry": quote.get("expiry", ""),
            "external_proxy_stale": bool(quote.get("stale")),
        })
    return base


def _ibkr_inventory_rows(*, logs: Path | str | None = None) -> list[dict[str, Any]]:
    symbols = [s.upper() for s in _env_csv("IBKR_DIRECT_EVENT_SYMBOLS", DEFAULT_IBKR_DIRECT_EVENT_SYMBOLS)]
    live_events = _read_ibkr_forecast_inventory(logs=logs)

    def build_row(symbol: str) -> dict[str, Any]:
        meta = IBKR_FORECAST_SYMBOL_META.get(symbol, {})
        event = live_events.get(symbol, {})
        title = str(event.get("title") or meta.get("title") or symbol)
        event_description = str(event.get("description") or "")
        meta_description = str(meta.get("description") or "")
        description = event_description
        if meta_description and meta_description not in description:
            description = f"{description} {meta_description}".strip()
        role = str(meta.get("leg_role") or "direct_prediction_event")
        pricing_status = str(event.get("pricing_status") or "inventory_unpriced")
        proxy_fields = _ibkr_external_proxy_quote_fields(symbol, pricing_status)
        status_label = _pricing_status_label(pricing_status)
        if proxy_fields.get("external_proxy_status") == "priced_external_proxy":
            status_label = f"{status_label}; proxy price available"
        row = {
            "ts": event.get("ts") or event.get("generated_at") or time.time(),
            "surface": "ibkr_prediction",
            "instrument": f"ibkr-prediction:{symbol}-EC",
            "direction": event.get("direction") or meta.get("direction") or "watch",
            "sizing_usdc": _inventory_sizing("ibkr_prediction"),
            "label": "WATCHLIST",
            "reason_code": pricing_status,
            "leg_title": title,
            "leg_slug": str(event.get("slug") or f"{symbol.lower()}-ec"),
            "leg_description": description,
            "leg_end_date": str(event.get("end_date") or event.get("last_trade_date") or ""),
            "leg_role": role,
            "direct_pair_role": str(meta.get("pair_role") or "direct forecast leg"),
            "pricing_status": pricing_status,
            "pricing_status_label": status_label,
            "pricing_detail": str(event.get("pricing_detail") or ""),
            "venue": str(event.get("venue") or "IBKR ForecastTrader"),
            "exchange": str(event.get("exchange") or "FORECASTX"),
            "sec_type": str(event.get("sec_type") or "EC"),
            "underlier_conid": str(event.get("underlier_conid") or event.get("yes_conid") or ""),
            "yes_conid": str(event.get("yes_conid") or event.get("underlier_conid") or ""),
            "yes_prices": event.get("yes_prices") or [],
            "inventory": True,
            "source": "ibkr_forecast_inventory",
        }
        row.update(proxy_fields)
        return row

    if not symbols:
        return []
    workers = _worker_count("IBKR_INVENTORY_WORKERS", 4, len(symbols))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(build_row, symbols))


def _polymarket_inventory_rows() -> list[dict[str, Any]]:
    slugs = _env_csv("POLYMARKET_DIRECT_EVENT_SLUGS", DEFAULT_POLYMARKET_DIRECT_EVENT_SLUGS)
    rows: list[dict[str, Any]] = []
    fetch_live = bool_env("POLYMARKET_DIRECT_EVENT_FETCH", True)
    for slug in slugs:
        fallback = POLYMARKET_WATCHLIST_META.get(slug, {})
        event = _fetch_polymarket_event(slug) if fetch_live else {}
        event = event or {}
        title = str(event.get("title") or fallback.get("title") or slug)
        description = str(event.get("description") or fallback.get("description") or "")
        yes_prices = event.get("yes_prices") if isinstance(event.get("yes_prices"), list) else []
        status = "priced_watchlist" if yes_prices else "metadata_watchlist"
        if event.get("closed") is True:
            status = "closed_watchlist"
        rows.append({
            "ts": time.time(),
            "surface": "polymarket",
            "instrument": f"polymarket:{event.get('id') or slug}",
            "direction": fallback.get("direction") or "watch",
            "sizing_usdc": _inventory_sizing("polymarket"),
            "label": "WATCHLIST",
            "reason_code": status,
            "leg_title": title,
            "leg_slug": str(event.get("slug") or slug),
            "leg_description": description,
            "leg_end_date": str(event.get("end_date") or fallback.get("end_date") or ""),
            "leg_role": "direct_prediction_event",
            "direct_pair_role": str(fallback.get("pair_role") or "direct prediction-event leg"),
            "pricing_status": status,
            "pricing_status_label": _pricing_status_label(status),
            "yes_prices": yes_prices,
            "volume": event.get("volume") or "",
            "liquidity": event.get("liquidity") or "",
            "inventory": True,
            "source": "polymarket_direct_watchlist",
        })
    return rows


def _fetch_kalshi_ai_events() -> list[dict[str, Any]]:
    if not bool_env("KALSHI_DIRECT_EVENT_FETCH", True):
        return []
    from adapters.kalshi import fetch_ai_events

    return fetch_ai_events(
        limit=int(os.environ.get("KALSHI_DIRECT_EVENT_LIMIT", "200")),
        max_pages=int(os.environ.get("KALSHI_DIRECT_EVENT_MAX_PAGES", "3")),
        max_events=int(os.environ.get("KALSHI_DIRECT_EVENT_MAX_EVENTS", "8")),
        terms=_env_csv("KALSHI_DIRECT_EVENT_TERMS", DEFAULT_KALSHI_DIRECT_EVENT_TERMS),
        timeout=_num_env("KALSHI_EVENT_TIMEOUT", 3.0),
    )


def _kalshi_inventory_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in _fetch_kalshi_ai_events():
        if not isinstance(event, dict):
            continue
        yes_prices = event.get("yes_prices") if isinstance(event.get("yes_prices"), list) else []
        status = "priced_watchlist" if yes_prices else "metadata_watchlist"
        event_ticker = str(event.get("event_ticker") or event.get("id") or event.get("slug") or "")
        if not event_ticker:
            continue
        rows.append({
            "ts": time.time(),
            "surface": "kalshi",
            "instrument": f"kalshi:{event_ticker}",
            "direction": "short",
            "sizing_usdc": _inventory_sizing("kalshi"),
            "label": "WATCHLIST",
            "reason_code": status,
            "leg_title": str(event.get("title") or event_ticker),
            "leg_slug": str(event.get("slug") or event_ticker.lower()),
            "leg_description": str(event.get("description") or ""),
            "leg_end_date": str(event.get("end_date") or ""),
            "leg_role": "direct_prediction_event",
            "direct_pair_role": "AI compute-demand leg",
            "pricing_status": status,
            "pricing_status_label": _pricing_status_label(status),
            "yes_prices": yes_prices,
            "volume": event.get("volume") or "",
            "liquidity": event.get("liquidity") or "",
            "venue": "Kalshi",
            "category": str(event.get("category") or ""),
            "series_ticker": str(event.get("series_ticker") or ""),
            "market_tickers": event.get("market_tickers") or [],
            "mutually_exclusive": bool(event.get("mutually_exclusive")),
            "inventory": True,
            "source": "kalshi_direct_ai_watchlist",
        })
    return rows


def direct_inventory_state(*, logs: Path | str | None = None) -> list[dict[str, Any]]:
    """Configured real direct-event surfaces shown as watchlist inventory.

    Inventory rows explain currently monitored IBKR/Polymarket/Kalshi legs, but they
    are not candidate rows. Polymarket still needs the preserved premium gate;
    IBKR and Kalshi event contracts still need usable quote fields before either
    can reach judge.classify() or Arc.
    """
    if not bool_env("DIRECT_EVENT_INVENTORY_ENABLED", True):
        return []
    builders = (
        lambda: _ibkr_inventory_rows(logs=logs),
        _polymarket_inventory_rows,
        _kalshi_inventory_rows,
    )
    rows: list[dict[str, Any]] = []
    workers = _worker_count("DIRECT_EVENT_INVENTORY_WORKERS", 3, len(builders))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(fn) for fn in builders]
        for future in futures:
            try:
                rows.extend(future.result())
            except Exception:
                continue
    return _visible_leg_rows(_enrich_leg_rows(rows, logs=logs))


def _row_has_yes_price(row: dict[str, Any]) -> bool:
    prices = row.get("yes_prices")
    if isinstance(prices, list):
        return any(_as_float(price) is not None for price in prices)
    return False


def _row_has_public_price(row: dict[str, Any]) -> bool:
    return _as_float(row.get("last_price")) is not None


def _row_has_external_proxy_price(row: dict[str, Any]) -> bool:
    return _as_float(row.get("external_proxy_last_price")) is not None


def _row_quote_sources(rows: list[dict[str, Any]]) -> list[str]:
    sources: set[str] = set()
    for row in rows:
        for key in ("source", "external_proxy_source"):
            value = str(row.get(key) or "").strip()
            if not value:
                continue
            for part in value.split(","):
                clean = part.strip()
                if clean:
                    sources.add(clean)
    return sorted(sources)


def _proxy_basket_history_rows(proxy_baskets: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Represent saved Yahoo close-history replay as venue evidence.

    This is not a live quote. It lets campaign/status surfaces accurately show
    that public/crypto proxy baskets are replay-priced even when live quote
    refresh is disabled during fallback snapshots.
    """
    if not isinstance(proxy_baskets, dict):
        return []
    baskets = [basket for basket in (proxy_baskets.get("baskets") or []) if isinstance(basket, dict)]
    primary = proxy_baskets.get("primary_basket")
    if isinstance(primary, dict):
        baskets.append(primary)
    by_symbol: dict[str, dict[str, Any]] = {}
    now = time.time()
    for basket in baskets:
        for symbol in basket.get("symbols_available") or []:
            clean = str(symbol or "").strip().upper()
            if not clean or clean in by_symbol:
                continue
            meta = PUBLIC_HEDGE_META.get(clean, {})
            by_symbol[clean] = sanitize_row({
                "ts": now,
                "surface": "crypto" if clean in {"BTC-USD", "ETH-USD", "BTC/USD", "ETH/USD"} else "public_market",
                "instrument": clean,
                "leg_slug": clean,
                "leg_title": meta.get("title") or clean,
                "display_label": meta.get("title") or clean,
                "leg_role": "close_history_proxy_replay",
                "direct_pair_role": meta.get("role") or "public hedge proxy",
                "direction": meta.get("direction") or "watch",
                "label": "REPLAY",
                "pricing_status": "priced_close_history",
                "pricing_status_label": _pricing_status_label("priced_close_history"),
                "source": "yahoo_close_history",
                "leg_description": "Yahoo close-history replay used for proxy basket PnL and signal validation.",
                "inventory": True,
            })
    return list(by_symbol.values())


def _ibkr_client_portal_health() -> dict[str, Any]:
    if not bool_env("IBKR_CP_HEALTH_FETCH", True):
        return {
            "status": "DISABLED",
            "reachable": False,
            "authenticated": False,
            "connected": False,
            "competing": False,
            "action": "IBKR_CP_HEALTH_FETCH=0 disables Client Portal health checks.",
        }
    try:
        from adapters.ibkr import client_portal_health

        return client_portal_health(timeout=_num_env("IBKR_CP_HEALTH_TIMEOUT", 1.5))
    except Exception as exc:
        return {
            "status": "UNREACHABLE",
            "reachable": False,
            "authenticated": False,
            "connected": False,
            "competing": False,
            "error_code": exc.__class__.__name__,
            "action": "Start Client Portal Gateway, login, then run npm run ibkr:cp-watchdog-once.",
        }


def _status_from_counts(
    *,
    rows: int,
    priced: int,
    external_proxy: int = 0,
    empty_status: str = "NEEDS_DISCOVERY",
) -> str:
    if rows <= 0:
        return empty_status
    if priced > 0:
        return "LIVE_PRICED"
    if external_proxy > 0:
        return "PROXY_PRICED"
    return "NEEDS_PRICE"


def _public_proxy_surface_status(rows: list[dict[str, Any]], *, empty_status: str = "NEEDS_QUOTES") -> str:
    if not rows:
        return empty_status
    live_priced = sum(
        1 for row in rows
        if _row_has_public_price(row) or str(row.get("pricing_status") or "") == "priced_public_market"
    )
    if live_priced > 0:
        return "LIVE_PRICED"
    replay_priced = sum(1 for row in rows if str(row.get("pricing_status") or "") == "priced_close_history")
    if replay_priced > 0:
        return "REPLAY_PRICED"
    return "NEEDS_PRICE"


def _venue_row(
    *,
    surface: str,
    label: str,
    role: str,
    rows: list[dict[str, Any]],
    status: str,
    gaps: list[str],
    health: dict[str, Any] | None = None,
    evidence_only: bool = False,
    direct_event_surface: bool = False,
    premium_gate_required: bool = False,
) -> dict[str, Any]:
    priced = [
        row for row in rows
        if _row_has_yes_price(row) or _row_has_public_price(row)
        or str(row.get("pricing_status") or "") in PRICED_STATUS_VALUES
    ]
    external = [row for row in rows if _row_has_external_proxy_price(row)]
    watchlist = [row for row in rows if str(row.get("label") or "") == "WATCHLIST" or row.get("inventory")]
    latest = max(rows, key=_row_ts) if rows else {}
    health = health or {}
    return {
        "surface": surface,
        "label": label,
        "role": role,
        "status": status,
        "auth_status": health.get("status", ""),
        "auth_reachable": health.get("reachable", ""),
        "auth_authenticated": health.get("authenticated", ""),
        "auth_connected": health.get("connected", ""),
        "auth_action": health.get("action", ""),
        "row_count": len(rows),
        "priced_count": len(priced),
        "watchlist_count": len(watchlist),
        "external_proxy_count": len(external),
        "quote_sources": _row_quote_sources(rows),
        "direct_event_surface": direct_event_surface,
        "evidence_only": evidence_only,
        "real_feed": len(rows) > 0,
        "can_drive_arc": False,
        "judge_required": True,
        "premium_gate_required": premium_gate_required,
        "latest_title": latest.get("display_label") or latest.get("leg_title") or latest.get("instrument") or "",
        "latest_slug": latest.get("leg_slug") or latest.get("instrument") or "",
        "latest_pricing_status": latest.get("pricing_status_label") or latest.get("pricing_status") or latest.get("reason_code") or "",
        "gaps": gaps,
    }


COMPUTE_POWER_ORACLE_QUERY_LABELS = {
    "ai_infra",
    "ai_capex_compute_demand",
    "data_center_power_policy",
    "nuclear_power_compute",
    "nvidia_ai_infra",
}


def _oracle_query_label(row: dict[str, Any]) -> str:
    query = row.get("query") if isinstance(row.get("query"), dict) else {}
    return str(query.get("label") or "").strip()


def _is_compute_power_oracle_receipt(row: dict[str, Any]) -> bool:
    label = _oracle_query_label(row)
    template = str(row.get("energy_template_id") or "").strip()
    slug_blob = f"{row.get('slug') or ''} {row.get('event_slug') or ''}".lower()
    if label in COMPUTE_POWER_ORACLE_QUERY_LABELS or template == "energy_ai_infra":
        return True
    return any(term in slug_blob for term in (
        "data-center",
        "data center",
        "datacenter",
        "ai-bubble",
        "ai capex",
        "ai-capex",
        "gpu",
        "compute",
        "nvidia",
    ))


def _oracle_evidence_state(*, logs: Path | str | None = None) -> dict[str, Any]:
    receipts = read_jsonl(log_dir(logs) / "energy_llm_oracle.jsonl", limit=250)
    verdict_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    raw_articles = 0
    filtered_articles = 0
    for row in receipts:
        verdict = str(row.get("verdict") or "UNKNOWN")
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        reason = str(row.get("reason_code") or "unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        coverage = row.get("coverage") if isinstance(row.get("coverage"), dict) else {}
        raw_articles += int(_as_float(coverage.get("raw")) or 0)
        filtered_articles += int(_as_float(coverage.get("after_filter")) or 0)
    current_desk_receipts = [row for row in receipts if _is_compute_power_oracle_receipt(row)]
    latest_scope = "compute_power" if current_desk_receipts else ("all_energy" if receipts else "none")
    latest = (current_desk_receipts or receipts)[-1] if receipts else {}
    return {
        "surface": "opoint_nebius",
        "label": "Opoint + Nebius oracle receipts",
        "role": "news-grounded evidence only",
        "status": "EVIDENCE_LOGGED" if receipts else "NO_RECEIPTS",
        "row_count": len(receipts),
        "current_desk_row_count": len(current_desk_receipts),
        "latest_scope": latest_scope,
        "latest_query_label": _oracle_query_label(latest),
        "priced_count": 0,
        "watchlist_count": 0,
        "external_proxy_count": 0,
        "direct_event_surface": False,
        "evidence_only": True,
        "real_feed": len(receipts) > 0,
        "can_drive_arc": False,
        "judge_required": True,
        "premium_gate_required": False,
        "latest_title": latest.get("event_slug") or latest.get("slug") or "",
        "latest_slug": latest.get("slug") or latest.get("event_slug") or "",
        "latest_pricing_status": latest.get("verdict") or "",
        "latest_model": latest.get("analyst_model") or "",
        "latest_reason_code": latest.get("reason_code") or "",
        "verdict_counts": verdict_counts,
        "reason_counts": reason_counts,
        "raw_articles": raw_articles,
        "filtered_articles": filtered_articles,
        "gaps": [
            "Oracle receipts are evidence only; they cannot trigger Circle or Arc.",
            "Missing or DEFER oracle output must not bypass premium scorer or judge.classify().",
        ],
    }


def venue_evidence_state(
    *,
    direct_inventory: list[dict[str, Any]],
    public_hedges: list[dict[str, Any]],
    verdicts: list[dict[str, Any]],
    proxy_baskets: dict[str, Any] | None = None,
    logs: Path | str | None = None,
) -> dict[str, Any]:
    """Explain which real surfaces are feeding the desk and what still blocks use.

    This is an operator-facing projection only. It does not fetch venues, score,
    judge, or route orders.
    """
    visible_verdicts = _visible_leg_rows(verdicts)

    def rows_for(surface: str) -> list[dict[str, Any]]:
        return [
            row for row in [*direct_inventory, *visible_verdicts]
            if str(row.get("surface") or "") == surface
        ]

    polymarket = rows_for("polymarket")
    kalshi = rows_for("kalshi")
    ibkr_prediction = rows_for("ibkr_prediction")
    public_market = [*public_hedges, *[row for row in visible_verdicts if str(row.get("surface") or "") in {"ibkr", "public_market"}]]
    crypto = [
        row for row in [*public_hedges, *visible_verdicts]
        if str(row.get("surface") or "") == "crypto"
        or str(row.get("leg_slug") or row.get("instrument") or "").upper() in {"BTC-USD", "ETH-USD", "BTC/USD", "ETH/USD"}
    ]
    history_rows = _proxy_basket_history_rows(proxy_baskets)
    live_priced_symbols = {
        str(row.get("leg_slug") or row.get("instrument") or "").strip().upper()
        for row in public_hedges
        if _row_has_public_price(row) or str(row.get("pricing_status") or "") == "priced_public_market"
    }
    public_market.extend(
        row for row in history_rows
        if str(row.get("surface") or "") == "public_market"
        and str(row.get("leg_slug") or row.get("instrument") or "").strip().upper() not in live_priced_symbols
    )
    crypto.extend(
        row for row in history_rows
        if str(row.get("surface") or "") == "crypto"
        and str(row.get("leg_slug") or row.get("instrument") or "").strip().upper() not in live_priced_symbols
    )

    ibkr_cp_health = _ibkr_client_portal_health()
    ibkr_priced = sum(1 for row in ibkr_prediction if _row_has_yes_price(row) or str(row.get("pricing_status") or "") == "priced_watchlist")
    ibkr_proxy = sum(1 for row in ibkr_prediction if _row_has_external_proxy_price(row))
    ibkr_gaps = (
        ["IBKR EC metadata is present, but venue bid/ask/last is still missing; external proxy marks are labelled separately."]
        if ibkr_prediction and ibkr_priced == 0 and ibkr_proxy > 0
        else ["Needs live EC bid/ask/last from Client Portal or TWS."]
    )
    if ibkr_cp_health.get("status") not in {"AUTHENTICATED", "DISABLED"}:
        ibkr_gaps.insert(
            0,
            f"IBKR Client Portal {str(ibkr_cp_health.get('status') or 'UNKNOWN').replace('_', ' ').lower()}: "
            f"{ibkr_cp_health.get('action') or 'reauthenticate the local gateway.'}",
        )
    rows = [
        _venue_row(
            surface="polymarket",
            label="Polymarket Gamma",
            role="direct event watchlist after premium scoring",
            rows=polymarket,
            status=_status_from_counts(
                rows=len(polymarket),
                priced=sum(1 for row in polymarket if _row_has_yes_price(row) or str(row.get("pricing_status") or "") == "priced_watchlist"),
            ),
            gaps=["Premium scorer must pass before any Polymarket leg can be promoted."] if polymarket else ["No configured Polymarket direct event rows."],
            direct_event_surface=True,
            premium_gate_required=True,
        ),
        _venue_row(
            surface="kalshi",
            label="Kalshi public event feed",
            role="direct AI/data-center forecast events",
            rows=kalshi,
            status=_status_from_counts(
                rows=len(kalshi),
                priced=sum(1 for row in kalshi if _row_has_yes_price(row) or str(row.get("pricing_status") or "") == "priced_watchlist"),
                empty_status="NEEDS_EVENT_MATCH",
            ),
            gaps=["Needs thesis-matched priced event contracts before promotion."] if kalshi else ["No thesis-matched Kalshi rows in the current snapshot."],
            direct_event_surface=True,
        ),
        _venue_row(
            surface="ibkr_prediction",
            label="IBKR ForecastTrader / ForecastEx",
            role="direct electricity and AI compute forecast contracts",
            rows=ibkr_prediction,
            status=_status_from_counts(rows=len(ibkr_prediction), priced=ibkr_priced, external_proxy=ibkr_proxy),
            gaps=ibkr_gaps,
            health=ibkr_cp_health,
            direct_event_surface=True,
        ),
        _venue_row(
            surface="public_market",
            label="Yahoo / IBKR / Alpaca public quote proxies",
            role="liquid public hedge expression",
            rows=public_market,
            status=_public_proxy_surface_status(public_market),
            gaps=["These are liquid proxies, not direct compute or electricity claims."],
        ),
        _venue_row(
            surface="crypto",
            label="BTC/ETH miner-margin proxy",
            role="power-sensitive miner-margin proxy",
            rows=crypto,
            status=_public_proxy_surface_status(crypto),
            gaps=["Crypto is proxy-only unless explicit miner-margin evidence is attached."],
        ),
        _oracle_evidence_state(logs=logs),
    ]
    return {
        "version": "venue_evidence_matrix_v1",
        "guardrail": "All rows are evidence or watchlist state only; no Circle or Arc action can happen before judge.classify() returns EXECUTE.",
        "rows": rows,
        "summary": {
            "surfaces": len(rows),
            "real_feed_surfaces": sum(1 for row in rows if row.get("real_feed")),
            "direct_event_surfaces": sum(1 for row in rows if row.get("direct_event_surface")),
            "priced_surfaces": sum(1 for row in rows if int(row.get("priced_count") or 0) > 0),
            "evidence_only_surfaces": sum(1 for row in rows if row.get("evidence_only")),
            "arc_ready_surfaces": 0,
        },
    }


def arc_tx_state(*, logs: Path | str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return _latest_first(read_tsv("arc_txs.tsv", limit=limit, logs=logs))


def pnl_state(*, logs: Path | str | None = None) -> dict[str, Any]:
    rows = read_tsv("pnl_reconciliation.tsv", logs=logs)
    total = 0.0
    wins = 0
    counted = 0
    for row in rows:
        value = row.get("actual_pnl") or row.get("actual_pnl_usd") or row.get("realized_pnl_usd")
        try:
            pnl = float(value)
        except (TypeError, ValueError):
            continue
        total += pnl
        wins += 1 if pnl > 0 else 0
        counted += 1
    return {
        "total": round(total, 6),
        "trades": counted,
        "win_rate": round((wins / counted) * 100.0, 3) if counted else 0.0,
    }


def enrich_pnl_state(
    pnl: dict[str, Any],
    *,
    spread_families: dict[str, Any],
    proxy_baskets: dict[str, Any],
    signal_direction: str = "",
    visible_positions: int,
) -> dict[str, Any]:
    trades = int(_as_float(pnl.get("trades")) or 0)
    primary_family = spread_families.get("primary_family") if isinstance(spread_families, dict) else {}
    primary_proxy, _proxy_gate = select_proxy_basket_for_direction(proxy_baskets, signal_direction)
    if trades <= 0:
        status = "NO_SETTLED_PNL"
        status_label = "No settled PnL"
        note = (
            "No reconciled fills or settlements exist yet. Replay rows and local mock "
            "tickets are not realized PnL."
        )
    elif visible_positions <= 0:
        status = "RECONCILED_ONLY"
        status_label = "Reconciled history only"
        note = "PnL comes from reconciliation rows; there are no currently visible Arc positions."
    else:
        status = "SETTLED_PNL"
        status_label = "Settled PnL"
        note = "PnL comes from reconciled fills or settlements."
    pnl.update({
        "status": status,
        "status_label": status_label,
        "display_total": f"${float(pnl.get('total') or 0):.4f}" if trades > 0 else status_label,
        "display_trades": str(trades) if trades > 0 else "0 settled",
        "mark_to_market_note": note,
        "spread_replay_status": (primary_family or {}).get("status", ""),
        "spread_replay_reason": (primary_family or {}).get("status_reason", ""),
        "spread_mark_changes": (primary_family or {}).get("observations", 0),
        "spread_raw_observations": (primary_family or {}).get("raw_observations", 0),
        "spread_collapsed_polls": (primary_family or {}).get("collapsed_repeated_marks", 0),
        "spread_oos_status": (primary_family or {}).get("oos_status", ""),
        "spread_oos_test_pnl_per_unit": (primary_family or {}).get("oos_test_pnl_per_unit", ""),
        "spread_oos_test_win_rate": (primary_family or {}).get("oos_test_win_rate", ""),
        "proxy_basket_id": (primary_proxy or {}).get("basket_id", ""),
        "proxy_basket_direction": (primary_proxy or {}).get("direction", ""),
        "proxy_latest_signal": (primary_proxy or {}).get("latest_signal", ""),
        "proxy_replay_status": (primary_proxy or {}).get("status", ""),
        "proxy_5d_return_pct": (((primary_proxy or {}).get("trailing_returns") or {}).get("5d") or {}).get("return_pct", ""),
        "proxy_1m_return_pct": (((primary_proxy or {}).get("trailing_returns") or {}).get("1m") or {}).get("return_pct", ""),
    })
    return pnl


def _row_ts(row: dict[str, Any]) -> float:
    try:
        return float(row.get("ts") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _visible_leg_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if not row.get("is_mock")
        and not row.get("is_thesis_mismatch")
        and not row.get("is_legacy_artifact")
    ]


def _leg_rollup_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(row.get("surface") or ""),
        str(row.get("instrument") or ""),
        str(row.get("direction") or ""),
        str(row.get("leg_role") or ""),
        str(row.get("label") or row.get("status") or ""),
        str(row.get("reason_code") or ""),
    )


def rollup_leg_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated scan rows while keeping the newest public metadata."""
    by_key: dict[tuple[str, str, str, str, str, str], dict[str, Any]] = {}
    for row in sorted(rows, key=_row_ts, reverse=True):
        key = _leg_rollup_key(row)
        current = by_key.get(key)
        if current is None:
            copy = dict(row)
            copy["repeat_count"] = 1
            copy["latest_ts"] = row.get("ts", "")
            copy["first_ts"] = row.get("ts", "")
            by_key[key] = copy
            continue
        current["repeat_count"] = int(current.get("repeat_count") or 1) + 1
        current["first_ts"] = row.get("ts", current.get("first_ts", ""))
    return sorted(by_key.values(), key=_row_ts, reverse=True)


def _package_key(row: dict[str, Any]) -> str:
    return (
        str(row.get("package_id") or "")
        or str(row.get("arb_signal_id") or "")
        or "|".join(str(part) for part in _leg_rollup_key(row)[:4])
    )


def _package_label(legs: list[dict[str, Any]]) -> str:
    labels = [str(leg.get("label") or "") for leg in legs]
    if "EXECUTE" in labels:
        return "EXECUTE"
    if labels and all(label == "REJECT" for label in labels):
        return "REJECT"
    if "CHALLENGE" in labels:
        return "CHALLENGE"
    if "DEFER" in labels:
        return "DEFER"
    return labels[0] if labels else "PENDING"


def _repeat_total(rows: list[dict[str, Any]]) -> int:
    return sum(int(row.get("repeat_count") or 1) for row in rows)


def _reason_codes(rows: list[dict[str, Any]]) -> list[str]:
    reasons = {
        str(row.get("reason_code") or "").strip()
        for row in rows
        if str(row.get("reason_code") or "").strip()
    }
    return sorted(reasons)


def _package_reason(label: str, legs: list[dict[str, Any]], fallback: str = "") -> str:
    matching = [leg for leg in legs if str(leg.get("label") or "") == label]
    if matching:
        latest = max(matching, key=_row_ts)
        return str(latest.get("reason_code") or fallback)
    actionable = [leg for leg in legs if str(leg.get("label") or "") != "REJECT"]
    if actionable:
        latest = max(actionable, key=_row_ts)
        return str(latest.get("reason_code") or fallback)
    return str(fallback or "")


def _blocked_summary(kind: str, rows: list[dict[str, Any]]) -> str:
    count = _repeat_total(rows)
    if count <= 0:
        return ""
    reasons = ", ".join(_reason_codes(rows)) or "judge gate"
    leg_word = "row" if count == 1 else "rows"
    return f"{count} {kind} scan {leg_word} blocked by {reasons}"


def package_state(
    verdicts: list[dict[str, Any]],
    positions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group recent public legs into understandable spread packages.

    The raw TSV rows remain append-only audit state. This projection is the
    operator-facing view: one package, its direct legs, its proxy legs, and the
    latest judge result.
    """
    visible_verdicts = _visible_leg_rows(verdicts)
    visible_positions = _visible_leg_rows(positions)
    grouped: dict[str, dict[str, Any]] = {}
    for row in sorted(visible_verdicts, key=_row_ts, reverse=True):
        key = _package_key(row)
        pkg = grouped.setdefault(key, {
            "id": key,
            "package_id": row.get("package_id", ""),
            "arb_signal_id": row.get("arb_signal_id", ""),
            "ts": row.get("ts", ""),
            "direction": row.get("direction", ""),
            "legs": [],
            "positions": [],
        })
        if _row_ts(row) >= _row_ts(pkg):
            pkg["ts"] = row.get("ts", pkg.get("ts", ""))
            pkg["direction"] = row.get("direction", pkg.get("direction", ""))
            pkg["reason_code"] = row.get("reason_code", pkg.get("reason_code", ""))
        pkg["legs"].append(row)
    for row in sorted(visible_positions, key=_row_ts, reverse=True):
        key = _package_key(row)
        pkg = grouped.setdefault(key, {
            "id": key,
            "package_id": row.get("package_id", ""),
            "arb_signal_id": row.get("arb_signal_id", ""),
            "ts": row.get("ts", ""),
            "direction": row.get("direction", ""),
            "legs": [],
            "positions": [],
        })
        pkg["positions"].append(row)
        if _row_ts(row) >= _row_ts(pkg):
            pkg["ts"] = row.get("ts", pkg.get("ts", ""))
            pkg["direction"] = row.get("direction", pkg.get("direction", ""))

    packages: list[dict[str, Any]] = []
    for pkg in grouped.values():
        legs = rollup_leg_rows(pkg["legs"])
        direct = [
            leg for leg in legs
            if str(leg.get("leg_role") or "") == "direct_prediction_event"
            or str(leg.get("surface") or "") in {"polymarket", "ibkr_prediction", "kalshi"}
        ]
        proxy = [leg for leg in legs if leg not in direct]
        actionable = [leg for leg in legs if str(leg.get("label") or "") != "REJECT"]
        actionable_direct = [leg for leg in direct if str(leg.get("label") or "") != "REJECT"]
        actionable_proxy = [leg for leg in proxy if str(leg.get("label") or "") != "REJECT"]
        rejected = [leg for leg in legs if str(leg.get("label") or "") == "REJECT"]
        rejected_direct = [leg for leg in direct if str(leg.get("label") or "") == "REJECT"]
        rejected_proxy = [leg for leg in proxy if str(leg.get("label") or "") == "REJECT"]
        label = _package_label(legs)
        reason = _package_reason(label, legs, str(pkg.get("reason_code") or ""))
        packages.append({
            **pkg,
            "label": label,
            "reason_code": reason,
            "legs": legs,
            "direct_legs": direct,
            "proxy_legs": proxy,
            "positions": rollup_leg_rows(pkg["positions"]),
            "leg_count": len(legs),
            "direct_leg_count": len(direct),
            "proxy_leg_count": len(proxy),
            "actionable_leg_count": len(actionable),
            "actionable_direct_leg_count": len(actionable_direct),
            "actionable_proxy_leg_count": len(actionable_proxy),
            "rejected_leg_count": len(rejected),
            "rejected_direct_leg_count": len(rejected_direct),
            "rejected_proxy_leg_count": len(rejected_proxy),
            "rejected_repeat_count": _repeat_total(rejected),
            "rejected_direct_repeat_count": _repeat_total(rejected_direct),
            "rejected_proxy_repeat_count": _repeat_total(rejected_proxy),
            "direct_reject_reasons": _reason_codes(rejected_direct),
            "proxy_reject_reasons": _reason_codes(rejected_proxy),
            "direct_blocked_summary": _blocked_summary("direct event", rejected_direct),
            "proxy_blocked_summary": _blocked_summary("proxy", rejected_proxy),
            "repeat_count": _repeat_total(legs),
        })
    return sorted(packages, key=_row_ts, reverse=True)


def runtime_status(*, logs: Path | str | None = None) -> dict[str, Any]:
    status = read_json(log_dir(logs) / "runtime_status.json", default={})
    if not isinstance(status, dict):
        return {}
    return sanitize_row(status)


def _telegram_sent_keys(*, logs: Path | str | None = None) -> set[str]:
    path = log_dir(logs) / TELEGRAM_SENT_NAME
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


def telegram_campaign_state(*, logs: Path | str | None = None) -> dict[str, Any]:
    sent = _telegram_sent_keys(logs=logs)
    posts = [
        {
            "key": key,
            "title": title,
            "description": description,
            "posted": key in sent,
            "status": "POSTED" if key in sent else "READY_TO_POST",
        }
        for key, title, description in TELEGRAM_CAMPAIGN_POSTS
    ]
    posted_count = sum(1 for post in posts if post["posted"])
    return {
        "version": "telegram_campaign_state_v1",
        "draft_command": "npm run telegram:campaign-draft",
        "post_command": "npm run telegram:campaign-post",
        "draft_available": True,
        "channel_configured": bool(os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()),
        "total_posts": len(posts),
        "posted_count": posted_count,
        "pending_count": len(posts) - posted_count,
        "status": "POSTED" if posted_count == len(posts) else "READY_TO_POST",
        "note": "Campaign status is read from telegram_sent.jsonl keys only; message bodies and bot tokens are not exposed.",
        "posts": posts,
    }


def _telegram_post_status(
    posts_def: tuple[tuple[str, str, str], ...],
    *,
    version: str,
    draft_command: str,
    post_command: str,
    note: str,
    logs: Path | str | None = None,
) -> dict[str, Any]:
    sent = _telegram_sent_keys(logs=logs)
    posts = [
        {
            "key": key,
            "title": title,
            "description": description,
            "posted": key in sent,
            "status": "POSTED" if key in sent else "READY_TO_POST",
        }
        for key, title, description in posts_def
    ]
    posted_count = sum(1 for post in posts if post["posted"])
    return {
        "version": version,
        "draft_command": draft_command,
        "post_command": post_command,
        "draft_available": True,
        "channel_configured": bool(os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()),
        "total_posts": len(posts),
        "posted_count": posted_count,
        "pending_count": len(posts) - posted_count,
        "status": "POSTED" if posted_count == len(posts) else "READY_TO_POST",
        "note": note,
        "posts": posts,
    }


def telegram_miniapp_release_state(*, logs: Path | str | None = None) -> dict[str, Any]:
    return _telegram_post_status(
        TELEGRAM_MINIAPP_RELEASE_POSTS,
        version="telegram_miniapp_release_state_v1",
        draft_command="npm run telegram:miniapp-release-draft",
        post_command="npm run telegram:miniapp-release-post",
        note="Mini App release status is read from telegram_sent.jsonl keys only; message bodies and bot tokens are not exposed.",
        logs=logs,
    )


def _count_rows(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _coverage_status(score: float) -> str:
    if score >= 0.85:
        return "READY"
    if score >= 0.50:
        return "PARTIAL"
    return "NEEDS_WORK"


def _coverage_item(
    *,
    item_id: str,
    label: str,
    score: float,
    metric: str,
    evidence: str,
    next_step: str,
) -> dict[str, Any]:
    clean_score = max(0.0, min(1.0, float(score)))
    return {
        "id": item_id,
        "label": label,
        "status": _coverage_status(clean_score),
        "score": round(clean_score * 100.0, 1),
        "metric": metric,
        "evidence": evidence,
        "next_step": next_step,
    }


def _requirement_item(
    *,
    item_id: str,
    label: str,
    score: float,
    evidence: list[str],
    gaps: list[str] | None = None,
) -> dict[str, Any]:
    clean_score = max(0.0, min(1.0, float(score)))
    return {
        "id": item_id,
        "label": label,
        "status": _coverage_status(clean_score),
        "score": round(clean_score * 100.0, 1),
        "evidence": [str(item) for item in evidence if str(item).strip()],
        "gaps": [str(item) for item in (gaps or []) if str(item).strip()],
    }


def goal_coverage_state(
    *,
    spread_families: dict[str, Any],
    synthetic_instrument: dict[str, Any],
    profitability_ledger: dict[str, Any],
    portfolio_signal: dict[str, Any],
    venue_evidence: dict[str, Any],
    oracle_evidence: dict[str, Any],
    telegram_campaign: dict[str, Any],
    telegram_miniapp_release: dict[str, Any],
    pnl: dict[str, Any],
) -> dict[str, Any]:
    """Summarize progress against the current product goal.

    This is a product/readiness projection. It only aggregates already-public
    sanitized state; it does not fetch venues, score candidates, judge, or call
    Circle/Arc.
    """
    coverage = spread_families.get("index_coverage") if isinstance(spread_families.get("index_coverage"), dict) else {}
    electricity = coverage.get("electricity") if isinstance(coverage.get("electricity"), dict) else {}
    compute = coverage.get("compute") if isinstance(coverage.get("compute"), dict) else {}
    archetypes = coverage.get("spread_archetypes") if isinstance(coverage.get("spread_archetypes"), dict) else {}
    outputs = synthetic_instrument.get("outputs") if isinstance(synthetic_instrument.get("outputs"), dict) else {}
    menu = outputs.get("syndicated_instrument_menu") if isinstance(outputs.get("syndicated_instrument_menu"), list) else []
    trade_map = outputs.get("spread_archetype_trade_map") if isinstance(outputs.get("spread_archetype_trade_map"), list) else []
    direct_pairs = outputs.get("direct_event_pair_candidates") if isinstance(outputs.get("direct_event_pair_candidates"), dict) else {}
    ledger_rows = profitability_ledger.get("rows") if isinstance(profitability_ledger.get("rows"), list) else []
    portfolio_rows = portfolio_signal.get("rows") if isinstance(portfolio_signal.get("rows"), list) else []
    venue_rows = venue_evidence.get("rows") if isinstance(venue_evidence.get("rows"), list) else []
    venue_summary = venue_evidence.get("summary") if isinstance(venue_evidence.get("summary"), dict) else {}

    electricity_usable = _safe_int(electricity.get("usable"))
    electricity_total = _safe_int(electricity.get("total"))
    compute_usable = _safe_int(compute.get("usable"))
    compute_total = _safe_int(compute.get("total"))
    archetype_total = _safe_int(archetypes.get("total"))
    archetype_replayed = _safe_int(archetypes.get("replayed"))
    archetype_oos = _safe_int(archetypes.get("oos_passed") or archetypes.get("oos_pass"))
    promotable_rows = sum(
        1
        for row in [*trade_map, *ledger_rows]
        if isinstance(row, dict)
        and (
            row.get("is_promotable")
            or row.get("replay_promotable")
            or row.get("spread_replay_promotable")
            or row.get("oos_passed")
            or row.get("oos_status") == "PASSED"
            or row.get("spread_oos_status") == "PASSED"
        )
    )
    profitable_rows = sum(
        1
        for row in ledger_rows
        if isinstance(row, dict)
        and (
            (_as_float(row.get("paper_total_return_pct") or row.get("total_return_pct")) or 0.0) > 0
            or (_as_float(row.get("latest_paper_pnl_usdc") or row.get("latest_mark_pnl_usdc") or row.get("latest_pnl_usdc")) or 0.0) > 0
        )
    )
    buy_or_sell_rows = sum(
        1
        for row in ledger_rows
        if isinstance(row, dict)
        and any(token in str(row.get("profitability_status") or row.get("latest_signal") or row.get("tradability_action") or "").upper() for token in ("BUY", "SELL", "CLOSE", "AVOID"))
    )
    direct_surfaces = _safe_int(venue_summary.get("direct_event_surfaces"))
    priced_surfaces = _safe_int(venue_summary.get("priced_surfaces"))
    real_feed_surfaces = _safe_int(venue_summary.get("real_feed_surfaces"))
    ready_pairs = _safe_int(direct_pairs.get("ready_for_judge_count"))
    total_pairs = _safe_int(direct_pairs.get("total_count") or _count_rows(direct_pairs.get("rows")))
    oracle_current = _safe_int(oracle_evidence.get("current_desk_row_count"))
    campaign_total = _safe_int(telegram_campaign.get("total_posts"))
    campaign_posted = _safe_int(telegram_campaign.get("posted_count"))
    release_total = _safe_int(telegram_miniapp_release.get("total_posts"))
    release_posted = _safe_int(telegram_miniapp_release.get("posted_count"))
    electricity_tradeability = electricity.get("tradeability_counts") if isinstance(electricity.get("tradeability_counts"), dict) else {}
    compute_tradeability = compute.get("tradeability_counts") if isinstance(compute.get("tradeability_counts"), dict) else {}
    electricity_families = electricity.get("family_counts") if isinstance(electricity.get("family_counts"), dict) else {}
    compute_families = compute.get("family_counts") if isinstance(compute.get("family_counts"), dict) else {}

    index_score = (
        (1.0 if electricity_usable >= 5 else electricity_usable / 5.0)
        + (1.0 if compute_usable >= 4 else compute_usable / 4.0)
        + (1.0 if archetype_replayed >= 10 else archetype_replayed / 10.0)
        + (1.0 if archetype_oos >= 1 else 0.0)
    ) / 4.0
    profitability_score = (
        (1.0 if ledger_rows else 0.0)
        + (1.0 if profitable_rows >= 3 else profitable_rows / 3.0)
        + (1.0 if promotable_rows >= 5 else promotable_rows / 5.0)
        + (1.0 if buy_or_sell_rows >= 1 else 0.0)
    ) / 4.0
    venue_score = (
        (1.0 if direct_surfaces >= 3 else direct_surfaces / 3.0)
        + (1.0 if priced_surfaces >= 2 else priced_surfaces / 2.0)
        + (1.0 if real_feed_surfaces >= 4 else real_feed_surfaces / 4.0)
        + (1.0 if ready_pairs >= 1 else 0.0)
        + (1.0 if oracle_current >= 1 else 0.0)
    ) / 5.0
    signal_score = (
        (1.0 if portfolio_rows else 0.0)
        + (1.0 if portfolio_signal.get("action") else 0.0)
        + (1.0 if _safe_int(pnl.get("paper_buy_count")) + _safe_int(pnl.get("paper_close_or_avoid_count")) >= 1 else 0.0)
        + (1.0 if pnl.get("paper_latest_mark_pnl_usdc") not in ("", None) else 0.0)
    ) / 4.0
    ui_score = (
        (release_posted / release_total if release_total else 0.0)
        + (campaign_posted / campaign_total if campaign_total else 0.0)
    ) / 2.0

    items = [
        _coverage_item(
            item_id="indexes_spreads",
            label="Indexes and oil-style spreads",
            score=index_score,
            metric=f"{electricity_usable}/{electricity_total} electricity, {compute_usable}/{compute_total} compute, {archetype_replayed}/{archetype_total} spreads replayed",
            evidence=coverage.get("summary") or "Index catalog and spread archetype coverage are generated from backend replay state.",
            next_step="Wire planned ISO/regional compute curves so proxy basis rows become physical basis rows.",
        ),
        _coverage_item(
            item_id="profitability_backtests",
            label="Backtested profitability",
            score=profitability_score,
            metric=f"{len(ledger_rows)} ledger rows, {profitable_rows} positive, {promotable_rows} promotable/OOS rows",
            evidence=profitability_ledger.get("realized_note") or "Replay rows and local paper marks are separated from settled PnL.",
            next_step="Keep counting every tested spread/slug and reconcile real fills when settlements exist.",
        ),
        _coverage_item(
            item_id="real_venue_copy",
            label="Real venue copy matrix",
            score=venue_score,
            metric=f"{len(venue_rows)} surfaces, {priced_surfaces} priced, {ready_pairs}/{total_pairs} direct pairs ready",
            evidence=venue_evidence.get("guardrail") or "Venues are evidence/watchlist state until judge.classify() returns EXECUTE.",
            next_step="Refresh IBKR/Kalshi/Polymarket pricing and run premium scorer + judge on matched direct pairs.",
        ),
        _coverage_item(
            item_id="signals_pnl",
            label="Buy/sell and PnL tracking",
            score=signal_score,
            metric=f"action {portfolio_signal.get('action') or 'none'}, paper latest {pnl.get('paper_latest_mark_pnl_usdc') or 'n/a'} USDC",
            evidence=pnl.get("mark_to_market_note") or "Paper tickets are tracked separately from settled venue/Arc PnL.",
            next_step="Open and close account-owned paper tickets during demo to populate realized paper PnL.",
        ),
        _coverage_item(
            item_id="frontend_tg",
            label="Frontend, Mini App, Telegram campaign",
            score=ui_score,
            metric=f"Mini App release {release_posted}/{release_total}, campaign {campaign_posted}/{campaign_total}",
            evidence="Release/campaign state is read from sent keys only; message bodies and bot tokens are not exposed.",
            next_step="Post any remaining deduped channel campaign updates after the latest screenshot refresh.",
        ),
    ]
    requirements = [
        _requirement_item(
            item_id="req_1_indexes_spreads",
            label="1. Index universe and spread families",
            score=(
                (1.0 if electricity_total >= 10 and electricity_usable >= 5 else min(electricity_usable / 5.0, 0.8))
                + (1.0 if compute_total >= 10 and compute_usable >= 4 else min(compute_usable / 4.0, 0.8))
                + (1.0 if archetype_total >= 8 and archetype_replayed >= 8 else min(archetype_replayed / 8.0, 0.8))
                + (1.0 if electricity_families and compute_families else 0.0)
            ) / 4.0,
            evidence=[
                f"{electricity_usable}/{electricity_total} electricity indexes usable; families: {', '.join(sorted(electricity_families)) or 'not bucketed'}",
                f"{compute_usable}/{compute_total} compute indexes usable; families: {', '.join(sorted(compute_families)) or 'not bucketed'}",
                f"{archetype_replayed}/{archetype_total} oil-style spread forms replayed.",
            ],
            gaps=[] if electricity_total >= 10 and compute_total >= 10 and archetype_replayed >= 8 else [
                "Expand catalog or replay evidence until both index universes and spread families clear thresholds.",
            ],
        ),
        _requirement_item(
            item_id="req_2_profitable_backtests",
            label="2. Profitability and OOS backtests",
            score=profitability_score,
            evidence=[
                f"{len(ledger_rows)} profitability ledger rows.",
                f"{profitable_rows} rows positive by paper return or latest mark PnL.",
                f"{promotable_rows} rows promotable/OOS; {archetype_oos} spread archetypes OOS-passed.",
            ],
            gaps=[] if profitability_score >= 0.85 else [
                "Need more positive replay/OOS rows before fresh buy labels should be promoted.",
            ],
        ),
        _requirement_item(
            item_id="req_3_real_venue_syndication",
            label="3. Real venues, LLM evidence, syndicated instruments",
            score=venue_score,
            evidence=[
                f"{len(menu)} syndicated instrument types generated.",
                f"{len(venue_rows)} venue rows, {real_feed_surfaces} real-feed surfaces, {priced_surfaces} priced surfaces.",
                f"{direct_surfaces} direct-event surfaces; {ready_pairs}/{total_pairs} direct pairs ready for premium/judge.",
                f"{oracle_current} current-desk Opoint/Nebius receipts.",
                f"Power tradeability: {electricity_tradeability}; compute tradeability: {compute_tradeability}.",
            ],
            gaps=[] if venue_score >= 0.85 and len(menu) >= 5 else [
                "Need more priced real venue rows or syndicated structures before treating this as a broad venue copy matrix.",
            ],
        ),
        _requirement_item(
            item_id="req_4_signals_pnl",
            label="4. Buy/sell signals and PnL tracking",
            score=signal_score,
            evidence=[
                f"Portfolio action: {portfolio_signal.get('action') or 'none'}.",
                f"{len(portfolio_rows)} signal rows; paper latest mark PnL {pnl.get('paper_latest_mark_pnl_usdc') or 'n/a'} USDC.",
                f"Paper buy count {_safe_int(pnl.get('paper_buy_count'))}; close/avoid count {_safe_int(pnl.get('paper_close_or_avoid_count'))}.",
            ],
            gaps=[] if signal_score >= 0.85 else [
                "Need account-owned paper tickets or signal rows before PnL tracking is demonstrable.",
            ],
        ),
        _requirement_item(
            item_id="req_5_frontend_tg",
            label="5. Frontend, Mini App, Telegram posts",
            score=ui_score,
            evidence=[
                f"Mini App release posts {release_posted}/{release_total}.",
                f"Campaign posts {campaign_posted}/{campaign_total}.",
                "Dashboard and Mini App consume this same sanitized goal coverage payload.",
            ],
            gaps=[] if ui_score >= 0.85 else [
                "Post remaining deduped Telegram updates and expose the latest payload in the Mini App.",
            ],
        ),
    ]
    overall_score = round(sum(float(item["score"]) for item in items) / max(len(items), 1), 1)
    return {
        "version": "goal_coverage_v1",
        "overall_score": overall_score,
        "overall_status": _coverage_status(overall_score / 100.0),
        "items": items,
        "requirements": requirements,
        "summary": (
            f"{archetype_replayed}/{archetype_total} spread forms replayed, "
            f"{len(menu)} syndicated instruments, {len(ledger_rows)} profitability rows, "
            f"{priced_surfaces} priced venue surfaces, {release_posted}/{release_total} Mini App release posts."
        ),
        "guardrail": "This is readiness telemetry only; Circle/Arc remain locked unless judge.classify() returns EXECUTE.",
    }


def _compact_row(row: dict[str, Any], *, max_text: int = 900) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, str) and key in {"description", "leg_description", "pricing_detail", "leg_connection"}:
            out[key] = value if len(value) <= max_text else f"{value[:max_text].rstrip()}..."
        else:
            out[key] = value
    return out


def _compact_trade_replay(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    out = dict(value)
    closed = out.get("closed_trades")
    if isinstance(closed, list):
        out["closed_trades"] = closed[-2:]
    return out


def _compact_synthetic_menu_item(row: dict[str, Any]) -> dict[str, Any]:
    out = _compact_row(row, max_text=600)
    for key in ("paper_trade_replay", "out_of_sample_replay"):
        if key in out:
            out[key] = _compact_trade_replay(out[key])
    return out


def _compact_profitability_row(row: dict[str, Any]) -> dict[str, Any]:
    out = _compact_row(row, max_text=600)
    marks = out.get("recent_paper_marks")
    if isinstance(marks, list):
        out["recent_paper_marks"] = marks[-3:]
    for key in ("paper_trade_replay", "out_of_sample_replay", "spread_out_of_sample_replay"):
        if key in out:
            out[key] = _compact_trade_replay(out[key])
    return out


def _compact_trade_map_row(row: dict[str, Any]) -> dict[str, Any]:
    out = _compact_row(row, max_text=600)
    out.pop("expressions", None)
    if "spread_out_of_sample_replay" in out:
        out["spread_out_of_sample_replay"] = _compact_trade_replay(out["spread_out_of_sample_replay"])
    selected = out.get("selected_expression")
    if isinstance(selected, dict):
        out["selected_expression"] = _compact_synthetic_menu_item(selected)
    return out


def _compact_venue_matrix(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    out = dict(value)
    rows = []
    for row in out.get("rows") or []:
        if not isinstance(row, dict):
            rows.append(row)
            continue
        clean = _compact_row(row, max_text=500)
        sample_legs = []
        for leg in clean.get("sample_legs") or []:
            if not isinstance(leg, dict):
                sample_legs.append(leg)
                continue
            leg_clean = _compact_row(leg, max_text=280)
            leg_clean.pop("description", None)
            sample_legs.append(leg_clean)
        clean["sample_legs"] = sample_legs[:3]
        links = clean.get("spread_links")
        if isinstance(links, list):
            clean["spread_links"] = links[:3]
        rows.append(clean)
    out["rows"] = rows
    return out


def _build_compact_snapshot(*, logs: Path | str | None = None) -> dict[str, Any]:
    out = snapshot(logs=logs)

    spread_families = out.get("spread_families")
    if isinstance(spread_families, dict):
        spread_families.pop("recorded_history_replay", None)
        spread_families.pop("proxy_history_replay", None)

    synthetic = out.get("synthetic_instrument")
    outputs = synthetic.get("outputs") if isinstance(synthetic, dict) else None
    if isinstance(outputs, dict):
        outputs.pop("spread_family_validation", None)
        outputs.pop("proxy_basket_validation", None)
        if isinstance(outputs.get("spread_archetype_trade_map"), list):
            outputs["spread_archetype_trade_map"] = [
                _compact_trade_map_row(row) if isinstance(row, dict) else row
                for row in outputs["spread_archetype_trade_map"][:10]
            ]
        ledger = outputs.get("spread_profitability_ledger")
        if isinstance(ledger, dict) and isinstance(ledger.get("rows"), list):
            ledger["rows"] = [
                _compact_profitability_row(row) if isinstance(row, dict) else row
                for row in ledger["rows"][:10]
            ]
        if isinstance(outputs.get("syndicated_instrument_menu"), list):
            outputs["syndicated_instrument_menu"] = [
                _compact_synthetic_menu_item(row) if isinstance(row, dict) else row
                for row in outputs["syndicated_instrument_menu"][:10]
            ]
        if isinstance(outputs.get("real_venue_copy_matrix"), dict):
            outputs["real_venue_copy_matrix"] = _compact_venue_matrix(outputs["real_venue_copy_matrix"])
        pairs = outputs.get("direct_event_pair_candidates")
        if isinstance(pairs, dict) and isinstance(pairs.get("rows"), list):
            pairs["rows"] = [
                _compact_row(row, max_text=500) if isinstance(row, dict) else row
                for row in pairs["rows"][:6]
            ]

    for key, limit in (("verdicts", 20), ("positions", 20), ("arc_txs", 20), ("packages", 12)):
        rows = out.get(key)
        if isinstance(rows, list):
            out[key] = [_compact_row(row) if isinstance(row, dict) else row for row in rows[:limit]]

    for key in ("verdict_rollups", "direct_inventory", "public_hedges"):
        rows = out.get(key)
        if isinstance(rows, list):
            out[key] = [_compact_row(row) if isinstance(row, dict) else row for row in rows]

    ledger = out.get("profitability_ledger")
    if isinstance(ledger, dict) and isinstance(ledger.get("rows"), list):
        ledger["rows"] = [
            _compact_profitability_row(row) if isinstance(row, dict) else row
            for row in ledger["rows"][:10]
        ]
    portfolio_signal = out.get("portfolio_signal")
    if isinstance(portfolio_signal, dict) and isinstance(portfolio_signal.get("rows"), list):
        portfolio_signal["rows"] = [
            _compact_profitability_row(row) if isinstance(row, dict) else row
            for row in portfolio_signal["rows"][:10]
        ]
    venue = out.get("venue_evidence")
    if isinstance(venue, dict):
        out["venue_evidence"] = _compact_venue_matrix(venue)

    return out


def compact_snapshot(*, logs: Path | str | None = None) -> dict[str, Any]:
    """Return the same product state with duplicate replay blobs removed.

    The full `snapshot()` remains the audit/internal projection. This compact
    shape is for browser, Mini App, and account endpoints where repeated
    backtest blobs and old raw rows make the UI slow without adding new user
    information.
    """
    global _COMPACT_SNAPSHOT_CACHE
    cache_seconds = _num_env("SNAPSHOT_CACHE_SECONDS", 60.0)
    cache_enabled = logs is None and cache_seconds > 0
    cache_key = str(log_dir(logs).resolve())
    now = time.time()
    if cache_enabled:
        with _COMPACT_SNAPSHOT_LOCK:
            if _COMPACT_SNAPSHOT_CACHE and _COMPACT_SNAPSHOT_CACHE[0] > now and _COMPACT_SNAPSHOT_CACHE[1] == cache_key:
                return copy.deepcopy(_COMPACT_SNAPSHOT_CACHE[2])

        _COMPACT_SNAPSHOT_BUILD_LOCK.acquire()
        try:
            with _COMPACT_SNAPSHOT_LOCK:
                if (
                    _COMPACT_SNAPSHOT_CACHE
                    and _COMPACT_SNAPSHOT_CACHE[0] > time.time()
                    and _COMPACT_SNAPSHOT_CACHE[1] == cache_key
                ):
                    return copy.deepcopy(_COMPACT_SNAPSHOT_CACHE[2])

            out = _build_compact_snapshot(logs=logs)
            with _COMPACT_SNAPSHOT_LOCK:
                _COMPACT_SNAPSHOT_CACHE = (time.time() + cache_seconds, cache_key, copy.deepcopy(out))
            return out
        finally:
            _COMPACT_SNAPSHOT_BUILD_LOCK.release()

    return _build_compact_snapshot(logs=logs)


def warm_compact_snapshot_cache() -> bool:
    try:
        compact_snapshot()
    except Exception:
        return False
    return True


def snapshot(*, logs: Path | str | None = None) -> dict[str, Any]:
    now = time.time()
    spread = spread_state(logs=logs)
    spread_families = spread_family_state(logs=logs)
    proxy_baskets = proxy_basket_state(logs=logs)
    signal = signal_state(logs=logs)
    signal_latest = signal.get("latest") if isinstance(signal.get("latest"), dict) else {}
    signal_direction = str((signal_latest or {}).get("direction") or "")
    active_proxy_basket, active_proxy_gate = select_proxy_basket_for_direction(proxy_baskets, signal_direction)
    if isinstance(proxy_baskets, dict):
        proxy_baskets = dict(proxy_baskets)
        proxy_baskets["active_direction"] = signal_direction
        proxy_baskets["active_basket"] = active_proxy_basket
        proxy_baskets["active_entry_gate_pass"] = active_proxy_gate
    verdicts = verdict_state(logs=logs)
    positions = position_state(logs=logs)
    direct_inventory = direct_inventory_state(logs=logs)
    public_hedges = public_hedge_state(logs=logs)
    verdict_rollups = rollup_leg_rows(_visible_leg_rows(verdicts))
    packages = package_state(verdicts, positions)
    venue_evidence = venue_evidence_state(
        direct_inventory=direct_inventory,
        public_hedges=public_hedges,
        verdicts=verdict_rollups,
        proxy_baskets=proxy_baskets,
        logs=logs,
    )
    oracle_evidence = _oracle_evidence_state(logs=logs)
    synthetic_instrument = propose_synthetic_instrument(
        spread=spread,
        signal=signal,
        direct_inventory=direct_inventory,
        public_hedges=public_hedges,
        packages=packages,
        verdicts=verdict_rollups,
        positions=positions,
        spread_family_validation=spread_families,
        proxy_basket_validation=proxy_baskets,
        oracle_evidence=oracle_evidence,
        venue_evidence=venue_evidence,
    )
    synthetic_outputs = synthetic_instrument.get("outputs") if isinstance(synthetic_instrument, dict) else {}
    if not isinstance(synthetic_outputs, dict):
        synthetic_outputs = {}
    profitability_ledger = synthetic_outputs.get("spread_profitability_ledger") or {}
    portfolio_signal = synthetic_outputs.get("portfolio_signal_summary") or {}
    pnl = pnl_state(logs=logs)
    real_positions = _visible_leg_rows(positions)
    real_verdicts = _visible_leg_rows(verdicts)
    job_ids = {
        str(row.get("job_id"))
        for row in real_positions
        if row.get("job_id") not in ("", None)
    }
    pnl.update({
        "has_reconciled": int(pnl.get("trades") or 0) > 0,
        "reconciled_trades": pnl.get("trades", 0),
        "wrapped_jobs": len(job_ids),
        "executed_verdicts": sum(1 for row in real_verdicts if row.get("label") == "EXECUTE"),
        "visible_positions": len(real_positions),
    })
    pnl = enrich_pnl_state(
        pnl,
        spread_families=spread_families,
        proxy_baskets=proxy_baskets,
        signal_direction=signal_direction,
        visible_positions=len(real_positions),
    )
    if isinstance(portfolio_signal, dict):
        pnl.update({
            "paper_portfolio_action": portfolio_signal.get("action", ""),
            "paper_portfolio_headline": portfolio_signal.get("headline", ""),
            "paper_ticket_total_pnl_usdc": portfolio_signal.get("paper_ticket_total_pnl_usdc", ""),
            "paper_ticket_realized_pnl_usdc": portfolio_signal.get("paper_ticket_realized_pnl_usdc", ""),
            "paper_ticket_open_pnl_usdc": portfolio_signal.get("paper_ticket_open_pnl_usdc", ""),
            "paper_latest_mark_pnl_usdc": portfolio_signal.get("latest_mark_total_pnl_usdc", ""),
            "paper_buy_count": portfolio_signal.get("buy_count", 0),
            "paper_close_or_avoid_count": portfolio_signal.get("close_or_avoid_count", 0),
            "paper_wait_count": portfolio_signal.get("wait_count", 0),
            "paper_replay_realized": bool(portfolio_signal.get("realized")),
        })
    telegram_campaign = telegram_campaign_state(logs=logs)
    telegram_miniapp_release = telegram_miniapp_release_state(logs=logs)
    goal_coverage = goal_coverage_state(
        spread_families=spread_families,
        synthetic_instrument=synthetic_instrument,
        profitability_ledger=profitability_ledger,
        portfolio_signal=portfolio_signal,
        venue_evidence=venue_evidence,
        oracle_evidence=oracle_evidence,
        telegram_campaign=telegram_campaign,
        telegram_miniapp_release=telegram_miniapp_release,
        pnl=pnl,
    )
    return {
        "ok": True,
        "generated_at": now,
        "mode": {
            "live_chain_enabled": bool_env("ENABLE_LIVE_CHAIN", False),
            "telegram_enabled": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        },
        "runtime": runtime_status(logs=logs),
        "spread": spread,
        "spread_families": spread_families,
        "proxy_baskets": proxy_baskets,
        "signal": signal,
        "verdicts": verdicts,
        "verdict_rollups": verdict_rollups,
        "packages": packages,
        "synthetic_instrument": synthetic_instrument,
        "profitability_ledger": profitability_ledger,
        "portfolio_signal": portfolio_signal,
        "direct_inventory": direct_inventory,
        "public_hedges": public_hedges,
        "venue_evidence": venue_evidence,
        "positions": positions,
        "arc_txs": arc_tx_state(logs=logs),
        "pnl": pnl,
        "oracle": oracle_evidence,
        "telegram_campaign": telegram_campaign,
        "telegram_miniapp_release": telegram_miniapp_release,
        "goal_coverage": goal_coverage,
    }
