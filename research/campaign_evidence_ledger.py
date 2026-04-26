"""Append-only idempotent campaign evidence ledger (v3.15.2 COL).

The ledger is the source of truth for cross-run campaign history.
Every state transition, follow-up spawn, and failure classification
emits one event. The ledger is consumed by:

- ``campaign_preset_policy`` — derives preset-level active policy state
  (cooldown multiplication, priority downgrade, freeze).
- ``campaign_family_policy`` — derives candidate-family-level state.
- ``campaign_budget``         — historical runtime estimator.
- ``campaign_policy``         — follow-up idempotency oracle.
- ``campaign_digest``         — daily operations roll-up.

Format: JSON Lines (one event per line). A companion ``.meta.json``
carries the pin block because JSONL cannot hold top-level fields.

Idempotency contract (mirrors candidate_status_history):

    event_id = sha256("{campaign_id}|{event_type}|{at_utc}|"
                      "{reason_code}|{run_id}")

Replaying the same event produces zero new lines. Crash-recovery is a
no-op: re-emit, dedup on append.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Literal

from research._sidecar_io import write_sidecar_atomic
from research.campaign_os_artifacts import build_pin_block, iso_utc
from research.campaign_templates import CampaignType

LEDGER_SCHEMA_VERSION: str = "1.0"
LEDGER_META_SCHEMA_VERSION: str = "1.0"

EventType = Literal[
    "campaign_spawned",
    "campaign_leased",
    "campaign_started",
    "campaign_completed",
    "campaign_failed",
    "canceled_duplicate",
    "canceled_upstream_stale",
    "lease_expired",
    "reject_no_survivor",
    "paper_blocked",
    "insufficient_trades",
    "screening_criteria_not_met",
    "divergence_exceeded",
    "duplicate_detected",
    "duplicate_spawn_rejected",
    "rate_limited_followup",
    "preset_state_changed",
    "candidate_family_state_changed",
    "budget_exceeded",
    "upstream_stale_detected",
    "preset_frozen",
    "preset_thawed",
    # v3.15.10 — additive funnel-policy events.
    "funnel_decision_emitted",
    "funnel_evidence_stale_or_mismatched",
    "funnel_technical_no_freeze",
    "funnel_policy_error",
]

EVENT_TYPES: tuple[str, ...] = (
    "campaign_spawned",
    "campaign_leased",
    "campaign_started",
    "campaign_completed",
    "campaign_failed",
    "canceled_duplicate",
    "canceled_upstream_stale",
    "lease_expired",
    "reject_no_survivor",
    "paper_blocked",
    "insufficient_trades",
    "screening_criteria_not_met",
    "divergence_exceeded",
    "duplicate_detected",
    "duplicate_spawn_rejected",
    "rate_limited_followup",
    "preset_state_changed",
    "candidate_family_state_changed",
    "budget_exceeded",
    "upstream_stale_detected",
    "preset_frozen",
    "preset_thawed",
    # v3.15.10 — additive funnel-policy events.
    "funnel_decision_emitted",
    "funnel_evidence_stale_or_mismatched",
    "funnel_technical_no_freeze",
    "funnel_policy_error",
)

# Sentinel for events that do not carry a reason (e.g. clean completion).
REASON_CODE_NONE: str = "none"


@dataclass(frozen=True)
class LedgerEvent:
    """One line in the JSONL ledger.

    ``reason_code`` reuses the closed vocabulary from
    ``orchestration.task.ReasonCode`` ∪ ``paper_readiness.BLOCKING_REASONS``
    ∪ {``none``}. No new taxonomies are introduced here.
    """

    event_id: str
    campaign_id: str
    parent_campaign_id: str | None
    lineage_root_campaign_id: str
    preset_name: str
    strategy_family: str | None
    asset_class: str | None
    campaign_type: CampaignType
    event_type: EventType
    reason_code: str
    outcome: str | None
    meaningful_classification: str | None
    run_id: str | None
    source_artifact: str | None
    at_utc: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def build_event_id(
    *,
    campaign_id: str,
    event_type: EventType,
    at_utc: str,
    reason_code: str,
    run_id: str | None,
) -> str:
    """Deterministic event id; pipe-delimited sha256."""
    parts = [
        campaign_id,
        event_type,
        at_utc,
        reason_code,
        run_id if run_id is not None else "",
    ]
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def make_event(
    *,
    campaign_id: str,
    parent_campaign_id: str | None,
    lineage_root_campaign_id: str,
    preset_name: str,
    campaign_type: CampaignType,
    event_type: EventType,
    at_utc: datetime,
    strategy_family: str | None = None,
    asset_class: str | None = None,
    reason_code: str = REASON_CODE_NONE,
    outcome: str | None = None,
    meaningful_classification: str | None = None,
    run_id: str | None = None,
    source_artifact: str | None = None,
    extra: dict[str, Any] | None = None,
) -> LedgerEvent:
    """Factory that fills the deterministic ``event_id``."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event_type {event_type!r}")
    at_iso = iso_utc(at_utc)
    event_id = build_event_id(
        campaign_id=campaign_id,
        event_type=event_type,
        at_utc=at_iso,
        reason_code=reason_code,
        run_id=run_id,
    )
    return LedgerEvent(
        event_id=event_id,
        campaign_id=campaign_id,
        parent_campaign_id=parent_campaign_id,
        lineage_root_campaign_id=lineage_root_campaign_id,
        preset_name=preset_name,
        strategy_family=strategy_family,
        asset_class=asset_class,
        campaign_type=campaign_type,
        event_type=event_type,
        reason_code=reason_code,
        outcome=outcome,
        meaningful_classification=meaningful_classification,
        run_id=run_id,
        source_artifact=source_artifact,
        at_utc=at_iso,
        extra=dict(extra or {}),
    )


