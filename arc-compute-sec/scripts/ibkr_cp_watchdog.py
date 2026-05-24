"""Keep the local IBKR Client Portal session warm.

This is read-only. It calls `/tickle` and the soft `/iserver/reauthenticate`
path exposed by the local Client Portal Gateway. It cannot recover an expired
browser/2FA login; in that case the operator must reopen https://localhost:5055.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters import ibkr


def _status_bool(status: dict[str, Any], key: str) -> Any:
    if key in status:
        return status.get(key)
    auth_status = status.get("authStatus")
    if isinstance(auth_status, dict) and key in auth_status:
        return auth_status.get(key)
    iserver = status.get("iserver")
    if isinstance(iserver, dict) and key in iserver:
        return iserver.get(key)
    return "unknown"


def check_once() -> int:
    try:
        status = ibkr.client_portal_ensure_ready()
    except RuntimeError as exc:
        print(f"IBKR Client Portal restore failed: {exc}", file=sys.stderr)
        print("Open https://localhost:5055, complete login/2FA, then rerun this command.", file=sys.stderr)
        return 1
    authenticated = _status_bool(status, "authenticated")
    connected = _status_bool(status, "connected")
    competing = _status_bool(status, "competing")
    if authenticated is True and connected is True:
        try:
            ibkr.client_portal_tickle()
        except RuntimeError as exc:
            print(f"IBKR Client Portal tickle warning: {exc}", file=sys.stderr)
        print(
            "IBKR Client Portal ready: "
            f"authenticated={authenticated} connected={connected} competing={competing}"
        )
        return 0
    print(
        "IBKR Client Portal not ready after soft restore: "
        f"authenticated={authenticated} connected={connected} competing={competing}",
        file=sys.stderr,
    )
    print("If this persists, reopen https://localhost:5055 and complete login/2FA.", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only IBKR Client Portal keepalive/soft-reauth watchdog")
    parser.add_argument("--once", action="store_true", help="Run one check and exit")
    parser.add_argument("--interval", type=float, default=60.0, help="Seconds between checks in loop mode")
    args = parser.parse_args(argv)
    if args.once:
        return check_once()
    while True:
        check_once()
        time.sleep(max(5.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
