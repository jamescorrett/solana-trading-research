from __future__ import annotations

import json
from pathlib import Path

from cented_re.market import parse_market_event

MINT = "EcM95RK5swUTPXvuBXdJYMTAfb96bnvyxBYgteN8pump"
CENTED = "CyaE1VxvBrahnPWkqm5VsdCvyS2QmNht2UFrKJHga54o"

DIRS = [
    Path("data/raw/market_state/optimus_transactions"),
    Path("data/raw/market_state/optimus_later_transactions"),
    Path("data/raw/market_state/optimus_cented_anchors"),
]


def load_events():
    docs = {}

    for directory in DIRS:
        for path in directory.glob("*.json"):
            if path.name.startswith("_"):
                continue

            with path.open() as f:
                doc = json.load(f)

            tx = doc.get("result")
            if not tx:
                continue

            sigs = tx.get("transaction", {}).get("signatures", [])
            if not sigs:
                continue

            docs[sigs[0]] = (doc, path.name)

    events = []

    for sig, (doc, name) in docs.items():
        try:
            e = parse_market_event(
                doc,
                MINT,
                source_file=name,
            )
            if e:
                events.append(e)
        except Exception as exc:
            print("PARSE ERROR", sig[:16], exc)

    return sorted(events, key=lambda e: e.order_key)


events = load_events()

real = [
    e for e in events
    if e.action in {"BUY", "SELL", "CREATE_AND_BUY"}
]

cented = [
    e for e in real
    if e.actor == CENTED
    and e.action in {"BUY", "CREATE_AND_BUY"}
]

# ------------------------------------------------------------
# Group Cented transactions that occur in the same slot.
#
# We call these EXECUTION BURSTS rather than "decisions":
# they may represent one strategy decision split over several txs.
# ------------------------------------------------------------

bursts = []

for e in cented:
    if not bursts or bursts[-1]["slot"] != e.slot:
        bursts.append({
            "slot": e.slot,
            "block_time": e.block_time,
            "actions": [e],
        })
    else:
        bursts[-1]["actions"].append(e)


def previous_external_trade(anchor):
    candidates = [
        e for e in real
        if e.actor != CENTED
        and e.actor
        and e.order_key < anchor.order_key
        and e.effective_price_sol_per_token is not None
        and (e.gross_sol or 0) >= 0.01
    ]

    if not candidates:
        return None

    return candidates[-1]


def returning_buyers(anchor, seconds):
    if anchor.block_time is None:
        return set()

    recent_buys = [
        e for e in real
        if e.actor
        and e.actor != CENTED
        and e.action in {"BUY", "CREATE_AND_BUY"}
        and e.order_key < anchor.order_key
        and e.block_time is not None
        and e.block_time >= anchor.block_time - seconds
    ]

    returning = set()

    for current in recent_buys:
        had_previous_buy = any(
            prior.actor == current.actor
            and prior.action in {"BUY", "CREATE_AND_BUY"}
            and prior.order_key < current.order_key
            for prior in real
        )

        if had_previous_buy:
            returning.add(current.actor)

    return returning


print("=" * 100)
print("OPTIMUS — CENTED EXECUTION BURSTS")
print("=" * 100)

start = bursts[0]["block_time"]

for i, burst in enumerate(bursts):
    actions = burst["actions"]
    anchor = actions[0]

    elapsed = anchor.block_time - start

    total_sol = sum(
        e.gross_sol or 0
        for e in actions
    )

    previous = previous_external_trade(anchor)

    if previous:
        pre_price = (
            previous.effective_price_sol_per_token
            * 1_000_000
        )
    else:
        pre_price = None

    r2 = returning_buyers(anchor, 2)
    r5 = returning_buyers(anchor, 5)

    label = "ENTRY" if i == 0 else f"SCALE #{i}"

    print()
    print(
        f"{label:<8}"
        f" +{elapsed:>3}s"
        f" slot={burst['slot']}"
        f" txs={len(actions)}"
        f" totalSOL={total_sol:.3f}"
    )

    for e in actions:
        print(
            f"    idx={e.transaction_index:<5}"
            f" SOL={(e.gross_sol or 0):.3f}"
        )

    print(
        f"    pre-price proxy: "
        f"{pre_price:.8f} SOL/1m"
        if pre_price is not None
        else "    pre-price proxy: n/a"
    )

    print(
        f"    returning buyers:"
        f" 2s={len(r2)}"
        f" 5s={len(r5)}"
    )

print()
print(f"Raw Cented buy transactions: {len(cented)}")
print(f"Same-slot execution bursts:  {len(bursts)}")
