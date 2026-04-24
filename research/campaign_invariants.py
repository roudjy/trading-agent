"""Must-hold runtime invariants for the v3.15.2 Campaign OS.

Runs at the tail of every launcher tick and every integration test.
Failure raises ``CampaignInvariantViolation`` — the launcher logs the
event to the ledger as ``budget_exceeded`` / ``duplicate_detected`` as
appropriate and exits non-zero, so cron surfaces the regression.

Invariants (plan §R3.3.1):

    I1  Single active campaign (respects ``max_concurrent_campaigns``)
    I2  No duplicate campaigns per uniqueness key
    I3  No orphans (queue ↔ registry membership)
    I4  Registry-queue state agreement for active entries
    I5  Ledger completeness: every terminal transition has an event
    I6  Deterministic policy output (tested via fixtures, not this fn)
    I7  Campaign-id uniqueness across time
    I8  Lineage integrity (parent/root refer to existing records)
    I9  Follow-up idempotency: one child per (parent, followup type)

Pure read-only function. Accepts the pre-loaded artifacts; raises on
the first violation with a structured message. Callers may run it in
a try/except and log the violation instead of re-raising if they
deliberately operate under partial invariants (not recommended).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from research.campaign_registry import CAMPAIGN_STATES


class CampaignInvariantViolation(RuntimeError):
    """A hard invariant was violated; the tick must abort without writes."""


_ACTIVE_STATES: frozenset[str] = frozenset({"pending", "leased", "running"})


@dataclass(frozen=True)
class InvariantReport:
    checked: tuple[str, ...]
    passed: tuple[str, ...]


def assert_invariants(
    *,
    registry: dict[str, Any],
    queue: dict[str, Any],
    events: list[dict[str, Any]],
    max_concurrent_campaigns: int,
) -> InvariantReport:
    """Check every invariant; raise on the first violation."""
    checks = (
        ("I1_single_active", lambda: _i1_single_active(registry, max_concurrent_campaigns)),
        ("I2_no_duplicates", lambda: _i2_no_duplicates(registry)),
        ("I3_no_orphans", lambda: _i3_no_orphans(registry, queue)),
        ("I4_state_agreement", lambda: _i4_state_agreement(registry, queue)),
        ("I5_ledger_completeness", lambda: _i5_ledger_completeness(registry, events)),
        ("I7_id_uniqueness", lambda: _i7_id_uniqueness(registry)),
        ("I8_lineage_integrity", lambda: _i8_lineage_integrity(registry)),
        ("I9_followup_idempotency", lambda: _i9_followup_idempotency(registry)),
    )
    passed: list[str] = []
    for name, check in checks:
        check()  # raises CampaignInvariantViolation on failure
        passed.append(name)
    return InvariantReport(
        checked=tuple(n for n, _ in checks),
        passed=tuple(passed),
    )


def _i1_single_active(
    registry: dict[str, Any],
    max_concurrent: int,
) -> None:
    active = [
        r
        for r in (registry.get("campaigns") or {}).values()
        if r.get("state") in ("leased", "running")
    ]
    if len(active) > int(max_concurrent):
        raise CampaignInvariantViolation(
            f"I1 violation: {len(active)} active campaigns exceeds "
            f"max_concurrent={max_concurrent}: "
            f"{sorted(str(r.get('campaign_id')) for r in active)}"
        )


def _i2_no_duplicates(registry: dict[str, Any]) -> None:
    """Root campaigns use ``None`` for the parent slot so two distinct root
    records with the same ``(type, preset, fingerprint)`` collide — matching
    the ``has_duplicate`` semantics in the registry module."""
    seen: dict[tuple[str, str, str, str], str] = {}
    for cid, record in (registry.get("campaigns") or {}).items():
        if record.get("state") in ("canceled", "archived"):
            continue
        parent = record.get("parent_campaign_id") or ""
        key = (
            str(record.get("campaign_type") or ""),
            str(record.get("preset_name") or ""),
            str(parent),
            str(record.get("input_artifact_fingerprint") or ""),
        )
        if key in seen:
            raise CampaignInvariantViolation(
                f"I2 violation: duplicate campaigns for key {key!r}: "
                f"{seen[key]!r} and {cid!r}"
            )
        seen[key] = str(cid)


def _i3_no_orphans(
    registry: dict[str, Any],
    queue: dict[str, Any],
) -> None:
    campaigns = registry.get("campaigns") or {}
    queue_ids = {
        str(entry.get("campaign_id") or "")
        for entry in (queue.get("queue") or [])
    }
    for qid in queue_ids:
        if qid and qid not in campaigns:
            raise CampaignInvariantViolation(
                f"I3 violation: queue references unknown campaign_id {qid!r}"
            )
    for cid, record in campaigns.items():
        if record.get("state") not in _ACTIVE_STATES:
            continue
        if cid not in queue_ids:
            raise CampaignInvariantViolation(
                f"I3 violation: registry entry {cid!r} in state "
                f"{record.get('state')!r} absent from queue"
            )


def _i4_state_agreement(
    registry: dict[str, Any],
    queue: dict[str, Any],
) -> None:
    campaigns = registry.get("campaigns") or {}
    for entry in queue.get("queue") or []:
        cid = str(entry.get("campaign_id") or "")
        record = campaigns.get(cid)
        if not record:
            continue
        if record.get("state") != entry.get("state"):
            raise CampaignInvariantViolation(
                f"I4 violation: state mismatch for {cid!r}: "
                f"registry={record.get('state')!r} queue={entry.get('state')!r}"
            )


def _i5_ledger_completeness(
    registry: dict[str, Any],
    events: list[dict[str, Any]],
) -> None:
    """Every terminal record must have a matching ``campaign_completed`` or
    ``campaign_failed`` or cancel event."""
    terminal_records = [
        r
        for r in (registry.get("campaigns") or {}).values()
        if r.get("state") in ("completed", "failed", "canceled", "archived")
    ]
    event_ids_by_campaign: dict[str, set[str]] = {}
    for ev in events:
        cid = str(ev.get("campaign_id") or "")
        event_ids_by_campaign.setdefault(cid, set()).add(
            str(ev.get("event_type") or "")
        )
    for record in terminal_records:
        cid = str(record.get("campaign_id") or "")
        state = record.get("state")
        types = event_ids_by_campaign.get(cid, set())
        if state == "completed" and "campaign_completed" not in types:
            raise CampaignInvariantViolation(
                f"I5 violation: completed campaign {cid!r} lacks "
                f"campaign_completed ledger event"
            )
        if state == "failed" and "campaign_failed" not in types:
            raise CampaignInvariantViolation(
                f"I5 violation: failed campaign {cid!r} lacks "
                f"campaign_failed ledger event"
            )
        if state == "canceled" and not (
            "canceled_duplicate" in types or "canceled_upstream_stale" in types
        ):
            raise CampaignInvariantViolation(
                f"I5 violation: canceled campaign {cid!r} lacks "
                f"cancelation ledger event"
            )


def _i7_id_uniqueness(registry: dict[str, Any]) -> None:
    campaigns = registry.get("campaigns") or {}
    ids = list(campaigns.keys())
    if len(ids) != len(set(ids)):
        raise CampaignInvariantViolation(
            "I7 violation: duplicate campaign_id keys in registry"
        )


def _i8_lineage_integrity(registry: dict[str, Any]) -> None:
    campaigns = registry.get("campaigns") or {}
    for cid, record in campaigns.items():
        parent = record.get("parent_campaign_id")
        if parent is not None and parent not in campaigns:
            raise CampaignInvariantViolation(
                f"I8 violation: campaign {cid!r} parent {parent!r} not in registry"
            )
        root = record.get("lineage_root_campaign_id")
        if root and root not in campaigns:
            raise CampaignInvariantViolation(
                f"I8 violation: campaign {cid!r} root {root!r} not in registry"
            )


def _i9_followup_idempotency(registry: dict[str, Any]) -> None:
    seen: dict[tuple[str, str], str] = {}
    for cid, record in (registry.get("campaigns") or {}).items():
        parent = record.get("parent_campaign_id")
        if not parent:
            continue
        if record.get("state") in ("canceled", "archived"):
            continue
        key = (str(parent), str(record.get("campaign_type") or ""))
        if key in seen:
            raise CampaignInvariantViolation(
                f"I9 violation: duplicate follow-up for {key!r}: "
                f"{seen[key]!r} and {cid!r}"
            )
        seen[key] = str(cid)


__all__ = [
    "CAMPAIGN_STATES",
    "CampaignInvariantViolation",
    "InvariantReport",
    "assert_invariants",
]
