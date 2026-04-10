"""Append-only JSONL audit log with monotonically increasing sequence ids."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

AUDIT_LOG_PATH = Path("logs/audit.log")
_LOCK = threading.Lock()


def _next_sequence_id() -> int:
    if not AUDIT_LOG_PATH.exists():
        return 1

    try:
        lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 1

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        sequence_id = payload.get("sequence_id")
        if isinstance(sequence_id, int):
            return sequence_id + 1
    return 1


def append(event: str, actor: str, payload: dict) -> None:
    """Append a single audit record as JSONL."""
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with _LOCK:
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "sequence_id": _next_sequence_id(),
            "event": event,
            "actor": actor,
            "payload": payload,
        }
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
