# Solana Trading Behaviour Research

A Python research project investigating observable trading activity around a publicly attributed Solana wallet. The aim is to understand what can be inferred from on-chain evidence **before** an entry, without relying on information that only became available afterwards.

This is research tooling, **not a trading bot** or a demonstrated profitable strategy.

## What is in the repository

- Asynchronous WebSocket collector using Solana `logsSubscribe` for the Pump.fun program and a configurable target wallet.
- Append-only JSONL data containing signatures, slots, receive timestamps, logs and original notifications.
- Separate streams for general logs, target activity and potential launches.
- Reconnection handling, data inspection commands and scripts for reconstructing transaction sequences.
- Tests covering collection, extraction, market-data handling and normalisation.

The analysis scripts examine observed trading sequences. The collector does not, by itself, train a predictive model or establish profitability.

## Running it

Requires Python 3.11+ and a Helius API key.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Set `HELIUS_API_KEY` in `.env`, then run:

```bash
cented-collect
```

Inspect collected records:

```bash
cented-inspect data/raw/logs
python scripts/show_latest.py
```

Run tests with `pytest -q`. Raw outputs are stored in date/hour-partitioned directories under `data/raw/`. The real API key and collected raw data should remain outside version control.

## Research method

The main concern is look-ahead bias. A feature used to explain an entry must have been observable before that entry:

```text
feature_available_at <= snapshot_cutoff < target_action
```

The workflow is to collect raw evidence, establish which transactions are relevant, reconstruct the timing of actions and test explanations against what was observable at that point. See [research notes](RESEARCH_NOTES.md) for examples, with observations kept distinct from hypotheses.

Public attribution does not prove wallet ownership. A single trading sequence is not evidence of a general strategy.

## AI-assisted development

I used AI-assisted coding for parts of the implementation and debugging. I led the investigation: selecting research questions, making engineering and data-collection decisions, designing validation approaches, checking outputs and interpreting results. AI-generated suggestions were treated as code and hypotheses to review, not as independent evidence.

## Matched-entry evaluation

An exploratory matched-token evaluation is documented in [EVALUATION.md](EVALUATION.md),
with the model, permutation tests, bootstrap validation, and a reviewed derived feature dataset.
The figures describe internal retrospective evaluation, not trading performance or an
independent future holdout.
