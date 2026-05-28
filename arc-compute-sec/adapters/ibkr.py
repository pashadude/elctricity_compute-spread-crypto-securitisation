"""IBKR demo paper-trading adapter via ib_insync.

This adapter ONLY uses the paper-trading account. It connects to the IB
Gateway/TWS on `IBKR_HOST:IBKR_GATEWAY_PORT` (defaults 127.0.0.1:4002).
`IBKR_PORT` is accepted as a compatibility alias for the Brent strategy repo.
The operator must have Gateway running in paper mode before any chain
phase starts; pre-Gate-A this adapter is unreachable.

If the connection is not available, `place_paper_order` either:
  - returns a deterministic stub fill report (when called with dry_run=True)
  - raises RuntimeError with a clear diagnostic
"""
from __future__ import annotations

import asyncio
import calendar
import csv
import hashlib
import json
import math
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

# `ib_insync` requires a running asyncio event loop on import in some
# environments. We try to lazy-init.

_ib_singleton: Any = None
_forecast_tws_unavailable_reason: str | None = None
_FORECAST_KEYWORDS = (
    "ai", "artificial intelligence", "compute", "data center", "datacenter",
    "electric", "electricity", "energy", "ercot", "grid", "industrial production",
    "fed funds", "gdp", "gas", "inference", "natural gas", "nvidia", "oil",
    "power", "renewable", "temperature", "training", "unemployment", "weather",
)
_TWS_FORECAST_TERMS = (
    "electricity", "renewable energy", "natural gas", "crude oil", "oil",
    "temperature", "weather", "Nvidia", "AI", "industrial production",
    "Fed Funds", "CPI", "unemployment", "GDP",
)
_PUBLIC_FUTURE_SYMBOLS: dict[str, tuple[str, str, str]] = {
    "CL": ("CL", "NYMEX", "USD"),
    "CL=F": ("CL", "NYMEX", "USD"),
    "BZ": ("BZ", "NYMEX", "USD"),
    "BZ=F": ("BZ", "NYMEX", "USD"),
    "NG": ("NG", "NYMEX", "USD"),
    "NG=F": ("NG", "NYMEX", "USD"),
    "RB": ("RB", "NYMEX", "USD"),
    "RB=F": ("RB", "NYMEX", "USD"),
    "HO": ("HO", "NYMEX", "USD"),
    "HO=F": ("HO", "NYMEX", "USD"),
    "ZQ": ("ZQ", "CBOT", "USD"),
    "ZQ=F": ("ZQ", "CBOT", "USD"),
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _ibkr_host() -> str:
    return os.environ.get("IBKR_HOST", "127.0.0.1")


def _ibkr_port() -> int:
    # Brent strategy uses IBKR_PORT; this repo historically used
    # IBKR_GATEWAY_PORT. Gateway paper=4002, TWS paper=7497.
    raw = os.environ.get("IBKR_GATEWAY_PORT") or os.environ.get("IBKR_PORT") or "4002"
    try:
        return int(raw)
    except ValueError:
        return 4002


def _ibkr_client_id() -> int:
    try:
        return int(os.environ.get("IBKR_CLIENT_ID", "42"))
    except ValueError:
        return 42


def _cp_timeout() -> float:
    try:
        return float(os.environ.get("IBKR_CP_TIMEOUT", "8"))
    except ValueError:
        return 8.0


def _cp_restore_timeout() -> float:
    try:
        return float(os.environ.get("IBKR_CP_RESTORE_TIMEOUT", "3"))
    except ValueError:
        return 3.0


def _cp_reauth_wait_seconds() -> float:
    try:
        return float(os.environ.get("IBKR_CP_REAUTH_WAIT_SECONDS", "8"))
    except ValueError:
        return 8.0


def _cp_base_url() -> str:
    return os.environ.get("IBKR_CP_BASE_URL", "https://localhost:5055/v1/api").rstrip("/")


def _cp_verify_ssl() -> bool:
    return os.environ.get("IBKR_CP_VERIFY_SSL", "0").strip().lower() in {"1", "true", "yes"}


def _cp_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> Any:
    """Read one IBKR Client Portal endpoint.

    This is intentionally read-only. The local Client Portal Gateway commonly
    uses a self-signed certificate, so SSL verification is opt-in via
    IBKR_CP_VERIFY_SSL=1.
    """
    base_url = _cp_base_url()
    url = f"{base_url}/{path.lstrip('/')}"
    try:
        resp = requests.request(
            method,
            url,
            params=params,
            json=json_body,
            timeout=timeout if timeout is not None else _cp_timeout(),
            verify=_cp_verify_ssl(),
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"IBKR Client Portal API not reachable at {base_url}. "
            "Start Client Portal Gateway or an authenticated IBKR Desktop/API session, "
            "then confirm /iserver/auth/status is authenticated. "
            f"Underlying error: {exc!r}"
        ) from exc
    try:
        return resp.json()
    except ValueError as exc:
        raise RuntimeError(f"IBKR Client Portal returned non-JSON for {path}") from exc


def _cp_get(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> Any:
    return _cp_request("GET", path, params=params, timeout=timeout)


def _cp_post(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> Any:
    return _cp_request("POST", path, params=params, json_body=json_body, timeout=timeout)


def client_portal_auth_status() -> dict[str, Any]:
    body = _cp_get("/iserver/auth/status")
    return body if isinstance(body, dict) else {"raw": body}


def client_portal_health(*, timeout: float | None = None) -> dict[str, Any]:
    """Return a sanitized Client Portal health snapshot for operator UI.

    The raw IBKR status can include local hardware identifiers. This helper
    deliberately exposes only connectivity/auth booleans and an action hint.
    """
    base_url = _cp_base_url()
    login_url = base_url.rsplit("/v1/api", 1)[0] if base_url.endswith("/v1/api") else base_url
    try:
        status = _cp_get(
            "/iserver/auth/status",
            timeout=timeout if timeout is not None else min(_cp_timeout(), 2.0),
        )
    except RuntimeError as exc:
        cause = exc.__cause__
        return {
            "status": "UNREACHABLE",
            "reachable": False,
            "authenticated": False,
            "connected": False,
            "competing": False,
            "error_code": cause.__class__.__name__ if cause else exc.__class__.__name__,
            "action": f"Start Client Portal Gateway and open {login_url} to login.",
        }
    authenticated = _cp_status_bool(status, "authenticated") is True
    connected = _cp_status_bool(status, "connected") is True
    competing = _cp_status_bool(status, "competing") is True
    if authenticated and connected and not competing:
        health_status = "AUTHENTICATED"
        action = "Client Portal is authenticated; venue EC quotes can be requested."
    elif competing:
        health_status = "COMPETING_SESSION"
        action = "Close duplicate IBKR sessions or use a separate login, then reauthenticate Client Portal."
    else:
        health_status = "NEEDS_REAUTH"
        action = f"Open {login_url}, finish login/2FA, then run npm run ibkr:cp-watchdog-once."
    return {
        "status": health_status,
        "reachable": True,
        "authenticated": authenticated,
        "connected": connected,
        "competing": competing,
        "action": action,
    }


def client_portal_user_status() -> dict[str, Any]:
    body = _cp_get("/one/user")
    return body if isinstance(body, dict) else {"raw": body}


def _cp_status_bool(status: dict[str, Any], key: str) -> Any:
    if key in status:
        return status.get(key)
    auth_status = status.get("authStatus")
    if isinstance(auth_status, dict) and key in auth_status:
        return auth_status.get(key)
    iserver = status.get("iserver")
    if isinstance(iserver, dict) and key in iserver:
        return iserver.get(key)
    return None


def client_portal_tickle() -> dict[str, Any]:
    """Keep the local Client Portal session alive if the gateway is responsive."""
    body = _cp_get("/tickle", timeout=_cp_restore_timeout())
    return body if isinstance(body, dict) else {"raw": body}


def client_portal_reauthenticate(*, wait_seconds: float | None = None) -> dict[str, Any]:
    """Trigger IBKR's soft brokerage-bridge reauth and poll auth status.

    This can recover the common "SSO is live, /iserver is not established" case.
    It cannot recover a wedged Java Client Portal Gateway process or an expired
    browser login that requires a human/2FA flow.
    """
    _cp_post("/iserver/reauthenticate", timeout=_cp_restore_timeout())
    deadline = time.time() + (wait_seconds if wait_seconds is not None else _cp_reauth_wait_seconds())
    latest: dict[str, Any] = {}
    while time.time() <= deadline:
        try:
            latest = client_portal_auth_status()
        except RuntimeError:
            time.sleep(0.5)
            continue
        if _cp_status_bool(latest, "authenticated") is True and _cp_status_bool(latest, "connected") is True:
            return latest
        time.sleep(0.5)
    return latest


def client_portal_ensure_ready() -> dict[str, Any]:
    """Return auth status, attempting one soft restore when configured.

    Controlled by `IBKR_CP_AUTO_REAUTH` (default: on). The restore sequence is
    read-only: `/tickle`, then `POST /iserver/reauthenticate`, then status poll.
    """
    try:
        status = client_portal_auth_status()
    except RuntimeError as exc:
        if not _env_bool("IBKR_CP_AUTO_REAUTH", True):
            raise
        print(f"[ibkr] Client Portal status check failed; attempting soft restore: {exc}")
        try:
            client_portal_tickle()
        except RuntimeError as tickle_exc:
            print(f"[ibkr] Client Portal tickle failed before reauth: {tickle_exc}")
        try:
            return client_portal_reauthenticate()
        except RuntimeError as restore_exc:
            raise RuntimeError(
                f"IBKR Client Portal soft restore failed after status error: {restore_exc}"
            ) from exc
    if _cp_status_bool(status, "authenticated") is True and _cp_status_bool(status, "connected") is True:
        return status
    if not _env_bool("IBKR_CP_AUTO_REAUTH", True):
        return status
    try:
        client_portal_tickle()
    except RuntimeError as exc:
        print(f"[ibkr] Client Portal tickle failed before reauth: {exc}")
    restored = client_portal_reauthenticate()
    return restored or status


def _date_to_contract_month(value: str) -> str | None:
    try:
        dt = datetime.strptime(str(value), "%Y%m%d")
    except ValueError:
        return None
    return f"{calendar.month_abbr[dt.month].upper()}{str(dt.year)[-2:]}"


def _parse_float(value: Any) -> float | None:
    try:
        out = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    if out < 0:
        return None
    # IBKR sometimes returns event prices as cents. Normalise to payout dollars.
    if out > 1.0 and out <= 100.0:
        return out / 100.0
    return out if out <= 1.0 else None


def _parse_positive_price(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(out) and out > 0:
        return out
    return None


def _ticker_public_price(ticker: Any) -> float | None:
    """Extract a positive stock/futures quote from an ib_insync ticker."""
    candidates: list[Any] = []
    try:
        candidates.append(ticker.marketPrice())
    except Exception:
        pass
    candidates.extend([
        getattr(ticker, "last", None),
        getattr(ticker, "close", None),
    ])
    try:
        candidates.append(ticker.midpoint())
    except Exception:
        pass
    candidates.extend([
        getattr(ticker, "delayedLast", None),
        getattr(ticker, "delayedClose", None),
    ])
    for cand in candidates:
        price = _parse_positive_price(cand)
        if price is not None:
            return price
    bid = _parse_positive_price(getattr(ticker, "bid", None))
    ask = _parse_positive_price(getattr(ticker, "ask", None))
    if bid is not None and ask is not None and bid <= ask:
        return (bid + ask) / 2.0
    return None


def _snapshot_price(row: dict[str, Any]) -> float | None:
    last = _parse_float(row.get("31"))
    bid = _parse_float(row.get("84"))
    ask = _parse_float(row.get("86"))
    if bid is not None and ask is not None and bid <= ask:
        return (bid + ask) / 2.0
    return last


def _forecast_tws_wait_seconds() -> float:
    try:
        return max(0.5, float(os.environ.get("IBKR_FORECAST_TWS_WAIT_SECONDS", "3")))
    except ValueError:
        return 3.0


def _forecast_tws_event_price(conid: Any) -> tuple[float | None, str]:
    """Try a delayed TWS snapshot for a ForecastTrader EC contract.

    Client Portal sometimes exposes ForecastTrader EC metadata but returns no
    bid/ask/last fields for `/iserver/marketdata/snapshot`. This fallback is
    still read-only and uses the paper TWS/Gateway socket if it is available.
    """
    global _forecast_tws_unavailable_reason
    if not conid:
        return None, "missing_conid"
    if _forecast_tws_unavailable_reason:
        return None, _forecast_tws_unavailable_reason
    try:
        from ib_insync import Contract

        ib = _connect()
        contract = Contract(conId=int(conid), secType="EC", exchange="FORECASTX", currency="USD")
        try:
            qualified = ib.qualifyContracts(contract)
            if qualified:
                contract = qualified[0]
        except Exception:
            pass
        ticker = ib.reqMktData(contract, "", False, False)
        ib.sleep(_forecast_tws_wait_seconds())
        bid = _parse_float(getattr(ticker, "bid", None))
        ask = _parse_float(getattr(ticker, "ask", None))
        last = _parse_float(getattr(ticker, "last", None))
        close = _parse_float(getattr(ticker, "close", None))
        try:
            market_price = _parse_float(ticker.marketPrice())
        except Exception:
            market_price = None
        try:
            ib.cancelMktData(contract)
        except Exception:
            pass
    except Exception as exc:
        reason = exc.__class__.__name__
        if "Gateway not reachable" in str(exc) or "Connect call failed" in str(exc):
            _forecast_tws_unavailable_reason = reason
        return None, reason
    if bid is not None and ask is not None and bid <= ask:
        return (bid + ask) / 2.0, "ibkr_tws_bid_ask"
    for price, source in (
        (last, "ibkr_tws_last"),
        (market_price, "ibkr_tws_market_price"),
        (close, "ibkr_tws_close"),
    ):
        if price is not None:
            return price, source
    return None, "tws_no_bid_ask_last"


def _flatten_forecast_markets(tree: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(tree, dict):
        return out
    for node_id, node in tree.items():
        if not isinstance(node, dict):
            continue
        labels: list[str] = []
        cur = node
        seen: set[str] = set()
        while isinstance(cur, dict):
            label = cur.get("label")
            if label:
                labels.append(str(label))
            parent_id = cur.get("parentId")
            if not parent_id or parent_id in seen:
                break
            seen.add(str(parent_id))
            cur = tree.get(parent_id) or {}
        category_path = " / ".join(reversed(labels))
        for market in node.get("markets") or []:
            if not isinstance(market, dict):
                continue
            out.append({
                "category_id": node_id,
                "category_path": category_path,
                "name": market.get("name") or market.get("label") or "",
                "symbol": market.get("symbol") or "",
                "exchange": market.get("exchange") or "FORECASTX",
                "underlier_conid": market.get("conid"),
                "raw": market,
            })
    return out


def _forecast_market_matches_thesis(market: dict[str, Any]) -> bool:
    blob = " ".join(str(market.get(k) or "") for k in ("name", "symbol", "category_path")).lower()
    return any(_keyword_in_blob(blob, term) for term in _FORECAST_KEYWORDS)


def _keyword_in_blob(blob: str, term: str) -> bool:
    if len(term) <= 3:
        return re.search(rf"\b{re.escape(term)}\b", blob) is not None
    return term in blob


def _forecast_theme(name: str, symbol: str = "") -> str:
    blob = f"{name} {symbol}".lower()
    if any(_keyword_in_blob(blob, term) for term in ("nvidia", "ai", "compute", "inference", "training", "data center", "datacenter")):
        return "ai_compute"
    if any(_keyword_in_blob(blob, term) for term in ("electric", "energy", "renewable", "power", "grid", "oil", "gas", "crude")):
        return "energy_power"
    if any(_keyword_in_blob(blob, term) for term in ("temperature", "weather", "co2", "carbon")):
        return "weather_climate"
    if any(_keyword_in_blob(blob, term) for term in ("industrial production", "fed funds", "cpi", "unemployment", "gdp")):
        return "macro"
    return "other"


def _forecast_market_key(market: dict[str, Any]) -> tuple[str, str]:
    return (str(market.get("symbol") or ""), str(market.get("underlier_conid") or ""))


def _dedupe_forecast_markets(markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for market in markets:
        key = _forecast_market_key(market)
        if key in seen:
            continue
        seen.add(key)
        out.append(market)
    return out


def _tws_forecast_terms() -> list[str]:
    raw = os.environ.get("IBKR_TWS_FORECAST_TERMS", "").strip()
    if not raw:
        return list(_TWS_FORECAST_TERMS)
    return [term.strip() for term in raw.split(",") if term.strip()]


def fetch_forecast_markets_from_client_portal(*, thesis_only: bool = True) -> list[dict[str, Any]]:
    """Read the ForecastEx category tree from the authenticated demo account.

    Returns market-level metadata. These are underlier markets, not yet priced
    YES/NO contracts.
    """
    tree = _cp_get("/trsrv/event/category-tree")
    markets = _flatten_forecast_markets(tree if isinstance(tree, dict) else {})
    if thesis_only:
        markets = [m for m in markets if _forecast_market_matches_thesis(m)]
    return markets


def fetch_forecast_markets_from_tws(
    *,
    terms: list[str] | None = None,
    thesis_only: bool = True,
) -> list[dict[str, Any]]:
    """Discover ForecastTrader/Event Contract underliers through TWS.

    TWS exposes event underliers through matching-symbol rows whose
    derivativeSecTypes include `EC`. This gives the demo account's eligible
    event-market symbols and underlier conids. It does not by itself return the
    tradable Yes/No contract conids; the Client Portal/Web API is still needed
    for priced contract discovery.
    """
    ib = _connect()
    markets: list[dict[str, Any]] = []
    for term in terms or _tws_forecast_terms():
        try:
            rows = ib.reqMatchingSymbols(term)
        except Exception as exc:
            print(f"[ibkr] TWS ForecastTrader matching-symbol search failed for {term!r}: {exc!r}")
            continue
        for row in rows:
            contract = getattr(row, "contract", None)
            derivative_types = list(getattr(row, "derivativeSecTypes", []) or [])
            if "EC" not in derivative_types or contract is None:
                continue
            symbol = str(getattr(contract, "symbol", "") or "").strip()
            if not symbol:
                continue
            description = str(getattr(contract, "description", "") or symbol)
            exchange = (
                getattr(contract, "primaryExchange", None)
                or getattr(contract, "exchange", None)
                or "FORECASTX"
            )
            theme = _forecast_theme(description, symbol)
            market = {
                "category_id": f"tws:{term}",
                "category_path": f"TWS matching-symbol search / {term}",
                "name": description,
                "symbol": symbol,
                "exchange": exchange,
                "underlier_conid": getattr(contract, "conId", None),
                "derivative_sec_types": derivative_types,
                "source": "ibkr_tws",
                "theme": theme,
                "raw": {
                    "symbol": symbol,
                    "secType": getattr(contract, "secType", None),
                    "conId": getattr(contract, "conId", None),
                    "primaryExchange": getattr(contract, "primaryExchange", None),
                    "currency": getattr(contract, "currency", None),
                    "description": description,
                    "derivativeSecTypes": derivative_types,
                    "search_term": term,
                },
            }
            if not thesis_only or theme != "other":
                markets.append(market)
    return _dedupe_forecast_markets(markets)


def fetch_forecast_markets(*, thesis_only: bool = True) -> list[dict[str, Any]]:
    """Discover ForecastTrader/Event Contract underlier markets.

    `IBKR_FORECAST_MARKET_SOURCE` controls discovery:
    - `client_portal`: Web API category tree only.
    - `tws`: TWS matching-symbol underliers only.
    - `both`: try Client Portal, then TWS.
    """
    source = os.environ.get("IBKR_FORECAST_MARKET_SOURCE", "client_portal").strip().lower()
    if source in {"tws", "gateway"}:
        return fetch_forecast_markets_from_tws(thesis_only=thesis_only)
    if source in {"both", "all"}:
        markets: list[dict[str, Any]] = []
        try:
            markets.extend(fetch_forecast_markets_from_client_portal(thesis_only=thesis_only))
        except RuntimeError as exc:
            print(f"[ibkr] Client Portal ForecastTrader category tree unavailable: {exc}")
        markets.extend(fetch_forecast_markets_from_tws(thesis_only=thesis_only))
        return _dedupe_forecast_markets(markets)
    return fetch_forecast_markets_from_client_portal(thesis_only=thesis_only)


def _forecast_search_result(symbol: str) -> dict[str, Any] | None:
    body = _cp_get("/iserver/secdef/search", params={"symbol": symbol})
    records = body if isinstance(body, list) else []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if str(rec.get("description") or "").upper() == "FORECASTX" or "FORECASTX" in str(rec.get("companyHeader") or "").upper():
            return rec
    return None


def _forecast_snapshots(conids: list[int | str]) -> dict[str, dict[str, Any]]:
    if not conids:
        return {}
    rows = _cp_get(
        "/iserver/marketdata/snapshot",
        params={"conids": ",".join(str(c) for c in conids), "fields": "31,84,85,86,88,7059"},
    )
    out: dict[str, dict[str, Any]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        conid = str(row.get("conid") or row.get("conidEx") or "").split("@")[0]
        if conid:
            out[conid] = row
    return out


def _forecast_sections(search: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for section in search.get("sections") or []:
        if isinstance(section, dict) and section.get("secType"):
            out.add(str(section.get("secType")).upper())
    return out


def _forecast_ec_event_for_market(market: dict[str, Any], search: dict[str, Any]) -> dict[str, Any] | None:
    underlier_conid = search.get("conid") or market.get("underlier_conid")
    if not underlier_conid:
        return None
    symbol = str(search.get("symbol") or market.get("symbol") or "").strip()
    name = str(search.get("companyName") or market.get("name") or symbol)
    snapshots = _forecast_snapshots([underlier_conid])
    snapshot = snapshots.get(str(underlier_conid), {})
    price = _snapshot_price(snapshot)
    price_source = "ibkr_client_portal_snapshot"
    pricing_detail = ""
    if price is None:
        tws_price, tws_status = _forecast_tws_event_price(underlier_conid)
        if tws_price is not None:
            price = tws_price
            price_source = tws_status
        else:
            pricing_detail = (
                "IBKR returned EC metadata, but Client Portal snapshot had no "
                f"bid/ask/last fields and TWS fallback returned {tws_status}."
            )
    yes_prices = [price, max(0.0, 1.0 - price)] if price is not None else []
    event = {
        "id": f"{symbol or underlier_conid}-EC",
        "symbol": symbol,
        "slug": f"{(symbol or str(underlier_conid)).lower()}-ec",
        "title": name,
        "description": (
            "IBKR ForecastTrader / ForecastEx event contract discovered as "
            "secType=EC through Client Portal. "
            f"Category: {market.get('category_path') or 'ForecastEx'}."
        ),
        "yes_prices": yes_prices,
        "venue": "IBKR ForecastTrader",
        "exchange": "FORECASTX",
        "sec_type": "EC",
        "underlier_conid": underlier_conid,
        "yes_conid": underlier_conid,
        "no_conid": None,
        "source": price_source if yes_prices else "ibkr_client_portal",
        "pricing_status": "priced" if yes_prices else "ibkr_quote_unavailable",
        "pricing_detail": pricing_detail,
        "raw_response_hash": hashlib.sha256(
            json.dumps({"market": market, "search": search, "snapshot": snapshot}, sort_keys=True, default=str).encode()
        ).hexdigest(),
    }
    return event


def _forecast_contract_events_for_market(market: dict[str, Any]) -> list[dict[str, Any]]:
    symbol = str(market.get("symbol") or "").strip()
    if not symbol:
        return []
    search = _forecast_search_result(symbol)
    if not search:
        return []
    if "EC" in _forecast_sections(search):
        event = _forecast_ec_event_for_market(market, search)
        return [event] if event else []
    underlier_conid = search.get("conid") or market.get("underlier_conid")
    expiries = [x for x in str(search.get("opt") or "").split(";") if x]
    max_months = int(os.environ.get("IBKR_FORECAST_MAX_MONTHS", "2"))
    max_strikes = int(os.environ.get("IBKR_FORECAST_MAX_STRIKES", "4"))
    events: list[dict[str, Any]] = []
    for expiry in expiries[:max_months]:
        month = _date_to_contract_month(expiry)
        if not month:
            continue
        strikes_body = _cp_get(
            "/iserver/secdef/strikes",
            params={"conid": underlier_conid, "exchange": "FORECASTX", "sectype": "OPT", "month": month},
        )
        strikes = []
        if isinstance(strikes_body, dict):
            strikes = list(strikes_body.get("call") or strikes_body.get("put") or [])
        for strike in strikes[:max_strikes]:
            info = _cp_get(
                "/iserver/secdef/info",
                params={
                    "conid": underlier_conid,
                    "exchange": "FORECASTX",
                    "sectype": "OPT",
                    "month": month,
                    "strike": strike,
                },
            )
            records = [r for r in (info if isinstance(info, list) else []) if isinstance(r, dict)]
            yes = next((r for r in records if str(r.get("right") or "").upper() == "C" or "YES" in str(r.get("desc2") or "").upper()), None)
            no = next((r for r in records if str(r.get("right") or "").upper() == "P" or "NO" in str(r.get("desc2") or "").upper()), None)
            if not yes or not no:
                continue
            snapshots = _forecast_snapshots([yes.get("conid"), no.get("conid")])
            yes_price = _snapshot_price(snapshots.get(str(yes.get("conid")), {}))
            no_price = _snapshot_price(snapshots.get(str(no.get("conid")), {}))
            if yes_price is None or no_price is None:
                continue
            name = str(market.get("name") or search.get("companyName") or symbol)
            events.append({
                "id": f"{symbol}-{month}-{strike}",
                "symbol": symbol,
                "slug": f"{symbol.lower()}-{month.lower()}-{str(strike).replace('.', 'pt')}",
                "title": name,
                "description": (
                    f"IBKR ForecastTrader / ForecastEx event contract. "
                    f"Category: {market.get('category_path') or 'ForecastEx'}; "
                    f"strike={strike}; YES={yes.get('desc2')}; NO={no.get('desc2')}."
                ),
                "yes_prices": [yes_price, no_price],
                "venue": "IBKR ForecastTrader",
                "exchange": "FORECASTX",
                "sec_type": "OPT",
                "underlier_conid": underlier_conid,
                "yes_conid": yes.get("conid"),
                "no_conid": no.get("conid"),
                "contract_month": month,
                "last_trade_date": expiry,
                "end_date": expiry,
                "strike": strike,
                "source": "ibkr_client_portal",
                "raw_response_hash": hashlib.sha256(
                    json.dumps({"market": market, "yes": yes, "no": no}, sort_keys=True, default=str).encode()
                ).hexdigest(),
            })
    return events


def fetch_prediction_events_from_client_portal(*, thesis_only: bool = True) -> list[dict[str, Any]]:
    """Discover priced ForecastTrader contracts from an authenticated demo account.

    This is read-only: category tree -> secdef search -> strikes/info ->
    market-data snapshot. It never submits orders.
    """
    client_portal_ensure_ready()
    max_markets = int(os.environ.get("IBKR_FORECAST_MAX_MARKETS", "6"))
    events: list[dict[str, Any]] = []
    for market in fetch_forecast_markets(thesis_only=thesis_only)[:max_markets]:
        events.extend(_forecast_contract_events_for_market(market))
    return events


def fetch_prediction_events_for_symbols(symbols: list[str]) -> list[dict[str, Any]]:
    """Resolve priced ForecastTrader contracts for known event underlier symbols.

    This path only uses Client Portal/Web API and does not require a concurrent
    TWS/Gateway socket session. It is useful when the operator must close TWS to
    let Client Portal own the brokerage bridge.
    """
    client_portal_ensure_ready()
    events: list[dict[str, Any]] = []
    for symbol in symbols:
        clean = str(symbol or "").strip().upper()
        if not clean:
            continue
        events.extend(_forecast_contract_events_for_market({
            "symbol": clean,
            "name": clean,
            "category_path": "operator supplied IBKR ForecastTrader symbol",
        }))
    return events


def _connect():
    global _ib_singleton
    if _ib_singleton is not None and _ib_singleton.isConnected():
        return _ib_singleton
    host = _ibkr_host()
    port = _ibkr_port()
    client_id = _ibkr_client_id()
    try:
        # Ensure there is an event loop in this thread (Python 3.12 doesn't
        # implicitly create one).
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("closed")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        from ib_insync import IB
        ib = IB()
        ib.connect(host, port, clientId=client_id, timeout=8)
        # IBKR paper accounts don't have a real-time market-data
        # subscription; reqTickers() returns NaN otherwise. Type 3 =
        # DELAYED_FROZEN — free, returns the last delayed quote. Switching
        # to real-time is a per-account decision the operator makes inside
        # Gateway settings; the adapter doesn't override it.
        ib.reqMarketDataType(3)
        _ib_singleton = ib
        return ib
    except Exception as exc:
        raise RuntimeError(
            f"IBKR Gateway not reachable at {host}:{port} "
            f"(clientId={client_id}). Start IB Gateway/TWS API in paper-trading mode "
            "(Gateway paper=4002, TWS paper=7497). "
            f"Underlying error: {exc!r}"
        )


def _stub_fill(symbol: str, direction: str, qty: int) -> dict:
    fill_ts = time.time()
    return {
        "surface": "ibkr",
        "instrument": symbol,
        "direction": direction,
        "qty": qty,
        "entry_price": 0.0,
        "fill_ts": fill_ts,
        "fill_id": hashlib.sha256(
            f"stub|{symbol}|{direction}|{qty}|{fill_ts}".encode()
        ).hexdigest()[:16],
        "raw_response_hash": "stub",
        "stub": True,
    }


def place_paper_order(symbol: str, direction: str, qty: int = 1,
                      *, dry_run: bool = False) -> dict:
    """Place a MarketOrder for `qty` shares of `symbol`. direction ∈ {"long","short"}.

    Returns a FillReport-shaped dict.
    """
    if dry_run:
        return _stub_fill(symbol, direction, qty)
    try:
        ib = _connect()
    except RuntimeError as exc:
        # Gateway not reachable — return a stub but log the reason. The
        # caller can decide to skip the wrap; for v0 paper demo we proceed.
        print(f"[ibkr] {exc}")
        return _stub_fill(symbol, direction, qty)
    from ib_insync import Stock, MarketOrder
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)
    side = "SELL" if direction == "short" else "BUY"
    order = MarketOrder(side, qty)
    trade = ib.placeOrder(contract, order)
    # Poll up to ~10s for the fill.
    deadline = time.time() + 10
    while time.time() < deadline and not trade.isDone():
        ib.waitOnUpdate(timeout=0.5)
    fills = trade.fills
    entry_price = float(fills[0].execution.price) if fills else 0.0
    fill_ts = time.time()
    raw = str(trade.orderStatus.__dict__ if trade.orderStatus else {})
    return {
        "surface": "ibkr",
        "instrument": symbol,
        "direction": direction,
        "qty": qty,
        "entry_price": entry_price,
        "fill_ts": fill_ts,
        "fill_id": str(trade.order.permId or "")[:16] or hashlib.sha256(raw.encode()).hexdigest()[:16],
        "raw_response_hash": hashlib.sha256(raw.encode()).hexdigest(),
        "stub": False,
    }


def fetch_prediction_events() -> list[dict]:
    """Read IBKR prediction-market events.

    Curated JSON remains supported for demos. When
    `IBKR_FORECAST_DISCOVERY=1`, the adapter also uses the authenticated IBKR
    Client Portal demo account to discover priced ForecastTrader contracts.
    """
    events: list[dict[str, Any]] = []
    raw = os.environ.get("IBKR_PREDICTION_EVENTS_JSON", "").strip()
    if raw:
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("IBKR_PREDICTION_EVENTS_JSON must be a JSON list") from exc
        if not isinstance(decoded, list):
            raise RuntimeError("IBKR_PREDICTION_EVENTS_JSON must be a JSON list")
        events.extend(event for event in decoded if isinstance(event, dict))
    if _env_bool("IBKR_FORECAST_DISCOVERY", False):
        try:
            events.extend(fetch_prediction_events_from_client_portal())
        except RuntimeError as exc:
            print(f"[ibkr] ForecastTrader discovery unavailable: {exc}")
    return events


def simulate_prediction_fill(
    instrument: str,
    direction: str,
    yes_prices: list[float],
    *,
    notional_usdc: float,
    metadata: dict[str, Any] | None = None,
) -> dict:
    """Paper fill for an IBKR ForecastTrader/Event Contract candidate.

    This is a read/live metadata surface in v1. It intentionally does not
    submit a TWS order for event contracts until the operator provides the
    account-specific contract definition and permissions.
    """
    fill_ts = time.time()
    md = metadata or {}
    return {
        "surface": "ibkr_prediction",
        "instrument": instrument,
        "direction": direction,
        "yes_prices_at_open": list(yes_prices),
        "notional_usdc": float(notional_usdc),
        "venue": md.get("venue") or "IBKR ForecastTrader",
        "exchange": md.get("exchange") or "FORECASTX",
        "sec_type": md.get("sec_type") or "OPT",
        "fill_ts": fill_ts,
        "fill_id": hashlib.sha256(
            f"ibkr-prediction|{instrument}|{direction}|{yes_prices}|{fill_ts}".encode()
        ).hexdigest()[:16],
        "raw_response_hash": "paper-ibkr-prediction-v1",
        "stub": True,
    }


def _front_future_contract(symbol: str, exchange: str, currency: str) -> Any | None:
    ib = _connect()
    from ib_insync import Future

    details = ib.reqContractDetails(Future(symbol=symbol, exchange=exchange, currency=currency))
    today = datetime.now(UTC).strftime("%Y%m%d")
    contracts: list[Any] = []
    for detail in details or []:
        contract = getattr(detail, "contract", None)
        expiry = str(getattr(contract, "lastTradeDateOrContractMonth", "") or "")
        if not contract or not expiry:
            continue
        expiry_key = expiry[:8] if len(expiry) >= 8 else f"{expiry[:6]}01"
        if expiry_key >= today:
            contracts.append(contract)
    contracts.sort(key=lambda c: str(getattr(c, "lastTradeDateOrContractMonth", "") or ""))
    return contracts[0] if contracts else None


def _latest_price_for_contract(contract: Any) -> float | None:
    ib = _connect()
    qualified = ib.qualifyContracts(contract)
    if qualified:
        contract = qualified[0]
    tickers = ib.reqTickers(contract)
    ticker = tickers[0] if tickers else None
    price = _ticker_public_price(ticker) if ticker is not None else None
    if price is not None:
        return price
    try:
        wait_seconds = max(0.5, float(os.environ.get("IBKR_PUBLIC_QUOTE_WAIT_SECONDS", "4.0")))
    except ValueError:
        wait_seconds = 4.0
    ticker = ib.reqMktData(contract, "", False, False)
    ib.sleep(wait_seconds)
    price = _ticker_public_price(ticker)
    try:
        ib.cancelMktData(contract)
    except Exception:
        pass
    if price is not None:
        return price
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=os.environ.get("IBKR_PUBLIC_QUOTE_HISTORY_DURATION", "5 D"),
            barSizeSetting="1 day",
            whatToShow=os.environ.get("IBKR_PUBLIC_QUOTE_HISTORY_WHAT", "TRADES"),
            useRTH=True,
            formatDate=1,
        )
    except Exception:
        return None
    for bar in reversed(list(bars or [])):
        close = _parse_positive_price(getattr(bar, "close", None))
        if close is not None:
            return close
    return None


def fetch_front_future_quote(symbol: str, *, exchange: str, currency: str = "USD") -> dict[str, Any] | None:
    """Read a delayed/live front-month futures mark from TWS/Gateway.

    This mirrors the Brent strategy's terminal workflow: enumerate futures
    contracts through IBKR, choose the nearest non-expired expiry, and read a
    delayed/live market-data mark. It is a read-only proxy quote, not a
    ForecastTrader EC contract price.
    """
    root = str(symbol or "").strip().upper()
    if not root:
        return None
    contract = _front_future_contract(root, exchange, currency)
    if contract is None:
        return None
    price = _latest_price_for_contract(contract)
    if price is None:
        return None
    return {
        "symbol": root,
        "price": float(price),
        "currency": str(getattr(contract, "currency", None) or currency),
        "exchange": str(getattr(contract, "exchange", None) or exchange),
        "local_symbol": str(getattr(contract, "localSymbol", None) or ""),
        "expiry": str(getattr(contract, "lastTradeDateOrContractMonth", None) or ""),
        "conid": str(getattr(contract, "conId", None) or ""),
        "source": "ibkr_tws_front_future",
    }


def _energy_history_csv_paths() -> list[Path]:
    raw = os.environ.get("IBKR_ENERGY_HISTORY_CSV", "").strip()
    if raw:
        return [Path(raw).expanduser()]
    try:
        vsprojects = Path(__file__).resolve().parents[3]
    except IndexError:
        return []
    return [vsprojects / "brent_strategy" / "improm_signal" / "data" / "ibkr_energy_history.csv"]


def fetch_energy_history_csv_quote(symbol: str) -> dict[str, Any] | None:
    clean = str(symbol or "").strip().upper()
    future = _PUBLIC_FUTURE_SYMBOLS.get(clean)
    if not future:
        return None
    root, exchange, currency = future
    if root not in {"CL", "BZ", "NG", "RB", "HO"}:
        return None
    best: dict[str, Any] | None = None
    for path in _energy_history_csv_paths():
        if not path.exists():
            continue
        try:
            with path.open(newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    if str(row.get("symbol") or "").strip().upper() != root:
                        continue
                    price = _parse_positive_price(row.get("settle"))
                    if price is None:
                        continue
                    candidate = {
                        "date": str(row.get("date") or ""),
                        "expiry": str(row.get("expiry") or ""),
                        "price": price,
                    }
                    if (
                        best is None
                        or candidate["date"] > best["date"]
                        or (candidate["date"] == best["date"] and candidate["expiry"] < best["expiry"])
                    ):
                        best = candidate
        except OSError:
            continue
    if best is None:
        return None
    return {
        "symbol": root,
        "requested_symbol": clean,
        "price": float(best["price"]),
        "currency": currency,
        "exchange": exchange,
        "expiry": best["expiry"],
        "regular_market_time": best["date"],
        "source": "ibkr_energy_history_csv",
        "stale": True,
    }


def fetch_public_quote(symbol: str) -> dict[str, Any] | None:
    """Read a public proxy quote from TWS/Gateway.

    Stocks use SMART stock contracts. Energy/rate futures accept both IBKR root
    symbols (`BZ`, `NG`) and Yahoo-style futures tickers (`BZ=F`, `NG=F`).
    """
    clean = str(symbol or "").strip().upper()
    if not clean:
        return None
    future = _PUBLIC_FUTURE_SYMBOLS.get(clean)
    if future:
        root, exchange, currency = future
        if not _env_bool("IBKR_PUBLIC_FUTURES_LIVE_FIRST", False):
            quote = fetch_energy_history_csv_quote(clean)
            if quote:
                return quote
        try:
            quote = fetch_front_future_quote(root, exchange=exchange, currency=currency)
        except RuntimeError:
            quote = None
        if quote:
            quote["requested_symbol"] = clean
            return quote
        return fetch_energy_history_csv_quote(clean)
    if "-" in clean:
        return None
    price = fetch_last_price(clean)
    if price is None:
        return None
    return {
        "symbol": clean,
        "price": float(price),
        "currency": "USD",
        "exchange": "SMART",
        "source": "ibkr_tws_stock",
    }


def fetch_last_price(symbol: str) -> float | None:
    """Used by the Phase 0.6 smoke test.

    Falls through several ticker fields in preference order because paper
    accounts on delayed data populate different fields than real-time
    accounts: marketPrice (NaN on delayed), last/close/midpoint, then
    explicit delayed fields, finally bid/ask midpoint.
    """
    try:
        ib = _connect()
    except RuntimeError as exc:
        print(f"[ibkr] {exc}")
        return None
    from ib_insync import Stock
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)
    [tk] = ib.reqTickers(contract)
    return _ticker_public_price(tk)
