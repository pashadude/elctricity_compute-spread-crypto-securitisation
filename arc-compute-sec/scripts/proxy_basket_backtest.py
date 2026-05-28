"""Fetch Yahoo close history and replay public proxy basket templates."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.yahoo_finance import fetch_chart_history
from agent import proxy_basket_backtest


def run(*, range_name: str, interval: str, timeout: float) -> dict:
    histories = {}
    errors = {}
    for symbol in proxy_basket_backtest.required_symbols():
        try:
            history = fetch_chart_history(symbol, range=range_name, interval=interval, timeout=timeout)
        except Exception as exc:
            message = str(exc).replace("\n", " ")[:180]
            errors[symbol] = f"{exc.__class__.__name__}: {message}" if message else exc.__class__.__name__
            continue
        if history:
            histories[symbol] = history
        else:
            errors[symbol] = "no_history"
    summary = proxy_basket_backtest.summarize(histories)
    summary["fetch_enabled"] = True
    summary["history_range"] = range_name
    summary["history_interval"] = interval
    summary["history_symbols_loaded"] = sorted(histories)
    summary["history_errors"] = errors
    return summary


def render(summary: dict) -> str:
    primary = summary.get("primary_basket") or {}
    lines = [
        "# Proxy Basket Backtest",
        "",
        f"Policy: {summary.get('policy')}",
        f"History: {summary.get('history_range')} / {summary.get('history_interval')}",
        f"Entry gate: {summary.get('entry_gate_pass')}",
        "",
    ]
    if primary:
        lines.extend([
        f"Primary: {primary.get('label')} ({primary.get('status')})",
        f"Recommendation: {primary.get('recommendation')}",
        f"Signal: {primary.get('latest_signal', 'MONITOR')} - {primary.get('signal_reason', '')}",
        f"Return: {float(primary.get('total_return_pct') or 0):.2f}%",
        f"WR: {float(primary.get('win_rate') or 0):.2f}%",
            f"Max DD: {float(primary.get('max_drawdown_pct') or 0):.2f}%",
            f"Reason: {primary.get('status_reason')}",
        "",
    ])
    trailing = primary.get("trailing_returns") if isinstance(primary.get("trailing_returns"), dict) else {}
    if trailing:
        lines.extend([
            "| Horizon | Return | Observations |",
            "|---|---:|---:|",
        ])
        for label in ("5d", "1m", "3m", "6m"):
            row = trailing.get(label) or {}
            if not row:
                continue
            lines.append(
                f"| {label} | {float(row.get('return_pct') or 0):.2f}% | "
                f"{int(row.get('observations') or 0)} |"
            )
        lines.append("")
    lines.extend([
        "| Basket | Signal | Status | Recommendation | Return | 5d | 1m | WR | Max DD | Days |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|",
    ])
    for basket in summary.get("baskets") or []:
        btrail = basket.get("trailing_returns") if isinstance(basket.get("trailing_returns"), dict) else {}
        ret_5d = (btrail.get("5d") or {}).get("return_pct")
        ret_1m = (btrail.get("1m") or {}).get("return_pct")
        lines.append(
            f"| {basket.get('label')} | {basket.get('latest_signal', 'MONITOR')} | "
            f"{basket.get('status')} | {basket.get('recommendation')} | "
            f"{float(basket.get('total_return_pct') or 0):.2f}% | "
            f"{float(ret_5d or 0):.2f}% | "
            f"{float(ret_1m or 0):.2f}% | "
            f"{float(basket.get('win_rate') or 0):.2f}% | "
            f"{float(basket.get('max_drawdown_pct') or 0):.2f}% | "
            f"{int(basket.get('observations') or 0)} |"
        )
    if summary.get("history_errors"):
        lines.extend(["", "Missing/error symbols: " + ", ".join(sorted(summary["history_errors"]))])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest public proxy basket templates with Yahoo close history")
    parser.add_argument("--range", dest="range_name", default="6mo")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--timeout", type=float, default=4.0)
    parser.add_argument("--metrics-out", type=Path, default=Path("logs/proxy_basket_backtest.json"))
    parser.add_argument("--report-out", type=Path)
    args = parser.parse_args(argv)

    summary = run(range_name=args.range_name, interval=args.interval, timeout=args.timeout)
    report = render(summary)
    print(report, end="")
    args.metrics_out.parent.mkdir(parents=True, exist_ok=True)
    args.metrics_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
