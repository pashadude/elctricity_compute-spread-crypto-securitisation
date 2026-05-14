"""Agent package init.

One-shot environment fixup: macOS python.org Python 3.12 ships with an
empty default OpenSSL trust store at /Library/Frameworks/.../etc/openssl/,
which causes `urllib3`-based SDKs (including the Circle Developer-Controlled
Wallets SDK) to fail with `CERTIFICATE_VERIFY_FAILED: unable to get local
issuer certificate`. `requests` works because it ships with `certifi` by
default; `urllib3` directly does not.

The fix is to point `SSL_CERT_FILE` at the certifi bundle the venv already
has. We use `setdefault` so an operator-set value (e.g., corporate CA
bundle) wins.

This module is imported the moment any `agent.*` submodule is loaded, so
the env var is set before the Circle SDK or web3.py reach for SSL. No
runtime cost beyond one stat + one os.environ write at import.
"""
from __future__ import annotations

import os


def _ensure_ssl_cert_file() -> None:
    if os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi
    except ImportError:
        return
    bundle = certifi.where()
    if bundle and os.path.exists(bundle):
        os.environ.setdefault("SSL_CERT_FILE", bundle)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", bundle)


_ensure_ssl_cert_file()
