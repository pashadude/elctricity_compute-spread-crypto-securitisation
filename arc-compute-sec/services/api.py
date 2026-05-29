"""Small stdlib HTTP API for the local operator dashboard."""
from __future__ import annotations

import gzip
import json
import mimetypes
import os
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from services import accounts, scan_requests, state, user_portfolio


_SNAPSHOT_RESPONSE_LOCK = threading.RLock()
_SNAPSHOT_RESPONSE_BUILD_LOCK = threading.Lock()
_SNAPSHOT_RESPONSE_CACHE: dict[bool, tuple[float, bytes]] = {}
_API_METRICS_LOCK = threading.RLock()
_API_METRICS: dict[str, object] = {
    "started_at": time.time(),
    "paths": {},
}
_RATE_LIMIT_LOCK = threading.RLock()
_RATE_LIMITS: dict[str, deque[float]] = {}


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw in ("", None):
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _record_response(path: str, status: int, byte_count: int) -> None:
    now = time.time()
    with _API_METRICS_LOCK:
        paths = _API_METRICS.setdefault("paths", {})
        assert isinstance(paths, dict)
        row = paths.setdefault(path, {"count": 0, "bytes": 0, "last_status": 0, "last_at": 0.0})
        assert isinstance(row, dict)
        row["count"] = int(row.get("count") or 0) + 1
        row["bytes"] = int(row.get("bytes") or 0) + max(0, int(byte_count))
        row["last_status"] = int(status)
        row["last_at"] = now


def _api_metrics() -> dict[str, object]:
    with _API_METRICS_LOCK:
        started_at = float(_API_METRICS.get("started_at") or time.time())
        paths = _API_METRICS.get("paths") if isinstance(_API_METRICS.get("paths"), dict) else {}
        rows = []
        for path, row in paths.items():
            if not isinstance(row, dict):
                continue
            rows.append({
                "path": path,
                "count": int(row.get("count") or 0),
                "bytes": int(row.get("bytes") or 0),
                "last_status": int(row.get("last_status") or 0),
                "last_at": float(row.get("last_at") or 0.0),
            })
        rows.sort(key=lambda row: (int(row["bytes"]), int(row["count"])), reverse=True)
    return {
        "started_at": started_at,
        "uptime_seconds": max(0.0, time.time() - started_at),
        "paths": rows[:12],
    }


