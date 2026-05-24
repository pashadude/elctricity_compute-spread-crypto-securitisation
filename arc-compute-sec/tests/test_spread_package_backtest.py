from agent import spread_package_backtest as spb


def test_spread_package_backtest_uses_direct_event_evidence():
    summary = spb.summarize()

    assert summary["policy"] == "canonical_spread_package_v1"
    assert summary["direct_event_backtest"]["total_fills"] == 1301
    assert summary["direct_event_backtest"]["energy_classified"] == 122
    assert summary["acceptance"]["ai_infra_wr_pass"] is True
    assert summary["acceptance"]["ai_infra_pnl_pass"] is True
    assert summary["proxy_leg_policy"]["crypto_counted_as_direct_proof"] is False


def test_spread_package_backtest_report_explains_proxy_discipline():
    report = spb.render_report(spb.summarize())

    assert "This report validates the package story, not raw BTC exposure." in report
    assert "Crypto counted as direct proof: False" in report
    assert "miner-margin proxy legs" in report
