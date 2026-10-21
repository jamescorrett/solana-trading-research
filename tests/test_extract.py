from cented_re.config import DEFAULT_PUMP_PROGRAM, DEFAULT_TARGET
from cented_re.extract import (
    account_keys,
    logs_look_like_pump_launch,
    logs_result_from_notification,
    looks_like_pump_launch,
    result_from_notification,
    signature,
    slot,
)


def fixture_result():
    return {
        "slot": 12345,
        "signature": "sig-123",
        "transaction": {
            "transaction": {
                "message": {
                    "accountKeys": [
                        {"pubkey": "creator", "signer": True, "writable": True},
                        {"pubkey": DEFAULT_PUMP_PROGRAM, "signer": False, "writable": False},
                        {"pubkey": DEFAULT_TARGET, "signer": True, "writable": True},
                    ],
                    "instructions": [],
                },
                "signatures": ["fallback-sig"],
            },
            "meta": {
                "logMessages": ["Program log: Instruction: CreateV2"],
                "loadedAddresses": {"writable": ["lookup-1"], "readonly": []},
            },
        },
    }


def test_enhanced_notification_extractors_remain_compatible():
    result = fixture_result()
    message = {"method": "transactionNotification", "params": {"result": result}}
    assert result_from_notification(message) == result
    assert slot(result) == 12345
    assert signature(result) == "sig-123"
    assert account_keys(result) == ["creator", DEFAULT_PUMP_PROGRAM, DEFAULT_TARGET, "lookup-1"]
    assert looks_like_pump_launch(result, DEFAULT_PUMP_PROGRAM)


def test_standard_logs_notification_extractors():
    message = {
        "method": "logsNotification",
        "params": {
            "subscription": 10,
            "result": {
                "context": {"slot": 88},
                "value": {
                    "signature": "sig-logs",
                    "err": None,
                    "logs": ["Program log: Instruction: CreateV2"],
                },
            },
        },
    }
    parsed = logs_result_from_notification(message)
    assert parsed is not None
    event_slot, value = parsed
    assert event_slot == 88
    assert value["signature"] == "sig-logs"
    assert logs_look_like_pump_launch(value)


def test_non_notifications_ignored():
    assert result_from_notification({"id": 420, "result": 99}) is None
    assert logs_result_from_notification({"id": 420, "result": 99}) is None
