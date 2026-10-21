from cented_re.market import between, parse_market_event, trade_features

MINT = "Mint1111111111111111111111111111111111111"
ALICE = "Alice111111111111111111111111111111111111"
CURVE = "Curve111111111111111111111111111111111111"


def make_tx(sig="sig", slot=100, idx=1, block_time=1000, instruction="Buy", pre_tokens=0, post_tokens=1_000_000, gross=1_000_000_000):
    buy = instruction in {"Buy", "BuyV2"}
    source, destination = (ALICE, CURVE) if buy else (CURVE, ALICE)
    return {"result": {
        "slot": slot, "transactionIndex": idx, "blockTime": block_time,
        "transaction": {"signatures": [sig], "message": {"accountKeys": [{"pubkey": ALICE, "signer": True, "writable": True}]}},
        "meta": {
            "err": None, "preBalances": [10_000_000_000], "postBalances": [9_000_000_000],
            "preTokenBalances": [{"owner": ALICE, "mint": MINT, "uiTokenAmount": {"amount": str(pre_tokens), "decimals": 6}}],
            "postTokenBalances": [{"owner": ALICE, "mint": MINT, "uiTokenAmount": {"amount": str(post_tokens), "decimals": 6}}],
            "logMessages": [f"Program log: Instruction: {instruction}"],
            "innerInstructions": [{"index": 3, "instructions": [{"program": "system", "parsed": {"type": "transfer", "info": {"source": source, "destination": destination, "lamports": gross}}}]}],
        }
    }}


def test_buy_recovers_actor_and_gross_sol():
    e = parse_market_event(make_tx(pre_tokens=0, post_tokens=2_000_000, gross=3_000_000_000), MINT)
    assert e.action == "BUY" and e.actor == ALICE and e.token_delta == 2.0 and e.gross_sol == 3.0


def test_sell():
    e = parse_market_event(make_tx(instruction="Sell", pre_tokens=2_000_000, post_tokens=500_000, gross=750_000_000), MINT)
    assert e.action == "SELL" and e.actor == ALICE and e.token_delta == -1.5 and e.gross_sol == 0.75


def test_ordering_and_no_leakage():
    a = parse_market_event(make_tx(sig="a", slot=10, idx=1, block_time=999), MINT)
    b = parse_market_event(make_tx(sig="b", slot=10, idx=2, block_time=1000), MINT)
    c = parse_market_event(make_tx(sig="c", slot=10, idx=3, block_time=1000), MINT)
    assert [e.signature for e in between([a,b,c], a, c)] == ["b"]
    f = trade_features([a,b,c], end=b, seconds=5)
    assert f["trades"] == 1
