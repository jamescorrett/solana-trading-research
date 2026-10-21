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

N_PERMUTATIONS = 1000
N_BOOTSTRAPS = 5000
SEED = 42


with DATA.open() as f:
    rows = list(csv.DictReader(f))


for i, row in enumerate(rows):
    row["_index"] = i

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


groups = defaultdict(list)

for row in rows:
    groups[
        row["match_id"]
    ].append(row)


# Chronological ordering is defined by the
# real Cented positive in each matched group.
def group_time(group):
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
        group_time(item[1]),
)


X = np.array([
    [
        row[feature]
        for feature in FEATURES
    ]
    for row in rows
])


true_labels = np.array([
    row["label"]
    for row in rows
])


FOLD_STARTS = [
    16,
    20,
    24,
    28,
]


def make_model():
    return Pipeline([
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


def evaluate(labels):

    all_y = []
    all_probability = []

    group_predictions = (
        defaultdict(list)
    )

    for start in FOLD_STARTS:

        train_groups = (
            ordered_groups[:start]
        )

        test_groups = (
            ordered_groups[
                start:start + 4
            ]
        )

        train_indices = [
            row["_index"]
            for _, group in train_groups
            for row in group
        ]

        test_indices = [
            row["_index"]
            for _, group in test_groups
            for row in group
        ]

        model = make_model()

        model.fit(
            X[train_indices],
            labels[train_indices],
        )

        probabilities = (
            model.predict_proba(
                X[test_indices]
            )[:, 1]
        )

        for index, probability in zip(
            test_indices,
            probabilities,
        ):
            row = rows[index]

            group_predictions[
                row["match_id"]
            ].append({
                "index": index,
                "label":
                    int(labels[index]),
                "probability":
                    float(probability),
            })

            all_y.append(
                int(labels[index])
            )

            all_probability.append(
                float(probability)
            )

    auc = roc_auc_score(
        all_y,
        all_probability,
    )

    ap = average_precision_score(
        all_y,
        all_probability,
    )

    top1_credit = []
    ranks = []

    for predictions in (
        group_predictions.values()
    ):

        positive = next(
            p
            for p in predictions
            if p["label"] == 1
        )

        p_positive = (
            positive["probability"]
        )

        greater = sum(
            p["probability"]
            > p_positive
            for p in predictions
        )

        equal = sum(
            np.isclose(
                p["probability"],
                p_positive,
            )
            for p in predictions
        )

        rank = (
            greater
            + 1
            + (equal - 1) / 2
        )

        ranks.append(rank)

        max_probability = max(
            p["probability"]
            for p in predictions
        )

        if np.isclose(
            p_positive,
            max_probability,
        ):
            tied_max = sum(
                np.isclose(
                    p["probability"],
                    max_probability,
                )
                for p in predictions
            )

            top1_credit.append(
                1 / tied_max
            )

        else:
            top1_credit.append(0.0)

    return {
        "auc": auc,
        "ap": ap,
        "top1":
            np.mean(top1_credit),
        "mean_rank":
            np.mean(ranks),
        "group_predictions":
            group_predictions,
    }


# ------------------------------------------------------------
# Observed chronological performance
# ------------------------------------------------------------

observed = evaluate(
    true_labels
)


print("=" * 100)
print("MATCHED ENTRY SIGNAL VALIDATION")
print("=" * 100)

print(
    f"Observed ROC-AUC:    "
    f"{observed['auc']:.3f}"
)

print(
    f"Observed AP:         "
    f"{observed['ap']:.3f}"
)

print(
    f"Observed top-1:      "
    f"{observed['top1']:.1%}"
)

print(
    f"Observed mean rank:  "
    f"{observed['mean_rank']:.2f}"
)


# ------------------------------------------------------------
# Group-preserving permutation test
#
# Under the null, randomly choose exactly one
# of the four tokens in every matched group
# to be the "selected" token.
#
# Features and chronological structure stay
# completely unchanged.
# ------------------------------------------------------------

rng = np.random.default_rng(SEED)

null_auc = []
null_ap = []
null_top1 = []
null_rank = []


print()
print(
    f"Running {N_PERMUTATIONS:,} "
    f"group-preserving permutations..."
)


for permutation in range(
    N_PERMUTATIONS
):

    labels = np.zeros(
        len(rows),
        dtype=int,
    )

    for _, group in ordered_groups:

        indices = [
            row["_index"]
            for row in group
        ]

        chosen = rng.choice(
            indices
        )

        labels[chosen] = 1

    result = evaluate(labels)

    null_auc.append(
        result["auc"]
    )

    null_ap.append(
        result["ap"]
    )

    null_top1.append(
        result["top1"]
    )

    null_rank.append(
        result["mean_rank"]
    )


null_auc = np.array(
    null_auc
)

null_ap = np.array(
    null_ap
)

null_top1 = np.array(
    null_top1
)

null_rank = np.array(
    null_rank
)


def upper_p(null, observed_value):
    return (
        1
        + np.sum(
            null >= observed_value
        )
    ) / (
        len(null) + 1
    )


def lower_p(null, observed_value):
    return (
        1
        + np.sum(
            null <= observed_value
        )
    ) / (
        len(null) + 1
    )


print()
print("=" * 100)
print("PERMUTATION TEST")
print("=" * 100)

print(
    f"{'Metric':<18}"
    f"{'Observed':>12}"
    f"{'Null mean':>14}"
    f"{'Empirical p':>16}"
)

print("-" * 60)

print(
    f"{'ROC-AUC':<18}"
    f"{observed['auc']:>12.3f}"
    f"{null_auc.mean():>14.3f}"
    f"{upper_p(null_auc, observed['auc']):>16.4f}"
)

print(
    f"{'AP':<18}"
    f"{observed['ap']:>12.3f}"
    f"{null_ap.mean():>14.3f}"
    f"{upper_p(null_ap, observed['ap']):>16.4f}"
)

print(
    f"{'Top-1 rate':<18}"
    f"{observed['top1']:>12.3f}"
    f"{null_top1.mean():>14.3f}"
    f"{upper_p(null_top1, observed['top1']):>16.4f}"
)

print(
    f"{'Mean rank':<18}"
    f"{observed['mean_rank']:>12.3f}"
    f"{null_rank.mean():>14.3f}"
    f"{lower_p(null_rank, observed['mean_rank']):>16.4f}"
)


# ------------------------------------------------------------
# Group bootstrap confidence intervals for the
# 16 held-out matched groups.
# ------------------------------------------------------------

observed_groups = list(
    observed[
        "group_predictions"
    ].values()
)


def metrics_from_predictions(
    sampled_groups
):

    y = []
    probability = []

    top1 = []
    ranks = []

    for predictions in sampled_groups:

        y.extend(
            p["label"]
            for p in predictions
        )

        probability.extend(
            p["probability"]
            for p in predictions
        )

        positive = next(
            p
            for p in predictions
            if p["label"] == 1
        )

        positive_probability = (
            positive["probability"]
        )

        greater = sum(
            p["probability"]
            > positive_probability
            for p in predictions
        )

        equal = sum(
            np.isclose(
                p["probability"],
                positive_probability,
            )
            for p in predictions
        )

        rank = (
            greater
            + 1
            + (equal - 1) / 2
        )

        ranks.append(rank)

        maximum = max(
            p["probability"]
            for p in predictions
        )

        if np.isclose(
            positive_probability,
            maximum,
        ):
            ties = sum(
                np.isclose(
                    p["probability"],
                    maximum,
                )
                for p in predictions
            )

            top1.append(
                1 / ties
            )

        else:
            top1.append(0.0)

    return (
        roc_auc_score(
            y,
            probability,
        ),
        average_precision_score(
            y,
            probability,
        ),
        np.mean(top1),
        np.mean(ranks),
    )


bootstrap = []


for _ in range(
    N_BOOTSTRAPS
):

    indices = rng.integers(
        0,
        len(observed_groups),
        size=len(observed_groups),
    )

    sampled = [
        observed_groups[i]
        for i in indices
    ]

    bootstrap.append(
        metrics_from_predictions(
            sampled
        )
    )


bootstrap = np.array(
    bootstrap
)


def ci(column):
    low, high = np.percentile(
        bootstrap[:, column],
        [2.5, 97.5],
    )

    return low, high


print()
print("=" * 100)
print("GROUP-BOOTSTRAP 95% CONFIDENCE INTERVALS")
print("=" * 100)

names = [
    "ROC-AUC",
    "AP",
    "Top-1 rate",
    "Mean rank",
]

observed_values = [
    observed["auc"],
    observed["ap"],
    observed["top1"],
    observed["mean_rank"],
]


for i, (
    name,
    value,
) in enumerate(
    zip(
        names,
        observed_values,
    )
):

    low, high = ci(i)

    print(
        f"{name:<18}"
        f"{value:>8.3f}"
        f"   95% CI "
        f"[{low:.3f}, {high:.3f}]"
    )


print()
print("=" * 100)
print("INTERPRETATION NOTE")
print("=" * 100)

print(
    "Permutation testing preserves the 1-positive / "
    "3-control matched-group design and chronological "
    "evaluation structure."
)

print(
    "These results strengthen internal evidence, but "
    "they do not replace evaluation on a genuinely "
    "new future dataset."
)

print(
    "Feature/model choices were developed using this "
    "research dataset, so results should be presented "
    "as exploratory rather than final production "
    "performance."
)
