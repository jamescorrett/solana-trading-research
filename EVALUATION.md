# Matched-entry signal evaluation (exploratory)

This document describes an internal research experiment examining whether recent on-chain activity helps distinguish a publicly attributed wallet's chosen tokens from matched alternative tokens. It is **not** evidence of a deployed predictor, profitable trading strategy or successful replication of the wallet's complete strategy.

## Research question and data

At the time of an observed first entry, did the selected token have distinguishable recent transaction features compared with alternatives of the same launch age?

The locally evaluated matched dataset contains **32 groups / 128 observations**: one observed target entry and three retrospectively selected controls in each group (32 positive examples, 96 controls). The dataset audit reported no invalid 1:3 groups, no repeated mints and consistent launch ages within groups. Selection and verification of controls is retrospective and may introduce bias. These results do not establish whether a comparable set of controls could have been identified at a live decision point.

Nine modelling features were used:

| Window | Features |
|---|---|
| 2 seconds | Buys, unique buyers |
| 5 seconds | Buys, unique buyers, failed transactions, failure rate, maximum buys in one slot |
| 10 seconds | Buys, unique buyers |

The dataset builder (`scripts/build_matched_entry_dataset.py`) includes only transactions satisfying `blockTime < snapshot_time`. This prevents features based on later **block timestamps**, but does not establish when a live system would have received those transactions. Some trade classifications are approximated from balance movements.

## Model and chronological evaluation

The experiment uses `StandardScaler` followed by `LogisticRegression` (`C=1.0`, `class_weight="balanced"`, `max_iter=5000`, `random_state=42`). The scaler and classifier are fitted anew **inside each training fold**.

Matched groups are ordered by the positive token's **creation block time**. Expanding folds train on groups 1–16 / 1–20 / 1–24 / 1–28 and test on groups 17–20 / 21–24 / 25–28 / 29–32 respectively. The pooled held-out metrics therefore cover **16 groups / 64 observations**, not 128 independently tested observations.

A local structural/chronology audit, using the same creation-time group ordering as the evaluation scripts, measured the separation between the latest training snapshot and earliest testing snapshot at **299, 165, 1,064, and 458 seconds** across the four folds. Thus it found no snapshot-time train/test overlap in those folds. This does **not** establish live availability of every feature or eliminate retrospective selection bias.

## Results reproduced in the researcher's local environment

The researcher reran the model-evaluation and validation scripts on the saved original matched CSV on 21 October 2026, reproducing the previously reported values below. The underlying original dataset has **not been independently inspected or rerun by the reviewer**. If a derived features-only CSV is made public, readers can independently run the analysis code on those derived inputs, though that will not reproduce the preceding selection and raw-data reconstruction process.

| Metric | Local result |
|---|---:|
| Pooled chronological ROC-AUC | **0.680** |
| Pooled chronological average precision (AP) | **0.461** |
| Held-out target top-ranked | **8/16 = 50.0%** (random group baseline 25%) |
| ROC-AUC permutation p-value | **0.0060** |
| AP permutation p-value | **0.0070** |
| Top-1 permutation p-value | **0.0130** |
| ROC-AUC 95% group-bootstrap interval | **[0.540, 0.805]** |
| AP 95% group-bootstrap interval | **[0.369, 0.652]** |
| Top-1 95% group-bootstrap interval | **[0.250, 0.750]** |

Per-fold held-out ROC-AUCs were **0.812, 0.802, 0.479, and 0.771** (four groups per fold), showing meaningful variation with the small test samples.

The model-evaluation script reports **mean rank 1.81** using the exact sorted rank of the positive token in each held-out group. The validation script instead assigns **average ranks for near-tied probabilities** (via `np.isclose`) and reports **1.906**, with a group-bootstrap interval of **[1.406, 2.469]**. These are different ranking conventions, not independent model outcomes. Both report 50% top-1 performance.

### Statistical testing limitations

The validation script uses **1,000 group-preserving permutations** with one randomly reassigned positive label per four-token group and refits the model across the same folds on each iteration. It uses **5,000 bootstrap resamples of held-out group predictions**, *not* repeated refits, to estimate intervals. The bootstrap therefore omits training and feature-selection uncertainty. Small numbers of positive test groups and exploratory feature/model choices reduce the strength of the inferential claims. In particular, the permutation p-values are **exploratory**, not independent confirmatory evidence after all research decisions have been fixed.

Single-feature matching results reported by the evaluation script use **all 32 groups** and are descriptive, **not** separate held-out performances.

## Reproducing the published evaluation

Python 3.11+ is recommended.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-evaluation.txt
mkdir -p data/processed
cp evaluation-data/cented_matched_entry_dataset_v1.csv data/processed/
python scripts/audit_matched_dataset.py
python scripts/evaluate_matched_entry_model.py
python scripts/validate_matched_entry_signal.py
```

The `evaluation-data/` input, if published, contains only features, labels, group identifiers and timing fields, with synthetic token/group names rather than raw wallet, transaction or mint identifiers. This **reproduces downstream calculations only**. Inspect it before publication. The original builder requires separately collected or verified inputs:

- `data/processed/cented_positive_launch_anchors.json`
- `data/processed/verified_pump_controls.json`
- `data/raw/multi_token/preentry/signatures/*.json`
- `data/raw/multi_token/preentry/transactions/*.json`
- `data/raw/control_histories/*.json`

Those inputs are not provided in this public evaluation package. The project deliberately does not publish raw transaction archives, API keys or local credentials.

## Future research

Freeze the control-selection rules, feature definitions, preprocessing, model and evaluation procedure, then evaluate on **newly collected, genuinely unseen** future entries and contemporaneously eligible controls. Record receipt timestamps to evaluate real-world feature availability. Report results regardless of whether the future test succeeds.

## Attribution

The researcher directed experiment design, collection, modelling questions and interpretation, with AI assistance on parts of the implementation and debugging. The claims above are limited to what the provided methods and local output support.
