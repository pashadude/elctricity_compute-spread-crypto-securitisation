"""Electricity-compute spread identifier.

Core model:
    S_t = compute_$_per_gpu_hr − k × electricity_$_per_MWh × kWh_per_gpu_hr

The agent emits a signal when the z-score of S_t over a 30-day rolling
window exceeds threshold_z. The signal carries direction:

    direction = "compute_expensive"      when z(S_t) >  threshold
    direction = "electricity_expensive"  when z(S_t) < -threshold

History bootstrap: the first time we compute a signal there is no prior
history. We synthesize a 30-day pseudo-history from the live point with
±3% Gaussian jitter so a z-score is computable. Subsequent runs use the
persisted history in `logs/spread_history.tsv`.

This module performs NO chain or trading actions. It only reads feeds
and writes one signal row per run.
"""
from __future__ import annotations

import csv
import math
import os
import random
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

_HISTORY_PATH = Path(__file__).resolve().parent.parent / "logs" / "spread_history.tsv"
_SIGNALS_PATH = Path(__file__).resolve().parent.parent / "logs" / "arb_signals.tsv"

DEFAULT_K = float(os.environ.get("ARB_K_FACTOR", "0.5"))
DEFAULT_KWH_PER_GPU_HR = float(os.environ.get("ARB_KWH_PER_GPU_HR", "0.7"))
DEFAULT_Z_THRESHOLD = float(os.environ.get("ARB_Z_THRESHOLD", "1.0"))

HISTORY_WINDOW = 30 * 24  # 30 days, hourly granularity ⇒ 720 points

DIRECTION_COMPUTE_EXPENSIVE = "compute_expensive"
DIRECTION_ELEC_EXPENSIVE = "electricity_expensive"


@dataclass(frozen=True, slots=True)
class SpreadPoint:
    ts: float
    region: str
    electricity_per_mwh: float
    compute_per_gpu_hr: float
    S_t: float
    k: float
    kwh_per_gpu_hr: float


@dataclass(frozen=True, slots=True)
class ArbSignal:
    signal_id: str
    ts: float
    region: str
    S_t: float
    z: float
    direction: str
    conviction: float    # |z|
    ttl_hours: int       # how long the signal is considered actionable
    electricity_per_mwh: float
    compute_per_gpu_hr: float


def compute_spread(
    electricity_per_mwh: float,
    compute_per_gpu_hr: float,
    region: str,
    k: float = DEFAULT_K,
    kwh_per_gpu_hr: float = DEFAULT_KWH_PER_GPU_HR,
) -> SpreadPoint:
    """Compute one S_t observation.

    Units (this matters — earlier versions had a 1000× bug):
      electricity_per_mwh  : $/MWh           (industry standard for wholesale)
      compute_per_gpu_hr   : $/GPU-hr        (AWS spot p4d/p5 quote shape)
      kwh_per_gpu_hr       : kWh per GPU-hr  (e.g. 0.7 for an H100-class instance)
      k                    : dimensionless   (PUE × utilisation factor, ≈ 0.4–0.7)

    S_t units must be $/GPU-hr. The electricity term is $/MWh × kWh/GPU-hr,
    which is $/GPU-hr × (kWh/MWh) = $/GPU-hr ÷ 1000. We divide by 1000
    inline so callers can keep passing industry-standard $/MWh.

    Sanity check: ERCOT ind ~$72/MWh, p4d ~$1.54/GPU-hr, k=0.5, kWh=0.7
      S_t = 1.54 − 0.5 × (72 / 1000) × 0.7 = 1.54 − 0.0252 = $1.5148/GPU-hr
    """
    s_t = float(compute_per_gpu_hr) - float(k) * (float(electricity_per_mwh) / 1000.0) * float(kwh_per_gpu_hr)
    return SpreadPoint(
        ts=time.time(),
        region=region,
        electricity_per_mwh=float(electricity_per_mwh),
        compute_per_gpu_hr=float(compute_per_gpu_hr),
        S_t=s_t,
        k=float(k),
        kwh_per_gpu_hr=float(kwh_per_gpu_hr),
    )


def _ensure_logs_dir() -> None:
    _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)


