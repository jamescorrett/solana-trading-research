from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any

LAMPORTS_PER_SOL = 1_000_000_000


@dataclass
class NormalizedTargetAction:
    signature: str
    slot: int | None
    transaction_index: int | None
    block_time: int | None

    target_wallet: str
    target_present: bool
    target_signer: bool
    target_writable: bool

    action: str
    mint: str | None

    wallet_sol_delta: float | None
    wallet_fee_lamports: int | None

    token_balance_before: float | None
    token_balance_after: float | None
    token_delta: float | None

    pump_instructions: list[str]
    all_instruction_logs: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pubkey(key: Any) -> str:
    if isinstance(key, dict):
        return key.get("pubkey", "")
    return str(key)


def _ui_amount(balance: dict[str, Any]) -> float:
    ui = balance.get("uiTokenAmount", {})
    amount = int(ui.get("amount", "0"))
    decimals = int(ui.get("decimals", 0))
    return amount / (10 ** decimals)


def _token_balances_for_owner(
    balances: list[dict[str, Any]] | None,
    owner: str,
) -> dict[str, float]:
    by_mint: defaultdict[str, float] = defaultdict(float)

    for b in balances or []:
        if b.get("owner") != owner:
            continue
        by_mint[b["mint"]] += _ui_amount(b)

    return dict(by_mint)


def _instruction_logs(logs: list[str] | None) -> list[str]:
    return [
        log.split("Instruction:", 1)[1].strip()
        for log in (logs or [])
        if "Instruction:" in log
    ]


def _pump_instruction_logs(logs: list[str] | None) -> list[str]:
    """
    Pump logs are emitted as normal 'Program log: Instruction: X' messages.
    For V1 we retain the instruction names that matter for classification.
    """
    wanted = {
        "Create",
        "CreateV2",
        "Buy",
        "BuyV2",
        "Sell",
        "SellV2",
    }
    return [x for x in _instruction_logs(logs) if x in wanted]


def unwrap_rpc_document(document: dict[str, Any]) -> dict[str, Any] | None:
    """
    Accepts either:
      {"jsonrpc": ..., "result": {...}}
    or our known-positive wrapper:
      {"madeonsol_trade": ..., "helius_transaction": {"result": {...}}}
    """
    if "helius_transaction" in document:
        return document["helius_transaction"].get("result")
    return document.get("result")


def normalize_target_transaction(
    rpc_document: dict[str, Any],
    target_wallet: str,
) -> NormalizedTargetAction:
    tx = unwrap_rpc_document(rpc_document)

    if not tx:
        raise ValueError("Document contains no transaction result")

    message = tx["transaction"]["message"]
    meta = tx["meta"]
    keys = message.get("accountKeys", [])

    target_index = None
    target_signer = False
    target_writable = False

    for idx, key in enumerate(keys):
        if _pubkey(key) == target_wallet:
            target_index = idx
            if isinstance(key, dict):
                target_signer = bool(key.get("signer"))
                target_writable = bool(key.get("writable"))
            break

    wallet_sol_delta = None
    if target_index is not None:
        wallet_sol_delta = (
            meta["postBalances"][target_index]
            - meta["preBalances"][target_index]
        ) / LAMPORTS_PER_SOL

    pre = _token_balances_for_owner(
        meta.get("preTokenBalances"), target_wallet
    )
    post = _token_balances_for_owner(
        meta.get("postTokenBalances"), target_wallet
    )

    mint_changes: list[tuple[str, float, float, float]] = []

    for mint in set(pre) | set(post):
        before = pre.get(mint, 0.0)
        after = post.get(mint, 0.0)
        delta = after - before

        if abs(delta) > 1e-12:
            mint_changes.append((mint, before, after, delta))

    # For V1 Cented actions we expect one economically relevant mint.
    # If multiple move, choose the largest absolute token movement and retain
    # classification conservatively.
    chosen = None
    if mint_changes:
        chosen = max(mint_changes, key=lambda x: abs(x[3]))

    mint = chosen[0] if chosen else None
    token_before = chosen[1] if chosen else None
    token_after = chosen[2] if chosen else None
    token_delta = chosen[3] if chosen else None

    logs = meta.get("logMessages", [])
    all_ix = _instruction_logs(logs)
    pump_ix = _pump_instruction_logs(logs)

    create = any(x in {"Create", "CreateV2"} for x in pump_ix)
    buy = any(x in {"Buy", "BuyV2"} for x in pump_ix)
    sell = any(x in {"Sell", "SellV2"} for x in pump_ix)

    action = "OTHER"

    # Require direct target activity for trading labels.
    direct_target = target_signer or target_writable

    if direct_target and create and buy and token_delta is not None and token_delta > 0:
        action = "CREATE_AND_BUY"

    elif direct_target and buy and token_delta is not None and token_delta > 0:
        if token_before is not None and abs(token_before) <= 1e-12:
            action = "FIRST_BUY"
        else:
            action = "ADD_BUY"

    elif direct_target and sell and token_delta is not None and token_delta < 0:
        if token_after is not None and abs(token_after) <= 1e-12:
            action = "FULL_SELL"
        else:
            action = "PARTIAL_SELL"

    signature = ""
    signatures = tx.get("transaction", {}).get("signatures", [])
    if signatures:
        signature = signatures[0]

    return NormalizedTargetAction(
        signature=signature,
        slot=tx.get("slot"),
        transaction_index=tx.get("transactionIndex"),
        block_time=tx.get("blockTime"),
        target_wallet=target_wallet,
        target_present=target_index is not None,
        target_signer=target_signer,
        target_writable=target_writable,
        action=action,
        mint=mint,
        wallet_sol_delta=wallet_sol_delta,
        wallet_fee_lamports=meta.get("fee"),
        token_balance_before=token_before,
        token_balance_after=token_after,
        token_delta=token_delta,
        pump_instructions=pump_ix,
        all_instruction_logs=all_ix,
    )
