"""24/7 scan worker.

The worker schedules and drains scan requests, but the actual trading/Arc
boundary remains in `agent.runtime`: judge first, wrap only on EXECUTE.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from agent import arb_identifier, runtime
from services import scan_requests
from services.state import bool_env, log_dir, sanitize_row

STATUS_NAME = "runtime_status.json"


def _status_path(logs: Path | str | None = None) -> Path:
    return log_dir(logs) / STATUS_NAME


def write_status(update: dict[str, Any], *, logs: Path | str | None = None) -> dict[str, Any]:
    path = _status_path(logs)
    path.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                current.update(raw)
        except json.JSONDecodeError:
            pass
    current.update(update)
    current["updated_at"] = time.time()
    path.write_text(json.dumps(sanitize_row(current), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return current


def _runtime_args(request: dict[str, Any]) -> argparse.Namespace:
    requested_live = bool(request.get("live"))
    live = requested_live and bool_env("ENABLE_LIVE_CHAIN", False)
    force_signal = request.get("force_signal")
    return argparse.Namespace(
        scan=True,
        once=False,
        force_signal=float(force_signal) if force_signal not in (None, "") else None,
        mock_elec=None,
        mock_compute=None,
        z_threshold=float(os.environ.get("ARB_Z_THRESHOLD", arb_identifier.DEFAULT_Z_THRESHOLD)),
        sizing_equity=float(os.environ.get("SIZING_EQUITY_USDC", "1.0")),
        sizing_crypto=float(os.environ.get("SIZING_CRYPTO_USDC", "1.0")),
        sizing_polymarket=float(os.environ.get("SIZING_POLYMARKET_USDC", "1.0")),
        sizing_ibkr_prediction=float(os.environ.get("SIZING_IBKR_PREDICTION_USDC", "1.0")),
        multi_surface=bool(request.get("multi_surface", True)),
        max_actions=int(request.get("max_positions") or 1),
        expires=int(os.environ.get("ARC_JOB_EXPIRES_SECONDS", "600")),
        dry_run=not live,
        settle=bool(request.get("settle", False)) and live,
        no_persist=False,
    )


def run_scan_request(request: dict[str, Any], *, logs: Path | str | None = None) -> int:
    request_id = str(request.get("request_id") or "scheduled")
    with scan_requests.scan_lock(logs=logs) as acquired:
        if not acquired:
            write_status({
                "state": "busy",
                "last_skipped_request_id": request_id,
                "last_error": "scan_lock_held",
            }, logs=logs)
            return 75
        write_status({
            "state": "running",
            "last_request_id": request_id,
            "last_source": request.get("source", "worker"),
            "dry_run": not bool(request.get("live")),
            "last_error": "",
        }, logs=logs)
        try:
            rc = runtime.run_once(_runtime_args(request))
        except Exception as exc:
            scan_requests.mark_request(request_id, "failed", logs=logs, error=str(exc))
            write_status({
                "state": "error",
                "last_request_id": request_id,
                "last_error": str(exc),
                "last_failure_at": time.time(),
            }, logs=logs)
            raise
        scan_requests.mark_request(request_id, "done", logs=logs, return_code=rc)
        write_status({
            "state": "idle",
            "last_request_id": request_id,
            "last_return_code": rc,
            "last_success_at": time.time(),
            "last_error": "",
        }, logs=logs)
        return rc


def run_once(*, logs: Path | str | None = None, scheduled: bool = False) -> int:
    pending = scan_requests.pending_requests(logs=logs)
    if pending:
        return run_scan_request(pending[0], logs=logs)
    if scheduled:
        request = scan_requests.enqueue_scan(
            source="worker",
            live=bool_env("WORKER_LIVE_CHAIN", False),
            force_signal=os.environ.get("WORKER_FORCE_SIGNAL"),
            max_positions=int(os.environ.get("WORKER_MAX_POSITIONS", "1")),
            multi_surface=bool_env("WORKER_MULTI_SURFACE", True),
            settle=bool_env("WORKER_SETTLE", False),
            logs=logs,
        )
        return run_scan_request(request, logs=logs)
    write_status({"state": "idle", "last_error": ""}, logs=logs)
    return 0


def loop(*, interval_seconds: float, logs: Path | str | None = None) -> None:
    write_status({"state": "starting", "interval_seconds": interval_seconds}, logs=logs)
    while True:
        try:
            run_once(logs=logs, scheduled=True)
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            write_status({"state": "stopped"}, logs=logs)
            raise
        except Exception as exc:
            backoff = float(os.environ.get("WORKER_ERROR_BACKOFF_SECONDS", "60"))
            write_status({"state": "backoff", "last_error": str(exc), "backoff_seconds": backoff}, logs=logs)
            time.sleep(backoff)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Arc Compute Sec 24/7 scan worker")
    parser.add_argument("--once", action="store_true", help="Drain one queued/scheduled scan and exit")
    parser.add_argument("--no-scheduled", action="store_true", help="Only drain queued requests")
    parser.add_argument("--interval", type=float, default=float(os.environ.get("WORKER_INTERVAL_SECONDS", "300")))
    args = parser.parse_args(argv)
    if args.once:
        return run_once(scheduled=not args.no_scheduled)
    loop(interval_seconds=args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
