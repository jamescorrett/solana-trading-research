from __future__ import annotations

import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


WINDOWS = (1, 2, 5, 10)

POS_ANCHORS = Path(
    "data/processed/cented_positive_launch_anchors.json"
)

POS_SIG_DIR = Path(
    "data/raw/multi_token/preentry/signatures"
)

POS_TX_DIR = Path(
    "data/raw/multi_token/preentry/transactions"
)

CONTROLS = Path(
    "data/processed/verified_pump_controls.json"
)

CONTROL_DIR = Path(
    "data/raw/control_histories"
)

OUT_JSON = Path(
    "data/processed/cented_matched_entry_dataset_v1.json"
)

OUT_CSV = Path(
    "data/processed/cented_matched_entry_dataset_v1.csv"
)


def signature_of(tx):
    sigs = (
        tx.get("transaction", {})
        .get("signatures", [])
    )

    return sigs[0] if sigs else None


def account_info(tx):
    message = (
        tx.get("transaction", {})
        .get("message", {})
    )

    keys = message.get(
        "accountKeys",
        []
    )

    pubkeys = []
    signers = set()

    if keys and isinstance(keys[0], dict):

        for key in keys:

            pub = key.get("pubkey")

            if pub:
                pubkeys.append(pub)

                if key.get("signer"):
                    signers.add(pub)

    else:

        pubkeys = list(keys)

        required = (
            message.get("header", {})
            .get(
                "numRequiredSignatures",
                0
            )
        )

        signers = set(
            pubkeys[:required]
        )

    return pubkeys, signers


def token_owner_totals(
    meta,
    field,
    mint,
):
    totals = defaultdict(float)

    for balance in (
        meta.get(field, [])
        or []
    ):

        if balance.get("mint") != mint:
            continue

        owner = balance.get("owner")

        if not owner:
            continue

        ui = balance.get(
            "uiTokenAmount",
            {}
        )

        amount = ui.get("amount")
        decimals = ui.get("decimals")

        if (
            amount is None
            or decimals is None
        ):
            continue

        totals[owner] += (
            int(amount)
            / (10 ** int(decimals))
        )

    return totals


def economic_trade(
    tx,
    mint,
):
    meta = tx.get("meta") or {}

    if meta.get("err") is not None:
        return None

    pubkeys, signers = account_info(
        tx
    )

    pre = token_owner_totals(
        meta,
        "preTokenBalances",
        mint,
    )

    post = token_owner_totals(
        meta,
        "postTokenBalances",
        mint,
    )

    movers = []

    for owner in set(pre) | set(post):

        delta = (
            post.get(owner, 0.0)
            - pre.get(owner, 0.0)
        )

        if (
            abs(delta) > 1e-12
            and owner in signers
        ):
            movers.append(
                (owner, delta)
            )

    if len(movers) != 1:
        return None

    actor, token_delta = movers[0]

    try:
        index = pubkeys.index(actor)
    except ValueError:
        return None

    pre_sol = meta.get(
        "preBalances",
        []
    )

    post_sol = meta.get(
        "postBalances",
        []
    )

    if (
        index >= len(pre_sol)
        or index >= len(post_sol)
    ):
        return None

    sol_delta = (
        post_sol[index]
        - pre_sol[index]
    ) / 1_000_000_000

    if (
        token_delta > 0
        and sol_delta < 0
    ):
        side = "BUY"

    elif (
        token_delta < 0
        and sol_delta > 0
    ):
        side = "SELL"

    else:
        return None

    return {
        "side": side,
        "actor": actor,
        "block_time":
            int(tx["blockTime"]),
        "slot":
            int(tx.get("slot", 0)),
        "transaction_index":
            int(
                tx.get(
                    "transactionIndex",
                    -1
                )
            ),
        "approx_sol":
            abs(sol_delta),
    }


def dedupe_transactions(txs):
    result = {}

    for tx in txs:

        if not tx:
            continue

        sig = signature_of(tx)

        if not sig:
            continue

        result[sig] = tx

    return list(
        result.values()
    )