def _rate_limited(path: str, *, limit: int, window_seconds: float) -> bool:
    if limit <= 0 or window_seconds <= 0:
        return False
    now = time.time()
    cutoff = now - window_seconds
    with _RATE_LIMIT_LOCK:
        rows = _RATE_LIMITS.setdefault(path, deque())
        while rows and rows[0] < cutoff:
            rows.popleft()
        if len(rows) >= limit:
            return True
        rows.append(now)
    return False


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "ArcComputeSecAPI/0.1"
    protocol_version = "HTTP/1.0"

    def setup(self) -> None:
        super().setup()
        timeout = _float_env("API_SOCKET_TIMEOUT_SECONDS", 5.0)
        if timeout > 0 and hasattr(self.connection, "settimeout"):
            self.connection.settimeout(timeout)

    def handle(self) -> None:
        self.close_connection = True
        self.handle_one_request()

    def log_message(self, fmt: str, *args) -> None:
        if state.bool_env("API_ACCESS_LOG", False):
            super().log_message(fmt, *args)

    def _send_json(self, status: int, payload: dict | list, *, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
        compressed = "gzip" in (self.headers.get("Accept-Encoding") or "").lower()
        if compressed:
            body = gzip.compress(body)
        self._send_json_bytes(status, body, compressed=compressed, headers=headers)

    def _send_json_bytes(
        self,
        status: int,
        body: bytes,
        *,
        compressed: bool = False,
        headers: dict[str, str] | None = None,
        cache_control: str = "no-store",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("Connection", "close")
        if compressed:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Access-Control-Allow-Origin", os.environ.get("API_CORS_ORIGIN", "*"))
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass
        _record_response(urlparse(self.path).path, status, len(body))
        self.close_connection = True

    def _send_snapshot(self) -> None:
        compressed = "gzip" in (self.headers.get("Accept-Encoding") or "").lower()
        cache_seconds = _float_env(
            "API_SNAPSHOT_RESPONSE_CACHE_SECONDS",
            _float_env("SNAPSHOT_CACHE_SECONDS", 60.0),
        )
        cache_control = f"public, max-age={max(1, int(cache_seconds))}, stale-while-revalidate={max(30, int(cache_seconds * 2))}"
        if cache_seconds > 0:
            now = time.time()
            with _SNAPSHOT_RESPONSE_LOCK:
                cached = _SNAPSHOT_RESPONSE_CACHE.get(compressed)
                if cached and cached[0] > now:
                    self._send_json_bytes(200, cached[1], compressed=compressed, cache_control=cache_control)
                    return

            _SNAPSHOT_RESPONSE_BUILD_LOCK.acquire()
            try:
                now = time.time()
                with _SNAPSHOT_RESPONSE_LOCK:
                    cached = _SNAPSHOT_RESPONSE_CACHE.get(compressed)
                    if cached and cached[0] > now:
                        self._send_json_bytes(200, cached[1], compressed=compressed, cache_control=cache_control)
                        return

                body = json.dumps(state.compact_snapshot(), separators=(",", ":"), default=str).encode("utf-8")
                if compressed:
                    body = gzip.compress(body)
                with _SNAPSHOT_RESPONSE_LOCK:
                    _SNAPSHOT_RESPONSE_CACHE[compressed] = (time.time() + cache_seconds, body)
                self._send_json_bytes(200, body, compressed=compressed, cache_control=cache_control)
                return
            finally:
                _SNAPSHOT_RESPONSE_BUILD_LOCK.release()

        self._send_json(200, state.compact_snapshot())

    def _send_empty(self, status: int, *, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Connection", "close")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        _record_response(urlparse(self.path).path, status, 0)
        self.close_connection = True

    def _read_body_bytes(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _read_json_body(self) -> dict:
        body = self._read_body_bytes()
        if not body:
            return {}
        try:
            parsed = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", os.environ.get("API_CORS_ORIGIN", "*"))
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Circle-Signature, X-Circle-Key-Id, X-Telegram-Bot-Api-Secret-Token")
        self.end_headers()

    def do_HEAD(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/circle/webhook":
            self._send_empty(200)
            return
        self._send_empty(404)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            self._send_json(200, {
                "ok": True,
                "mode": {
                    "live_chain_enabled": state.bool_env("ENABLE_LIVE_CHAIN", False),
                    "telegram_enabled": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
                },
                "runtime": state.runtime_status(),
                "api": _api_metrics(),
            })
            return
        if path == "/api/snapshot":
            if _rate_limited(
                path,
                limit=int(_float_env("API_RATE_LIMIT_SNAPSHOT_PER_10S", 80.0)),
                window_seconds=10.0,
            ):
                self._send_json(429, {"ok": False, "error": "rate_limited", "retry_after": 10}, headers={"Retry-After": "10"})
                return
            self._send_snapshot()
            return
        if path == "/api/verdicts":
            self._send_json(200, state.verdict_state())
            return
        if path == "/api/positions":
            self._send_json(200, state.position_state())
            return
        if path == "/api/signals":
            self._send_json(200, state.signal_state())
            return
        if path == "/api/scan-requests":
            self._send_json(200, list(scan_requests.requests_by_id().values()))
            return
        if path == "/api/account":
            if _rate_limited(
                path,
                limit=int(_float_env("API_RATE_LIMIT_ACCOUNT_PER_10S", 30.0)),
                window_seconds=10.0,
            ):
                self._send_json(429, {"ok": False, "error": "rate_limited", "retry_after": 10}, headers={"Retry-After": "10"})
                return
            self._send_json(200, {
                "ok": True,
                "account": accounts.account_from_cookie(self.headers.get("Cookie")),
                "mode": accounts.account_mode(),
            })
            return
        if path == "/api/account/portfolio":
            if _rate_limited(
                path,
                limit=int(_float_env("API_RATE_LIMIT_ACCOUNT_PER_10S", 30.0)),
                window_seconds=10.0,
            ):
                self._send_json(429, {"ok": False, "error": "rate_limited", "retry_after": 10}, headers={"Retry-After": "10"})
                return
            account = accounts.account_from_cookie(self.headers.get("Cookie"))
            if not account:
                self._send_json(200, user_portfolio.portfolio_state(account, snapshot_data={"synthetic_instrument": {"outputs": {}}}))
                return
            self._send_json(200, user_portfolio.portfolio_state(account, snapshot_data=state.compact_snapshot()))
            return
        self._serve_static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/telegram/webhook":
            self._handle_telegram_webhook()
            return
        if path == "/api/circle/webhook":
            self._handle_circle_webhook()
            return
        if path == "/api/account/operator/demo-payment":
            self._handle_demo_operator_payment()
            return
        if path == "/api/account/logout":
            self._send_json(
                200,
                {"ok": True, "account": None},
                headers={"Set-Cookie": accounts.clear_session_cookie_header()},
            )
            return
        if path == "/api/account/portfolio/open":
            self._handle_portfolio_open()
            return
        if path == "/api/account/portfolio/close":
            self._handle_portfolio_close()
            return
        if path not in {"/api/scans", "/api/scans/live"}:
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        payload = self._read_json_body()
        live = path == "/api/scans/live"
        if live and not state.bool_env("ENABLE_LIVE_CHAIN", False):
            self._send_json(403, {"ok": False, "error": "live_chain_disabled"})
            return
        request = scan_requests.enqueue_scan(
            source="api",
            live=live,
            force_signal=payload.get("force_signal"),
            max_positions=int(payload.get("max_positions") or 1),
            multi_surface=bool(payload.get("multi_surface", True)),
            settle=bool(payload.get("settle", False)),
        )
        self._send_json(202, {"ok": True, "request": request})

    def _handle_telegram_webhook(self) -> None:
        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
        if secret and self.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
            self._send_json(403, {"ok": False, "error": "invalid_telegram_secret"})
            return
        payload = self._read_json_body()
        try:
            from integrations.telegram_bot import process_update
            process_update(payload)
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": str(exc)})
            return
        self._send_json(200, {"ok": True})

    def _handle_demo_operator_payment(self) -> None:
        if not state.bool_env("ALLOW_DEMO_OPERATOR_PAYMENT", True):
            self._send_json(403, {"ok": False, "error": "demo_payments_disabled"})
            return
        payload = self._read_json_body()
        try:
            account = accounts.create_operator_account(
                wallet_address=str(payload.get("wallet_address") or payload.get("walletAddress") or ""),
                tx_hash=str(payload.get("tx_hash") or payload.get("txHash") or ""),
                source="circle_testnet_demo",
                verified=True,
            )
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
            return
        self._send_json(
            200,
            {"ok": True, "account": account, "mode": accounts.account_mode()},
            headers={"Set-Cookie": accounts.session_cookie_header(account["id"])},
        )

    def _handle_portfolio_open(self) -> None:
        account = accounts.account_from_cookie(self.headers.get("Cookie"))
        if not account:
            self._send_json(401, {"ok": False, "error": "account_required"})
            return
        payload = self._read_json_body()
        try:
            result = user_portfolio.open_position(
                account,
                instrument_id=str(payload.get("instrument_id") or payload.get("instrumentId") or ""),
                notional_usdc=payload.get("notional_usdc") or payload.get("notionalUsdc"),
            )
        except PermissionError as exc:
            self._send_json(401, {"ok": False, "error": str(exc)})
            return
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
            return
        self._send_json(200, result)

    def _handle_portfolio_close(self) -> None:
        account = accounts.account_from_cookie(self.headers.get("Cookie"))
        if not account:
            self._send_json(401, {"ok": False, "error": "account_required"})
            return
        payload = self._read_json_body()
        try:
            result = user_portfolio.close_position(
                account,
                position_id=str(payload.get("position_id") or payload.get("positionId") or ""),
            )
        except PermissionError as exc:
            self._send_json(401, {"ok": False, "error": str(exc)})
            return
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
            return
        self._send_json(200, result)

    def _handle_circle_webhook(self) -> None:
        raw_body = self._read_body_bytes()
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "invalid_json"})
            return
        if not isinstance(payload, dict):
            self._send_json(400, {"ok": False, "error": "invalid_payload"})
            return
        try:
            result = accounts.handle_circle_webhook(
                payload,
                raw_body=raw_body,
                signature=self.headers.get("X-Circle-Signature"),
                key_id=self.headers.get("X-Circle-Key-Id"),
            )
        except RuntimeError as exc:
            self._send_json(503, {"ok": False, "error": str(exc)})
            return
        if not result.get("ok"):
            self._send_json(403, result)
            return
        self._send_json(200, result)

    def _serve_static(self, url_path: str) -> None:
        root = state.frontend_dir().resolve()
        if url_path in {"", "/", "/dashboard", "/telegram", "/tg", "/account"}:
            target = root / "Arc Compute Sec.html"
        else:
            rel = unquote(url_path.lstrip("/"))
            target = (root / rel).resolve()
            if root not in target.parents and target != root:
                self._send_json(403, {"ok": False, "error": "forbidden"})
                return
        if not target.exists() or not target.is_file():
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if target.suffix in {".html", ".jsx"} else "public, max-age=60")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass
        _record_response(url_path, 200, len(body))
        self.close_connection = True


class ArcThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False


def make_server(host: str = "0.0.0.0", port: int = 8080) -> ThreadingHTTPServer:
    return ArcThreadingHTTPServer((host, port), ApiHandler)


def main() -> int:
    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT") or os.environ.get("API_PORT") or "8080")
    httpd = make_server(host, port)
    threading.Thread(target=state.warm_compact_snapshot_cache, daemon=True).start()
    print(f"[api] serving http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
