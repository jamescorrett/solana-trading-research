from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable

LAMPORTS_PER_SOL = 1_000_000_000


@dataclass
class MarketEvent:
    signature: str
    slot: int
    transaction_index: int
    block_time: int | None
    mint: str
    action: str
    actor: str | None
    wallet_sol_delta: float | None
    gross_sol: float | None
    gross_sol_source: str | None
    token_balance_before: float | None
    token_balance_after: float | None
    token_delta: float | None
    effective_price_sol_per_token: float | None
    pump_instructions: list[str]
    source_file: str | None = None

    @property
    def order_key(self) -> tuple[int, int]:
        return self.slot, self.transaction_index

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pubkey(key: Any) -> str:
    return str(key.get("pubkey", "")) if isinstance(key, dict) else str(key)


def _signers(tx: dict[str, Any]) -> set[str]:
    return {
        _pubkey(k)
        for k in tx["transaction"]["message"].get("accountKeys", [])
        if isinstance(k, dict) and k.get("signer")
    }


def _wallet_sol_delta(tx: dict[str, Any], address: str) -> float | None:
    keys = tx["transaction"]["message"].get("accountKeys", [])
    idx = next((i for i, k in enumerate(keys) if _pubkey(k) == address), None)
    if idx is None:
        return None
    meta = tx.get("meta") or {}
    return (meta["postBalances"][idx] - meta["preBalances"][idx]) / LAMPORTS_PER_SOL


def _token_amount(balance: dict[str, Any]) -> float:
    ui = balance.get("uiTokenAmount") or {}
    return int(ui.get("amount", "0")) / (10 ** int(ui.get("decimals", 0)))


def _balances_by_owner(balances: list[dict[str, Any]] | None, mint: str) -> dict[str, float]:
    out: defaultdict[str, float] = defaultdict(float)
    for b in balances or []:
        if b.get("mint") == mint and b.get("owner"):
            out[b["owner"]] += _token_amount(b)
    return dict(out)


def _token_changes(tx: dict[str, Any], mint: str) -> dict[str, tuple[float, float, float]]:
    meta = tx.get("meta") or {}
    pre = _balances_by_owner(meta.get("preTokenBalances"), mint)
    post = _balances_by_owner(meta.get("postTokenBalances"), mint)
    out = {}
    for owner in set(pre) | set(post):
        before, after = pre.get(owner, 0.0), post.get(owner, 0.0)
        delta = after - before
        if abs(delta) > 1e-12:
            out[owner] = before, after, delta
    return out


def _pump_instruction_names(tx: dict[str, Any]) -> list[str]:
    wanted = {"Create", "CreateV2", "Buy", "BuyV2", "Sell", "SellV2"}
    names = []
    for log in (tx.get("meta") or {}).get("logMessages") or []:
        if "Instruction:" in log:
            name = log.split("Instruction:", 1)[1].strip()
            if name in wanted:
                names.append(name)
    return names


def _pick_actor(tx: dict[str, Any], mint: str, direction: str):
    signers = _signers(tx)
    changes = _token_changes(tx, mint)
    wanted_positive = direction == "buy"
    candidates = []
    for owner, change in changes.items():
        delta = change[2]
        if owner in signers and ((wanted_positive and delta > 0) or (not wanted_positive and delta < 0)):
            candidates.append((owner, change))
    return max(candidates, key=lambda x: abs(x[1][2])) if candidates else (None, None)


def _inner_transfer_sol(tx: dict[str, Any], actor: str, direction: str) -> float | None:
    total = 0
    found = False
    for group in (tx.get("meta") or {}).get("innerInstructions") or []:
        for ix in group.get("instructions") or []:
            if ix.get("program") != "system":
                continue
            parsed = ix.get("parsed") or {}
            if parsed.get("type") != "transfer":
                continue
            info = parsed.get("info") or {}
            if direction == "buy" and info.get("source") == actor:
                total += int(info.get("lamports", 0)); found = True
            elif direction == "sell" and info.get("destination") == actor:
                total += int(info.get("lamports", 0)); found = True
    return total / LAMPORTS_PER_SOL if found else None


def unwrap_rpc_document(doc: dict[str, Any]) -> dict[str, Any] | None:
    if "helius_transaction" in doc:
        return doc["helius_transaction"].get("result")
    return doc.get("result")


