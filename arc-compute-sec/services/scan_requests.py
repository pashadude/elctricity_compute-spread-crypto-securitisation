"""File-backed scan request queue shared by API, worker, and Telegram."""
from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from services.state import bool_env, log_dir, sanitize_row

QUEUE_NAME = "scan_requests.jsonl"
LOCK_NAME = "scan.lock"
LOCK_STALE_SECONDS = 60 * 30


def _pid_start_ticks(pid: int) -> str | None:
    """Return the Linux/macOS process start marker when available.

    On Linux this is `/proc/<pid>/stat` field 22. It lets a restarted Docker
    container distinguish the new PID 1 from a lock left by the previous PID 1.
    On platforms without procfs we return None and fall back to time staleness.
    """
    stat_path = Path("/proc") / str(pid) / "stat"
    try:
        fields = stat_path.read_text(encoding="utf-8").split()
    except OSError:
        return None
    if len(fields) < 22:
        return None
    return fields[21]


def _lock_owner_alive(payload: dict[str, Any]) -> bool | None:
    try:
        pid = int(payload.get("pid", 0))
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    expected_start = payload.get("pid_start_ticks")
    current_start = _pid_start_ticks(pid)
    if current_start is not None and expected_start is None:
        return False
    if current_start is None:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return None
    return str(current_start) == str(expected_start)


def _queue_path(logs: Path | str | None = None) -> Path:
    return log_dir(logs) / QUEUE_NAME


def append_event(event: dict[str, Any], *, logs: Path | str | None = None) -> None:
    path = _queue_path(logs)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True, default=str) + "\n")


def enqueue_scan(
    *,
    source: str,
    live: bool = False,
    force_signal: float | None = None,
    max_positions: int = 1,
    multi_surface: bool = True,
    settle: bool = False,
    logs: Path | str | None = None,
    user_id: str | int | None = None,
) -> dict[str, Any]:
    live_allowed = bool_env("ENABLE_LIVE_CHAIN", False)
    request = {
        "event": "queued",
        "request_id": str(uuid.uuid4())[:12],
        "ts": time.time(),
        "source": source,
        "user_id": "" if user_id is None else str(user_id),
        "live": bool(live and live_allowed),
        "requested_live": bool(live),
        "force_signal": force_signal,
        "max_positions": int(max_positions),
        "multi_surface": bool(multi_surface),
        "settle": bool(settle and live and live_allowed),
        "status": "queued",
    }
    append_event(request, logs=logs)
    return sanitize_row(request)


def _read_events(*, logs: Path | str | None = None) -> list[dict[str, Any]]:
    path = _queue_path(logs)
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                out.append(raw)
    return out


def requests_by_id(*, logs: Path | str | None = None) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for event in _read_events(logs=logs):
        request_id = str(event.get("request_id") or "")
        if not request_id:
            continue
        base = merged.get(request_id, {})
        base.update(event)
        merged[request_id] = base
    return {k: sanitize_row(v) for k, v in merged.items()}


def pending_requests(*, logs: Path | str | None = None) -> list[dict[str, Any]]:
    pending = [v for v in requests_by_id(logs=logs).values() if v.get("status") == "queued"]
    pending.sort(key=lambda row: float(row.get("ts", 0.0)))
    return pending


def mark_request(
    request_id: str,
    status: str,
    *,
    logs: Path | str | None = None,
    return_code: int | None = None,
    error: str = "",
) -> None:
    append_event({
        "event": status,
        "request_id": request_id,
        "ts": time.time(),
        "status": status,
        "return_code": return_code,
        "error": error,
    }, logs=logs)


def _lock_path(logs: Path | str | None = None) -> Path:
    return log_dir(logs) / LOCK_NAME


@contextmanager
def scan_lock(*, logs: Path | str | None = None, stale_seconds: int = LOCK_STALE_SECONDS) -> Iterator[bool]:
    path = _lock_path(logs)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            lock_ts = float(payload.get("ts", 0.0))
        except (OSError, json.JSONDecodeError, ValueError):
            payload = {}
            lock_ts = 0.0
        owner_alive = _lock_owner_alive(payload)
        if owner_alive is False:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        elif now - lock_ts <= stale_seconds:
            yield False
            return
        else:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        yield False
        return
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            pid = os.getpid()
            fh.write(json.dumps({"ts": now, "pid": pid, "pid_start_ticks": _pid_start_ticks(pid)}))
        yield True
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
