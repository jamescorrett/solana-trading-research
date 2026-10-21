from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from cented_re.market import parse_market_event

MINT = "EcM95RK5swUTPXvuBXdJYMTAfb96bnvyxBYgteN8pump"
CENTED = "CyaE1VxvBrahnPWkqm5VsdCvyS2QmNht2UFrKJHga54o"

DIRS = [
    Path("data/raw/market_state/optimus_transactions"),
    Path("data/raw/market_state/optimus_later_transactions"),
    Path("data/raw/market_state/optimus_cented_anchors"),
]

MIN_PRICE_TRADE_SOL = 0.01


def load_events():
    docs = {}

    for directory in DIRS:
        for path in directory.glob("*.json"):
            if path.name.startswith("_"):
                continue

            with path.open() as f:
                doc = json.load(f)

            tx = doc.get("result")

            if tx is None and "helius_transaction" in doc:
                tx = doc["helius_transaction"].get("result")

            if not tx:
                continue

            signatures = (
                tx.get("transaction", {})
                .get("signatures", [])
            )

            if not signatures:
                continue

            docs[signatures[0]] = (doc, path.name)

    events = []

    for sig, (doc, source_name) in docs.items():
        try:
            event = parse_market_event(
                doc,
                MINT,
                source_file=source_name,
            )

            if event:
                events.append(event)

        except Exception as exc:
            print("PARSE ERROR:", sig[:16], exc)

    events.sort(key=lambda e: e.order_key)

    return events


def is_real_trade(e):
    return e.action in {
        "BUY",
        "SELL",
        "CREATE_AND_BUY",
    }


def is_buy(e):
    return e.action in {
        "BUY",
        "CREATE_AND_BUY",
    }


def price_per_million(e):
    if e.effective_price_sol_per_token is None:
        return None

    return (
        e.effective_price_sol_per_token
        * 1_000_000
    )


def price_bearing(e):
    return (
        is_real_trade(e)
        and e.actor != CENTED
        and e.actor is not None
        and e.gross_sol is not None
        and e.gross_sol >= MIN_PRICE_TRADE_SOL
        and price_per_million(e) is not None
    )


def pct_change(a, b):
    """
    Percentage change from a -> b.
    """
    if a is None or b is None or a == 0:
        return None

    return ((b / a) - 1) * 100


def fmt_pct(x):
    if x is None:
        return "   n/a"

    return f"{x:+6.1f}%"


def returning_buyer_count(
    all_real,
    recent,
):
    recent_buyers = {
        e.actor
        for e in recent
        if is_buy(e)
        and e.actor
        and e.actor != CENTED
    }

    returning = 0

    for actor in recent_buyers:
        actor_recent = [
            e
            for e in recent
            if e.actor == actor
            and is_buy(e)
        ]

        if not actor_recent:
            continue

        first_recent_key = min(
            e.order_key
            for e in actor_recent
        )

        had_earlier_buy = any(
            e.actor == actor
            and is_buy(e)
            and e.order_key < first_recent_key
            for e in all_real
        )

        if had_earlier_buy:
            returning += 1

    return returning


def window_features(
    all_real,
    anchor,
    seconds,
):
    prior = [
        e
        for e in all_real
        if e.order_key < anchor.order_key
        and e.actor != CENTED
        and e.actor is not None
    ]

    if anchor.block_time is None:
        return None

    recent = [
        e
        for e in prior
        if e.block_time is not None
        and e.block_time >= (
            anchor.block_time - seconds
        )
    ]

    buys = [
        e for e in recent
        if is_buy(e)
    ]

    sells = [
        e for e in recent
        if e.action == "SELL"
    ]

    buy_sol = sum(
        e.gross_sol or 0
        for e in buys
    )

    sell_sol = sum(
        e.gross_sol or 0
        for e in sells
    )

    traders = {
        e.actor
        for e in recent
        if e.actor
    }

    returning = returning_buyer_count(
        all_real,
        recent,
    )

    # Price-bearing trades only.
    p_events = [
        e
        for e in recent
        if price_bearing(e)
    ]

    prices = [
        price_per_million(e)
        for e in p_events
    ]

    start_price = (
        prices[0]
        if prices
        else None
    )

    end_price = (
        prices[-1]
        if prices
        else None
    )

    high_price = (
        max(prices)
        if prices
        else None
    )

    low_price = (
        min(prices)
        if prices
        else None
    )

    window_return = pct_change(
        start_price,
        end_price,
    )

    drawdown_from_high = pct_change(
        high_price,
        end_price,
    )

    rebound_from_low = pct_change(
        low_price,
        end_price,
    )

    return {
        "trades": len(recent),
        "buys": len(buys),
        "sells": len(sells),
        "traders": len(traders),
        "returning": returning,
        "buy_sol": buy_sol,
        "sell_sol": sell_sol,
        "net_sol": buy_sol - sell_sol,
        "start_price": start_price,
        "end_price": end_price,
        "high_price": high_price,
        "low_price": low_price,
        "return_pct": window_return,
        "drawdown_pct": drawdown_from_high,
        "rebound_pct": rebound_from_low,
        "price_trades": len(prices),
    }


