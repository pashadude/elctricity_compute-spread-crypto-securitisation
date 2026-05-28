import math
import random
import tempfile
import os
from pathlib import Path

import pytest

from agent import arb_identifier as ai


def test_compute_spread_basic():
    pt = ai.compute_spread(
        electricity_per_mwh=80.0, compute_per_gpu_hr=1.50, region="MOCK",
        k=0.5, kwh_per_gpu_hr=0.7,
    )
    # $/GPU-hr units: 1.50 - 0.5 * (80/1000) * 0.7 = 1.50 - 0.028 = 1.472
    assert math.isclose(pt.S_t, 1.472, abs_tol=1e-9)
    assert math.isclose(pt.power_cost_per_gpu_hr, 0.028, abs_tol=1e-9)
    assert math.isclose(pt.power_cost_share, 0.028 / 1.50, abs_tol=1e-9)
    assert pt.region == "MOCK"


def test_compute_spread_with_low_electricity():
    pt = ai.compute_spread(electricity_per_mwh=20.0, compute_per_gpu_hr=2.00,
                            region="X", k=0.5, kwh_per_gpu_hr=0.5)
    # 2 - 0.5 * (20/1000) * 0.5 = 2 - 0.005 = 1.995
    assert math.isclose(pt.S_t, 1.995, abs_tol=1e-9)


def test_compute_spread_ercot_realworld():
    # Sanity: ERCOT industrial ~$72/MWh, AWS p4d spot ~$1.54/GPU-hr.
    # 1.54 - 0.5 * (72/1000) * 0.7 = 1.54 - 0.0252 = 1.5148
    pt = ai.compute_spread(electricity_per_mwh=72.0, compute_per_gpu_hr=1.54,
                            region="ERCO", k=0.5, kwh_per_gpu_hr=0.7)
    assert math.isclose(pt.S_t, 1.5148, abs_tol=1e-4)


def test_zscore_with_constant_history():
    # No variance → z=0 (we don't blow up)
    z = ai._zscore(5.0, [5.0, 5.0, 5.0, 5.0])
    assert z == 0.0


def test_zscore_meaningful():
    # Need real variance in the history for a non-zero z.
    z = ai._zscore(10.0, [4.0, 5.0, 5.0, 6.0])
    assert z > 0
    z2 = ai._zscore(0.0, [4.0, 5.0, 5.0, 6.0])
    assert z2 < 0


def test_zscore_constant_history_is_zero():
    # Defensive: constant history → zero std → returns 0 (no NaN).
    assert ai._zscore(10.0, [5.0, 5.0, 5.0]) == 0.0


def test_score_signal_bootstrap_then_no_signal(monkeypatch, tmp_path):
    # Point persistence at a clean tmp dir
    monkeypatch.setattr(ai, "_HISTORY_PATH", tmp_path / "h.tsv")
    monkeypatch.setattr(ai, "_SIGNALS_PATH", tmp_path / "s.tsv")
    pt = ai.compute_spread(80, 1.5, "T1")
    # With bootstrap pseudo-history (Gaussian around base), z should be small.
    rng = random.Random(42)
    sig = ai.score_signal(pt, threshold_z=5.0, rng=rng, persist=True)
    assert sig is None


def test_score_signal_forced(monkeypatch, tmp_path):
    monkeypatch.setattr(ai, "_HISTORY_PATH", tmp_path / "h.tsv")
    monkeypatch.setattr(ai, "_SIGNALS_PATH", tmp_path / "s.tsv")
    pt = ai.compute_spread(80, 1.5, "T2")
    sig = ai.score_signal(pt, threshold_z=1.0, forced=2.0, persist=True)
    assert sig is not None
    assert sig.z == 2.0
    assert sig.direction == ai.DIRECTION_COMPUTE_EXPENSIVE
    assert (tmp_path / "s.tsv").exists()


def test_score_signal_forced_negative():
    pt = ai.compute_spread(200, 0.5, "T3")
    sig = ai.score_signal(pt, threshold_z=0.5, forced=-2.0, persist=False)
    assert sig is not None
    assert sig.direction == ai.DIRECTION_ELEC_EXPENSIVE


def test_append_history_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr(ai, "_HISTORY_PATH", tmp_path / "h.tsv")
    pt = ai.compute_spread(80, 1.5, "T4")
    ai.append_history(pt)
    ai.append_history(pt)
    read = ai._read_history()
    assert len(read) == 2
    assert math.isclose(read[0], pt.S_t, abs_tol=1e-3)
