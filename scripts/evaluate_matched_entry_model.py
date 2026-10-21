from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


DATA = Path(
    "data/processed/"
    "cented_matched_entry_dataset_v1.csv"
)


FEATURES = [
    "w2_buys",
    "w2_unique_buyers",

    "w5_buys",
    "w5_unique_buyers",
    "w5_tx_failed",
    "w5_failure_rate",
    "w5_max_buys_same_slot",

    "w10_buys",
    "w10_unique_buyers",
]


with DATA.open() as f:
    rows = list(
        csv.DictReader(f)
    )


for row in rows:

    row["label"] = int(
        row["label"]
    )

    row["creation_block_time"] = int(
        row["creation_block_time"]
    )

    for feature in FEATURES:
        row[feature] = float(
            row[feature]
        )


# ------------------------------------------------------------
# Group rows by matched positive.
# ------------------------------------------------------------

groups = defaultdict(list)

for row in rows:
    groups[
        row["match_id"]
    ].append(row)


def positive_time(group):
    positive = next(
        r
        for r in group
        if r["label"] == 1
    )

    return positive[
        "creation_block_time"
    ]


ordered_groups = sorted(
    groups.items(),
    key=lambda item:
        positive_time(item[1]),
)


print("=" * 100)
print("MATCHED ENTRY MODEL EVALUATION")
print("=" * 100)

print(
    f"Matched groups: {len(ordered_groups)}"
)

print(
    f"Rows:           {len(rows)}"
)

print(
    f"Features:       {len(FEATURES)}"
)

print()

print("Primary features:")

for feature in FEATURES:
    print(f"  {feature}")


# ------------------------------------------------------------
# First: single-feature matched ranking.
#
# Random chance for being highest among four
# matched tokens = 25%.
#
# Give fractional credit for ties.
# ------------------------------------------------------------

print()
print("=" * 100)
print("SINGLE-FEATURE MATCHED RANKING")
print("=" * 100)

print(
    f"{'Feature':<28}"
    f"{'Top-1 credit':>16}"
    f"{'Mean rank':>14}"
)

print("-" * 58)


def rank_group(
    group,
    feature,
):

    values = [
        (
            float(r[feature]),
            r["label"],
        )
        for r in group
    ]

    positive_value = next(
        value
        for value, label in values
        if label == 1
    )

    greater = sum(
        value > positive_value
        for value, _ in values
    )

    equal = sum(
        value == positive_value
        for value, _ in values
    )

    # Average rank under ties.
    rank = (
        greater
        + 1
        + (equal - 1) / 2
    )

    maximum = max(
        value
        for value, _ in values
    )

    if positive_value == maximum:

        tied_max = sum(
            value == maximum
            for value, _ in values
        )

        top_credit = (
            1.0 / tied_max
        )

    else:
        top_credit = 0.0

    return rank, top_credit


for feature in FEATURES:

    ranks = []
    credits = []

    for _, group in ordered_groups:

        rank, credit = rank_group(
            group,
            feature,
        )

        ranks.append(rank)
        credits.append(credit)

    print(
        f"{feature:<28}"
        f"{sum(credits) / len(credits):>15.1%}"
        f"{sum(ranks) / len(ranks):>14.2f}"
    )


print()
print(
    "Random baseline: "
    "25% top-1, mean rank 2.50"
)


# ------------------------------------------------------------
# Expanding chronological evaluation.
#
# Train:
#   first 16 groups
#
# Test:
#   next 4
#
# Then expand training by four groups and repeat.
#
# This produces predictions for the final
# 16 matched groups without training on future groups.
# ------------------------------------------------------------

print()
print("=" * 100)
print("EXPANDING CHRONOLOGICAL LOGISTIC REGRESSION")
print("=" * 100)


all_y = []
all_prob = []
test_predictions = []

coefficient_rows = []


fold_starts = [
    16,
    20,
    24,
    28,
]


