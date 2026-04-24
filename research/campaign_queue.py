"""Campaign queue — ordered execution view over the registry (v3.15.2 COL).

The queue is *not* the source of truth. Per R3.3.2 the registry owns all
campaign metadata; the queue holds:

- the deterministic execution order
- per-entry lease state
- ``earliest_retry_utc`` for failed-retriable entries

If the queue and registry ever disagree for an active campaign, the
queue is rebuilt from the registry; the registry is never rebuilt from
the queue. This module exposes the pure transforms that keep the view
in sync.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from research._sidecar_io import write_sidecar_atomic
from research.campaign_os_artifacts import build_pin_block, iso_utc

QUEUE_SCHEMA_VERSION: str = "1.0"
QUEUE_ARTIFACT_PATH: Path = Path("research/campaign_queue_latest.v1.json")

# States that are considered "active" (tracked in the queue).
ACTIVE_QUEUE_STATES: frozenset[str] = frozenset(
    {"pending", "leased", "running"}
)

# Deterministic ordering of queue entries.
_QUEUE_SORT_KEY = ("priority_tier", "spawned_at_utc", "campaign_id")


@dataclass(frozen=True)
class QueueEntry:
    campaign_id: str
    priority_tier: int
    spawned_at_utc: str
    state: str
    earliest_retry_utc: str | None
    lease: dict[str, Any] | None
    estimated_runtime_seconds: int
    extra: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "priority_tier": int(self.priority_tier),
            "spawned_at_utc": self.spawned_at_utc,
            "state": self.state,
            "earliest_retry_utc": self.earliest_retry_utc,
            "lease": self.lease,
            "estimated_runtime_seconds": int(self.estimated_runtime_seconds),
            **self.extra,
        }


def queue_entry_from_record(record: dict[str, Any]) -> QueueEntry:
    """Project a registry record down to its queue-entry view."""
    return QueueEntry(
        campaign_id=str(record["campaign_id"]),
        priority_tier=int(record.get("priority_tier") or 3),
        spawned_at_utc=str(record.get("spawned_at_utc") or ""),
        state=str(record.get("state") or "pending"),
        earliest_retry_utc=record.get("earliest_retry_utc"),
        lease=_lease_dict(record),
        estimated_runtime_seconds=int(
            record.get("estimated_runtime_seconds") or 0
        ),
    )


def _lease_dict(record: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the lease block out of a registry record, if present."""
    if record.get("state") not in ("leased", "running"):
        return None
    lease = record.get("lease")
    if isinstance(lease, dict):
        return dict(lease)
    return None


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------


def load_queue(path: Path = QUEUE_ARTIFACT_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"queue": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"queue": []}
    if not isinstance(raw, dict):
        return {"queue": []}
    raw.setdefault("queue", [])
    return raw


def write_queue(
    queue: dict[str, Any],
    *,
    generated_at_utc: datetime,
    git_revision: str | None = None,
    path: Path = QUEUE_ARTIFACT_PATH,
) -> None:
    pins = build_pin_block(
        schema_version=QUEUE_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
        run_id=None,
        artifact_state="healthy",
    )
    entries = queue.get("queue") or []
    sorted_entries = sorted(entries, key=_sort_key)
    payload = {**pins, "queue": sorted_entries}
    write_sidecar_atomic(path, payload)


def _sort_key(entry: dict[str, Any]) -> tuple[int, str, str]:
    return (
        int(entry.get("priority_tier") or 3),
        str(entry.get("spawned_at_utc") or ""),
        str(entry.get("campaign_id") or ""),
    )


# ---------------------------------------------------------------------------
# Pure transforms
# ---------------------------------------------------------------------------


def rebuild_queue_from_registry(
    registry: dict[str, Any],
) -> dict[str, Any]:
    """Return a fresh queue dict derived from registry active entries.

    Used on startup to recover from a corrupt/missing queue artifact
    and to enforce registry-is-source-of-truth after any manual edit.
    """
    campaigns = registry.get("campaigns") or {}
    entries: list[dict[str, Any]] = []
    for record in campaigns.values():
        if record.get("state") not in ACTIVE_QUEUE_STATES:
            continue
        entry = queue_entry_from_record(record).to_payload()
        entries.append(entry)
    entries.sort(key=_sort_key)
    return {"queue": entries}


def upsert_entry(
    queue: dict[str, Any],
    entry: QueueEntry,
) -> dict[str, Any]:
    entries = [
        e for e in (queue.get("queue") or []) if e.get("campaign_id") != entry.campaign_id
    ]
    entries.append(entry.to_payload())
    entries.sort(key=_sort_key)
    return {**queue, "queue": entries}


def remove_entry(
    queue: dict[str, Any],
    campaign_id: str,
) -> dict[str, Any]:
    entries = [
        e
        for e in (queue.get("queue") or [])
        if e.get("campaign_id") != campaign_id
    ]
    return {**queue, "queue": entries}


def set_lease(
    queue: dict[str, Any],
    *,
    campaign_id: str,
    lease_payload: dict[str, Any],
    to_state: str = "leased",
) -> dict[str, Any]:
    entries = list(queue.get("queue") or [])
    for entry in entries:
        if entry.get("campaign_id") == campaign_id:
            entry["state"] = to_state
            entry["lease"] = dict(lease_payload)
    return {**queue, "queue": entries}


def clear_lease(
    queue: dict[str, Any],
    *,
    campaign_id: str,
    to_state: str = "pending",
    earliest_retry_utc: datetime | None = None,
) -> dict[str, Any]:
    entries = list(queue.get("queue") or [])
    for entry in entries:
        if entry.get("campaign_id") == campaign_id:
            entry["state"] = to_state
            entry["lease"] = None
            entry["earliest_retry_utc"] = (
                iso_utc(earliest_retry_utc) if earliest_retry_utc else None
            )
    return {**queue, "queue": entries}


def find_entry(
    queue: dict[str, Any],
    campaign_id: str,
) -> dict[str, Any] | None:
    for entry in queue.get("queue") or []:
        if entry.get("campaign_id") == campaign_id:
            return dict(entry)
    return None


def active_lease_count(queue: dict[str, Any]) -> int:
    return sum(
        1
        for e in (queue.get("queue") or [])
        if e.get("state") in ("leased", "running")
        and isinstance(e.get("lease"), dict)
    )


__all__ = [
    "ACTIVE_QUEUE_STATES",
    "QUEUE_ARTIFACT_PATH",
    "QUEUE_SCHEMA_VERSION",
    "QueueEntry",
    "active_lease_count",
    "clear_lease",
    "find_entry",
    "load_queue",
    "queue_entry_from_record",
    "rebuild_queue_from_registry",
    "remove_entry",
    "set_lease",
    "upsert_entry",
    "write_queue",
]
