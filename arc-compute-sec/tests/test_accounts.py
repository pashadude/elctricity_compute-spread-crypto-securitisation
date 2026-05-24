import json
import base64

from services import accounts


def _signed_circle_payload(payload: dict):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    raw_body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    signature = private_key.sign(raw_body, ec.ECDSA(hashes.SHA256()))
    return raw_body, base64.b64encode(signature).decode(), base64.b64encode(public_der).decode()


def test_session_cookie_roundtrip(monkeypatch):
    monkeypatch.setenv("ACCOUNT_SESSION_SECRET", "test-secret")
    token = accounts.make_session_token("op_123", now=1000)

    assert accounts.verify_session_token(token, now=1001) == "op_123"
    assert accounts.verify_session_token(token + "x", now=1001) is None


def test_session_cookie_rejects_expired_token(monkeypatch):
    monkeypatch.setenv("ACCOUNT_SESSION_SECRET", "test-secret")
    token = accounts.make_session_token("op_123", now=1000)

    assert accounts.verify_session_token(token, now=1000 + accounts.SESSION_TTL_SECONDS + 1) is None


def test_operator_account_persists_and_cookie_restores(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("ACCOUNT_SESSION_SECRET", "test-secret")

    account = accounts.create_operator_account(
        wallet_address="0x7a3B4C6D8E9F1029384756aBcDEF1234567890aB",
        tx_hash="0xabc",
    )
    cookie = accounts.session_cookie_header(account["id"])
    restored = accounts.account_from_cookie(cookie)

    assert account["status"] == "active"
    assert restored["id"] == account["id"]
    assert restored["payment"]["amountUsdc"] == "5"
    assert "accounts.json" in {p.name for p in tmp_path.iterdir()}


def test_circle_webhook_can_activate_account_when_signature_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("CIRCLE_WEBHOOK_REQUIRE_SIGNATURE", "0")
    payload = {
        "subscriptionId": "sub",
        "notificationId": "notif-1",
        "notificationType": "transactions.inbound",
        "notification": {
            "status": "COMPLETE",
            "txHash": "0xfeed",
            "destinationAddress": "0x7a3B4C6D8E9F1029384756aBcDEF1234567890aB",
            "amount": "5",
        },
        "version": 2,
    }

    result = accounts.handle_circle_webhook(
        payload,
        raw_body=json.dumps(payload).encode(),
        signature=None,
        key_id=None,
    )

    assert result["ok"] is True
    assert result["status"] == "account_activated"
    assert result["account"]["payment"]["source"] == "circle_webhook"


def test_circle_webhook_rejects_underpayment_when_signature_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("CIRCLE_WEBHOOK_REQUIRE_SIGNATURE", "0")
    payload = {
        "notificationId": "notif-2",
        "notificationType": "transactions.inbound",
        "notification": {
            "status": "COMPLETE",
            "txHash": "0xfeed",
            "destinationAddress": "0x7a3B4C6D8E9F1029384756aBcDEF1234567890aB",
            "amount": "4.99",
        },
        "version": 2,
    }

    result = accounts.handle_circle_webhook(
        payload,
        raw_body=json.dumps(payload).encode(),
        signature=None,
        key_id=None,
    )

    assert result["ok"] is False
    assert result["error"] == "insufficient_payment_amount"


def test_circle_webhook_accepts_valid_signature(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("CIRCLE_WEBHOOK_REQUIRE_SIGNATURE", "1")
    payload = {
        "notificationId": "notif-signed-1",
        "notificationType": "transactions.inbound",
        "notification": {
            "status": "COMPLETE",
            "txHash": "0xsigned",
            "destinationAddress": "0x7a3B4C6D8E9F1029384756aBcDEF1234567890aB",
            "amount": "5",
        },
        "version": 2,
    }
    raw_body, signature, public_key = _signed_circle_payload(payload)
    monkeypatch.setattr(
        accounts,
        "_circle_public_key",
        lambda key_id: {"algorithm": "ECDSA_SHA_256", "publicKey": public_key},
    )

    result = accounts.handle_circle_webhook(
        payload,
        raw_body=raw_body,
        signature=signature,
        key_id="circle-key-1",
    )

    assert result["ok"] is True
    assert result["status"] == "account_activated"
    assert result["account"]["payment"]["source"] == "circle_webhook"


def test_circle_webhook_rejects_invalid_signature(tmp_path, monkeypatch):
    monkeypatch.setenv("ARC_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("CIRCLE_WEBHOOK_REQUIRE_SIGNATURE", "1")
    payload = {
        "notificationId": "notif-signed-2",
        "notificationType": "transactions.inbound",
        "notification": {
            "status": "COMPLETE",
            "txHash": "0xsigned",
            "destinationAddress": "0x7a3B4C6D8E9F1029384756aBcDEF1234567890aB",
            "amount": "5",
        },
        "version": 2,
    }
    raw_body, signature, public_key = _signed_circle_payload(payload)
    tampered = raw_body.replace(b"0xsigned", b"0xtamper")
    monkeypatch.setattr(
        accounts,
        "_circle_public_key",
        lambda key_id: {"algorithm": "ECDSA_SHA_256", "publicKey": public_key},
    )

    result = accounts.handle_circle_webhook(
        payload,
        raw_body=tampered,
        signature=signature,
        key_id="circle-key-1",
    )

    assert result == {"ok": False, "error": "invalid_circle_signature"}
