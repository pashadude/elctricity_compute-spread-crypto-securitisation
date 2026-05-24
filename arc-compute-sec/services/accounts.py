"""Server-owned Operator account and payment state.

The browser may display account data, but paid access is granted only from this
module. Accounts are persisted under ARC_LOG_DIR so Docker volumes keep state
across API restarts without committing any user data.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from services import state


SESSION_COOKIE = "botozen_session"
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
OPERATOR_USDC = Decimal("5")
ACCOUNT_VERSION = 1
_LOCK = threading.RLock()
_CIRCLE_KEY_CACHE: dict[str, dict[str, str]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _store_path(logs: Path | str | None = None) -> Path:
    explicit = os.environ.get("ACCOUNT_STORE_PATH")
    if explicit:
        return Path(explicit)
    return state.log_dir(logs) / "accounts.json"


def _empty_store() -> dict[str, Any]:
    return {"version": ACCOUNT_VERSION, "accounts": {}, "payments": {}, "webhooks": {}}


def _read_store(logs: Path | str | None = None) -> dict[str, Any]:
    path = _store_path(logs)
    if not path.exists():
        return _empty_store()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()
    data.setdefault("version", ACCOUNT_VERSION)
    data.setdefault("accounts", {})
    data.setdefault("payments", {})
    data.setdefault("webhooks", {})
    return data


def _write_store(data: dict[str, Any], logs: Path | str | None = None) -> None:
    path = _store_path(logs)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, indent=2, sort_keys=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".accounts.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
            fh.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _account_id(wallet_address: str) -> str:
    digest = hashlib.sha256(wallet_address.lower().encode("utf-8")).hexdigest()[:14]
    return f"op_{digest}"


def _payment_id(source: str, tx_hash: str | None, notification_id: str | None = None) -> str:
    raw = notification_id or tx_hash or f"{source}:{secrets.token_hex(12)}"
    digest = hashlib.sha256(str(raw).encode("utf-8")).hexdigest()[:16]
    return f"pay_{digest}"


def _normalize_wallet(wallet_address: str | None) -> str:
    wallet = str(wallet_address or "").strip()
    if not wallet:
        raise ValueError("wallet_address_required")
    if not wallet.startswith("0x") or len(wallet) < 10:
        raise ValueError("invalid_wallet_address")
    return wallet


def _normalize_tx_hash(tx_hash: str | None) -> str:
    tx = str(tx_hash or "").strip()
    return tx or f"demo-{secrets.token_hex(12)}"


def _public_account(account: dict[str, Any] | None) -> dict[str, Any] | None:
    if not account:
        return None
    allowed = {
        "id",
        "status",
        "planId",
        "planName",
        "priceUsd",
        "testUsdc",
        "network",
        "walletAddress",
        "txHash",
        "createdAt",
        "updatedAt",
        "renewsAt",
        "entitlements",
        "payment",
    }
    return {k: v for k, v in account.items() if k in allowed}


def account_mode() -> dict[str, Any]:
    return {
        "session_cookie": SESSION_COOKIE,
        "session_secret_configured": bool(os.environ.get("ACCOUNT_SESSION_SECRET", "").strip()),
        "secure_cookie": _cookie_secure(),
        "demo_payments_enabled": state.bool_env("ALLOW_DEMO_OPERATOR_PAYMENT", True),
        "circle_webhook_signature_required": state.bool_env("CIRCLE_WEBHOOK_REQUIRE_SIGNATURE", True),
        "circle_webhook_endpoint": "/api/circle/webhook",
    }


def _secret() -> bytes:
    configured = os.environ.get("ACCOUNT_SESSION_SECRET", "").strip()
    if configured:
        return hashlib.sha256(configured.encode("utf-8")).digest()
    # Development fallback only. Production readiness is exposed in account_mode.
    return hashlib.sha256(f"dev-only:{state.PROJECT_ROOT}".encode("utf-8")).digest()


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def make_session_token(account_id: str, *, now: float | None = None) -> str:
    issued = int(now or time.time())
    payload = {"account_id": account_id, "iat": issued, "exp": issued + SESSION_TTL_SECONDS}
    encoded = _b64e(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64e(sig)}"


def verify_session_token(token: str, *, now: float | None = None) -> str | None:
    try:
        encoded, supplied_sig = token.split(".", 1)
        expected = _b64e(hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied_sig, expected):
            return None
        payload = json.loads(_b64d(encoded).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if int(payload.get("exp") or 0) < int(now or time.time()):
        return None
    account_id = str(payload.get("account_id") or "")
    return account_id or None


def _cookie_secure() -> bool:
    if os.environ.get("ACCOUNT_COOKIE_SECURE") is not None:
        return state.bool_env("ACCOUNT_COOKIE_SECURE", False)
    base = os.environ.get("PUBLIC_BASE_URL", "").strip().lower()
    return base.startswith("https://") and "localhost" not in base and "127.0.0.1" not in base


def session_cookie_header(account_id: str) -> str:
    parts = [
        f"{SESSION_COOKIE}={make_session_token(account_id)}",
        "Path=/",
        f"Max-Age={SESSION_TTL_SECONDS}",
        "HttpOnly",
        "SameSite=Lax",
    ]
    if _cookie_secure():
        parts.append("Secure")
    return "; ".join(parts)


def clear_session_cookie_header() -> str:
    parts = [f"{SESSION_COOKIE}=", "Path=/", "Max-Age=0", "HttpOnly", "SameSite=Lax"]
    if _cookie_secure():
        parts.append("Secure")
    return "; ".join(parts)


def _cookies(raw: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in str(raw or "").split(";"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def account_from_cookie(cookie_header: str | None, *, logs: Path | str | None = None) -> dict[str, Any] | None:
    token = _cookies(cookie_header).get(SESSION_COOKIE)
    if not token:
        return None
    account_id = verify_session_token(token)
    if not account_id:
        return None
    with _LOCK:
        account = _read_store(logs).get("accounts", {}).get(account_id)
    return _public_account(account)


def get_account(account_id: str, *, logs: Path | str | None = None) -> dict[str, Any] | None:
    with _LOCK:
        account = _read_store(logs).get("accounts", {}).get(account_id)
    return _public_account(account)


def create_operator_account(
    *,
    wallet_address: str,
    tx_hash: str | None = None,
    source: str = "circle_testnet_demo",
    verified: bool = True,
    notification_id: str | None = None,
    event: dict[str, Any] | None = None,
    logs: Path | str | None = None,
) -> dict[str, Any]:
    wallet = _normalize_wallet(wallet_address)
    tx = _normalize_tx_hash(tx_hash)
    now = _now()
    account_id = _account_id(wallet)
    payment_id = _payment_id(source, tx, notification_id)
    status = "active" if verified else "pending_payment"
    payment = {
        "id": payment_id,
        "provider": "circle",
        "source": source,
        "status": "verified" if verified else "pending",
        "amountUsdc": str(OPERATOR_USDC),
        "txHash": tx,
        "notificationId": notification_id or "",
        "verifiedAt": _iso(now) if verified else "",
    }
    with _LOCK:
        data = _read_store(logs)
        existing = data["accounts"].get(account_id, {})
        created_at = existing.get("createdAt") or _iso(now)
        account = {
            **existing,
            "id": account_id,
            "status": status,
            "planId": "operator",
            "planName": "Operator",
            "priceUsd": "5",
            "testUsdc": str(OPERATOR_USDC),
            "network": "Arc Testnet",
            "walletAddress": wallet,
            "txHash": tx,
            "createdAt": created_at,
            "updatedAt": _iso(now),
            "renewsAt": _iso(now + timedelta(days=30)),
            "entitlements": [
                "package_dashboard",
                "actionable_alerts",
                "telegram_scan_commands",
                "oracle_backtest_view",
                "arc_testnet_wrap_controls",
            ],
            "payment": payment,
        }
        data["accounts"][account_id] = account
        data["payments"][payment_id] = {
            **payment,
            "accountId": account_id,
            "event": event or {},
        }
        _write_store(data, logs)
    return _public_account(account) or {}


def _walk_values(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for child in value.values():
            values.extend(_walk_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_walk_values(child))
    return values


def _find_key(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in keys and child not in (None, "", []):
                return child
        for child in value.values():
            found = _find_key(child, keys)
            if found not in (None, "", []):
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_key(child, keys)
            if found not in (None, "", []):
                return found
    return None


def _decimal_from_any(value: Any) -> Decimal | None:
    if isinstance(value, list):
        for item in value:
            parsed = _decimal_from_any(item)
            if parsed is not None:
                return parsed
        return None
    if isinstance(value, dict):
        for key in ("amount", "value", "amountUsd", "amountUSDC"):
            if key in value:
                parsed = _decimal_from_any(value[key])
                if parsed is not None:
                    return parsed
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _extract_circle_payment(payload: dict[str, Any]) -> dict[str, Any]:
    notification = payload.get("notification") if isinstance(payload.get("notification"), dict) else {}
    tx_hash = _find_key(notification, {"txhash", "transactionhash", "blockchaintxhash", "hash"})
    wallet = _find_key(notification, {"walletaddress", "destinationaddress", "toaddress", "address"})
    amount = _decimal_from_any(_find_key(notification, {"amount", "amounts", "amountusdc"}))
    status = str(_find_key(notification, {"state", "status"}) or "").lower()
    return {
        "notification": notification,
        "notification_id": str(payload.get("notificationId") or ""),
        "type": str(payload.get("notificationType") or ""),
        "tx_hash": str(tx_hash or ""),
        "wallet_address": str(wallet or ""),
        "amount": amount,
        "status": status,
    }


def _circle_public_key(key_id: str) -> dict[str, str]:
    if key_id in _CIRCLE_KEY_CACHE:
        return _CIRCLE_KEY_CACHE[key_id]
    api_key = os.environ.get("CIRCLE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("circle_api_key_required")
    template = os.environ.get(
        "CIRCLE_WEBHOOK_PUBLIC_KEY_URL_TEMPLATE",
        "https://api.circle.com/v2/notifications/publicKey/{key_id}",
    )
    url = template.replace("{keyId}", key_id).format(key_id=key_id)
    req = urllib.request.Request(
        url,
        headers={"accept": "application/json", "authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"circle_public_key_fetch_failed: {exc}") from exc
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict) or not data.get("publicKey"):
        raise RuntimeError("circle_public_key_missing")
    out = {"algorithm": str(data.get("algorithm") or ""), "publicKey": str(data["publicKey"])}
    _CIRCLE_KEY_CACHE[key_id] = out
    return out


def verify_circle_signature(raw_body: bytes, signature: str | None, key_id: str | None) -> bool:
    if not state.bool_env("CIRCLE_WEBHOOK_REQUIRE_SIGNATURE", True):
        return True
    if not signature or not key_id:
        return False
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError as exc:
        raise RuntimeError("cryptography_required_for_circle_webhooks") from exc
    key_data = _circle_public_key(key_id)
    if key_data.get("algorithm") and key_data["algorithm"] != "ECDSA_SHA_256":
        raise RuntimeError(f"unsupported_circle_signature_algorithm:{key_data['algorithm']}")
    public_key = serialization.load_der_public_key(base64.b64decode(key_data["publicKey"]))
    try:
        public_key.verify(base64.b64decode(signature), raw_body, ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError):
        return False
    return True


def handle_circle_webhook(
    payload: dict[str, Any],
    *,
    raw_body: bytes,
    signature: str | None,
    key_id: str | None,
    logs: Path | str | None = None,
) -> dict[str, Any]:
    if not verify_circle_signature(raw_body, signature, key_id):
        return {"ok": False, "error": "invalid_circle_signature"}
    notification_id = str(payload.get("notificationId") or "")
    notification_type = str(payload.get("notificationType") or "")
    if notification_type == "webhooks.test":
        return {"ok": True, "status": "verified_test"}
    if not notification_type.startswith("transactions."):
        return {"ok": True, "status": "ignored", "notification_type": notification_type}

    extracted = _extract_circle_payment(payload)
    status = extracted["status"]
    if status and status not in {"complete", "completed", "confirmed"}:
        return {"ok": True, "status": "payment_not_complete", "payment_status": status}
    amount = extracted["amount"]
    if amount is not None and amount < OPERATOR_USDC:
        return {"ok": False, "error": "insufficient_payment_amount", "amount": str(amount)}
    wallet = extracted["wallet_address"]
    if not wallet:
        return {"ok": True, "status": "no_wallet_match", "notification_id": notification_id}

    account = create_operator_account(
        wallet_address=wallet,
        tx_hash=extracted["tx_hash"],
        source="circle_webhook",
        verified=True,
        notification_id=notification_id,
        event=payload,
        logs=logs,
    )
    with _LOCK:
        data = _read_store(logs)
        data["webhooks"][notification_id or secrets.token_hex(8)] = {
            "type": notification_type,
            "accountId": account["id"],
            "receivedAt": _iso(_now()),
        }
        _write_store(data, logs)
    return {"ok": True, "status": "account_activated", "account": account}
