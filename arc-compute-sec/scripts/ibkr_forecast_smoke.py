"""Read-only IBKR ForecastTrader/Event Contract discovery smoke.

This does not place orders. TWS discovery finds account-visible event
underliers. Priced YES/NO contract discovery additionally needs the IBKR
Client Portal/Web API gateway because IBKR resolves event contract conids via
Web API endpoints.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters import ibkr
from services.state import log_dir


def _cp_bool(status: dict[str, Any], key: str) -> Any:
    if key in status:
        return status.get(key)
    auth_status = status.get("authStatus")
    if isinstance(auth_status, dict) and key in auth_status:
        return auth_status.get(key)
    iserver = status.get("iserver")
    if isinstance(iserver, dict) and key in iserver:
        return iserver.get(key)
    return "unknown"


def _print_client_portal_help() -> None:
    print(
        "Client Portal Gateway is required for priced ForecastTrader YES/NO legs.\n"
        "Next checks:\n"
        "  1. Start IBKR Client Portal Gateway, not just TWS/IB Gateway.\n"
        "  2. If macOS ControlCenter owns port 5000, set listenPort: 5055 in root/conf.yaml.\n"
        "  3. Open https://localhost:5055 in a browser and log in with the paper username.\n"
        "  4. Confirm the page says Client login succeeds.\n"
        "  5. Re-run: curl -k https://localhost:5055/v1/api/iserver/auth/status\n"
        "  6. Then re-run: npm run ibkr:forecast-priced-smoke",
        file=sys.stderr,
    )


def _check_client_portal_ready() -> bool:
    try:
        status = ibkr.client_portal_ensure_ready()
    except RuntimeError as exc:
        print(f"IBKR Client Portal preflight failed: {exc}", file=sys.stderr)
        _print_client_portal_help()
        return False
    authenticated = _cp_bool(status, "authenticated")
    connected = _cp_bool(status, "connected")
    competing = _cp_bool(status, "competing")
    print(
        "IBKR Client Portal status: "
        f"authenticated={authenticated} connected={connected} competing={competing}"
    )
    if authenticated is not True:
        try:
            user_status = ibkr.client_portal_user_status()
        except RuntimeError:
            user_status = {}
        if isinstance(user_status, dict) and user_status.get("features"):
            print(
                "Client Portal SSO is live, but the IBKR brokerage bridge is not authenticated. "
                "This usually shows up as `/iserver` returning `no bridge` or ssodh token errors. "
                "Close duplicate IBKR sessions or use a separate IBKR username for Client Portal API, "
                "then login again and retry.",
                file=sys.stderr,
            )
            return False
        _print_client_portal_help()
        return False
    return True


def _fmt_market(market: dict[str, Any]) -> str:
    symbol = market.get("symbol") or "?"
    name = market.get("name") or "Unnamed event underlier"
    theme = market.get("theme") or "unknown"
    conid = market.get("underlier_conid") or "?"
    source = market.get("source") or "ibkr"
    return f"{symbol:<8} {theme:<16} conid={conid} source={source} :: {name}"


def _fmt_event(event: dict[str, Any]) -> str:
    symbol = event.get("symbol") or event.get("slug") or event.get("id") or "?"
    title = event.get("title") or "Untitled event"
    expiry = event.get("end_date") or event.get("last_trade_date") or "?"
    prices = event.get("yes_prices") or []
    price_text = "/".join(f"{float(px):.3f}" for px in prices) if prices else "unpriced"
    status = event.get("pricing_status") or ("priced" if prices else "unpriced")
    sec_type = event.get("sec_type") or "?"
    conid = event.get("yes_conid") or event.get("underlier_conid") or "?"
    return f"{symbol:<8} {sec_type:<4} conid={conid} status={status} expiry={expiry} yes/no={price_text} :: {title}"


def _public_inventory_event(event: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "id",
        "symbol",
        "slug",
        "title",
        "description",
        "yes_prices",
        "venue",
        "exchange",
        "sec_type",
        "underlier_conid",
        "yes_conid",
        "no_conid",
        "contract_month",
        "last_trade_date",
        "end_date",
        "strike",
        "source",
        "pricing_status",
        "raw_response_hash",
    }
    return {key: event.get(key) for key in allowed if key in event}


def _write_inventory(events: list[dict[str, Any]]) -> None:
    path = log_dir() / "ibkr_forecast_inventory.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": time.time(),
        "source": "scripts/ibkr_forecast_smoke.py",
        "events": [_public_inventory_event(event) for event in events],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"IBKR direct-event inventory written: {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test read-only IBKR event discovery")
    parser.add_argument(
        "--source",
        choices=["tws", "client_portal", "both"],
        default="tws",
        help="Where to discover event underliers from; default is TWS because it is already running locally.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Show all event underliers found, not only compute/energy/macro thesis matches.",
    )
    parser.add_argument(
        "--priced",
        action="store_true",
        help="Also try to resolve priced YES/NO contract conids through IBKR Client Portal/Web API.",
    )
    parser.add_argument(
        "--symbols",
        default="",
        help="Comma-separated known ForecastTrader underlier symbols to price via Client Portal without TWS discovery.",
    )
    parser.add_argument(
        "--no-write-inventory",
        action="store_true",
        help="Do not write the sanitized logs/ibkr_forecast_inventory.json snapshot.",
    )
    parser.add_argument("--limit", type=int, default=20, help="Maximum rows to print per section.")
    args = parser.parse_args(argv)

    source = "both" if args.source == "both" else args.source
    os.environ["IBKR_FORECAST_MARKET_SOURCE"] = source
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    markets: list[dict[str, Any]] = []
    if symbols:
        print(f"IBKR ForecastTrader underliers: using {len(symbols)} operator-supplied symbols")
        for symbol in symbols[: args.limit]:
            print(f"  {symbol:<8} operator_symbol  conid=? source=manual :: {symbol}")
    else:
        try:
            markets = ibkr.fetch_forecast_markets(thesis_only=not args.all)
        except RuntimeError as exc:
            print(f"IBKR ForecastTrader underlier discovery failed: {exc}", file=sys.stderr)
            return 1

        print(f"IBKR ForecastTrader underliers: {len(markets)} found via {source}")
        for market in markets[: args.limit]:
            print("  " + _fmt_market(market))

    if not args.priced:
        print(
            "Priced YES/NO contracts were not requested. Run with --priced after "
            "IBKR Client Portal Gateway is authenticated on IBKR_CP_BASE_URL."
        )
        return 0 if markets or symbols else 1

    if not _check_client_portal_ready():
        return 1

    try:
        if symbols:
            events = ibkr.fetch_prediction_events_for_symbols(symbols)
        else:
            events = ibkr.fetch_prediction_events_from_client_portal(thesis_only=not args.all)
    except RuntimeError as exc:
        print(f"IBKR priced contract discovery failed: {exc}", file=sys.stderr)
        return 1

    priced_count = sum(1 for event in events if event.get("yes_prices"))
    print(f"IBKR ForecastTrader contracts: {len(events)} found ({priced_count} priced)")
    for event in events[: args.limit]:
        print("  " + _fmt_event(event))
    if not args.no_write_inventory:
        _write_inventory(events)
    return 0 if events else 1


if __name__ == "__main__":
    raise SystemExit(main())
