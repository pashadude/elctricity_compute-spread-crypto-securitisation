from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.yahoo_finance import fetch_chart_history
from agent import spread_family_backtest, spread_proxy_history

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"


def _latest_tsv_row(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    import csv

    with path.open("r", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    return rows[-1] if rows else {}


def _num(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _anchors(logs: Path) -> tuple[float, float]:
    latest = _latest_tsv_row(logs / "spread_history.tsv")
    return (
        _num(latest.get("electricity_per_mwh"), 62.6),
        _num(latest.get("compute_per_gpu_hr"), 0.86635),
    )


def _fetch_histories(symbols: list[str], *, range_name: str, interval: str, timeout: float) -> dict[str, dict[str, Any]]:
    histories: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        try:
            history = fetch_chart_history(symbol, range=range_name, interval=interval, timeout=timeout)
        except Exception as exc:
            history = {"symbol": symbol, "points": [], "source": "yahoo_finance_chart", "error": str(exc)}
        if isinstance(history, dict):
            histories[symbol] = history
    return histories


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build public proxy spread history and replay spread families")
    parser.add_argument("--logs", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--range", dest="range_name", default="6mo")
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--timeout", type=float, default=4.0)
    parser.add_argument("--history-out", type=Path)
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--metrics-out", type=Path)
    args = parser.parse_args(argv)

    logs = args.logs
    elec_anchor, compute_anchor = _anchors(logs)
    symbols = sorted({
        *spread_proxy_history.DEFAULT_ELECTRICITY_PROXY_WEIGHTS,
        *spread_proxy_history.DEFAULT_COMPUTE_PROXY_WEIGHTS,
    })
    histories = _fetch_histories(symbols, range_name=args.range_name, interval=args.interval, timeout=args.timeout)
    history_points = {symbol: len((history.get("points") or [])) for symbol, history in histories.items()}
    history_errors = {
        symbol: history.get("error")
        for symbol, history in histories.items()
        if history.get("error")
    }
    built = spread_proxy_history.build_spread_rows(
        histories,
        electricity_anchor_per_mwh=elec_anchor,
        compute_anchor_per_gpu_hr=compute_anchor,
    )
    history_out = args.history_out or (logs / "spread_proxy_history.tsv")
    spread_proxy_history.write_rows(history_out, built["rows"])
    replay = spread_family_backtest.summarize(
        built["rows"],
        strategy_modes=(
            spread_family_backtest.STRATEGY_MEAN_REVERSION,
            spread_family_backtest.STRATEGY_MOMENTUM,
        ),
    )
    metrics = {
        "proxy_history": {
            key: value for key, value in built.items() if key != "rows"
        },
        "rows": len(built["rows"]),
        "history_points": history_points,
        "history_errors": history_errors,
        "spread_family_replay": replay,
    }
    metrics_out = args.metrics_out or (logs / "spread_proxy_backtest.json")
    metrics_out.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    if args.report_out:
        lines = [
            "# Public Proxy Spread Replay",
            "",
            f"Rows: {len(built['rows'])}",
            f"Electricity symbols: {', '.join(built['electricity_index']['symbols_available'])}",
            f"Compute symbols: {', '.join(built['compute_index']['symbols_available'])}",
            f"Coverage: {(replay.get('index_coverage') or {}).get('summary', 'index coverage loading')}",
            "",
            "## Families",
            "",
            "| Family | Status | Trades | WR | PnL/unit | OOS |",
            "|---|---:|---:|---:|---:|---|",
        ]
        for family in replay.get("families", []):
            lines.append(
                f"| {family['label']} | {family['status']} | {family['tested_trades']} | "
                f"{family['win_rate']:.2f}% | {family['total_pnl_per_unit']:.6f} | "
                f"{family.get('oos_status', 'NO_REPLAY')} {float(family.get('oos_test_pnl_per_unit') or 0):.6f} |"
            )
        args.report_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "rows": len(built["rows"]),
        "history_out": str(history_out),
        "metrics_out": str(metrics_out),
        "entry_gate_pass": replay.get("entry_gate_pass"),
        "primary_status": (replay.get("primary_family") or {}).get("status"),
        "primary_label": (replay.get("primary_family") or {}).get("label"),
        "primary_oos_status": (replay.get("primary_family") or {}).get("oos_status"),
        "primary_oos_test_pnl_per_unit": (replay.get("primary_family") or {}).get("oos_test_pnl_per_unit"),
        "index_coverage": replay.get("index_coverage"),
        "history_points": history_points,
        "history_errors": history_errors,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