def parse_market_event(doc: dict[str, Any], mint: str, *, source_file: str | None = None) -> MarketEvent | None:
    tx = unwrap_rpc_document(doc)
    if not tx or not tx.get("meta") or tx["meta"].get("err") is not None:
        return None

    pump_ix = _pump_instruction_names(tx)
    create = any(x in {"Create", "CreateV2"} for x in pump_ix)
    buy = any(x in {"Buy", "BuyV2"} for x in pump_ix)
    sell = any(x in {"Sell", "SellV2"} for x in pump_ix)

    if create and buy:
        action, direction = "CREATE_AND_BUY", "buy"
    elif buy and not sell:
        action, direction = "BUY", "buy"
    elif sell and not buy:
        action, direction = "SELL", "sell"
    elif create:
        action, direction = "CREATE", None
    elif buy and sell:
        action, direction = "MULTI", None
    else:
        action, direction = "OTHER", None

    actor = None
    change = None
    if direction:
        actor, change = _pick_actor(tx, mint, direction)
    elif action == "CREATE":
        signers = list(_signers(tx))
        actor = signers[0] if signers else None

    wallet_delta = _wallet_sol_delta(tx, actor) if actor else None
    gross_sol = None
    gross_source = None
    if actor and direction:
        gross_sol = _inner_transfer_sol(tx, actor, direction)
        if gross_sol is not None:
            gross_source = "inner_system_transfers"
        elif wallet_delta is not None:
            gross_sol = abs(wallet_delta)
            gross_source = "wallet_delta_fallback"

    before = change[0] if change else None
    after = change[1] if change else None
    token_delta = change[2] if change else None
    price = gross_sol / abs(token_delta) if gross_sol is not None and token_delta not in (None, 0) else None

    sigs = tx.get("transaction", {}).get("signatures") or []
    tx_idx = tx.get("transactionIndex")
    if tx_idx is None:
        raise ValueError(f"transactionIndex missing for {sigs[0] if sigs else '<unknown>'}")

    return MarketEvent(
        signature=sigs[0] if sigs else "",
        slot=int(tx["slot"]),
        transaction_index=int(tx_idx),
        block_time=tx.get("blockTime"),
        mint=mint,
        action=action,
        actor=actor,
        wallet_sol_delta=wallet_delta,
        gross_sol=gross_sol,
        gross_sol_source=gross_source,
        token_balance_before=before,
        token_balance_after=after,
        token_delta=token_delta,
        effective_price_sol_per_token=price,
        pump_instructions=pump_ix,
        source_file=source_file,
    )


def between(events: Iterable[MarketEvent], left: MarketEvent, right: MarketEvent) -> list[MarketEvent]:
    return sorted([e for e in events if left.order_key < e.order_key < right.order_key], key=lambda e: e.order_key)


def trade_features(events: Iterable[MarketEvent], *, end: MarketEvent, seconds: int | None = None) -> dict[str, Any]:
    selected = [e for e in events if e.order_key < end.order_key]
    if seconds is not None and end.block_time is not None:
        start = end.block_time - seconds
        selected = [e for e in selected if e.block_time is not None and e.block_time >= start]

    trades = [e for e in selected if e.action in {"BUY", "SELL", "CREATE_AND_BUY"} and e.actor]
    buys = [e for e in trades if e.action in {"BUY", "CREATE_AND_BUY"}]
    sells = [e for e in trades if e.action == "SELL"]
    buy_vals = [e.gross_sol for e in buys if e.gross_sol is not None]
    sell_vals = [e.gross_sol for e in sells if e.gross_sol is not None]
    counts = Counter(e.actor for e in trades if e.actor)

    return {
        "window_seconds": seconds,
        "trades": len(trades),
        "buys": len(buys),
        "sells": len(sells),
        "unique_traders": len(counts),
        "repeat_traders": sum(n > 1 for n in counts.values()),
        "buy_sol": sum(buy_vals),
        "sell_sol": sum(sell_vals),
        "net_buy_sol": sum(buy_vals) - sum(sell_vals),
        "largest_buy_sol": max(buy_vals, default=0.0),
        "largest_sell_sol": max(sell_vals, default=0.0),
    }
