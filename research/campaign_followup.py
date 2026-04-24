"""Follow-up derivation — pure function that reads a completed campaign.

For each completed parent in the registry, ``derive_followups`` emits
zero or more ``SpawnRequest`` objects. The launcher consumes these in
§R3.2 step 4 of the policy engine — the follow-up phase runs *before*
``daily_primary`` candidates, so survivors always get confirmed and
paper-blocked candidates get a retry slot before new primary compute is
spent.

Idempotency (I9):
- For every ``(parent_campaign_id, followup_campaign_type)`` tuple the
  registry and ledger together enforce at-most-one child. ``derive_followups``
  itself checks both before emitting a request — no launcher-side
  "did I already spawn this?" bookkeeping.

Closed triggers:
- ``survivor_confirmation_if_survivor`` — parent had survivors.
- ``paper_followup_if_blocked``         — parent ``paper_readiness.status
  == "blocked"`` with non-technical blocking reason.
- ``daily_control_weekly``              — one per preset family per ISO
  week, after ≥1 ``daily_primary`` completed in the week.

Paper-blocked *technical* reasons (``malformed_return_stream`` and
``insufficient_oos_days``) reclassify the parent as
``uninformative_technical_failure`` and do **not** trigger a follow-up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from research.campaign_evidence_ledger import has_followup_for
from research.campaign_registry import has_child_of_type
from research.campaign_templates import CampaignType

# Technical blocking reasons that do not warrant a follow-up.
_TECHNICAL_BLOCKING_REASONS: frozenset[str] = frozenset(
    {
        "malformed_return_stream",
        "insufficient_oos_days",
    }
)

# Non-technical blocking reasons that trigger a paper_followup.
_PAPER_FOLLOWUP_BLOCKING_REASONS: frozenset[str] = frozenset(
    {
        "excessive_divergence",
        "no_candidate_returns",
        "missing_execution_events",
        "insufficient_venue_mapping",
    }
)


@dataclass(frozen=True)
class SpawnRequest:
    """Request for the policy engine to spawn a new campaign."""

    campaign_type: CampaignType
    preset_name: str
    template_id: str
    parent_campaign_id: str | None
    lineage_root_campaign_id: str
    spawn_reason: str
    subtype: str | None = None
    priority_tier: int = 1
    extra: dict[str, Any] = field(default_factory=dict)


def _iso_week(ts: datetime) -> tuple[int, int]:
    year, week, _ = ts.astimezone(UTC).isocalendar()
    return int(year), int(week)


def _derive_survivor_confirmation(
    parent: dict[str, Any],
    *,
    registry: dict[str, Any],
    events: list[dict[str, Any]],
) -> SpawnRequest | None:
    if parent.get("outcome") != "completed_with_candidates":
        return None
    preset_name = str(parent.get("preset_name") or "")
    parent_id = str(parent.get("campaign_id") or "")
    lineage_root = str(parent.get("lineage_root_campaign_id") or parent_id)
    if has_child_of_type(
        registry,
        parent_campaign_id=parent_id,
        followup_campaign_type="survivor_confirmation",
    ):
        return None
    if has_followup_for(
        events,
        parent_campaign_id=parent_id,
        followup_campaign_type="survivor_confirmation",
    ):
        return None
    return SpawnRequest(
        campaign_type="survivor_confirmation",
        preset_name=preset_name,
        template_id=f"survivor_confirmation__{preset_name}",
        parent_campaign_id=parent_id,
        lineage_root_campaign_id=lineage_root,
        spawn_reason="survivor_found",
        priority_tier=1,
    )


def _derive_paper_followup(
    parent: dict[str, Any],
    *,
    registry: dict[str, Any],
    events: list[dict[str, Any]],
    paper_blocked_reason: str | None,
    weekly_cap: int,
    now_utc: datetime,
) -> SpawnRequest | None:
    if parent.get("outcome") != "paper_blocked":
        return None
    if not paper_blocked_reason:
        return None
    if paper_blocked_reason in _TECHNICAL_BLOCKING_REASONS:
        return None
    if paper_blocked_reason not in _PAPER_FOLLOWUP_BLOCKING_REASONS:
        return None
    preset_name = str(parent.get("preset_name") or "")
    parent_id = str(parent.get("campaign_id") or "")
    lineage_root = str(parent.get("lineage_root_campaign_id") or parent_id)
    if has_child_of_type(
        registry,
        parent_campaign_id=parent_id,
        followup_campaign_type="paper_followup",
    ):
        return None
    if has_followup_for(
        events,
        parent_campaign_id=parent_id,
        followup_campaign_type="paper_followup",
    ):
        return None
    if _count_paper_followups_this_week(events, preset_name, now_utc) >= max(0, int(weekly_cap)):
        return None
    return SpawnRequest(
        campaign_type="paper_followup",
        preset_name=preset_name,
        template_id=f"paper_followup__{preset_name}",
        parent_campaign_id=parent_id,
        lineage_root_campaign_id=lineage_root,
        spawn_reason=f"paper_blocked_{paper_blocked_reason}",
        subtype=paper_blocked_reason,
        priority_tier=1,
    )


def _count_paper_followups_this_week(
    events: list[dict[str, Any]],
    preset_name: str,
    now_utc: datetime,
) -> int:
    year, week = _iso_week(now_utc)
    count = 0
    for ev in events:
        if ev.get("event_type") != "campaign_spawned":
            continue
        if ev.get("campaign_type") != "paper_followup":
            continue
        if ev.get("preset_name") != preset_name:
            continue
        try:
            ts = datetime.fromisoformat(
                str(ev.get("at_utc") or "").replace("Z", "+00:00")
            ).astimezone(UTC)
        except ValueError:
            continue
        if _iso_week(ts) == (year, week):
            count += 1
    return count


def _derive_daily_control(
    preset_name: str,
    *,
    registry: dict[str, Any],
    events: list[dict[str, Any]],
    now_utc: datetime,
) -> SpawnRequest | None:
    year, week = _iso_week(now_utc)
    # Require at least one completed daily_primary this week.
    primary_this_week = False
    control_this_week = False
    for ev in events:
        if ev.get("preset_name") != preset_name:
            continue
        try:
            ts = datetime.fromisoformat(
                str(ev.get("at_utc") or "").replace("Z", "+00:00")
            ).astimezone(UTC)
        except ValueError:
            continue
        if _iso_week(ts) != (year, week):
            continue
        if (
            ev.get("event_type") == "campaign_completed"
            and ev.get("campaign_type") == "daily_primary"
        ):
            primary_this_week = True
        if (
            ev.get("event_type") == "campaign_spawned"
            and ev.get("campaign_type") == "daily_control"
        ):
            control_this_week = True
    if not primary_this_week or control_this_week:
        return None
    # Idempotency: no live control already in registry for the same preset.
    for record in (registry.get("campaigns") or {}).values():
        if record.get("preset_name") != preset_name:
            continue
        if record.get("campaign_type") != "daily_control":
            continue
        if record.get("state") in ("canceled", "archived"):
            continue
        return None
    return SpawnRequest(
        campaign_type="daily_control",
        preset_name=preset_name,
        template_id=f"daily_control__{preset_name}",
        parent_campaign_id=None,
        lineage_root_campaign_id="",
        spawn_reason="weekly_control_baseline",
        subtype="scrambled_returns",
        priority_tier=3,
    )


def derive_followups(
    *,
    parent_record: dict[str, Any],
    registry: dict[str, Any],
    events: list[dict[str, Any]],
    paper_blocked_reason: str | None,
    paper_followup_weekly_cap: int,
    now_utc: datetime,
) -> list[SpawnRequest]:
    """Return the zero-or-more spawn requests owed to ``parent_record``."""
    out: list[SpawnRequest] = []
    survivor = _derive_survivor_confirmation(
        parent_record,
        registry=registry,
        events=events,
    )
    if survivor is not None:
        out.append(survivor)

    paper = _derive_paper_followup(
        parent_record,
        registry=registry,
        events=events,
        paper_blocked_reason=paper_blocked_reason,
        weekly_cap=paper_followup_weekly_cap,
        now_utc=now_utc,
    )
    if paper is not None:
        out.append(paper)

    return out


def derive_weekly_controls(
    *,
    preset_names: list[str],
    registry: dict[str, Any],
    events: list[dict[str, Any]],
    now_utc: datetime,
) -> list[SpawnRequest]:
    """Return the daily_control spawn requests for this ISO week."""
    out: list[SpawnRequest] = []
    for preset_name in sorted(set(preset_names)):
        req = _derive_daily_control(
            preset_name,
            registry=registry,
            events=events,
            now_utc=now_utc,
        )
        if req is not None:
            out.append(req)
    return out


__all__ = [
    "SpawnRequest",
    "derive_followups",
    "derive_weekly_controls",
]
