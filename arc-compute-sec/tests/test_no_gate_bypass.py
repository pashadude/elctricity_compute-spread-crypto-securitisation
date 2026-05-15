import pathlib
import re
from dataclasses import asdict
from types import SimpleNamespace

from adapters import polymarket
from agent import arb_identifier, judge, runtime


def _signal():
    return arb_identifier.ArbSignal(
        signal_id="sig-gate",
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


def _gate_result(passes: bool, premium: float):
    return SimpleNamespace(
        passes_gate=passes,
        premium=premium,
        rejection_reason=None if passes else "premium_below_zero",
        raw={"premium": premium},
    )


def test_positive_fresh_energy_candidate_executes_without_gate_bypass(tmp_path, monkeypatch):
    monkeypatch.setattr(judge, "_JUDGEMENTS_PATH", tmp_path / "judgements.tsv")
    monkeypatch.setattr(runtime, "_POSITIONS_PATH", tmp_path / "positions.tsv")
    monkeypatch.setattr(
        polymarket,
        "fetch_events",
        lambda: [{
            "id": "energy-positive",
            "slug": "wti-positive",
            "title": "Will WTI > $90 by Q3?",
            "markets": [{"outcomePrice": "0.55"}, {"outcomePrice": "0.50"}],
        }],
    )
    monkeypatch.setattr(polymarket, "score_candidate", lambda **_: _gate_result(True, 0.05))

    wrapped = []

    def fake_wrap(candidate, fill_report, signal, identity, expires_seconds=600, dry_run=True):
        wrapped.append(candidate.candidate_id)
        return {"dry_run": True, "deliverable_hash": "0xabc", "candidate_id": candidate.candidate_id}

    monkeypatch.setattr(runtime, "wrap_position", fake_wrap)

    candidates = runtime._polymarket_candidates(_signal(), live_scan=True, sizing_usdc=1.0)
    results = runtime.process_candidates(
        candidates,
        state=judge.default_state(),
        dry_run=True,
        signal=_signal(),
        max_positions=1,
    )

    assert len(candidates) == 1
    assert results[0]["verdict"]["label"] == judge.LABEL_EXECUTE
    assert wrapped == [candidates[0].candidate_id]


def test_mock_s4_case_a_is_premium_gate_positive():
    candidates = runtime._polymarket_candidates(_signal(), live_scan=False, sizing_usdc=1.0)
    assert len(candidates) == 1
    scorer_result = runtime._scorer_result_for_candidate(candidates[0])
    verdict = judge.classify(asdict(candidates[0]), judge.default_state(), scorer_result)
    assert scorer_result["passes_gate"] is True
    assert scorer_result["premium"] > 0
    assert verdict.label == judge.LABEL_EXECUTE


def test_negative_premium_rejects_and_does_not_wrap(tmp_path, monkeypatch):
    monkeypatch.setattr(judge, "_JUDGEMENTS_PATH", tmp_path / "judgements.tsv")
    monkeypatch.setattr(runtime, "_POSITIONS_PATH", tmp_path / "positions.tsv")
    monkeypatch.setattr(
        polymarket,
        "fetch_events",
        lambda: [{
            "id": "energy-negative",
            "slug": "wti-negative",
            "title": "Will WTI > $90 by Q3?",
            "markets": [{"outcomePrice": "0.30"}, {"outcomePrice": "0.50"}],
        }],
    )
    monkeypatch.setattr(polymarket, "score_candidate", lambda **_: _gate_result(False, -0.20))

    def fail_wrap(*args, **kwargs):
        raise AssertionError("wrap_position must not be called for premium-gate REJECT")

    monkeypatch.setattr(runtime, "wrap_position", fail_wrap)

    candidates = runtime._polymarket_candidates(_signal(), live_scan=True, sizing_usdc=1.0)
    results = runtime.process_candidates(
        candidates,
        state=judge.default_state(),
        dry_run=True,
        signal=_signal(),
        max_positions=1,
    )

    assert len(candidates) == 1
    assert results[0]["verdict"]["label"] == judge.LABEL_REJECT
    assert results[0]["verdict"]["reason_code"] == "premium_gate_fail"


def test_off_template_event_drops_before_scoring(monkeypatch):
    calls = {"score": 0}

    def score_candidate(**kwargs):
        calls["score"] += 1
        return _gate_result(True, 0.10)

    monkeypatch.setattr(polymarket, "score_candidate", score_candidate)

    out = polymarket.classify_and_gate(
        [{
            "id": "music",
            "slug": "music",
            "title": "Will Taylor Swift release an album?",
            "markets": [{"outcomePrice": "0.70"}, {"outcomePrice": "0.40"}],
        }],
        include_rejected=True,
    )

    assert out == []
    assert calls["score"] == 0


def test_repository_has_no_false_premium_gate_assignment():
    root = pathlib.Path(__file__).resolve().parent.parent
    pattern = re.compile(r"require_non_negative_premium\s*=\s*False")
    violations = []
    for py in root.rglob("*.py"):
        parts = set(py.parts)
        if {".venv", "node_modules", "__pycache__", "upstream"} & parts:
            continue
        text = py.read_text(errors="replace")
        in_docstring = False
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
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
    assert not violations
