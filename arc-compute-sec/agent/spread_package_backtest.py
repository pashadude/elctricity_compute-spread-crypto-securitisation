"""Backtest report for the spread-package story.

This report is intentionally conservative:
- direct prediction-event legs can use the historical energy classifier /
  premium-gate evidence;
- BTC/ETH and equities are proxy legs and are not counted as direct proof of
  securitizing the electricity-compute spread.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent import energy_oracle_backtest
from agent import spread_family_backtest
from agent import proxy_basket_backtest

DEFAULT_BACKWARD_CHECK = (
    Path(__file__).resolve().parent.parent
    / "templates"
    / "energy"
    / "backward_check.txt"
)


@dataclass(frozen=True, slots=True)
class HistoricalSummary:
    total_fills: int
    energy_classified: int
    ai_infra_n: int
    ai_infra_wr: float
    ai_infra_pnl: float
    geopolitics_n: int
    geopolitics_wr: float
    geopolitics_pnl: float


def _match_int(pattern: str, text: str) -> int:
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise ValueError(f"missing integer pattern: {pattern}")
    return int(match.group(1).replace(",", ""))


def _match_template_row(template: str, text: str) -> tuple[int, float, float]:
    pattern = rf"^{re.escape(template)}\s+(\d+)\s+([0-9.]+)\s+(-?[0-9.]+)"
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise ValueError(f"missing template row: {template}")
    return int(match.group(1)), float(match.group(2)), float(match.group(3))


def load_backward_summary(path: Path = DEFAULT_BACKWARD_CHECK) -> HistoricalSummary:
    text = path.read_text(encoding="utf-8")
    ai_n, ai_wr, ai_pnl = _match_template_row("energy_ai_infra", text)
    geo_n, geo_wr, geo_pnl = _match_template_row("energy_geopolitics", text)
    return HistoricalSummary(
        total_fills=_match_int(r"^Total fills:\s+([0-9,]+)", text),
        energy_classified=_match_int(r"^Energy-classified:\s+([0-9,]+)", text),
        ai_infra_n=ai_n,
        ai_infra_wr=ai_wr,
        ai_infra_pnl=ai_pnl,
        geopolitics_n=geo_n,
        geopolitics_wr=geo_wr,
        geopolitics_pnl=geo_pnl,
    )


def _read_spread_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def summarize(
    *,
    backward_check: Path = DEFAULT_BACKWARD_CHECK,
    master_fills_tsv: Path | None = None,
    spread_history_tsv: Path | None = None,
    proxy_basket_json: Path | None = None,
) -> dict[str, Any]:
    historical = load_backward_summary(backward_check)
    out: dict[str, Any] = {
        "policy": "canonical_spread_package_v1",
        "how_it_works": [
            "Compute S_t from electricity and GPU spot prices.",
            "Build a canonical spread package with the signal, thesis, intended direct pair, and available legs.",
            "Use direct prediction-event pairs as spread claims; label BTC/ETH and equities as proxies only.",
            "Wrap the judged package on Arc only after judge.classify() returns EXECUTE.",
        ],
        "direct_event_backtest": asdict(historical),
        "acceptance": {
            "ai_infra_wr_pass": historical.ai_infra_wr >= 0.85,
            "ai_infra_pnl_pass": historical.ai_infra_pnl > 0,
            "energy_classifier_has_coverage": historical.energy_classified >= 100,
        },
        "proxy_leg_policy": {
            "crypto_counted_as_direct_proof": False,
            "reason": (
                "BTC/USD and ETH/USD are miner-margin proxy legs. They can be "
                "used for live-read liquidity, but their realized PnL must be "
                "reconciled separately and must not be sold as direct spread "
                "securitization evidence."
            ),
        },
    }
    if master_fills_tsv is not None and master_fills_tsv.exists():
        gate_summary, _fills = energy_oracle_backtest.run(master_fills_tsv)
        out["premium_gate_backtest"] = gate_summary
    else:
        out["premium_gate_backtest"] = {
            "status": "not_run",
            "reason": "master_fills_v4.tsv not present in this workspace",
        }
    if spread_history_tsv is not None and spread_history_tsv.exists():
        rows = _read_spread_history(spread_history_tsv)
    else:
        default_spread_history = Path(__file__).resolve().parent.parent / "logs" / "spread_history.tsv"
        rows = _read_spread_history(default_spread_history)
    out["spread_family_replay"] = spread_family_backtest.summarize(rows)
    proxy_path = proxy_basket_json or (Path(__file__).resolve().parent.parent / "logs" / "proxy_basket_backtest.json")
    if proxy_path.exists():
        try:
            proxy_summary = json.loads(proxy_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            proxy_summary = proxy_basket_backtest.summarize({})
            proxy_summary["status_reason"] = "proxy_basket_backtest.json exists but is not valid JSON"
    else:
        proxy_summary = proxy_basket_backtest.summarize({})
        proxy_summary["status_reason"] = "Run npm run proxy:backtest to attach Yahoo close-history proxy replay."
    out["proxy_basket_replay"] = proxy_summary
    return out


def render_report(summary: dict[str, Any]) -> str:
    direct = summary["direct_event_backtest"]
    acceptance = summary["acceptance"]
    proxy = summary["proxy_leg_policy"]
    lines = [
        "# Spread Package Backtest Report",
        "",
        "This report validates the package story, not raw BTC exposure.",
        "",
        "## Four-Step Package",
        "",
    ]
    lines.extend(f"{i}. {step}" for i, step in enumerate(summary["how_it_works"], 1))
    lines.extend([
        "",
        "## Direct Event Evidence",
        "",
        "| Segment | n | WR | PnL |",
        "|---|---:|---:|---:|",
        f"| Historical fills scanned | {direct['total_fills']} |  |  |",
        f"| Energy-classified fills | {direct['energy_classified']} |  |  |",
        f"| AI-infra direct leg | {direct['ai_infra_n']} | {direct['ai_infra_wr']:.3f} | {direct['ai_infra_pnl']:.3f} |",
        f"| Energy geopolitics direct leg | {direct['geopolitics_n']} | {direct['geopolitics_wr']:.3f} | {direct['geopolitics_pnl']:.3f} |",
        "",
        "## Acceptance",
        "",
        f"- AI-infra WR >= 0.85: {acceptance['ai_infra_wr_pass']}",
        f"- AI-infra PnL > 0: {acceptance['ai_infra_pnl_pass']}",
        f"- Energy-classified coverage >= 100: {acceptance['energy_classifier_has_coverage']}",
        "",
        "## Proxy Discipline",
        "",
        f"Crypto counted as direct proof: {proxy['crypto_counted_as_direct_proof']}",
        "",
        proxy["reason"],
    ])
    premium = summary.get("premium_gate_backtest") or {}
    if premium.get("status") == "not_run":
        lines.extend([
            "",
            "## Premium Gate Replay",
            "",
            f"Status: {premium['status']} ({premium['reason']}).",
        ])
    elif premium:
        lines.extend([
            "",
            "## Premium Gate Replay",
            "",
            f"Gate-kept fills: {premium['gate_kept']['n']}",
            f"Gate-kept WR: {premium['gate_kept']['wr']:.3f}",
            f"Gate-kept PnL: {premium['gate_kept']['pnl']:.3f}",
        ])
    replay = summary.get("spread_family_replay") or {}
    primary = replay.get("primary_family") or {}
    if primary:
        lines.extend([
            "",
            "## Spread-Family Replay",
            "",
            f"Primary family: {primary.get('label')} ({primary.get('status')})",
            f"Latest z: {float(primary.get('latest_z') or 0):.3f}",
            f"Walk-forward trades: {int(primary.get('tested_trades') or 0)}",
            f"WR: {float(primary.get('win_rate') or 0):.2f}%",
            f"Total PnL/unit: {float(primary.get('total_pnl_per_unit') or 0):.6f}",
            "",
            primary.get("status_reason", ""),
        ])
    proxy = summary.get("proxy_basket_replay") or {}
    proxy_primary = proxy.get("primary_basket") or {}
    if proxy_primary:
        lines.extend([
            "",
            "## Proxy Basket Replay",
            "",
            f"Primary basket: {proxy_primary.get('label')} ({proxy_primary.get('status')})",
            f"Recommendation: {proxy_primary.get('recommendation')}",
            f"Return: {float(proxy_primary.get('total_return_pct') or 0):.2f}%",
            f"WR: {float(proxy_primary.get('win_rate') or 0):.2f}%",
            f"Max DD: {float(proxy_primary.get('max_drawdown_pct') or 0):.2f}%",
            "",
            proxy_primary.get("status_reason", proxy.get("status_reason", "")),
        ])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest canonical spread-package evidence")
    parser.add_argument("--backward-check", type=Path, default=DEFAULT_BACKWARD_CHECK)
    parser.add_argument("--master-fills-tsv", type=Path)
    parser.add_argument("--spread-history-tsv", type=Path)
    parser.add_argument("--proxy-basket-json", type=Path)
    parser.add_argument("--report-out", type=Path)
    parser.add_argument("--metrics-out", type=Path)
    args = parser.parse_args(argv)

    summary = summarize(
        backward_check=args.backward_check,
        master_fills_tsv=args.master_fills_tsv,
        spread_history_tsv=args.spread_history_tsv,
        proxy_basket_json=args.proxy_basket_json,
    )
    report = render_report(summary)
    print(report, end="")
    if args.report_out:
        args.report_out.write_text(report, encoding="utf-8")
    if args.metrics_out:
        args.metrics_out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