def extract_features(
    txs,
    mint,
    snapshot_time,
):
    txs = dedupe_transactions(
        txs
    )

    # Strict cutoff for both labels.
    txs = [
        tx
        for tx in txs
        if (
            tx.get("blockTime")
            is not None
            and int(tx["blockTime"])
            < snapshot_time
        )
    ]

    trades = []

    for tx in txs:

        trade = economic_trade(
            tx,
            mint,
        )

        if trade is not None:
            trades.append(trade)

    features = {}

    for seconds in WINDOWS:

        start = (
            snapshot_time
            - seconds
        )

        recent_tx = [
            tx
            for tx in txs
            if (
                start
                <= int(tx["blockTime"])
                < snapshot_time
            )
        ]

        failed = sum(
            (
                (tx.get("meta") or {})
                .get("err")
                is not None
            )
            for tx in recent_tx
        )

        successful = (
            len(recent_tx)
            - failed
        )

        recent_trades = [
            t
            for t in trades
            if (
                start
                <= t["block_time"]
                < snapshot_time
            )
        ]

        buys = [
            t
            for t in recent_trades
            if t["side"] == "BUY"
        ]

        sells = [
            t
            for t in recent_trades
            if t["side"] == "SELL"
        ]

        buyers = {
            t["actor"]
            for t in buys
        }

        sellers = {
            t["actor"]
            for t in sells
        }

        prior_buyers = {
            t["actor"]
            for t in trades
            if (
                t["side"] == "BUY"
                and t["block_time"]
                < start
            )
        }

        returning_buyers = (
            buyers
            & prior_buyers
        )

        buy_by_slot = Counter(
            t["slot"]
            for t in buys
        )

        prefix = f"w{seconds}_"

        features[
            prefix + "tx_total"
        ] = len(recent_tx)

        features[
            prefix + "tx_success"
        ] = successful

        features[
            prefix + "tx_failed"
        ] = failed

        features[
            prefix + "failure_rate"
        ] = (
            failed / len(recent_tx)
            if recent_tx
            else 0.0
        )

        features[
            prefix + "trades"
        ] = len(recent_trades)

        features[
            prefix + "buys"
        ] = len(buys)

        features[
            prefix + "sells"
        ] = len(sells)

        features[
            prefix + "unique_buyers"
        ] = len(buyers)

        features[
            prefix + "unique_sellers"
        ] = len(sellers)

        features[
            prefix + "returning_buyers"
        ] = len(returning_buyers)

        buy_sol = sum(
            t["approx_sol"]
            for t in buys
        )

        sell_sol = sum(
            t["approx_sol"]
            for t in sells
        )

        features[
            prefix + "buy_sol_approx"
        ] = buy_sol

        features[
            prefix + "sell_sol_approx"
        ] = sell_sol

        features[
            prefix + "net_sol_approx"
        ] = (
            buy_sol - sell_sol
        )

        features[
            prefix + "max_buys_same_slot"
        ] = (
            max(
                buy_by_slot.values()
            )
            if buy_by_slot
            else 0
        )

        features[
            prefix + "multi_buy_slots"
        ] = sum(
            n >= 2
            for n in (
                buy_by_slot.values()
            )
        )

    return features


# ------------------------------------------------------------
# Positive raw-history lookup
# ------------------------------------------------------------

signature_sets = {}

for path in POS_SIG_DIR.glob(
    "*.json"
):
    with path.open() as f:
        record = json.load(f)

    signature_sets[
        record["mint"]
    ] = record


def load_positive_transactions(
    mint,
):
    record = signature_sets[mint]

    txs = []

    for sig_row in record[
        "signatures"
    ]:

        sig = sig_row["signature"]

        path = (
            POS_TX_DIR
            / f"{sig}.json"
        )

        if not path.exists():
            continue

        with path.open() as f:
            rpc = json.load(f)

        tx = rpc.get("result")

        if tx:
            txs.append(tx)

    return txs


# ------------------------------------------------------------
# Build positive rows
# ------------------------------------------------------------

with POS_ANCHORS.open() as f:
    anchors = json.load(f)

pump_positives = [
    r
    for r in anchors
    if r["family"]
    == "PUMP_CREATE_V2"
]


rows = []


for positive in pump_positives:

    mint = positive["mint"]

    txs = load_positive_transactions(
        mint
    )

    snapshot_time = int(
        positive[
            "entry_block_time"
        ]
    )

    features = extract_features(
        txs,
        mint,
        snapshot_time,
    )

    rows.append({
        "label": 1,
        "role": "CENTED_ENTRY",
        "match_id": mint,
        "symbol":
            positive["symbol"],
        "mint": mint,
        "launch_age_s":
            positive[
                "entry_age_s"
            ],
        "creation_block_time":
            positive[
                "creation_block_time"
            ],
        "snapshot_block_time":
            snapshot_time,
        "creation_time_delta_s": 0,
        **features,
    })


# ------------------------------------------------------------
# Build control rows
# ------------------------------------------------------------

with CONTROLS.open() as f:
    verified = json.load(f)

