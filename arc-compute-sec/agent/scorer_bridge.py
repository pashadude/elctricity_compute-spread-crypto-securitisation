"""Bridge to the upstream Polymarket scorer.

DRIFT from prior TASK.md: scorer lives at
  api/polymarket/longtail/scorer.py:47
inside the symlinked upstream repo. Import path is therefore
  from api.polymarket.longtail.scorer import filter_candidates, score_no_candidates
NOT `import scorer`.

We never set `require_non_negative_premium=False` here. The S1/S3 corridor
that allows negative premium lives on its own call sites in the upstream
repo; this build is the energy/AI-event S-4 leg only.
"""
from __future__ import annotations

import os
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

def _resolve_upstream_dir() -> Path:
    configured = os.environ.get("UPSTREAM_RELAYER_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (
        Path(__file__).resolve().parent.parent / "upstream" / "py-builder-relayer-client"
    ).resolve()


_UPSTREAM_DIR = _resolve_upstream_dir()
if str(_UPSTREAM_DIR) not in sys.path:
    sys.path.insert(0, str(_UPSTREAM_DIR))


def _stub_upstream_deps() -> None:
    """The upstream package's import chain pulls in `secrets_manager` (which
    in turn imports `google.cloud.secretmanager`) via `api/polymarket/__init__.py`.
    We don't need that codepath — we only call `filter_candidates`. Stub the
    modules so the import succeeds without GCP SDK installed.
    """
    if "secrets_manager" not in sys.modules:
        mod = types.ModuleType("secrets_manager")

        def _missing(*args, **kwargs):
            raise RuntimeError(
                "secrets_manager is stubbed in this build; the upstream private-key "
                "loader is unused here. If you see this, the call path is wrong."
            )

        mod.get_user_private_key = _missing  # type: ignore
        mod._get_private_key = _missing  # type: ignore
        sys.modules["secrets_manager"] = mod
    # Also stub google.cloud.secretmanager if downstream code path-imports it.
    if "google" not in sys.modules:
        g = types.ModuleType("google")
        gc = types.ModuleType("google.cloud")
        gcs = types.ModuleType("google.cloud.secretmanager")
        g.cloud = gc  # type: ignore
        gc.secretmanager = gcs  # type: ignore
        sys.modules.setdefault("google", g)
        sys.modules.setdefault("google.cloud", gc)
        sys.modules.setdefault("google.cloud.secretmanager", gcs)


_stub_upstream_deps()


@dataclass(frozen=True, slots=True)
class GateResult:
    passes_gate: bool
    premium: float
    rejection_reason: str | None
    raw: dict[str, Any]


def _make_candidate(price: float, event_avg_yes_price: float, token_id: str = "mock-token") -> Any:
    """Build a MarketCandidate matching the upstream dataclass shape.

    We use the actual dataclass when available so filter_candidates() sees
    real attribute types; if the dataclass can't be imported (test-only
    fallback) we degrade to SimpleNamespace.
    """
    try:
        scorer_mod = _load_scorer_module()
        MarketCandidate = sys.modules["api.polymarket.longtail.models"].MarketCandidate
    except Exception:
        from types import SimpleNamespace
        return SimpleNamespace(
            slug="mock", market_slug="mock-m", question="Will X happen?",
            condition_id="0x0", token_id=token_id, outcome="Yes",
            price=float(price), edge=1.0 - float(price), liquidity=0.0,
            volume=0.0, days_to_resolution=1.0, event_avg_yes_price=float(event_avg_yes_price),
            bucket_position=1, max_days_to_resolution_override=None,
        )
    return MarketCandidate(
        slug="mock-event",
        market_slug="mock-market",
        question="Mock question for gate test",
        condition_id="0x0",
        token_id=token_id,
        outcome="Yes",
        price=float(price),
        edge=1.0 - float(price),
        liquidity=0.0,
        volume=0.0,
        days_to_resolution=1.0,
        event_avg_yes_price=float(event_avg_yes_price),
        event_num_contenders=2,
        event_sum_yes_prices=float(price) + float(event_avg_yes_price),
        bucket_position=1,
    )