def _read_history(region: str | None = None, limit: int = HISTORY_WINDOW) -> list[float]:
    if not _HISTORY_PATH.exists():
        return []
    out: list[float] = []
    with _HISTORY_PATH.open("r", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            if region is not None and row.get("region") != region:
                continue
            try:
                out.append(float(row["S_t"]))
            except (KeyError, ValueError):
                continue
    return out[-limit:]


def append_history(point: SpreadPoint) -> None:
    _ensure_logs_dir()
    new = not _HISTORY_PATH.exists()
    with _HISTORY_PATH.open("a", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        if new:
            writer.writerow(["ts", "region", "electricity_per_mwh",
                             "compute_per_gpu_hr", "S_t", "k", "kwh_per_gpu_hr"])
        writer.writerow([
            f"{point.ts:.0f}",
            point.region,
            f"{point.electricity_per_mwh:.6f}",
            f"{point.compute_per_gpu_hr:.6f}",
            f"{point.S_t:.6f}",
            f"{point.k:.4f}",
            f"{point.kwh_per_gpu_hr:.4f}",
        ])


def _bootstrap_history(point: SpreadPoint, n: int = HISTORY_WINDOW, jitter_pct: float = 0.03,
                      rng: random.Random | None = None) -> list[float]:
    """Synthesize a pseudo-history around the live S_t for first-run z-score."""
    r = rng or random.Random(int(point.ts))
    base = point.S_t
    sigma = max(abs(base) * jitter_pct, 1e-6)
    return [r.gauss(base, sigma) for _ in range(n)]


def _zscore(value: float, history: Iterable[float]) -> float:
    hist = list(history)
    if len(hist) < 2:
        return 0.0
    mean = sum(hist) / len(hist)
    var = sum((h - mean) ** 2 for h in hist) / (len(hist) - 1)
    sd = math.sqrt(var) if var > 0 else 0.0
    if sd == 0:
        return 0.0
    return (value - mean) / sd


def score_signal(
    point: SpreadPoint,
    threshold_z: float = DEFAULT_Z_THRESHOLD,
    ttl_hours: int = 24,
    forced: float | None = None,
    persist: bool = True,
    rng: random.Random | None = None,
) -> ArbSignal | None:
    """Compute a signal from one fresh spread point.

    If `forced` is provided, that value is used as the z-score directly
    (for demos / Phase 4 Case A). Otherwise the z-score is computed
    against persisted history; if there's no history, a pseudo-history is
    bootstrapped from this point.

    Returns None if |z| < threshold (no actionable signal).
    """
    if forced is not None:
        z = float(forced)
    else:
        history = _read_history(region=point.region)
        if len(history) < 2:
            history = _bootstrap_history(point, rng=rng)
        z = _zscore(point.S_t, history)
        if persist:
            append_history(point)

    if abs(z) < threshold_z and forced is None:
        return None

    direction = (
        DIRECTION_COMPUTE_EXPENSIVE if z > 0 else DIRECTION_ELEC_EXPENSIVE
    )
    sig = ArbSignal(
        signal_id=str(uuid.uuid4())[:12],
        ts=point.ts,
        region=point.region,
        S_t=point.S_t,
        z=z,
        direction=direction,
        conviction=abs(z),
        ttl_hours=ttl_hours,
        electricity_per_mwh=point.electricity_per_mwh,
        compute_per_gpu_hr=point.compute_per_gpu_hr,
    )
    if persist:
        _persist_signal(sig)
    return sig


def _persist_signal(sig: ArbSignal) -> None:
    _ensure_logs_dir()
    new = not _SIGNALS_PATH.exists()
    with _SIGNALS_PATH.open("a", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        if new:
            writer.writerow([
                "ts", "signal_id", "region", "S_t", "z", "direction", "conviction",
                "ttl_hours", "electricity_per_mwh", "compute_per_gpu_hr",
            ])
        writer.writerow([
            f"{sig.ts:.0f}",
            sig.signal_id,
            sig.region,
            f"{sig.S_t:.6f}",
            f"{sig.z:.4f}",
            sig.direction,
            f"{sig.conviction:.4f}",
            sig.ttl_hours,
            f"{sig.electricity_per_mwh:.6f}",
            f"{sig.compute_per_gpu_hr:.6f}",
        ])
