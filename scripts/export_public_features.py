"""Export selected, pseudonymised matched evaluation features; read-only to source.

Copies only the columns used in the evaluation plus group structure and timestamps.
Does not attempt to verify the provenance of original labels or controls.
"""
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

FEATURES = [
    "w2_buys", "w2_unique_buyers", "w5_buys", "w5_unique_buyers",
    "w5_tx_failed", "w5_failure_rate", "w5_max_buys_same_slot",
    "w10_buys", "w10_unique_buyers",
]
FIELDS = ["match_id", "mint", "label", "creation_block_time", "snapshot_block_time", "launch_age_s", *FEATURES]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("destination", type=Path)
    args = p.parse_args()
    if args.source.resolve() == args.destination.resolve():
        raise SystemExit("Source and destination must differ")
    with args.source.open(newline="", encoding="utf-8") as inp:
        reader = csv.DictReader(inp)
        if not reader.fieldnames or not set(FIELDS).issubset(reader.fieldnames):
            raise SystemExit(f"Missing columns: {sorted(set(FIELDS) - set(reader.fieldnames or []))}")
        rows = list(reader)
    groups = defaultdict(list)
    for row in rows:
        groups[row["match_id"]].append(row)
    if len(groups) != 32 or len(rows) != 128:
        raise SystemExit(f"Unexpected input shape: {len(groups)} groups, {len(rows)} rows")
    for key, group in groups.items():
        if (len(group) != 4 or Counter(r["label"] for r in group) != {"1": 1, "0": 3}
                or len({r["launch_age_s"] for r in group}) != 1):
            raise SystemExit(f"Invalid matched group: {key[:16]}")
    group_names = {key: f"matched_group_{i:03d}" for i, key in enumerate(groups, 1)}
    output = []
    for i, row in enumerate(rows, 1):
        clean = {k: row[k] for k in FIELDS}
        clean["match_id"] = group_names[row["match_id"]]
        clean["mint"] = f"token_{i:04d}"
        output.append(clean)
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    with args.destination.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(output)
    print(f"Exported {len(output)} rows / {len(groups)} groups to: {args.destination}")
    print("Included columns:", ", ".join(FIELDS))
    print("No raw transactions, wallets, mint addresses, or symbol fields were copied.")
    print("Review the exported CSV before making it public.")


if __name__ == "__main__":
    main()
