from cented_re.normalize import normalize_target_transaction


TARGET = "CentedWallet111111111111111111111111111111"

def make_doc(
    *,
    pre_token: int,
    post_token: int,
    decimals: int = 6,
    pre_sol: int = 10_000_000_000,
    post_sol: int = 7_000_000_000,
    instructions=None,
):
    instructions = instructions or ["Buy"]

    return {
        "result": {
            "slot": 123,
            "transactionIndex": 5,
            "blockTime": 999,
            "transaction": {
                "signatures": ["sig"],
                "message": {
                    "accountKeys": [
                        {
                            "pubkey": TARGET,
                            "signer": True,
                            "writable": True,
                            "source": "transaction",
                        }
                    ]
                },
            },
            "meta": {
                "fee": 5000,
                "preBalances": [pre_sol],
                "postBalances": [post_sol],
                "preTokenBalances": [
                    {
                        "owner": TARGET,
                        "mint": "mint1",
                        "uiTokenAmount": {
                            "amount": str(pre_token),
                            "decimals": decimals,
                        },
                    }
                ],
                "postTokenBalances": [
                    {
                        "owner": TARGET,
                        "mint": "mint1",
                        "uiTokenAmount": {
                            "amount": str(post_token),
                            "decimals": decimals,
                        },
                    }
                ],
                "logMessages": [
                    f"Program log: Instruction: {x}"
                    for x in instructions
                ],
            },
        }
    }


def test_first_buy():
    row = normalize_target_transaction(
        make_doc(pre_token=0, post_token=1_000_000),
        TARGET,
    )
    assert row.action == "FIRST_BUY"
    assert row.token_delta == 1.0


def test_add_buy():
    row = normalize_target_transaction(
        make_doc(pre_token=2_000_000, post_token=3_000_000),
        TARGET,
    )
    assert row.action == "ADD_BUY"
    assert row.token_balance_before == 2.0


def test_create_and_buy():
    row = normalize_target_transaction(
        make_doc(
            pre_token=0,
            post_token=1_000_000,
            instructions=["CreateV2", "BuyV2"],
        ),
        TARGET,
    )
    assert row.action == "CREATE_AND_BUY"


def test_full_sell():
    row = normalize_target_transaction(
        make_doc(
            pre_token=2_000_000,
            post_token=0,
            pre_sol=7_000_000_000,
            post_sol=9_000_000_000,
            instructions=["Sell"],
        ),
        TARGET,
    )
    assert row.action == "FULL_SELL"
    assert row.token_delta == -2.0


def test_partial_sell():
    row = normalize_target_transaction(
        make_doc(
            pre_token=2_000_000,
            post_token=1_000_000,
            pre_sol=7_000_000_000,
            post_sol=8_000_000_000,
            instructions=["SellV2"],
        ),
        TARGET,
    )
    assert row.action == "PARTIAL_SELL"