def main():
    events = load_events()

    real = [
        e for e in events
        if is_real_trade(e)
    ]

    cented = sorted(
        [
            e for e in real
            if e.actor == CENTED
            and is_buy(e)
        ],
        key=lambda e: e.order_key,
    )

    if len(cented) != 8:
        print(
            f"WARNING: expected 8 Cented buys, "
            f"found {len(cented)}"
        )

    if not cented:
        raise SystemExit(
            "No Cented OPTIMUS buys found."
        )

    entry = cented[0]

    entry_price = price_per_million(entry)
    start_time = entry.block_time

    print("=" * 126)
    print("OPTIMUS — CENTED PRE-ACTION PRICE + FLOW FEATURES")
    print("=" * 126)

    for i, anchor in enumerate(cented):
        label = (
            "ENTRY"
            if i == 0
            else f"ADD #{i}"
        )

        elapsed = (
            anchor.block_time - start_time
            if (
                anchor.block_time is not None
                and start_time is not None
            )
            else 0
        )

        own_price = price_per_million(anchor)

        vs_entry = pct_change(
            entry_price,
            own_price,
        )

        print()
        print(
            f"{label:<7} "
            f"+{elapsed:>3}s "
            f"slot={anchor.slot} "
            f"idx={anchor.transaction_index:<5} "
            f"SOL={anchor.gross_sol:.3f} "
            f"exec_price={own_price:.8f} SOL/1m "
            f"vs_entry={fmt_pct(vs_entry)}"
        )

        print(
            "        "
            "win   trades   B   S  traders  ret "
            " buySOL sellSOL     net"
            "   priceRet  drawdown  rebound"
        )

        for seconds in [1, 2, 5, 10]:
            f = window_features(
                real,
                anchor,
                seconds,
            )

            print(
                f"        "
                f"{seconds:>2}s "
                f"{f['trades']:>7} "
                f"{f['buys']:>3} "
                f"{f['sells']:>3} "
                f"{f['traders']:>8} "
                f"{f['returning']:>4} "
                f"{f['buy_sol']:>7.3f} "
                f"{f['sell_sol']:>7.3f} "
                f"{f['net_sol']:>+7.3f} "
                f"{fmt_pct(f['return_pct']):>10} "
                f"{fmt_pct(f['drawdown_pct']):>10} "
                f"{fmt_pct(f['rebound_pct']):>9}"
            )

    print()
    print("=" * 126)
    print("PRICE MOVEMENT BETWEEN CENTED ACTIONS")
    print("=" * 126)

    for i in range(1, len(cented)):
        left = cented[i - 1]
        right = cented[i]

        left_price = price_per_million(left)
        right_price = price_per_million(right)

        change = pct_change(
            left_price,
            right_price,
        )

        dt = (
            right.block_time - left.block_time
            if (
                right.block_time is not None
                and left.block_time is not None
            )
            else None
        )

        print(
            f"ACTION #{i} -> #{i + 1}"
            f" | dt={dt:>3}s"
            f" | Cented execution-price change="
            f"{fmt_pct(change)}"
        )

    print()
    print(
        "NOTE: priceRet/drawdown/rebound use external "
        "trade-implied average execution prices, not exact "
        "Pump marginal spot prices."
    )


if __name__ == "__main__":
    main()
