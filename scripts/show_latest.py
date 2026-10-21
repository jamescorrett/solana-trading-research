from pathlib import Path
import orjson

files = sorted(Path("data/raw/target_wallet_logs").rglob("*.jsonl"))
if not files:
    raise SystemExit("No target-wallet log data collected yet")

lines = files[-1].read_bytes().splitlines()[-10:]
for line in lines:
    event = orjson.loads(line)
    print(event["slot"], event["signature"], event["tags"])
