import csv

from agent import energy_oracle_backtest as eob


def _write_master(path, rows):
    fields = [
        "fill_ts",
        "slug",
        "event_slug",
        "condition_id",
        "entry_price",
        "resolution_outcome",
        "realized_pnl",
        "category",
        "cadence",
        "premium",
    ]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def test_energy_oracle_backtest_applies_non_negative_premium_gate(tmp_path):
    tsv = tmp_path / "fills.tsv"
    _write_master(tsv, [
        {
            "fill_ts": "2026-04-01 00:00:00",
            "slug": "will-openai-release-gpt-5",
            "event_slug": "gpt-5-released-by",
            "condition_id": "0x1",
            "entry_price": "0.93",
            "resolution_outcome": "WIN",
            "realized_pnl": "3.50",
            "category": "other",
            "cadence": "monthly",
            "premium": "0.03",
        },
        {
            "fill_ts": "2026-04-02 00:00:00",
            "slug": "will-80-or-more-ships-transit-the-strait-of-hormuz",
            "event_slug": "strait-of-hormuz-week",
            "condition_id": "0x2",
            "entry_price": "0.93",
            "resolution_outcome": "LOSS",
            "realized_pnl": "-10.00",
            "category": "other",
            "cadence": "weekly",
            "premium": "-0.07",
        },
        {
            "fill_ts": "2026-04-03 00:00:00",
            "slug": "bitcoin-price-on-may-1",
            "event_slug": "bitcoin-price-on-may-1",
            "condition_id": "0x3",
            "entry_price": "0.90",
            "resolution_outcome": "WIN",
            "realized_pnl": "1.00",
            "category": "finance_crypto_corridor",
            "cadence": "weekly",
            "premium": "0.00",
        },
    ])

    summary, fills = eob.run(tsv)

    assert len(fills) == 2
    assert summary["baseline"]["n"] == 2
    assert summary["baseline"]["pnl"] == -6.5
    assert summary["oracle_kept"]["n"] == 1
    assert summary["oracle_kept"]["wr"] == 1.0
    assert summary["oracle_kept"]["pnl"] == 3.5
    assert summary["oracle_vetoed"]["n"] == 1
    assert summary["oracle_vetoed"]["pnl"] == -10.0
    assert summary["improvement"]["losses_vetoed"] == 1
    assert summary["improvement"]["wins_vetoed"] == 0
    assert {f.reason_code for f in fills} == {None, "premium_gate_fail"}


def test_energy_oracle_report_contains_template_breakdown(tmp_path):
    tsv = tmp_path / "fills.tsv"
    _write_master(tsv, [{
        "fill_ts": "2026-04-01 00:00:00",
        "slug": "will-nvidia-close-above-100",
        "event_slug": "nvda-week-april-3-2026",
        "condition_id": "0x1",
        "entry_price": "0.95",
        "resolution_outcome": "WIN",
        "realized_pnl": "2.00",
        "category": "finance_equity",
        "cadence": "weekly",
        "premium": "0.05",
    }])

    summary, _fills = eob.run(tsv)
    report = eob.render_report(summary)

    assert "Energy Oracle Backtest Report" in report
    assert "energy_classifier_plus_s4_non_negative_premium_gate" in report
    assert "`energy_ai_infra`" in report
