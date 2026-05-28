import math

from agent import spread_family_backtest as sfb


def _row(value, ts=0):
    compute = value + 0.025
    return {
        "ts": ts,
        "region": "ERCOT|us-east-1",
        "electricity_per_mwh": 71.428571,
        "compute_per_gpu_hr": compute,
        "S_t": value,
        "k": 0.5,
        "kwh_per_gpu_hr": 0.7,
    }


def test_compute_net_power_family_matches_current_spread_formula():
    family = next(f for f in sfb.SPREAD_FAMILIES if f.family_id == "compute_net_power_margin")
    row = {
        "electricity_per_mwh": 80.0,
        "compute_per_gpu_hr": 1.5,
        "k": 0.5,
        "kwh_per_gpu_hr": 0.7,
    }

    value = family.value_fn(sfb._row_inputs(row))

    assert math.isclose(value, 1.472, abs_tol=1e-9)


def test_flat_marks_do_not_promote_misleading_zero_pnl_backtest():
    rows = [_row(0.84, ts=i) for i in range(80)]

    summary = sfb.summarize(rows, window=10, horizon_steps=3, min_obs=20, min_distinct=4, min_trades=2)
    primary = next(f for f in summary["families"] if f["family_id"] == "compute_net_power_margin")

    assert summary["entry_gate_pass"] is False
    assert primary["status"] == "INSUFFICIENT_VARIANCE"
    assert primary["raw_observations"] == 80
    assert primary["observations"] == 1
    assert primary["collapsed_repeated_marks"] == 79
    assert primary["tested_trades"] == 0


def test_replay_collapses_repeated_poll_ticks_before_pnl():
    pattern = [0.82, 0.84, 0.86, 0.84]
    clean_rows = [_row(pattern[i % len(pattern)], ts=i) for i in range(80)]
    repeated_rows = []
    for i, value in enumerate(pattern[j % len(pattern)] for j in range(80)):
        for repeat in range(4):
            repeated_rows.append(_row(value, ts=(i * 10) + repeat))

    clean = sfb.summarize(clean_rows, window=8, horizon_steps=2, threshold_z=0.8, min_obs=20, min_distinct=3, min_trades=5)
    repeated = sfb.summarize(repeated_rows, window=8, horizon_steps=2, threshold_z=0.8, min_obs=20, min_distinct=3, min_trades=5)
    clean_primary = next(f for f in clean["families"] if f["family_id"] == "compute_net_power_margin")
    repeated_primary = next(f for f in repeated["families"] if f["family_id"] == "compute_net_power_margin")

    assert repeated_primary["raw_observations"] == 320
    assert repeated_primary["observations"] == clean_primary["observations"]
    assert repeated_primary["collapsed_repeated_marks"] == 240
    assert repeated_primary["tested_trades"] == clean_primary["tested_trades"]
    assert repeated_primary["total_pnl_per_unit"] == clean_primary["total_pnl_per_unit"]


def test_walk_forward_replay_promotes_mean_reverting_spread_family():
    # Alternating shocks make the no-lookahead mean-reversion replay positive.
    pattern = [0.82, 0.84, 0.86, 0.84]
    rows = [_row(pattern[i % len(pattern)], ts=i) for i in range(120)]

    summary = sfb.summarize(rows, window=8, horizon_steps=2, threshold_z=0.8, min_obs=20, min_distinct=3, min_trades=5)
    primary = next(f for f in summary["families"] if f["family_id"] == "compute_net_power_margin")

    assert primary["status"] == "PROMOTABLE"
    assert primary["win_rate"] >= 55
    assert primary["total_pnl_per_unit"] > 0
    assert primary["out_of_sample_replay"]["version"] == "spread_family_oos_replay_v1"
    assert primary["oos_status"] == "PASSED"
    assert primary["oos_test_pnl_per_unit"] > 0


