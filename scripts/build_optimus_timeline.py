from __future__ import annotations

import csv
import json
from pathlib import Path

from cented_re.market import MarketEvent, between, parse_market_event, trade_features

MINT = "EcM95RK5swUTPXvuBXdJYMTAfb96bnvyxBYgteN8pump"
CENTED = "CyaE1VxvBrahnPWkqm5VsdCvyS2QmNht2UFrKJHga54o"
FIRST_SIG = "3YipsxjvjaPcPNq3S8ttJhqUPffoBxNExqtcivE8F34kdYnULX9sE8MRrsu8itq9sUsY8Tn6JJk4E3ruvhSYDoan"
ADD_SIG = "2g37bo6Ca8K1xwn3t9Z8ftUYsB5BvD9T4F5oyxiuovVCAX5R8fthhUeFjfKx8e2mfbEErgRpbtbjrSqT3Q5BUBxQ"
SOURCE_DIR = Path("data/raw/market_state/optimus_transactions")
OUT_DIR = Path("data/processed")


def fmt(v):
    return "?" if v is None else f"{v:.4f}"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = sorted(p for p in SOURCE_DIR.glob("*.json") if not p.name.startswith("_"))
    if not paths:
        raise SystemExit(f"No JSON files found in {SOURCE_DIR}")

    events: list[MarketEvent] = []
    errors = []
    for path in paths:
        try:
            with path.open() as f:
                event = parse_market_event(json.load(f), MINT, source_file=path.name)
            if event:
                events.append(event)
        except Exception as exc:
            errors.append((path.name, str(exc)))

    events.sort(key=lambda e: e.order_key)
    by_sig = {e.signature: e for e in events}
    first = by_sig.get(FIRST_SIG)
    add = by_sig.get(ADD_SIG)
    if not first or not add:
        raise SystemExit("Known Cented anchor transaction failed to parse")

    relevant = [e for e in events if e.action in {"CREATE", "CREATE_AND_BUY", "BUY", "SELL"}]
    creates = [e for e in relevant if e.action in {"CREATE", "CREATE_AND_BUY"}]
    creation = min(creates, key=lambda e: e.order_key) if creates else None
    pre = [e for e in events if e.order_key < first.order_key]
    mid = between(events, first, add)

    print("\n" + "=" * 80)
    print("STAGE 3 — OPTIMUS MARKET RECONSTRUCTION")
    print("=" * 80)
    print(f"Files parsed:              {len(paths):,}")
    print(f"Parser errors:             {len(errors):,}")
    print(f"Relevant Pump events:      {len(relevant):,}")
    print(f"Buys:                      {sum(e.action in {'BUY','CREATE_AND_BUY'} for e in relevant):,}")
    print(f"Sells:                     {sum(e.action == 'SELL' for e in relevant):,}")
    print(f"Creates:                   {len(creates):,}")
    print(f"Unknown actor:             {sum(e.actor is None for e in relevant):,}")

    print("\nCented anchors:")
    print(f"  FIRST  slot={first.slot} idx={first.transaction_index} grossSOL={fmt(first.gross_sol)} actor={first.actor}")
    print(f"  ADD    slot={add.slot} idx={add.transaction_index} grossSOL={fmt(add.gross_sol)} actor={add.actor}")

    if creation and creation.block_time is not None and first.block_time is not None:
        print(f"\nEarliest creation:         slot={creation.slot} idx={creation.transaction_index}")
        print(f"Token age at entry:        {first.block_time - creation.block_time}s (blockTime resolution)")
    else:
        print("\nCreation transaction not resolved in this window")

    print("\nPRE-ENTRY FEATURES (strictly before Cented by slot + tx index)")
    print("-" * 80)
    for seconds in [1, 2, 5, 10, 15]:
        f = trade_features(events, end=first, seconds=seconds)
        print(
            f"{seconds:>2}s | trades={f['trades']:>4} buy={f['buys']:>4} sell={f['sells']:>4} "
            f"traders={f['unique_traders']:>4} repeat={f['repeat_traders']:>4} "
            f"buySOL={f['buy_sol']:>9.3f} sellSOL={f['sell_sol']:>9.3f} "
            f"net={f['net_buy_sol']:>9.3f} maxBuy={f['largest_buy_sol']:>7.3f}"
        )

    pre_trades = [e for e in pre if e.action in {"BUY", "SELL", "CREATE_AND_BUY"}]
    print("\nLAST 25 REAL TRADES BEFORE CENTED")
    print("-" * 80)
    for e in pre_trades[-25:]:
        dt = (e.block_time - first.block_time) if e.block_time is not None and first.block_time is not None else 0
        print(f"{dt:+3d}s slot={e.slot} idx={e.transaction_index:<4} {e.action:<14} SOL={fmt(e.gross_sol):>8} actor={(e.actor or '?')[:10]}...")

    mid_trades = [e for e in mid if e.action in {"BUY", "SELL", "CREATE_AND_BUY"}]
    print("\nBETWEEN CENTED FIRST BUY AND KNOWN ADD")
    print("-" * 80)
    print(f"Real trades between anchors: {len(mid_trades):,}")
    for e in mid_trades[:30]:
        dt = (e.block_time - first.block_time) if e.block_time is not None and first.block_time is not None else 0
        print(f"{dt:+3d}s slot={e.slot} idx={e.transaction_index:<4} {e.action:<14} SOL={fmt(e.gross_sol):>8} actor={(e.actor or '?')[:10]}...")
    if len(mid_trades) > 30:
        print(f"... {len(mid_trades)-30:,} more")

    jsonl = OUT_DIR / "optimus_timeline.jsonl"
    with jsonl.open("w") as f:
        for e in events:
            f.write(json.dumps(e.to_dict()) + "\n")

    fields = [
        "signature","slot","transaction_index","block_time","mint","action","actor",
        "wallet_sol_delta","gross_sol","gross_sol_source","token_balance_before",
        "token_balance_after","token_delta","effective_price_sol_per_token",
        "pump_instructions","source_file"
    ]
    csv_path = OUT_DIR / "optimus_timeline.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for e in events:
            row = e.to_dict(); row["pump_instructions"] = "|".join(row["pump_instructions"])
            w.writerow({k: row.get(k) for k in fields})

    summary = {
        "files_parsed": len(paths),
        "parser_errors": errors,
        "relevant_events": len(relevant),
        "first_buy": first.to_dict(),
        "known_add": add.to_dict(),
        "creation": creation.to_dict() if creation else None,
        "events_before_first_buy": len(pre),
        "events_between_first_and_add": len(mid),
        "pre_entry_features": {str(s): trade_features(events, end=first, seconds=s) for s in [1,2,5,10,15]},
    }
    with (OUT_DIR / "optimus_market_summary.json").open("w") as f:
        json.dump(summary, f, indent=2)

    print("\nWrote data/processed/optimus_timeline.{csv,jsonl} and optimus_market_summary.json")


if __name__ == "__main__":
    main()
