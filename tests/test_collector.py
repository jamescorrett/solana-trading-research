from pathlib import Path

from cented_re.collector import (
    PUMP_SUBSCRIBE_REQUEST_ID,
    TARGET_SUBSCRIBE_REQUEST_ID,
    make_log_envelope,
    subscription_requests,
)
from cented_re.config import Settings
from cented_re.extract import CREATE_LOG_MARKERS


def settings(tmp_path: Path) -> Settings:
    return Settings(
        HELIUS_API_KEY="test-key",
        TARGET_WALLET="target-wallet",
        PUMP_PROGRAM_ID="pump-program",
        DATA_DIR=tmp_path,
    )


def test_standard_logs_subscriptions_use_one_mention_each(tmp_path):
    requests = subscription_requests(settings(tmp_path))
    assert len(requests) == 2
    by_id = {req["id"]: req for req in requests}
    assert by_id[PUMP_SUBSCRIBE_REQUEST_ID]["method"] == "logsSubscribe"
    assert by_id[PUMP_SUBSCRIBE_REQUEST_ID]["params"][0] == {"mentions": ["pump-program"]}
    assert by_id[TARGET_SUBSCRIBE_REQUEST_ID]["params"][0] == {"mentions": ["target-wallet"]}


def test_log_envelope_tags_launch(tmp_path):
    message = {
        "method": "logsNotification",
        "params": {
            "subscription": 99,
            "result": {
                "context": {"slot": 7},
                "value": {
                    "signature": "abc",
                    "err": None,
                    "logs": [f"Program log: {CREATE_LOG_MARKERS[0]}"],
                },
            },
        },
    }
    env = make_log_envelope(message, "pump", settings(tmp_path))
    assert env is not None
    assert env["slot"] == 7
    assert env["signature"] == "abc"
    assert env["tags"]["pump_subscription"] is True
    assert env["tags"]["pump_launch_candidate"] is True
    assert env["raw_notification"] == message