# ---------------------------------------------------------------------------
# IO — append + read. Writes are idempotent by event_id.
# ---------------------------------------------------------------------------


def load_events(path: Path) -> list[dict[str, Any]]:
    """Read the ledger as a list of event dicts. Missing file → []."""
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                # Corrupt tail line — skip; rotation will clean it up.
                continue
    return events


def _serialize_event_line(event: LedgerEvent) -> str:
    """Canonical single-line JSON (no trailing newline)."""
    return json.dumps(event.to_payload(), sort_keys=True, ensure_ascii=False)


def append_events(
    path: Path,
    new_events: Iterable[LedgerEvent],
) -> list[LedgerEvent]:
    """Append events that are not already on disk. Returns the appended slice.

    Idempotent: events whose ``event_id`` already exists are skipped.
    Caller is responsible for holding the file lock if crossing processes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = {ev["event_id"] for ev in load_events(path)}
    appended: list[LedgerEvent] = []
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for event in new_events:
            if event.event_id in existing_ids:
                continue
            handle.write(_serialize_event_line(event))
            handle.write("\n")
            existing_ids.add(event.event_id)
            appended.append(event)
    return appended


def write_meta(
    meta_path: Path,
    *,
    generated_at_utc: datetime,
    git_revision: str | None,
    artifact_state: str = "healthy",
    event_count: int = 0,
    ledger_path: str | None = None,
) -> None:
    """Emit the ledger's companion meta sidecar carrying the pin block."""
    pins = build_pin_block(
        schema_version=LEDGER_META_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
        run_id=None,
        artifact_state="healthy" if artifact_state == "healthy" else "stale",
    )
    payload = {
        **pins,
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "ledger_path": ledger_path,
        "event_count": int(event_count),
    }
    write_sidecar_atomic(meta_path, payload)


# ---------------------------------------------------------------------------
# Query helpers — pure functions operating on the loaded event list.
# ---------------------------------------------------------------------------


def _parse_utc(at_utc: str) -> datetime:
    raw = at_utc.replace("Z", "+00:00")
    return datetime.fromisoformat(raw).astimezone(UTC)


def events_for_preset(
    events: list[dict[str, Any]],
    preset_name: str,
) -> list[dict[str, Any]]:
    return [ev for ev in events if ev.get("preset_name") == preset_name]


def last_n_outcomes_for_preset(
    events: list[dict[str, Any]],
    preset_name: str,
    n: int,
) -> list[dict[str, Any]]:
    """Return the last ``n`` completion/failure events for a preset."""
    candidates = [
        ev
        for ev in events
        if ev.get("preset_name") == preset_name
        and ev.get("event_type")
        in ("campaign_completed", "campaign_failed")
    ]
    candidates.sort(key=lambda ev: ev.get("at_utc", ""))
    return candidates[-n:]


