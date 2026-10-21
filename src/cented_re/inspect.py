from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import orjson
from rich.console import Console
from rich.table import Table

console = Console()


def iter_jsonl(paths: list[Path]):
    for path in paths:
        with path.open("rb") as fh:
            for line in fh:
                if line.strip():
                    yield orjson.loads(line)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect collected raw V1 JSONL files")
    parser.add_argument("path", nargs="?", default="data/raw/logs")
    args = parser.parse_args()

    root = Path(args.path)
    files = sorted(root.rglob("*.jsonl")) if root.is_dir() else [root]
    if not files:
        raise SystemExit(f"No .jsonl files found under {root}")

    counts = Counter()
    slots: list[int] = []
    signatures = set()
    for record in iter_jsonl(files):
        counts["events"] += 1
        tags = record.get("tags", {})
        counts["pump"] += bool(tags.get("pump_subscription") or tags.get("includes_pump_program"))
        counts["target"] += bool(
            tags.get("target_wallet_subscription") or tags.get("includes_target_wallet")
        )
        counts["launch_candidates"] += bool(tags.get("pump_launch_candidate"))
        counts["failed"] += bool(tags.get("failed"))
        sig = record.get("signature")
        if sig:
            signatures.add(sig)
        if isinstance(record.get("slot"), int):
            slots.append(record["slot"])

    table = Table(title="Dataset V1 raw collector")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key in ("events", "pump", "target", "launch_candidates", "failed"):
        table.add_row(key, f"{counts[key]:,}")
    table.add_row("unique signatures", f"{len(signatures):,}")
    if slots:
        table.add_row("slot range", f"{min(slots):,} → {max(slots):,}")
    console.print(table)