for fold_num, start in enumerate(
    fold_starts,
    1,
):

    train_groups = (
        ordered_groups[:start]
    )

    test_groups = (
        ordered_groups[
            start:start + 4
        ]
    )


    train_rows = [
        row
        for _, group in train_groups
        for row in group
    ]

    test_rows = [
        row
        for _, group in test_groups
        for row in group
    ]


    X_train = np.array([
        [
            row[f]
            for f in FEATURES
        ]
        for row in train_rows
    ])

    y_train = np.array([
        row["label"]
        for row in train_rows
    ])


    X_test = np.array([
        [
            row[f]
            for f in FEATURES
        ]
        for row in test_rows
    ])

    y_test = np.array([
        row["label"]
        for row in test_rows
    ])


    model = Pipeline([
        (
            "scale",
            StandardScaler(),
        ),
        (
            "logistic",
            LogisticRegression(
                class_weight="balanced",
                C=1.0,
                max_iter=5000,
                random_state=42,
            ),
        ),
    ])


    model.fit(
        X_train,
        y_train,
    )


    probabilities = (
        model.predict_proba(
            X_test
        )[:, 1]
    )


    fold_auc = roc_auc_score(
        y_test,
        probabilities,
    )

    fold_ap = (
        average_precision_score(
            y_test,
            probabilities,
        )
    )


    print(
        f"Fold {fold_num}: "
        f"train groups={len(train_groups):>2} "
        f"test groups={len(test_groups):>2} "
        f"AUC={fold_auc:.3f} "
        f"AP={fold_ap:.3f}"
    )


    all_y.extend(
        y_test.tolist()
    )

    all_prob.extend(
        probabilities.tolist()
    )


    for row, probability in zip(
        test_rows,
        probabilities,
    ):

        test_predictions.append({
            "match_id":
                row["match_id"],

            "label":
                row["label"],

            "probability":
                float(probability),
        })


    coefficients = (
        model.named_steps[
            "logistic"
        ].coef_[0]
    )

    coefficient_rows.append(
        coefficients
    )


# ------------------------------------------------------------
# Aggregate chronological metrics.
# ------------------------------------------------------------

auc = roc_auc_score(
    all_y,
    all_prob,
)

ap = average_precision_score(
    all_y,
    all_prob,
)


print()
print("-" * 100)

print(
    f"Combined chronological ROC-AUC: "
    f"{auc:.3f}"
)

print(
    f"Combined chronological AP:      "
    f"{ap:.3f}"
)

print(
    "Random baselines: "
    "ROC-AUC=0.500, AP=0.250"
)


# ------------------------------------------------------------
# Ranking performance inside each held-out group.
# ------------------------------------------------------------

pred_groups = defaultdict(list)

for prediction in test_predictions:
    pred_groups[
        prediction["match_id"]
    ].append(prediction)


top1 = 0
ranks = []
rr = []


print()
print("=" * 100)
print("HELD-OUT MATCHED RANKING")
print("=" * 100)


for match_id, predictions in (
    pred_groups.items()
):

    predictions = sorted(
        predictions,
        key=lambda r:
            r["probability"],
        reverse=True,
    )

    positive_index = next(
        i
        for i, r in enumerate(
            predictions,
            1,
        )
        if r["label"] == 1
    )

    ranks.append(
        positive_index
    )

    rr.append(
        1 / positive_index
    )

    if positive_index == 1:
        top1 += 1


print(
    f"Held-out groups:       "
    f"{len(pred_groups)}"
)

print(
    f"Cented token ranked #1:"
    f" {top1}/{len(pred_groups)} "
    f"({top1 / len(pred_groups):.1%})"
)

print(
    f"Mean Cented rank:      "
    f"{sum(ranks) / len(ranks):.2f}"
)

print(
    f"Mean reciprocal rank:  "
    f"{sum(rr) / len(rr):.3f}"
)

print()

print(
    "Random ranking baseline:"
)

print(
    "  #1 rate = 25.0%"
)

print(
    "  mean rank = 2.50"
)

print(
    "  mean reciprocal rank "
    "≈ 0.521"
)


# ------------------------------------------------------------
# Average standardized coefficients.
# Exploratory interpretation only.
# ------------------------------------------------------------

mean_coefs = np.mean(
    np.array(coefficient_rows),
    axis=0,
)


ranked_coefficients = sorted(
    zip(
        FEATURES,
        mean_coefs,
    ),
    key=lambda x:
        abs(x[1]),
    reverse=True,
)


print()
print("=" * 100)
print("AVERAGE STANDARDIZED LOGISTIC COEFFICIENTS")
print("=" * 100)

print(
    "Positive coefficient = "
    "associated with Cented selection."
)

print()


for feature, coefficient in (
    ranked_coefficients
):

    print(
        f"{feature:<28}"
        f"{coefficient:>9.3f}"
    )


print()
print(
    "NOTE: this is an internal chronological "
    "evaluation, not yet a genuinely future "
    "independent holdout dataset."
)
