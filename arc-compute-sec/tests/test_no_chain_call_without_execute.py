from agent import arb_identifier, judge, runtime, surface_router


def _signal():
    return arb_identifier.ArbSignal(
        signal_id="sig-chain",
        ts=1.0,
        region="MOCK",
        S_t=0.0,
        z=-2.0,
        direction=arb_identifier.DIRECTION_ELEC_EXPENSIVE,
        conviction=2.0,
        ttl_hours=24,
        electricity_per_mwh=100.0,
        compute_per_gpu_hr=1.5,
    )


def _candidate(**overrides):
    base = dict(
        candidate_id="cand-chain",
        arb_signal_id="sig-chain",
        surface="polymarket",
        instrument="polymarket:energy",
        direction="short",
        sizing_usdc=1.0,
        conviction=2.0,
        est_pnl_per_dollar=0.05,
        ttl_hours=24,
        metadata={
            "yes_prices": [0.55, 0.50],
            "energy_template_id": "energy_oil_price",
            "scorer_result": {
                "passes_gate": True,
                "premium": 0.05,
                "rejection_reason": None,
                "raw": {},
            },
        },
    )
    base.update(overrides)
    return surface_router.Candidate(**base)


def test_reject_verdict_never_reaches_wrap(tmp_path, monkeypatch):
    monkeypatch.setattr(judge, "_JUDGEMENTS_PATH", tmp_path / "judgements.tsv")
    monkeypatch.setattr(runtime, "_POSITIONS_PATH", tmp_path / "positions.tsv")

    def fail_wrap(*args, **kwargs):
        raise AssertionError("wrap_position must not be called for REJECT")

    monkeypatch.setattr(runtime, "wrap_position", fail_wrap)
    candidate = _candidate(metadata={
        "yes_prices": [0.30, 0.50],
        "energy_template_id": "energy_oil_price",
        "scorer_result": {
            "passes_gate": False,
            "premium": -0.20,
            "rejection_reason": "premium_below_zero",
            "raw": {},
        },
    })

    results = runtime.process_candidates(
        [candidate],
        state=judge.default_state(),
        dry_run=True,
        signal=_signal(),
        max_positions=1,
    )

    assert results[0]["verdict"]["label"] == judge.LABEL_REJECT
    assert not (tmp_path / "positions.tsv").exists()


def test_defer_verdict_never_reaches_wrap(tmp_path, monkeypatch):
    monkeypatch.setattr(judge, "_JUDGEMENTS_PATH", tmp_path / "judgements.tsv")
    monkeypatch.setattr(runtime, "_POSITIONS_PATH", tmp_path / "positions.tsv")

    def fail_wrap(*args, **kwargs):
        raise AssertionError("wrap_position must not be called for DEFER")

    monkeypatch.setattr(runtime, "wrap_position", fail_wrap)
    state = judge.default_state()
    candidate = _candidate(sizing_usdc=11.0)
    state["max_position_usdc"] = 20.0
    state["challenge_threshold_usdc"] = 10.0

    results = runtime.process_candidates(
        [candidate],
        state=state,
        dry_run=True,
        signal=_signal(),
        max_positions=1,
    )

    assert results[0]["verdict"]["label"] == judge.LABEL_DEFER
    assert not (tmp_path / "positions.tsv").exists()


def test_execute_verdict_is_required_before_wrap(tmp_path, monkeypatch):
    monkeypatch.setattr(judge, "_JUDGEMENTS_PATH", tmp_path / "judgements.tsv")
    monkeypatch.setattr(runtime, "_POSITIONS_PATH", tmp_path / "positions.tsv")
    calls = {"wrap": 0}

    def fake_wrap(candidate, fill_report, signal, identity, expires_seconds=600, dry_run=True):
        calls["wrap"] += 1
        return {"dry_run": True, "deliverable_hash": "0xabc", "candidate_id": candidate.candidate_id}

    monkeypatch.setattr(runtime, "wrap_position", fake_wrap)

    results = runtime.process_candidates(
        [_candidate()],
        state=judge.default_state(),
        dry_run=True,
        signal=_signal(),
        max_positions=1,
    )

    assert results[0]["verdict"]["label"] == judge.LABEL_EXECUTE
    assert calls["wrap"] == 1
