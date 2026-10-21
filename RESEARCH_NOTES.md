# Cented Reverse Engineering — Research Notes

## Confirmed findings

### F1 — CyaE... is a genuine Cented execution wallet
Known-positive Pump transaction shows:
- wallet is signer
- wallet is writable
- wallet SOL decreases
- wallet token balance increases
- Pump program is invoked

### F2 — Create-and-buy activity exists
Observed transaction:
- Instruction: CreateV2
- followed by Instruction: BuyV2
- ~22 SOL wallet outflow
- newly created mint is also signer

Classification:
CREATE_AND_BUY

## Hypotheses

### H1 — ~3 SOL base entry + ~0.25 SOL add tranche
Observed OPTIMUS sequence:
- initial buy: wallet delta ~-3.0074 SOL
- 10 slots / ~4 seconds later:
- add buy: wallet delta ~-0.2555 SOL

Interpretation:
Likely nominal sizing parameters of approximately:
- 3.0 SOL initial entry
- 0.25 SOL continuation/add

Status:
Strongly supported by one sequence.
Needs population-level validation.

### H2 — Adds may be momentum-confirmation driven
Between the first OPTIMUS buy and the 0.25 SOL add, effective token price increased substantially.

Possible triggers:
- price acceleration
- buy velocity
- smart-wallet participation
- volume acceleration
- low sell pressure

Status:
Speculative.

our earlier “software-defined sizing” hypothesis remains plausible, but the discovery of Axiom means we must distinguish Cented's strategy from Axiom's execution machinery. Things like durable nonces, priority-fee construction, fee routing and perhaps some transaction bundling may simply be Axiom implementation details.