from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import orjson


@dataclass
class JsonlSink:
    root: Path
    stream_name: str
    flush_every: int = 25

    def __post_init__(self) -> None:
        self._fh = None
        self._hour_key: str | None = None
        self._pending = 0

    def _path_for(self, now: datetime) -> Path:
        date = now.strftime("%Y-%m-%d")
        hour = now.strftime("%H")
        folder = self.root / self.stream_name / f"date={date}"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"hour={hour}.jsonl"

    def _ensure_open(self, now: datetime) -> None:
        hour_key = now.strftime("%Y-%m-%dT%H")
        if self._fh is not None and self._hour_key == hour_key:
            return
        self.close()
        path = self._path_for(now)
        self._fh = path.open("ab", buffering=1024 * 1024)
        self._hour_key = hour_key

    def write(self, record: dict[str, Any], now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self._ensure_open(now)
        assert self._fh is not None
        self._fh.write(orjson.dumps(record, option=orjson.OPT_APPEND_NEWLINE))
        self._pending += 1
        if self._pending >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        if self._fh is None:
            return
        self._fh.flush()
        os.fsync(self._fh.fileno())
        self._pending = 0

    def close(self) -> None:
        if self._fh is not None:
            self.flush()
            self._fh.close()
            self._fh = None
            self._hour_key = None

    def __enter__(self) -> "JsonlSink":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
