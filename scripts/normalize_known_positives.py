from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from cented_re.normalize import normalize_target_transaction


def main() -> None:
    load_dotenv(".env")

    target = os.environ.get(
        "TARGET_WALLET",
        "CyaE1VxvBrahnPWkqm5VsdCvyS2QmNht2UFrKJHga54o",
    )

    source_dir = Path("data/raw/known_positive")
    out_dir = Path("data/processed")
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(source_dir.glob("*.json"))

    if not files:
        raise SystemExit(
            "No JSON files found under data/raw/known_positive/"
        )

    rows = []

    print(f"Normalizing {len(files)} known-positive transaction files...\n")

    for path in files:
        with path.open() as f:
            doc = json.load(f)

        try:
            row = normalize_target_transaction(doc, target).to_dict()
        except Exception as exc:
            print(f"{path.name}: ERROR {exc}")
            continue

        row["source_file"] = path.name
        rows.append(row)

        print(
            f"{path.name:<34} "
            f"{row['action']:<16} "
            f"SOL={row['wallet_sol_delta']!s:<16} "
            f"mint={row['mint'] or '-'}"
        )

    jsonl_path = out_dir / "known_positive_actions.jsonl"
    with jsonl_path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    csv_path = out_dir / "known_positive_actions.csv"

    csv_fields = [
        "source_file",
        "signature",
        "slot",
        "transaction_index",
        "block_time",
        "target_wallet",
        "target_present",
        "target_signer",
        "target_writable",
        "action",
        "mint",
        "wallet_sol_delta",
        "wallet_fee_lamports",
        "token_balance_before",
        "token_balance_after",
        "token_delta",
        "pump_instructions",
    ]

    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields)
        writer.writeheader()

        for row in rows:
            out = {k: row.get(k) for k in csv_fields}
            out["pump_instructions"] = "|".join(row["pump_instructions"])
            writer.writerow(out)

    print("\nWrote:")
    print(f"  {jsonl_path}")
    print(f"  {csv_path}")


if __name__ == "__main__":
    main()
