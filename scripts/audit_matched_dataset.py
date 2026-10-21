"""Read-only audit of the local matched entry CSV; prints aggregate diagnostics only."""
import csv
from collections import Counter, defaultdict
from pathlib import Path

CSV = Path('data/processed/cented_matched_entry_dataset_v1.csv')
FOLDS = (16, 20, 24, 28)

if not CSV.exists():
    raise SystemExit(f'Cannot find {CSV}. Run from the original Cented project root.')
with CSV.open(newline='') as f:
    rows = list(csv.DictReader(f))

need = {'match_id','mint','label','creation_block_time','snapshot_block_time','launch_age_s'}
if not rows or not need.issubset(rows[0]):
    raise SystemExit(f'Missing CSV columns: {sorted(need-set(rows[0]) if rows else need)}')

groups = defaultdict(list)
for row in rows:
    groups[row['match_id']].append(row)

invalid = []
for key, group in groups.items():
    if (len(group)!=4 or Counter(x['label'] for x in group)!={'1':1,'0':3}
            or len({x['launch_age_s'] for x in group}) != 1):
        invalid.append(key)

mint_counts = Counter(x['mint'] for x in rows)
repeats = sum(n-1 for n in mint_counts.values() if n>1)

ordered = sorted(groups.items(),key=lambda item:int(next(x for x in item[1] if x['label']=='1')['creation_block_time']))
print('Dataset rows:',len(rows))
print('Matched groups:',len(groups))
print('Label counts:',dict(Counter(x['label'] for x in rows)))
print('Invalid 1-positive / 3-control / launch-age groups:',len(invalid))
print('Duplicate mint appearances:',repeats)

for start in FOLDS:
    if len(ordered)<start+4:
        print('Fold at',start,'has insufficient groups')
        continue
    train=[r for _,g in ordered[:start] for r in g]
    test=[r for _,g in ordered[start:start+4] for r in g]
    latest_train=max(int(r['snapshot_block_time']) for r in train)
    earliest_test=min(int(r['snapshot_block_time']) for r in test)
    gap=earliest_test-latest_train
    print(f'Fold train={start}, test={start+1}-{start+4}: earliest_test_snapshot - latest_train_snapshot = {gap}s', '(TIME OVERLAP)' if gap <= 0 else '(groups ordered by positive creation time)')

print('This audits structure and split timestamps only; it does not prove real-time feature availability or validate controls.')
