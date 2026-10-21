from __future__ import annotations

from typing import Any


CREATE_LOG_MARKERS = (
    "Instruction: Create",
    "Instruction: CreateV2",
)


def result_from_notification(message: dict[str, Any]) -> dict[str, Any] | None:
    """Extract an Enhanced transactionSubscribe result (paid-mode compatibility)."""
    if message.get("method") != "transactionNotification":
        return None
    result = message.get("params", {}).get("result")
    return result if isinstance(result, dict) else None


def logs_result_from_notification(message: dict[str, Any]) -> tuple[int | None, dict[str, Any]] | None:
    """Extract (slot, value) from a standard Solana logsSubscribe notification."""
    if message.get("method") != "logsNotification":
        return None
    result = message.get("params", {}).get("result")
    if not isinstance(result, dict):
        return None
    context = result.get("context", {})
    value = result.get("value")
    if not isinstance(value, dict):
        return None
    slot_value = context.get("slot")
    return (slot_value if isinstance(slot_value, int) else None, value)


def log_signature(value: dict[str, Any]) -> str | None:
    sig = value.get("signature")
    return sig if isinstance(sig, str) else None


def log_lines(value: dict[str, Any]) -> list[str]:
    raw_logs = value.get("logs", [])
    return [line for line in raw_logs or [] if isinstance(line, str)]


def log_is_failed(value: dict[str, Any]) -> bool:
    return value.get("err") is not None


def logs_look_like_pump_launch(value: dict[str, Any]) -> bool:
    joined = "\n".join(log_lines(value))
    return any(marker in joined for marker in CREATE_LOG_MARKERS)


def account_keys(result: dict[str, Any]) -> list[str]:
    """Extract account keys from a jsonParsed Enhanced transaction notification."""
    transaction = result.get("transaction", {})
    inner_tx = transaction.get("transaction", {})
    message = inner_tx.get("message", {}) if isinstance(inner_tx, dict) else {}

    keys: list[str] = []
    for item in message.get("accountKeys", []) or []:
        if isinstance(item, str):
            keys.append(item)
        elif isinstance(item, dict):
            pubkey = item.get("pubkey")
            if isinstance(pubkey, str):
                keys.append(pubkey)

    meta = transaction.get("meta", {}) if isinstance(transaction, dict) else {}
    loaded = meta.get("loadedAddresses", {}) if isinstance(meta, dict) else {}
    for group in ("writable", "readonly"):
        for item in loaded.get(group, []) or []:
            if isinstance(item, str):
                keys.append(item)

    return list(dict.fromkeys(keys))


def signature(result: dict[str, Any]) -> str | None:
    direct = result.get("signature")
    if isinstance(direct, str):
        return direct

    inner_tx = result.get("transaction", {}).get("transaction", {})
    if isinstance(inner_tx, dict):
        signatures = inner_tx.get("signatures") or []
        if signatures and isinstance(signatures[0], str):
            return signatures[0]
    return None


def slot(result: dict[str, Any]) -> int | None:
    value = result.get("slot")
    return value if isinstance(value, int) else None


def logs(result: dict[str, Any]) -> list[str]:
    meta = result.get("transaction", {}).get("meta", {})
    raw_logs = meta.get("logMessages", []) if isinstance(meta, dict) else []
    return [line for line in raw_logs or [] if isinstance(line, str)]


def looks_like_pump_launch(result: dict[str, Any], pump_program_id: str) -> bool:
    keys = account_keys(result)
    if pump_program_id not in keys:
        return False
    joined = "\n".join(logs(result))
    return any(marker in joined for marker in CREATE_LOG_MARKERS)
