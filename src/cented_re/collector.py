from __future__ import annotations

import asyncio
import random
import signal
from datetime import datetime, timezone
from typing import Any

import orjson
import websockets
from rich.console import Console

from .config import Settings
from .extract import (
    log_is_failed,
    log_lines,
    log_signature,
    logs_look_like_pump_launch,
    logs_result_from_notification,
)
from .storage import JsonlSink

console = Console()
PUMP_SUBSCRIBE_REQUEST_ID = 420
TARGET_SUBSCRIBE_REQUEST_ID = 421


def logs_subscription_request(request_id: int, address: str, commitment: str) -> dict[str, Any]:
    """Standard Solana logsSubscribe request; available on Helius Free."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "logsSubscribe",
        "params": [
            {"mentions": [address]},
            {"commitment": commitment},
        ],
    }


def subscription_requests(settings: Settings) -> list[dict[str, Any]]:
    # logsSubscribe allows only one address in `mentions`, so we create two
    # subscriptions on the same WebSocket connection.
    return [
        logs_subscription_request(
            PUMP_SUBSCRIBE_REQUEST_ID, settings.pump_program_id, settings.commitment
        ),
        logs_subscription_request(
            TARGET_SUBSCRIBE_REQUEST_ID, settings.target_wallet, settings.commitment
        ),
    ]


def make_log_envelope(
    message: dict[str, Any], subscription_kind: str, settings: Settings
) -> dict[str, Any] | None:
    parsed = logs_result_from_notification(message)
    if parsed is None:
        return None
    event_slot, value = parsed
    now = datetime.now(timezone.utc)
    failed = log_is_failed(value)

    return {
        "schema_version": 2,
        "source": "helius_logsSubscribe",
        "subscription_kind": subscription_kind,
        "received_at_utc": now.isoformat(timespec="microseconds"),
        "received_at_unix_ns": int(now.timestamp() * 1_000_000_000),
        "commitment": settings.commitment,
        "slot": event_slot,
        "signature": log_signature(value),
        "err": value.get("err"),
        "logs": log_lines(value),
        "tags": {
            "pump_subscription": subscription_kind == "pump",
            "target_wallet_subscription": subscription_kind == "target_wallet",
            "pump_launch_candidate": (
                subscription_kind == "pump" and logs_look_like_pump_launch(value)
            ),
            "failed": failed,
        },
        # Preserve the full provider notification at the raw layer.
        "raw_notification": message,
    }


async def collect(settings: Settings) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    raw_sink = JsonlSink(settings.data_dir / "raw", "logs", settings.flush_every)
    pump_sink = JsonlSink(settings.data_dir / "raw", "pump_logs", settings.flush_every)
    target_sink = JsonlSink(settings.data_dir / "raw", "target_wallet_logs", settings.flush_every)
    launch_sink = JsonlSink(settings.data_dir / "raw", "launch_candidates", settings.flush_every)

    backoff = 1.0
    total = pump = target = launches = skipped_failed = 0

    try:
        while not stop.is_set():
            try:
                console.print("[cyan]Connecting to Helius standard WebSocket…[/cyan]")
                async with websockets.connect(
                    settings.websocket_url,
                    ping_interval=45,
                    ping_timeout=20,
                    max_size=None,
                    close_timeout=5,
                ) as ws:
                    for request in subscription_requests(settings):
                        await ws.send(orjson.dumps(request).decode())

                    # Map Helius subscription IDs back to our two filters.
                    subscription_kinds: dict[int, str] = {}
                    backoff = 1.0

                    async for raw in ws:
                        if stop.is_set():
                            break
                        message = orjson.loads(raw)

                        request_id = message.get("id")
                        if request_id in {PUMP_SUBSCRIBE_REQUEST_ID, TARGET_SUBSCRIBE_REQUEST_ID}:
                            if "error" in message:
                                raise RuntimeError(f"Helius subscription error: {message['error']}")
                            sub_id = message.get("result")
                            if isinstance(sub_id, int):
                                kind = (
                                    "pump"
                                    if request_id == PUMP_SUBSCRIBE_REQUEST_ID
                                    else "target_wallet"
                                )
                                subscription_kinds[sub_id] = kind
                                console.print(f"[green]Subscribed[/green] {kind} id={sub_id}")
                            continue

                        if "error" in message:
                            raise RuntimeError(f"Helius WebSocket error: {message['error']}")
                        if message.get("method") != "logsNotification":
                            continue

                        sub_id = message.get("params", {}).get("subscription")
                        kind = subscription_kinds.get(sub_id)
                        if kind is None:
                            continue

                        envelope = make_log_envelope(message, kind, settings)
                        if envelope is None:
                            continue
                        if envelope["tags"]["failed"] and not settings.include_failed:
                            skipped_failed += 1
                            continue

                        raw_sink.write(envelope)
                        total += 1

                        if kind == "pump":
                            pump_sink.write(envelope)
                            pump += 1
                            if envelope["tags"]["pump_launch_candidate"]:
                                launch_sink.write(envelope)
                                launches += 1
                        else:
                            target_sink.write(envelope)
                            target += 1

                        if total % 250 == 0:
                            console.print(
                                f"events={total:,}  pump={pump:,}  target={target:,}  "
                                f"launch_candidates={launches:,}  failed_skipped={skipped_failed:,}"
                            )

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                console.print(f"[yellow]stream interrupted:[/yellow] {exc}")
                sleep_for = min(backoff, settings.reconnect_max_seconds) * random.uniform(0.8, 1.2)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=sleep_for)
                except TimeoutError:
                    pass
                backoff = min(backoff * 2, float(settings.reconnect_max_seconds))
    finally:
        raw_sink.close()
        pump_sink.close()
        target_sink.close()
        launch_sink.close()
        console.print(
            "[bold]Collector stopped.[/bold] "
            f"events={total:,}, pump={pump:,}, target={target:,}, "
            f"launches={launches:,}, failed_skipped={skipped_failed:,}"
        )