controls = [
    r
    for r in verified["controls"]
    if r["verified_negative"]
]


for control in controls:

    mint = control["mint"]

    path = (
        CONTROL_DIR
        / f"{mint}.json"
    )

    with path.open() as f:
        record = json.load(f)

    txs = record[
        "transactions"
    ]

    snapshot_time = int(
        control[
            "snapshot_block_time"
        ]
    )

    features = extract_features(
        txs,
        mint,
        snapshot_time,
    )

    rows.append({
        "label": 0,
        "role": "MATCHED_CONTROL",
        "match_id":
            control[
                "positive_mint"
            ],
        "symbol": "",
        "mint": mint,
        "launch_age_s":
            control[
                "snapshot_age_s"
            ],
        "creation_block_time":
            control[
                "creation_block_time"
            ],
        "snapshot_block_time":
            snapshot_time,
        "creation_time_delta_s":
            control[
                "creation_time_delta_s"
            ],
        **features,
    })


# ------------------------------------------------------------
# Validate matching
# ------------------------------------------------------------

groups = defaultdict(list)

for row in rows:
    groups[row["match_id"]].append(
        row
    )

bad_groups = []

for match_id, group in groups.items():

    positives = sum(
        r["label"] == 1
        for r in group
    )

    negatives = sum(
        r["label"] == 0
        for r in group
    )

    ages = {
        r["launch_age_s"]
        for r in group
    }

    if (
        positives != 1
        or negatives != 3
        or len(ages) != 1
    ):
        bad_groups.append({
            "match_id": match_id,
            "positives": positives,
            "negatives": negatives,
            "ages": sorted(ages),
        })


if bad_groups:
    raise RuntimeError(
        f"Bad matched groups: "
        f"{bad_groups}"
    )


# ------------------------------------------------------------
# Save
# ------------------------------------------------------------

with OUT_JSON.open("w") as f:
    json.dump(
        rows,
        f,
        indent=2,
    )


fieldnames = list(
    rows[0].keys()
)

with OUT_CSV.open(
    "w",
    newline="",
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=fieldnames,
    )

    writer.writeheader()
    writer.writerows(rows)


# ------------------------------------------------------------
# Audit summary
# ------------------------------------------------------------

positives = [
    r for r in rows
    if r["label"] == 1
]

negatives = [
    r for r in rows
    if r["label"] == 0
]


print("=" * 110)
print("MATCHED CENTED ENTRY DATASET")
print("=" * 110)

print(
    f"Rows:               "
    f"{len(rows)}"
)

print(
    f"Cented entries:     "
    f"{len(positives)}"
)

print(
    f"Matched controls:   "
    f"{len(negatives)}"
)

print(
    f"Matched groups:     "
    f"{len(groups)}"
)

print(
    f"Bad groups:         "
    f"{len(bad_groups)}"
)

print()
print(
    "Cutoff rule: tx.blockTime "
    "< snapshot.blockTime"
)

print()


audit_features = [
    "w2_tx_failed",
    "w2_buys",
    "w2_sells",
    "w2_unique_buyers",
    "w5_tx_failed",
    "w5_failure_rate",
    "w5_buys",
    "w5_sells",
    "w5_unique_buyers",
    "w5_returning_buyers",
    "w5_net_sol_approx",
    "w10_buys",
    "w10_sells",
]


print(
    f"{'Feature':<28}"
    f"{'Positive median':>18}"
    f"{'Control median':>18}"
)

print("-" * 66)


for feature in audit_features:

    p = [
        r[feature]
        for r in positives
    ]

    n = [
        r[feature]
        for r in negatives
    ]

    print(
        f"{feature:<28}"
        f"{statistics.median(p):>18.3f}"
        f"{statistics.median(n):>18.3f}"
    )


print()
print(
    "Matched comparisons "
    "(positive > mean of its 3 controls)"
)

print("-" * 66)


for feature in audit_features:

    wins = 0
    ties = 0

    for match_id, group in groups.items():

        p = next(
            r
            for r in group
            if r["label"] == 1
        )

        controls_here = [
            r
            for r in group
            if r["label"] == 0
        ]

        mean_control = (
            sum(
                r[feature]
                for r in controls_here
            )
            / len(controls_here)
        )

        if p[feature] > mean_control:
            wins += 1

        elif p[feature] == mean_control:
            ties += 1

    print(
        f"{feature:<28}"
        f"{wins:>2}/32 higher"
        f"   ties={ties}"
    )


print()
print("Saved:")
print(OUT_CSV)
print(OUT_JSON)
