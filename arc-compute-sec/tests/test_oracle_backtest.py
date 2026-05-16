import json

from agent import oracle_backtest as ob


def test_multiclass_brier_and_top1_accuracy():
    case = ob.OracleCase(
        key="evt-1",
        probabilities={"A": 0.70, "B": 0.20, "C": 0.10},
        resolved_outcome="A",
        candidate_outcome=None,
        side=None,
        confidence=0.8,
        realized_pnl=None,
        critic_passed=True,
    )

    score = ob.score_case(case)

    assert score.top1_hit is True
    assert round(score.brier, 4) == 0.14
    assert score.resolved_probability == 0.70


def test_no_candidate_oracle_veto_filters_losing_candidate():
    case = ob.OracleCase(
        key="evt-2",
        probabilities={"YES": 0.85, "NO": 0.15},
        resolved_outcome="YES",
        candidate_outcome="YES",
        side="NO",
        confidence=0.9,
        realized_pnl=-0.20,
        critic_passed=True,
    )

    score = ob.score_case(case, no_veto_threshold=0.10)
    metrics = ob.summarize([score], n_records=1, n_skipped=0)

    assert score.candidate_win is False
    assert score.oracle_veto is True
    assert metrics["losses_filtered"] == 1
    assert metrics["wins_filtered"] == 0
    assert metrics["oracle_saved_pnl_by_veto"] == 0.20


def test_no_candidate_oracle_can_filter_a_winner_too():
    case = ob.OracleCase(
        key="evt-3",
        probabilities={"YES": 0.60, "NO": 0.40},
        resolved_outcome="NO",
        candidate_outcome="YES",
        side="SHORT",
        confidence=0.6,
        realized_pnl=0.05,
        critic_passed=True,
    )

    score = ob.score_case(case, no_veto_threshold=0.10)
    metrics = ob.summarize([score], n_records=1, n_skipped=0)

    assert score.candidate_win is True
    assert score.oracle_veto is True
    assert metrics["losses_filtered"] == 0
    assert metrics["wins_filtered"] == 1
    assert metrics["oracle_saved_pnl_by_veto"] == -0.05


def test_parse_skips_critic_failed_by_default():
    records = [{
        "event_id": "evt-critic",
        "resolved_outcome": "YES",
        "analyst": {"probabilities": {"YES": 0.8, "NO": 0.2}},
        "critic": {"passed": False},
    }]

    cases, skips = ob.parse_cases(records)

    assert cases == []
    assert skips == ["1:evt-critic:critic_failed"]


def test_parse_can_join_outcomes_from_separate_jsonl(tmp_path):
    oracle_path = tmp_path / "oracle.jsonl"
    outcomes_path = tmp_path / "outcomes.jsonl"
    oracle_path.write_text(json.dumps({
        "candidate_id": "cand-join",
        "event_id": "evt-join",
        "candidate_outcome": "YES",
        "side": "NO",
        "analyst": {"probabilities": {"YES": 0.75, "NO": 0.25}},
        "critic": {"passed": True},
    }) + "\n")
    outcomes_path.write_text(json.dumps({
        "event_id": "evt-join",
        "resolved_outcome": "YES",
    }) + "\n")

    metrics, scores, skips = ob.run_backtest(
        oracle_jsonl=oracle_path,
        outcomes_jsonl=outcomes_path,
        no_veto_threshold=0.10,
    )

    assert skips == []
    assert metrics["scored"] == 1
    assert scores[0].oracle_veto is True
    assert scores[0].candidate_win is False


def test_invalid_probability_sum_is_skipped():
    records = [{
        "event_id": "evt-bad",
        "resolved_outcome": "YES",
        "analyst": {"probabilities": {"YES": 0.40, "NO": 0.20}},
    }]

    cases, skips = ob.parse_cases(records)

    assert cases == []
    assert "probabilities sum" in skips[0]
