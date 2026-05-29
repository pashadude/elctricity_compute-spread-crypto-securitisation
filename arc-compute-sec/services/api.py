"""Small stdlib HTTP API for the local operator dashboard."""
from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from services import accounts, scan_requests, state, user_portfolio


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "ArcComputeSecAPI/0.1"

    def log_message(self, fmt: str, *args) -> None:
        if state.bool_env("API_ACCESS_LOG", False):
            super().log_message(fmt, *args)

    def _send_json(self, status: int, payload: dict | list, *, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", os.environ.get("API_CORS_ORIGIN", "*"))
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status: int, *, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()

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
                "mode": state.snapshot()["mode"],
                "runtime": state.runtime_status(),
            })
            return
        if path == "/api/snapshot":
            self._send_json(200, state.snapshot())
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
            self._send_json(200, {
                "ok": True,
                "account": accounts.account_from_cookie(self.headers.get("Cookie")),
                "mode": accounts.account_mode(),
            })
            return
        if path == "/api/account/portfolio":
            account = accounts.account_from_cookie(self.headers.get("Cookie"))
            self._send_json(200, user_portfolio.portfolio_state(account))
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
        self.end_headers()
        self.wfile.write(body)


def make_server(host: str = "0.0.0.0", port: int = 8080) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), ApiHandler)


def main() -> int:
    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT") or os.environ.get("API_PORT") or "8080")
    httpd = make_server(host, port)
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