def test_walk_forward_replay_can_promote_trend_following_spread_family():
    rows = []
    for i in range(240):
        s_t = 0.80 + 0.0005 * i + 0.005 * math.sin(i * 2 * math.pi / 36)
        rows.append(_row(s_t, ts=i))

    summary = sfb.summarize(
        rows,
        strategy_modes=(sfb.STRATEGY_MEAN_REVERSION, sfb.STRATEGY_MOMENTUM),
    )
    primary = next(
        f for f in summary["families"]
        if f["family_id"] == "compute_net_power_margin" and f["strategy_id"] == sfb.STRATEGY_MOMENTUM
    )

    assert primary["status"] == "PROMOTABLE"
    assert primary["strategy_label"] == "Trend-following"
    assert primary["win_rate"] >= 55
    assert primary["total_pnl_per_unit"] > 0
    assert primary["oos_status"] == "PASSED"


def test_promotable_full_sample_is_blocked_when_oos_slice_fails():
    pattern = [0.82, 0.84, 0.86, 0.84]
    rows = []
    for i in range(200):
        rows.append(_row(pattern[i % len(pattern)], ts=i))
    for j in range(80):
        rows.append(_row(0.84 + 0.001 * j, ts=200 + j))

    summary = sfb.summarize(rows, window=8, horizon_steps=2, threshold_z=0.8, min_obs=20, min_distinct=3, min_trades=5)
    primary = next(f for f in summary["families"] if f["family_id"] == "compute_net_power_margin")

    assert primary["status"] == "FAILED_OOS_REPLAY"
    assert primary["is_promotable"] is False
    assert primary["total_pnl_per_unit"] > 0
    assert primary["win_rate"] >= 55
    assert primary["oos_status"] == "FAILED"
    assert primary["oos_test_pnl_per_unit"] < 0


def test_derived_calendar_families_use_prior_marks_without_forward_curves():
    rows = []
    for i in range(180):
        elec = 60.0 + 0.04 * i + 1.2 * math.sin(i * 2 * math.pi / 28)
        compute = 1.0 + 0.002 * i + 0.025 * math.sin(i * 2 * math.pi / 28)
        rows.append({
            "ts": i,
            "region": "ERCOT|us-east-1",
            "electricity_per_mwh": elec,
            "compute_per_gpu_hr": compute,
            "region_a_electricity_per_mwh": elec,
            "region_a_compute_per_gpu_hr": compute,
            "region_b_electricity_per_mwh": 58.0 + 0.02 * i + 0.7 * math.sin(i * 2 * math.pi / 31),
            "region_b_compute_per_gpu_hr": 0.96 + 0.0015 * i + 0.015 * math.sin(i * 2 * math.pi / 31),
            "k": 0.5,
            "kwh_per_gpu_hr": 0.7,
        })

    summary = sfb.summarize(
        rows,
        strategy_modes=(sfb.STRATEGY_MEAN_REVERSION, sfb.STRATEGY_MOMENTUM),
        window=12,
        horizon_steps=3,
        threshold_z=0.8,
        min_obs=40,
        min_distinct=8,
        min_trades=4,
    )

    compute_calendar = next(f for f in summary["families"] if f["family_id"] == "compute_prompt_calendar_21d")
    power_calendar = next(f for f in summary["families"] if f["family_id"] == "electricity_prompt_calendar_21d")
    curve_basis = next(f for f in summary["families"] if f["family_id"] == "compute_power_prompt_basis_21d")
    regional_basis = next(f for f in summary["families"] if f["family_id"] == "regional_compute_power_basis_proxy")
    scoreboard = summary["archetype_scoreboard"]

    assert compute_calendar["observations"] > 100
    assert compute_calendar["raw_observations"] == len(rows) - 21
    assert power_calendar["observations"] > 100
    assert curve_basis["observations"] > 100
    assert regional_basis["observations"] > 100
    assert "prior 21-mark" in compute_calendar["formula"]
    assert next(item for item in scoreboard if item["archetype_id"] == "compute_calendar_spread")["evidence_level"] == "replayed"
    assert next(item for item in scoreboard if item["archetype_id"] == "electricity_calendar_spread")["evidence_level"] == "replayed"
    assert next(item for item in scoreboard if item["archetype_id"] == "compute_power_calendar_basis")["evidence_level"] == "replayed"
    assert next(item for item in scoreboard if item["archetype_id"] == "regional_compute_power_basis")["evidence_level"] == "replayed"


