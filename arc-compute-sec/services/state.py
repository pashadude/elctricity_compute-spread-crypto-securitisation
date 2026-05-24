"""Read-only, sanitized backend state for API, worker, and Telegram.

This module intentionally reads only public runtime artifacts. It never exposes
`logs/identity.tsv`, wallet IDs, entity secrets, or `.env` values.
"""
from __future__ import annotations

import csv
import functools
import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from services.env import load_project_env
from agent.synthetic_instrument import propose_synthetic_instrument
from adapters.yahoo_finance import fetch_chart_quote
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
DEFAULT_PUBLIC_HEDGE_SYMBOLS = ("NVDA", "VRT", "ETN", "CEG", "NRG", "BTC-USD", "ETH-USD")
DEFAULT_PUBLIC_HEDGE_PRICE_SOURCES = ("yahoo",)
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


def sanitize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key is None or _is_sensitive_key(str(key)):
            continue
        if isinstance(value, str):
            out[str(key)] = _coerce_value(value)
        else:
            out[str(key)] = value
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
    latest = rows[-1] if rows else None
    history: list[float] = []
    for row in rows:
        try:
            history.append(float(row.get("S_t", 0.0)))
        except (TypeError, ValueError):
            continue
    return {"latest": latest, "history": history}


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
    if low == "price_unavailable":
        return "Price unavailable"
    if low == "closed_watchlist":
        return "Closed"
    return str(status or "Needs review").replace("_", " ")


def _fetch_ibkr_public_quote(symbol: str) -> dict[str, Any] | None:
    clean = str(symbol or "").strip().upper()
    if not clean or "-" in clean:
        return None
    try:
        from adapters.ibkr import fetch_last_price

        price = fetch_last_price(clean)
    except Exception as exc:
        return {
            "symbol": clean,
            "price": None,
            "source": "ibkr_tws",
            "error": exc.__class__.__name__,
        }
    if price is None:
        return None
    return {
        "symbol": clean,
        "price": float(price),
        "currency": "USD",
        "exchange": "SMART",
        "source": "ibkr_tws",
    }


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
        return fetch_chart_quote(symbol)
    except Exception as exc:
        return {
            "symbol": str(symbol or "").strip().upper(),
            "price": None,
            "source": "yahoo_finance_chart",
            "error": exc.__class__.__name__,
        }


def _fetch_public_quote(symbol: str) -> dict[str, Any] | None:
    cache_key = str(symbol or "").strip().upper()
    if not cache_key:
        return None
    sources = [item.lower() for item in _env_csv("PUBLIC_HEDGE_PRICE_SOURCES", DEFAULT_PUBLIC_HEDGE_PRICE_SOURCES)]
    source_key = ",".join(sources) or "yahoo"
    cached = cache.get("public_quote", f"{source_key}|{cache_key}")
    if isinstance(cached, dict):
        return cached
    quote: dict[str, Any] | None = None
    errors: list[str] = []
    for source in sources:
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


def public_hedge_state(*, logs: Path | str | None = None) -> list[dict[str, Any]]:
    """Priced public-market proxies used when direct event contracts are unpriced.

    These are not direct claims on compute or electricity. They are liquid,
    priced hedge references for the commercial compute-sale package.
    """
    now = time.time()
    rows: list[dict[str, Any]] = []
    fetch_live = bool_env("PUBLIC_HEDGE_FETCH", True)
    for symbol in _env_csv("PUBLIC_HEDGE_SYMBOLS", DEFAULT_PUBLIC_HEDGE_SYMBOLS):
        clean = symbol.strip().upper()
        if not clean:
            continue
        meta = PUBLIC_HEDGE_META.get(clean, {})
        quote = _fetch_public_quote(clean) if fetch_live else None
        price = quote.get("price") if isinstance(quote, dict) else None
        row = sanitize_row({
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
        rows.append(row)
    return rows


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
    env_name = "SIZING_IBKR_PREDICTION_USDC" if surface == "ibkr_prediction" else "SIZING_POLYMARKET_USDC"
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
    quote = _fetch_public_quote(proxy_symbol)
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
        })
    return base


def _ibkr_inventory_rows(*, logs: Path | str | None = None) -> list[dict[str, Any]]:
    symbols = [s.upper() for s in _env_csv("IBKR_DIRECT_EVENT_SYMBOLS", DEFAULT_IBKR_DIRECT_EVENT_SYMBOLS)]
    live_events = _read_ibkr_forecast_inventory(logs=logs)
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
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
        rows.append(row)
    return rows


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


def direct_inventory_state(*, logs: Path | str | None = None) -> list[dict[str, Any]]:
    """Configured real direct-event surfaces shown as watchlist inventory.

    Inventory rows explain currently monitored IBKR/Polymarket legs, but they
    are not candidate rows. Polymarket still needs the preserved premium gate;
    IBKR event contracts still need usable quote fields before either can reach
    judge.classify() or Arc.
    """
    if not bool_env("DIRECT_EVENT_INVENTORY_ENABLED", True):
        return []
    rows = _ibkr_inventory_rows(logs=logs) + _polymarket_inventory_rows()
    return _visible_leg_rows(_enrich_leg_rows(rows, logs=logs))


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


def snapshot(*, logs: Path | str | None = None) -> dict[str, Any]:
    now = time.time()
    spread = spread_state(logs=logs)
    signal = signal_state(logs=logs)
    verdicts = verdict_state(logs=logs)
    positions = position_state(logs=logs)
    direct_inventory = direct_inventory_state(logs=logs)
    public_hedges = public_hedge_state(logs=logs)
    verdict_rollups = rollup_leg_rows(_visible_leg_rows(verdicts))
    packages = package_state(verdicts, positions)
    synthetic_instrument = propose_synthetic_instrument(
        spread=spread,
        signal=signal,
        direct_inventory=direct_inventory,
        public_hedges=public_hedges,
        packages=packages,
        verdicts=verdict_rollups,
        positions=positions,
    )
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
    return {
        "ok": True,
        "generated_at": now,
        "mode": {
            "live_chain_enabled": bool_env("ENABLE_LIVE_CHAIN", False),
            "telegram_enabled": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        },
        "runtime": runtime_status(logs=logs),
        "spread": spread,
        "signal": signal,
        "verdicts": verdicts,
        "verdict_rollups": verdict_rollups,
        "packages": packages,
        "synthetic_instrument": synthetic_instrument,
        "direct_inventory": direct_inventory,
        "public_hedges": public_hedges,
        "positions": positions,
        "arc_txs": arc_tx_state(logs=logs),
        "pnl": pnl,
        "oracle": {},
    }
