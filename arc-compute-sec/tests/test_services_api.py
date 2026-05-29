import json
from io import BytesIO

from services.api import ApiHandler


class _FakeSocket:
    def __init__(self, request: bytes):
        self._request = BytesIO(request)
        self.response = BytesIO()

    def makefile(self, mode, *args, **kwargs):
        if "r" in mode:
            return self._request
        return self.response

    def sendall(self, data):
        self.response.write(data)

    def close(self):
        pass


class _FakeServer:
    server_name = "test"
    server_port = 0


def _request(method, path, *, body=b"", headers=None, return_headers=False):
    headers = headers or {}
    if body and "Content-Length" not in headers:
        headers["Content-Length"] = str(len(body))
    raw = f"{method} {path} HTTP/1.1\r\nHost: test\r\n".encode()
    for key, value in headers.items():
        raw += f"{key}: {value}\r\n".encode()
    raw += b"\r\n" + body
    sock = _FakeSocket(raw)
    ApiHandler(sock, ("127.0.0.1", 0), _FakeServer())
    response = sock.response.getvalue()
    head, _, payload = response.partition(b"\r\n\r\n")
    status = int(head.split()[1])
    response_headers = {}
    for line in head.decode().split("\r\n")[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        response_headers[key.lower()] = value.strip()
    if return_headers:
        return status, payload, response_headers
    return status, payload


def _serve(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "Arc Compute Sec.html").write_text("<html>ok</html>")
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("FRONTEND_DIR", str(frontend))


def test_api_serves_health_snapshot_and_frontend(tmp_path, monkeypatch):
    _serve(tmp_path, monkeypatch)

    health_status, health_body = _request("GET", "/api/health")
    snap_status, snap_body = _request("GET", "/api/snapshot")
    html_status, html_body = _request("GET", "/")
    account_status, account_body = _request("GET", "/account")
    health = json.loads(health_body)
    snap = json.loads(snap_body)
    html = html_body.decode()
    account_html = account_body.decode()

    assert health_status == 200
    assert snap_status == 200
    assert html_status == 200
    assert account_status == 200
    assert health["ok"] is True
    assert snap["ok"] is True
    assert html == "<html>ok</html>"
    assert account_html == "<html>ok</html>"


def test_api_enqueues_dry_run_scan_and_blocks_live_when_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("ENABLE_LIVE_CHAIN", raising=False)
    _serve(tmp_path, monkeypatch)

    status, payload = _request(
        "POST",
        "/api/scans",
        body=json.dumps({"force_signal": -2}).encode(),
        headers={"Content-Type": "application/json"},
    )
    live_status, _ = _request("POST", "/api/scans/live", body=b"{}")
    body = json.loads(payload)

    assert status == 202
    assert body["ok"] is True
    assert body["request"]["live"] is False
    assert live_status == 403


def test_api_account_demo_payment_sets_server_session(tmp_path, monkeypatch):
    _serve(tmp_path, monkeypatch)
    monkeypatch.setenv("ACCOUNT_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ALLOW_DEMO_OPERATOR_PAYMENT", "1")

    empty_status, empty_payload = _request("GET", "/api/account")
    pay_status, pay_payload, pay_headers = _request(
        "POST",
        "/api/account/operator/demo-payment",
        body=json.dumps({
            "wallet_address": "0x7a3B4C6D8E9F1029384756aBcDEF1234567890aB",
            "tx_hash": "0xabc",
        }).encode(),
        headers={"Content-Type": "application/json"},
        return_headers=True,
    )
    cookie = pay_headers["set-cookie"].split(";", 1)[0]
    session_status, session_payload = _request("GET", "/api/account", headers={"Cookie": cookie})
    logout_status, logout_payload, logout_headers = _request(
        "POST",
        "/api/account/logout",
        body=b"{}",
        headers={"Content-Type": "application/json", "Cookie": cookie},
        return_headers=True,
    )

    assert empty_status == 200
    assert json.loads(empty_payload)["account"] is None
    assert pay_status == 200
    assert json.loads(pay_payload)["account"]["status"] == "active"
    assert "httponly" in pay_headers["set-cookie"].lower()
    assert session_status == 200
    assert json.loads(session_payload)["account"]["payment"]["amountUsdc"] == "5"
    assert logout_status == 200
    assert json.loads(logout_payload)["account"] is None
    assert "Max-Age=0" in logout_headers["set-cookie"]


def test_api_account_portfolio_opens_and_closes_server_position(tmp_path, monkeypatch):
    _serve(tmp_path, monkeypatch)
    monkeypatch.setenv("ACCOUNT_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ALLOW_DEMO_OPERATOR_PAYMENT", "1")

    fake_snapshot = {
        "synthetic_instrument": {
            "outputs": {
                "syndicated_instrument_menu": [{
                    "instrument_type": "compute_receivable_hedge_note",
                    "basket_id": "miner_margin_power_pair",
                    "title": "ERCOT compute receivable hedge note",
                    "spread_archetype": "fuel_stack_compute_spread",
                    "payoff": "Long power exposure and short miner-margin beta.",
                    "collateral_needed": ["compute sale invoice"],
                    "direct_leg_target": "long energy/grid stress vs short compute demand",
                    "latest_signal": "BUY",
                    "status": "PAPER_BUY_ONLY",
                    "collateral_status": "not_asset_backed_v0",
                    "circle_testnet_ask_usdc": 1560,
                    "priced_symbols": ["BTC-USD", "NRG"],
                    "replay_status": "PROMOTABLE",
                    "win_rate": 62,
                    "max_drawdown_pct": -4.2,
                    "arc_gate": "LOCKED_UNTIL_JUDGE_EXECUTE",
                }]
            }
        },
        "profitability_ledger": {
            "rows": [{
                "archetype_id": "fuel_stack_compute_spread",
                "basket_id": "miner_margin_power_pair",
                "latest_signal": "BUY",
                "profitability_status": "PAPER_BUY",
                "paper_total_return_pct": 4,
                "recent_paper_marks": [
                    {"index_close": 100},
                    {"index_close": 104},
                ],
                "supports_fresh_buy": True,
            }]
        },
        "public_hedges": [
            {"instrument": "BTC-USD", "last_price": 100000, "source": "yahoo"},
            {"instrument": "NRG", "last_price": 80, "source": "yahoo"},
        ],
        "direct_inventory": [],
    }
    from services import user_portfolio
    monkeypatch.setattr(user_portfolio.state, "snapshot", lambda **_kwargs: fake_snapshot)

    no_session_status, no_session_body = _request("GET", "/api/account/portfolio")
    pay_status, _pay_payload, pay_headers = _request(
        "POST",
        "/api/account/operator/demo-payment",
        body=json.dumps({
            "wallet_address": "0x7a3B4C6D8E9F1029384756aBcDEF1234567890aB",
            "tx_hash": "0xabc",
        }).encode(),
        headers={"Content-Type": "application/json"},
        return_headers=True,
    )
    cookie = pay_headers["set-cookie"].split(";", 1)[0]
    portfolio_status, portfolio_body = _request("GET", "/api/account/portfolio", headers={"Cookie": cookie})
    instrument_id = json.loads(portfolio_body)["instruments"][0]["id"]
    open_status, open_body = _request(
        "POST",
        "/api/account/portfolio/open",
        body=json.dumps({"instrument_id": instrument_id, "notional_usdc": 500}).encode(),
        headers={"Content-Type": "application/json", "Cookie": cookie},
    )
    opened = json.loads(open_body)
    close_status, close_body = _request(
        "POST",
        "/api/account/portfolio/close",
        body=json.dumps({"position_id": opened["positions"][0]["positionId"]}).encode(),
        headers={"Content-Type": "application/json", "Cookie": cookie},
    )
    closed = json.loads(close_body)

    assert no_session_status == 200
    assert json.loads(no_session_body)["account_required"] is True
    assert pay_status == 200
    assert portfolio_status == 200
    assert open_status == 200
    assert opened["positions"][0]["notionalUsdc"] == 500
    assert opened["positions"][0]["entryMark"] == 1.04
    assert opened["summary"]["openCount"] == 1
    assert close_status == 200
    assert closed["summary"]["openCount"] == 0
    assert closed["summary"]["realizedCount"] == 1


def test_api_account_demo_payment_can_be_disabled(tmp_path, monkeypatch):
    _serve(tmp_path, monkeypatch)
    monkeypatch.setenv("ALLOW_DEMO_OPERATOR_PAYMENT", "0")

    status, payload = _request(
        "POST",
        "/api/account/operator/demo-payment",
        body=json.dumps({
            "wallet_address": "0x7a3B4C6D8E9F1029384756aBcDEF1234567890aB",
            "tx_hash": "0xabc",
        }).encode(),
        headers={"Content-Type": "application/json"},
    )

    assert status == 403
    assert json.loads(payload)["error"] == "demo_payments_disabled"


def test_api_circle_webhook_can_activate_operator_account(tmp_path, monkeypatch):
    _serve(tmp_path, monkeypatch)
    monkeypatch.setenv("CIRCLE_WEBHOOK_REQUIRE_SIGNATURE", "0")
    payload = {
        "notificationId": "notif-api-1",
        "notificationType": "transactions.inbound",
        "notification": {
            "status": "COMPLETE",
            "txHash": "0xfeed",
            "destinationAddress": "0x7a3B4C6D8E9F1029384756aBcDEF1234567890aB",
            "amount": "5",
        },
        "version": 2,
    }

    status, body = _request(
        "POST",
        "/api/circle/webhook",
        body=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    result = json.loads(body)

    assert status == 200
    assert result["status"] == "account_activated"
    assert result["account"]["payment"]["source"] == "circle_webhook"


def test_api_circle_webhook_head_check(tmp_path, monkeypatch):
    _serve(tmp_path, monkeypatch)

    status, body = _request("HEAD", "/api/circle/webhook")

    assert status == 200
    assert body == b""


def test_telegram_webhook_requires_secret_and_processes_update(tmp_path, monkeypatch):
    _serve(tmp_path, monkeypatch)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "secret")
    calls = []

    def fake_process_update(payload):
        calls.append(payload)

    import integrations.telegram_bot as telegram_bot
    monkeypatch.setattr(telegram_bot, "process_update", fake_process_update)

    bad_status, _ = _request(
        "POST",
        "/api/telegram/webhook",
        body=json.dumps({"update_id": 1}).encode(),
        headers={"Content-Type": "application/json"},
    )
    ok_status, ok_payload = _request(
        "POST",
        "/api/telegram/webhook",
        body=json.dumps({"update_id": 2}).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Telegram-Bot-Api-Secret-Token": "secret",
        },
    )

    assert bad_status == 403
    assert ok_status == 200
    assert json.loads(ok_payload)["ok"] is True
    assert calls == [{"update_id": 2}]
