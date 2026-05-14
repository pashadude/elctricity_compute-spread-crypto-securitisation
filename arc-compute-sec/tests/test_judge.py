from agent import judge


def _candidate(**overrides):
    base = dict(
        candidate_id="c1", arb_signal_id="s1", surface="ibkr",
        instrument="GOOGL", direction="short", sizing_usdc=1.0,
        conviction=2.0, est_pnl_per_dollar=0.01, ttl_hours=24,
        metadata={}, data_age_seconds=10,
    )
    base.update(overrides)
    return base


def test_execute_default():
    v = judge.classify(_candidate(), judge.default_state())
    assert v.label == judge.LABEL_EXECUTE


def test_reject_premium_gate():
    v = judge.classify(_candidate(surface="polymarket"), judge.default_state(),
                       scorer_result={"passes_gate": False, "premium": -0.02})
    assert v.label == judge.LABEL_REJECT
    assert v.reason_code == "premium_gate_fail"


def test_reject_size_cap():
    st = judge.default_state()
    st["max_position_usdc"] = 0.1
    v = judge.classify(_candidate(sizing_usdc=1.0), st)
    assert v.label == judge.LABEL_REJECT
    assert v.reason_code == "size_cap_breach"


def test_reject_concurrency_cap():
    st = judge.default_state()
    st["positions_open"] = 100
    st["max_concurrent_positions"] = 5
    v = judge.classify(_candidate(), st)
    assert v.label == judge.LABEL_REJECT
    assert v.reason_code == "concurrency_cap"


def test_defer_stale_data():
    st = judge.default_state()
    st["max_data_age_seconds"] = 5
    v = judge.classify(_candidate(data_age_seconds=999), st)
    assert v.label == judge.LABEL_DEFER
    assert v.reason_code == "stale_data"


def test_defer_under_sampled_surface():
    st = judge.default_state()
    st["min_resolutions_for_execute"] = 100
    v = judge.classify(_candidate(surface="crypto"), st)
    assert v.label == judge.LABEL_DEFER


def test_log_writes_row(tmp_path, monkeypatch):
    p = tmp_path / "j.tsv"
    monkeypatch.setattr(judge, "_JUDGEMENTS_PATH", p)
    c = _candidate(est_pnl_per_dollar=0.05)
    v = judge.classify(c, judge.default_state())
    judge.log(v, c)
    body = p.read_text()
    assert "EXECUTE" in body
    assert "GOOGL" in body


def test_gate_kwarg_exclusion():
    """Regression: the premium gate kwarg must never be set to False in
    executable code. The premium gate is the desk's only cross-validated
    edge (§6 anti-goal)."""
    import pathlib, re
    root = pathlib.Path(__file__).resolve().parent.parent
    # Match actual Python assignment/call usage, not prose mentions
    pattern = re.compile(r"require_non_negative_premium\s*=\s*False")
    violations = []
    for py in root.rglob("*.py"):
        parts = py.parts
        if any(skip in parts for skip in (".venv", "node_modules", "__pycache__", "upstream")):
            continue
        if py.resolve() == pathlib.Path(__file__).resolve():
            continue
        text = py.read_text(errors="replace")
        in_docstring = False
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            # Track triple-quote docstrings
            tq_count = stripped.count('"""') + stripped.count("'''")
            if tq_count == 1:
                in_docstring = not in_docstring
                continue
            if in_docstring:
                continue
            if stripped.startswith("#"):
                continue
            if pattern.search(line):
                violations.append(f"{py.relative_to(root)}:{i}: {stripped}")
    assert not violations, (
        "Gate kwarg bypass found — this violates §6 anti-goal.\n" + "\n".join(violations)
    )