def test_index_catalog_includes_compute_electricity_and_spread_archetypes():
    summary = sfb.summarize([], min_obs=1, min_distinct=1)
    catalog = summary["index_catalog"]
    coverage = summary["index_coverage"]
    scoreboard = summary["archetype_scoreboard"]

    assert any(item["id"] == "eia_ercot_tx_proxy" for item in catalog["electricity"])
    assert any(item["id"] == "ercot_hub_rt_lmp" for item in catalog["electricity"])
    assert any(item["id"] == "power_curve_prompt_term_proxy" for item in catalog["electricity"])
    assert any(item["id"] == "silicondata_h100_rental" for item in catalog["compute"])
    assert any(item["id"] == "aws_gpu_region_basis" for item in catalog["compute"])
    assert any(item["id"] == "public_compute_region_basis_proxy" for item in catalog["compute"])
    assert any(item["id"] == "compute_curve_prompt_term_proxy" for item in catalog["compute"])
    assert any(item["id"] == "public_power_region_basis_proxy" for item in catalog["electricity"])
    assert any(item["id"] == "compute_calendar_spread" for item in catalog["spread_archetypes"])
    assert any(item["id"] == "electricity_calendar_spread" for item in catalog["spread_archetypes"])
    assert any(item["id"] == "compute_power_calendar_basis" for item in catalog["spread_archetypes"])
    assert any(item["archetype_id"] == "compute_spark_spread" and item["evidence_level"] == "replayed" for item in scoreboard)
    calendar = next(item for item in scoreboard if item["archetype_id"] == "compute_calendar_spread")
    assert calendar["evidence_level"] == "replayed"
    assert "prior-mark term proxy" in calendar["required_indexes"]
    regional = next(item for item in scoreboard if item["archetype_id"] == "regional_compute_power_basis")
    assert regional["evidence_level"] == "replayed"
    assert regional["replay_status"] == "INSUFFICIENT_HISTORY"
    assert coverage["version"] == "index_coverage_v1"
    assert coverage["electricity"]["usable"] >= 5
    assert coverage["compute"]["usable"] >= 4
    assert coverage["spread_archetypes"]["total"] >= 8
    assert coverage["spread_archetypes"]["replayed"] >= 8
    assert coverage["spread_archetypes"]["planned"] == 0
    assert coverage["spread_archetypes"]["needs_history"] == []
    assert "electricity indexes usable" in coverage["summary"]


def test_archetype_scoreboard_surfaces_promotable_oil_style_spreads():
    rows = []
    for i in range(240):
        s_t = 0.80 + 0.0005 * i + 0.005 * math.sin(i * 2 * math.pi / 36)
        rows.append(_row(s_t, ts=i))

    summary = sfb.summarize(
        rows,
        strategy_modes=(sfb.STRATEGY_MEAN_REVERSION, sfb.STRATEGY_MOMENTUM),
    )
    scoreboard = summary["archetype_scoreboard"]
    spark = next(item for item in scoreboard if item["archetype_id"] == "compute_spark_spread")

    assert spark["evidence_level"] == "replayed"
    assert spark["is_promotable"] is True
    assert spark["strategy_label"] == "Trend-following"
    assert spark["oil_analogy"] == "refining crack spread"
    assert spark["oos_status"] == "PASSED"
    assert spark["oos_test_trades"] > 0