def _load_scorer_module():
    """Load `scorer.py` as a standalone module via importlib, bypassing the
    upstream package's `__init__.py` chains. This avoids loading
    polymarket_api.py (which has optional deps that aren't pinned in our
    requirements and would error at class-def time).
    """
    import importlib.util

    scorer_path = _UPSTREAM_DIR / "api" / "polymarket" / "longtail" / "scorer.py"
    if not scorer_path.exists():
        raise RuntimeError(
            f"Upstream scorer not found at {scorer_path}. Check symlink and the "
            f"upstream PINNED_SHA.txt."
        )

    # Pre-stub sibling modules the scorer imports so its top-level imports work.
    models_path = _UPSTREAM_DIR / "api" / "polymarket" / "longtail" / "models.py"

    if "api" not in sys.modules:
        api_mod = types.ModuleType("api")
        api_mod.__path__ = [str(_UPSTREAM_DIR / "api")]  # type: ignore
        sys.modules["api"] = api_mod
    if "api.polymarket" not in sys.modules:
        pm_mod = types.ModuleType("api.polymarket")
        pm_mod.__path__ = [str(_UPSTREAM_DIR / "api" / "polymarket")]  # type: ignore
        sys.modules["api.polymarket"] = pm_mod
    if "api.polymarket.utils" not in sys.modules:
        ut_mod = types.ModuleType("api.polymarket.utils")
        ut_mod.__path__ = [str(_UPSTREAM_DIR / "api" / "polymarket" / "utils")]  # type: ignore
        sys.modules["api.polymarket.utils"] = ut_mod
    if "api.polymarket.longtail" not in sys.modules:
        lt_mod = types.ModuleType("api.polymarket.longtail")
        lt_mod.__path__ = [str(_UPSTREAM_DIR / "api" / "polymarket" / "longtail")]  # type: ignore
        sys.modules["api.polymarket.longtail"] = lt_mod
    if "api.polymarket.utils.logger" not in sys.modules:
        logger_mod = types.ModuleType("api.polymarket.utils.logger")

        class _NoopLogger:
            def info(self, *args, **kwargs):
                return None

            def warning(self, *args, **kwargs):
                return None

            def debug(self, *args, **kwargs):
                return None

        def _get_logger(*args, **kwargs):
            return _NoopLogger()

        def _get_log_dir():
            return Path("/private/tmp")

        logger_mod.get_logger = _get_logger  # type: ignore[attr-defined]
        logger_mod.get_log_dir = _get_log_dir  # type: ignore[attr-defined]
        sys.modules["api.polymarket.utils.logger"] = logger_mod

    def _load(name: str, path: Path):
        if name in sys.modules:
            return sys.modules[name]
        spec = importlib.util.spec_from_file_location(name, str(path))
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not build spec for {name} at {path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    _load("api.polymarket.longtail.models", models_path)
    return _load("api.polymarket.longtail.scorer", scorer_path)


def score_candidate(
    price: float,
    event_avg_yes_price: float,
    normal_price: float | None = None,
) -> GateResult:
    """Run a single (price, event_avg_yes_price) tuple through the upstream
    premium gate.

    The upstream gate rejects when `price + event_avg_yes_price < 1.0`.
    `passes_gate=True` means the multi-outcome NO-overlay is profitable in
    expectation (sum of YES prices ≥ 1.0).
    """
    try:
        scorer_mod = _load_scorer_module()
        filter_candidates = scorer_mod.filter_candidates
    except Exception as exc:
        raise RuntimeError(
            "Could not load upstream scorer. Verify the symlink:\n"
            f"  {_UPSTREAM_DIR}/api/polymarket/longtail/scorer.py\n"
            f"Underlying error: {exc!r}"
        ) from exc

    cand = _make_candidate(price=price, event_avg_yes_price=event_avg_yes_price)
    # Pass min_price=0.0/max_price=1.0 so we test ONLY the premium gate here.
    # The upstream's broader price/liquidity gates are surface-specific and
    # apply in the live polymarket adapter, not in this Python-side gate test.
    accepted = filter_candidates(
        [cand],
        min_price=0.0,
        max_price=1.0,
        require_non_negative_premium=True,
    )
    premium = float(price) + float(event_avg_yes_price) - 1.0
    if accepted:
        return GateResult(
            passes_gate=True,
            premium=premium,
            rejection_reason=None,
            raw={"price": price, "event_avg_yes_price": event_avg_yes_price},
        )
    return GateResult(
        passes_gate=False,
        premium=premium,
        rejection_reason="premium_below_zero" if premium < 0 else "filtered_by_scorer",
        raw={"price": price, "event_avg_yes_price": event_avg_yes_price},
    )
