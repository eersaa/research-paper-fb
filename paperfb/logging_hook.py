"""JSONL logger for AG2 runs (spec §6.5, §6.7).

Each line is one event: {ts, agent, role, content, tool_calls, usage}.
Content payloads >1024 bytes are stored as {sha256, bytes} — never cleartext.
This is the non-leakage guard for the manuscript body (spec §6.7).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REDACT_THRESHOLD_BYTES = 1024


def redact(payload: Any) -> Any:
    """Pass through small payloads; replace large ones with a sha256 + size."""
    if not isinstance(payload, str):
        return payload
    encoded = payload.encode("utf-8")
    if len(encoded) <= REDACT_THRESHOLD_BYTES:
        return payload
    return {
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": len(encoded),
    }


class JsonlLogger:
    """Append-only JSONL log. One line per event. ts is UTC ISO-8601."""

    def __init__(self, path: Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self._path.open("a", encoding="utf-8")

    def log_event(self, event: dict) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            **event,
            "content": redact(event.get("content")),
        }
        self._fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fp.flush()

    def close(self) -> None:
        if not self._fp.closed:
            self._fp.close()

    def __enter__(self) -> "JsonlLogger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
