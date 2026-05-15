"""Phase 0.6 IBKR Gateway smoke.

This checks the local paper-trading Gateway only. It does not place orders,
call Arc, or read repo secrets.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapters.ibkr import fetch_last_price


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test local IBKR paper Gateway quotes")
    parser.add_argument("symbols", nargs="*", default=["GOOGL"],
                        help="Stock symbols to quote; defaults to GOOGL")
    args = parser.parse_args(argv)

    failures: list[str] = []
    for symbol in args.symbols:
        price = fetch_last_price(symbol)
        if price is None:
            failures.append(symbol)
            print(f"{symbol}: no price")
            continue
        print(f"{symbol}: {price:.4f}")

    if failures:
        print(
            "IBKR smoke failed for: "
            + ", ".join(failures)
            + ". Confirm Gateway is in paper mode with API socket enabled on 127.0.0.1:4002.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
