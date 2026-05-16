"""Python ↔ Arc Testnet glue.

We use the Circle Developer-Controlled-Wallets SDK to SUBMIT contract
calls (it handles entity-secret-protected signing for us), and web3.py
against the Arc HTTP RPC to DECODE event logs from the receipt.

Don't try to parse logs from Circle's tx-status response — it gives you
a transaction state object, not a receipt with logs. The pattern is:
  1. Submit via Circle SDK
  2. Poll Circle for `state == "COMPLETE"` and grab txHash
  3. Use web3.py `eth_getTransactionReceipt` against `ARC_RPC` to fetch
     the receipt and decode logs via the pinned ABIs.

All amounts are USDC base units (6 decimals) — see `contracts.arc_addresses.usdc6`.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from contracts.arc_addresses import (
    AGENTIC_COMMERCE,
    IDENTITY_REGISTRY,
    REPUTATION_REGISTRY,
    RPC_HTTP,
    USDC,
    VALIDATION_REGISTRY,
    CHAIN_NAME,
    usdc6,
)

_ABI_DIR = Path(__file__).resolve().parent.parent / "contracts" / "abis"

POLL_INTERVAL_S = 2.0
POLL_TIMEOUT_S = 180.0


def _load_abi(name: str) -> list:
    with (_ABI_DIR / name).open() as fh:
        return json.load(fh)


@dataclass(frozen=True, slots=True)
class ChainTx:
    circle_tx_id: str
    tx_hash: str
    block_number: int | None
    logs: list[dict]


def _circle_client():
    """Lazy-imported Circle SDK client. Reads `CIRCLE_API_KEY` and
    `CIRCLE_ENTITY_SECRET` from env. If they're missing, raises a clear
    diagnostic — the caller is responsible for checking before invoking.
    """
    key = os.environ.get("CIRCLE_API_KEY")
    secret = os.environ.get("CIRCLE_ENTITY_SECRET")
    if not key or not secret:
        raise RuntimeError(
            "CIRCLE_API_KEY and/or CIRCLE_ENTITY_SECRET missing. Paste your TESTNET "
            "key + entity secret into arc-compute-sec/.env before any chain call."
        )
    from circle.web3 import developer_controlled_wallets, utils
    client = utils.init_developer_controlled_wallets_client(
        api_key=key,
        entity_secret=secret,
    )
    return client, developer_controlled_wallets


def _as_dict(obj: Any) -> dict:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return obj
    return dict(getattr(obj, "__dict__", {}) or {})


def _w3():
    from web3 import Web3
    return Web3(Web3.HTTPProvider(RPC_HTTP, request_kwargs={"timeout": 30}))


def _poll_tx(tx_api, circle_tx_id: str, timeout_s: float = POLL_TIMEOUT_S) -> dict:
    def _tx_payload(resp_data: Any) -> dict:
        data = _as_dict(resp_data)
        tx = data.get("transaction")
        if tx is not None:
            return _as_dict(tx)
        return data

    deadline = time.time() + timeout_s
    last_state = None
    while time.time() < deadline:
        resp = tx_api.get_transaction(id=circle_tx_id)
        data = _tx_payload(resp.data)
        state = data.get("state") or data.get("status")
        last_state = state
        if state == "COMPLETE":
            return data
        if state in {"FAILED", "DENIED", "CANCELLED"}:
            raise RuntimeError(f"Circle tx {circle_tx_id} ended in {state}: {data}")
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError(f"Circle tx {circle_tx_id} did not complete in {timeout_s}s (last state={last_state})")


def _get_receipt(tx_hash: str, timeout_s: float = 60.0) -> dict:
    w3 = _w3()
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = w3.eth.get_transaction_receipt(tx_hash)
            if r is not None:
                return dict(r)
        except Exception:
            pass
        time.sleep(1.5)
    raise TimeoutError(f"Arc RPC did not return a receipt for {tx_hash} in {timeout_s}s")


def _decode_logs(receipt: dict, abi: list, contract_addr: str) -> list[dict]:
    """Decode logs from `contract_addr` only, using the given ABI."""
    from web3 import Web3
    w3 = _w3()
    contract = w3.eth.contract(address=Web3.to_checksum_address(contract_addr), abi=abi)
    decoded: list[dict] = []
    for log in receipt.get("logs", []):
        if (log.get("address") or "").lower() != contract_addr.lower():
            continue
        for ev_abi in [a for a in abi if a.get("type") == "event"]:
            try:
                ev = contract.events[ev_abi["name"]]().process_log(log)
                decoded.append({"event": ev_abi["name"], "args": dict(ev["args"])})
                break
            except Exception:
                continue
    return decoded


def exec_contract(
    wallet_id: str,
    contract_addr: str,
    abi_function_signature: str,
    abi_parameters: list,
    fee_level: str = "MEDIUM",
) -> str:
    """Submit a contract execution via Circle. Returns the Circle tx id.
    Does not wait for finality — caller uses `wait_for_tx` after.
    """
    client, developer_controlled_wallets = _circle_client()
    tx_api = developer_controlled_wallets.TransactionsApi(client)
    req = developer_controlled_wallets.CreateContractExecutionTransactionForDeveloperRequest.from_dict({
        "walletId": wallet_id,
        "contractAddress": contract_addr,
        "abiFunctionSignature": abi_function_signature,
        "abiParameters": abi_parameters,
        "feeLevel": fee_level,
    })
    resp = tx_api.create_developer_transaction_contract_execution(req)
    return resp.data.id


def wait_for_tx(circle_tx_id: str, abi: list, contract_addr: str) -> ChainTx:
    """Poll until Circle says COMPLETE, then fetch the receipt and decode logs."""
    client, developer_controlled_wallets = _circle_client()
    tx_api = developer_controlled_wallets.TransactionsApi(client)
    data = _poll_tx(tx_api, circle_tx_id)
    tx_hash = data.get("txHash") or data.get("transactionHash")
    if not tx_hash:
        raise RuntimeError(f"Circle returned COMPLETE without txHash: {data}")
    receipt = _get_receipt(tx_hash)
    logs = _decode_logs(receipt, abi, contract_addr)
    return ChainTx(
        circle_tx_id=circle_tx_id,
        tx_hash=tx_hash,
        block_number=receipt.get("blockNumber"),
        logs=logs,
    )


# -------------------- High-level wrappers --------------------

_IDENTITY_ABI = _load_abi("identity_registry.json")
_VALIDATION_ABI = _load_abi("validation_registry.json")
_REPUTATION_ABI = _load_abi("reputation_registry.json")
_COMMERCE_ABI = _load_abi("agentic_commerce.json")
_ERC20_ABI = _load_abi("erc20.json")


def register_identity(wallet_id: str, metadata_uri: str) -> ChainTx:
    cid = exec_contract(
        wallet_id=wallet_id,
        contract_addr=IDENTITY_REGISTRY,
        abi_function_signature="register(string)",
        abi_parameters=[metadata_uri],
    )
    return wait_for_tx(cid, _IDENTITY_ABI, IDENTITY_REGISTRY)


def validation_request(wallet_id: str, validator_addr: str, agent_id: int,
                       request_uri: str, request_hash_hex: str) -> ChainTx:
    cid = exec_contract(
        wallet_id=wallet_id,
        contract_addr=VALIDATION_REGISTRY,
        abi_function_signature="validationRequest(address,uint256,string,bytes32)",
        abi_parameters=[validator_addr, agent_id, request_uri, request_hash_hex],
    )
    return wait_for_tx(cid, _VALIDATION_ABI, VALIDATION_REGISTRY)


def validation_response(wallet_id: str, request_hash_hex: str, response_uint8: int,
                        response_uri: str, response_hash_hex: str, tag: str) -> ChainTx:
    cid = exec_contract(
        wallet_id=wallet_id,
        contract_addr=VALIDATION_REGISTRY,
        abi_function_signature="validationResponse(bytes32,uint8,string,bytes32,string)",
        abi_parameters=[request_hash_hex, response_uint8, response_uri, response_hash_hex, tag],
    )
    return wait_for_tx(cid, _VALIDATION_ABI, VALIDATION_REGISTRY)


def create_job(wallet_id: str, provider: str, evaluator: str, expired_at: int,
               description: str, hook: str = "0x0000000000000000000000000000000000000000") -> ChainTx:
    cid = exec_contract(
        wallet_id=wallet_id,
        contract_addr=AGENTIC_COMMERCE,
        abi_function_signature="createJob(address,address,uint256,string,address)",
        abi_parameters=[provider, evaluator, expired_at, description, hook],
    )
    return wait_for_tx(cid, _COMMERCE_ABI, AGENTIC_COMMERCE)


def set_budget(wallet_id: str, job_id: int, amount_usdc: float) -> ChainTx:
    cid = exec_contract(
        wallet_id=wallet_id,
        contract_addr=AGENTIC_COMMERCE,
        abi_function_signature="setBudget(uint256,uint256,bytes)",
        abi_parameters=[job_id, usdc6(amount_usdc), "0x"],
    )
    return wait_for_tx(cid, _COMMERCE_ABI, AGENTIC_COMMERCE)


def approve_usdc(wallet_id: str, spender: str, amount_usdc: float) -> ChainTx:
    cid = exec_contract(
        wallet_id=wallet_id,
        contract_addr=USDC,
        abi_function_signature="approve(address,uint256)",
        abi_parameters=[spender, usdc6(amount_usdc)],
    )
    return wait_for_tx(cid, _ERC20_ABI, USDC)


def _wallet_usdc(wallet_id: str) -> tuple[float, str | None]:
    client, developer_controlled_wallets = _circle_client()
    wallets_api = developer_controlled_wallets.WalletsApi(client)
    resp = wallets_api.list_wallet_balance(id=wallet_id, include_all=True)
    data = _as_dict(resp).get("data") or {}
    balances = data.get("tokenBalances") or data.get("token_balances") or []
    for bal in balances:
        b = _as_dict(bal)
        token = _as_dict(b.get("token") or {})
        if str(token.get("symbol", "")).upper() != "USDC":
            continue
        try:
            amount = float(b.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        return amount, token.get("id") or token.get("tokenId")
    return 0.0, None


def transfer_usdc(wallet_id: str, token_id: str, destination_addr: str,
                  amount_usdc: float) -> ChainTx:
    client, developer_controlled_wallets = _circle_client()
    tx_api = developer_controlled_wallets.TransactionsApi(client)
    req = developer_controlled_wallets.CreateTransferTransactionForDeveloperRequest.from_dict({
        "idempotencyKey": str(uuid.uuid4()),
        "walletId": wallet_id,
        "destinationAddress": destination_addr,
        "amounts": [f"{float(amount_usdc):.6f}".rstrip("0").rstrip(".")],
        "tokenId": token_id,
        "feeLevel": "MEDIUM",
    })
    resp = tx_api.create_developer_transaction_transfer(req)
    circle_tx_id = resp.data.id
    data = _poll_tx(tx_api, circle_tx_id)
    tx_hash = data.get("txHash") or data.get("transactionHash")
    if not tx_hash:
        raise RuntimeError(f"Circle returned COMPLETE without txHash: {data}")
    receipt = _get_receipt(tx_hash)
    return ChainTx(
        circle_tx_id=circle_tx_id,
        tx_hash=tx_hash,
        block_number=receipt.get("blockNumber"),
        logs=[],
    )


def ensure_client_usdc(desk_wallet_id: str, client_wallet_id: str,
                       client_wallet_addr: str, min_usdc: float,
                       top_up_usdc: float = 2.0) -> ChainTx | None:
    client_amount, _ = _wallet_usdc(client_wallet_id)
    if client_amount >= min_usdc:
        return None
    desk_amount, token_id = _wallet_usdc(desk_wallet_id)
    if not token_id:
        raise RuntimeError("desk wallet has no discoverable USDC token id")
    if desk_amount < top_up_usdc:
        raise RuntimeError(
            f"desk wallet has insufficient USDC to top up client "
            f"(need {top_up_usdc}, have {desk_amount})"
        )
    return transfer_usdc(
        wallet_id=desk_wallet_id,
        token_id=token_id,
        destination_addr=client_wallet_addr,
        amount_usdc=top_up_usdc,
    )


def fund_job(wallet_id: str, job_id: int) -> ChainTx:
    cid = exec_contract(
        wallet_id=wallet_id,
        contract_addr=AGENTIC_COMMERCE,
        abi_function_signature="fund(uint256,bytes)",
        abi_parameters=[job_id, "0x"],
    )
    return wait_for_tx(cid, _COMMERCE_ABI, AGENTIC_COMMERCE)


def submit_deliverable(wallet_id: str, job_id: int, deliverable_hash_hex: str) -> ChainTx:
    cid = exec_contract(
        wallet_id=wallet_id,
        contract_addr=AGENTIC_COMMERCE,
        abi_function_signature="submit(uint256,bytes32,bytes)",
        abi_parameters=[job_id, deliverable_hash_hex, "0x"],
    )
    return wait_for_tx(cid, _COMMERCE_ABI, AGENTIC_COMMERCE)


def complete_job(wallet_id: str, job_id: int, reason_hash_hex: str) -> ChainTx:
    """Used for BOTH win and loss settle. Final job status is Completed(3)
    for both; distinguish via the reason hash offchain (loss-path reason hash
    is keccak256("reject:<code>") — see helpers in `runtime.py`).
    """
    cid = exec_contract(
        wallet_id=wallet_id,
        contract_addr=AGENTIC_COMMERCE,
        abi_function_signature="complete(uint256,bytes32,bytes)",
        abi_parameters=[job_id, reason_hash_hex, "0x"],
    )
    return wait_for_tx(cid, _COMMERCE_ABI, AGENTIC_COMMERCE)


def give_feedback(wallet_id: str, agent_id: int, score: int, kind: int,
                  tag: str, feedback_hash_hex: str) -> ChainTx:
    if not -(2**127) <= score < 2**127:
        raise ValueError(f"giveFeedback score must fit in int128: {score}")
    cid = exec_contract(
        wallet_id=wallet_id,
        contract_addr=REPUTATION_REGISTRY,
        abi_function_signature="giveFeedback(uint256,int128,uint8,string,string,string,string,bytes32)",
        abi_parameters=[agent_id, score, kind, tag, "", "", "", feedback_hash_hex],
    )
    return wait_for_tx(cid, _REPUTATION_ABI, REPUTATION_REGISTRY)
