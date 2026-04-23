"""Append-only idempotent candidate lifecycle history for v3.12.

Each lifecycle transition is represented by a ``LifecycleEvent``.
Events carry a deterministic ``event_id = sha256(candidate_id | from
| to | run_id | reason_code)`` so reruns of the same run with
identical input produce zero new events after merge.

Merge contract:
- Existing history is loaded (or empty dict if absent).
- New events are appended, then deduplicated by ``event_id``.
- Within each candidate_id bucket events are sorted by
  ``(at_utc, event_id)`` for stable output regardless of insertion
  order.
- Top-level candidate_id keys are sorted alphabetically.
- The artifact is written via ``_sidecar_io.write_sidecar_atomic``
  so byte-reproducibility is enforced end-to-end.

Scope:
- v3.12 runtime only produces transitions within the active
  lifecycle subset (exploratory / candidate / rejected). The
  derivation helper validates every transition against
  ``validate_active_transition`` so reserved statuses never leak in.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from research._sidecar_io import write_sidecar_atomic
from research.candidate_lifecycle import (
    STATUS_MODEL_VERSION,
    CandidateLifecycleStatus,
    map_legacy_verdict,
    validate_active_transition,
)


STATUS_HISTORY_SCHEMA_VERSION = "1.0"
STATUS_HISTORY_INITIAL_FROM = "__initial__"


@dataclass(frozen=True)
class LifecycleEvent:
    event_id: str
    candidate_id: str
    from_status: str | None
    to_status: str
    reason_code: str | None
    run_id: str
    at_utc: str
    source_artifact: str

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


def build_event_id(
    candidate_id: str,
    from_status: str | None,
    to_status: str,
    run_id: str,
    reason_code: str | None,
) -> str:
    """Deterministic event identifier.

    Uses a pipe-delimited byte sequence to guarantee stable hashing
    across platforms and Python versions.
    """
    parts = [
        candidate_id,
        from_status if from_status is not None else STATUS_HISTORY_INITIAL_FROM,
        to_status,
        run_id,
        reason_code if reason_code is not None else "",
    ]
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _primary_reason_code(v1_entry: dict[str, Any]) -> str | None:
    """Pick a single canonical reason code for history events.

    Priority: first failed code -> first escalated code -> None.
    This keeps event_id deterministic without requiring the entire
    reasoning bag in the hash input.
    """
    reasoning = v1_entry.get("reasoning") or {}
    failed = reasoning.get("failed") or []
    escalated = reasoning.get("escalated") or []
    if failed:
        return str(failed[0])
    if escalated:
        return str(escalated[0])
    return None


def derive_events_from_run(
    registry_v2_entries: list[dict[str, Any]],
    run_id: str,
    now_utc: str,
    source_artifact: str = "research/candidate_registry_latest.v2.json",
) -> list[LifecycleEvent]:
    """Produce lifecycle events for each entry in a registry-v2 payload.

    Every entry yields exactly one event representing its initial
    placement in the v3.12 lifecycle (``from_status=None``). The
    transition target is the entry's current ``lifecycle_status`` and
    is validated against ``ACTIVE_TRANSITIONS_V3_12`` indirectly: any
    reserved status in the entry would have been blocked earlier.
    """
    events: list[LifecycleEvent] = []
    for entry in registry_v2_entries:
        candidate_id = str(entry["candidate_id"])
        lifecycle_status = str(entry["lifecycle_status"])
        # Defensive: enum membership check. If the entry smuggled a
        # reserved status string, this raises; it should have been
        # blocked earlier in the pipeline.
        target_enum = CandidateLifecycleStatus(lifecycle_status)
        # For initial placement we treat from_status as None, but we
        # still require the target to be active (not reserved).
        if target_enum not in {
            CandidateLifecycleStatus.REJECTED,
            CandidateLifecycleStatus.EXPLORATORY,
            CandidateLifecycleStatus.CANDIDATE,
        }:
            from research.candidate_lifecycle import ReservedStatusError
            raise ReservedStatusError(
                f"candidate {candidate_id!r} carries reserved lifecycle "
                f"status {lifecycle_status!r} in registry-v2; v3.12 forbids this"
            )

        reason_code = _primary_reason_code(
            {"reasoning": entry.get("observed_reason_codes_as_reasoning")}
        )
        # registry-v2 stores observed codes flat; reassemble a minimal
        # reasoning shape to pass through _primary_reason_code
        # without depending on v1-structure here.
        observed = entry.get("observed_reason_codes") or []
        if observed:
            reason_code = str(observed[0])

        events.append(
            LifecycleEvent(
                event_id=build_event_id(
                    candidate_id=candidate_id,
                    from_status=None,
                    to_status=lifecycle_status,
                    run_id=run_id,
                    reason_code=reason_code,
                ),
                candidate_id=candidate_id,
                from_status=None,
                to_status=lifecycle_status,
                reason_code=reason_code,
                run_id=run_id,
                at_utc=now_utc,
                source_artifact=source_artifact,
            )
        )
    return events


def load_existing_history(path: Path) -> dict[str, Any]:
    """Read the existing history artifact; return an empty skeleton if absent."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def merge_history(
    existing_history: dict[str, list[dict[str, Any]]],
    new_events: list[LifecycleEvent],
) -> dict[str, list[dict[str, Any]]]:
    """Merge events into an existing history with idempotent semantics.

    - Dedupe by ``event_id``
    - Stable sort within each candidate_id: ``(at_utc, event_id)``
    - Sort top-level keys alphabetically on return
    """
    merged: dict[str, list[dict[str, Any]]] = {
        cid: list(events) for cid, events in existing_history.items()
    }

    for event in new_events:
        bucket = merged.setdefault(event.candidate_id, [])
        existing_ids = {ev["event_id"] for ev in bucket}
        if event.event_id in existing_ids:
            continue
        bucket.append(event.to_payload())

    # Stable sort within each bucket, then sort bucket keys.
    sorted_history: dict[str, list[dict[str, Any]]] = {}
    for candidate_id in sorted(merged.keys()):
        bucket = merged[candidate_id]
        bucket.sort(key=lambda ev: (ev.get("at_utc", ""), ev.get("event_id", "")))
        sorted_history[candidate_id] = bucket

    return sorted_history


def build_history_payload(
    history: dict[str, list[dict[str, Any]]],
    generated_at_utc: str,
) -> dict[str, Any]:
    """Assemble the top-level history artifact payload."""
    return {
        "schema_version": STATUS_HISTORY_SCHEMA_VERSION,
        "status_model_version": STATUS_MODEL_VERSION,
        "generated_at_utc": generated_at_utc,
        "history": history,
    }


def write_history(path: Path, payload: dict[str, Any]) -> None:
    """Persist the history payload through the canonical IO helper."""
    write_sidecar_atomic(path, payload)


# Re-export commonly used helpers at module level for convenience.
__all__ = [
    "LifecycleEvent",
    "STATUS_HISTORY_SCHEMA_VERSION",
    "build_event_id",
    "build_history_payload",
    "derive_events_from_run",
    "load_existing_history",
    "map_legacy_verdict",  # re-export for integration convenience
    "merge_history",
    "validate_active_transition",
    "write_history",
]