def reason_code_frequency(
    events: list[dict[str, Any]],
    preset_name: str,
    window: int,
) -> Counter[str]:
    """Counter over reason_codes from the last ``window`` outcomes."""
    slice_ = last_n_outcomes_for_preset(events, preset_name, window)
    return Counter(
        str(ev.get("reason_code") or REASON_CODE_NONE) for ev in slice_
    )


def consecutive_outcome_streak(
    events: list[dict[str, Any]],
    preset_name: str,
    outcome_values: tuple[str, ...],
) -> int:
    """Count the tail streak of events whose outcome ∈ ``outcome_values``."""
    ordered = [
        ev
        for ev in events
        if ev.get("preset_name") == preset_name
        and ev.get("event_type") == "campaign_completed"
    ]
    ordered.sort(key=lambda ev: ev.get("at_utc", ""))
    streak = 0
    for ev in reversed(ordered):
        if ev.get("outcome") in outcome_values:
            streak += 1
        else:
            break
    return streak


def family_outcome_counts(
    events: list[dict[str, Any]],
    strategy_family: str,
    asset_class: str,
    window_days: int,
    now_utc: datetime,
) -> Counter[str]:
    """Count reason_codes for a (family, asset_class) within the window."""
    cutoff = now_utc.timestamp() - window_days * 86_400
    hits: Counter[str] = Counter()
    for ev in events:
        if ev.get("strategy_family") != strategy_family:
            continue
        if ev.get("asset_class") != asset_class:
            continue
        try:
            ts = _parse_utc(str(ev.get("at_utc") or ""))
        except (ValueError, TypeError):
            continue
        if ts.timestamp() < cutoff:
            continue
        code = str(ev.get("reason_code") or REASON_CODE_NONE)
        hits[code] += 1
    return hits


def has_followup_for(
    events: list[dict[str, Any]],
    *,
    parent_campaign_id: str,
    followup_campaign_type: CampaignType,
) -> bool:
    """True iff any ``campaign_spawned`` event matches the key."""
    for ev in events:
        if ev.get("event_type") != "campaign_spawned":
            continue
        if ev.get("parent_campaign_id") != parent_campaign_id:
            continue
        if ev.get("campaign_type") == followup_campaign_type:
            return True
    return False


def time_since_last(
    events: list[dict[str, Any]],
    *,
    preset_name: str,
    event_type: EventType,
    now_utc: datetime,
) -> float | None:
    """Seconds since the most recent matching event; None if absent."""
    latest: datetime | None = None
    for ev in events:
        if ev.get("preset_name") != preset_name:
            continue
        if ev.get("event_type") != event_type:
            continue
        try:
            ts = _parse_utc(str(ev.get("at_utc") or ""))
        except (ValueError, TypeError):
            continue
        if latest is None or ts > latest:
            latest = ts
    if latest is None:
        return None
    return (now_utc.astimezone(UTC) - latest).total_seconds()


def is_preset_frozen(
    events: list[dict[str, Any]],
    preset_name: str,
) -> bool:
    """True iff the latest freeze/thaw pair leaves the preset frozen."""
    frozen_at: datetime | None = None
    thawed_at: datetime | None = None
    for ev in events:
        if ev.get("preset_name") != preset_name:
            continue
        etype = ev.get("event_type")
        if etype not in ("preset_frozen", "preset_thawed"):
            continue
        try:
            ts = _parse_utc(str(ev.get("at_utc") or ""))
        except (ValueError, TypeError):
            continue
        if etype == "preset_frozen":
            if frozen_at is None or ts > frozen_at:
                frozen_at = ts
        else:
            if thawed_at is None or ts > thawed_at:
                thawed_at = ts
    if frozen_at is None:
        return False
    if thawed_at is None:
        return True
    return frozen_at > thawed_at


__all__ = [
    "EVENT_TYPES",
    "EventType",
    "LEDGER_META_SCHEMA_VERSION",
    "LEDGER_SCHEMA_VERSION",
    "LedgerEvent",
    "REASON_CODE_NONE",
    "append_events",
    "build_event_id",
    "consecutive_outcome_streak",
    "events_for_preset",
    "family_outcome_counts",
    "has_followup_for",
    "is_preset_frozen",
    "last_n_outcomes_for_preset",
    "load_events",
    "make_event",
    "reason_code_frequency",
    "time_since_last",
    "write_meta",
]
