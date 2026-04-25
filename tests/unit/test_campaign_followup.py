"""Tests for research.campaign_followup (v3.15.2 survivor/paper/control)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from research.campaign_evidence_ledger import make_event
from research.campaign_followup import (
    SpawnRequest,
    derive_followups,
    derive_weekly_controls,
)


PRESET = "trend_equities_4h_baseline"


@pytest.fixture
def now_utc() -> datetime:
    return datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC)


def _parent_record(
    *,
    campaign_id: str = "col-parent",
    outcome: str = "completed_with_candidates",
    preset: str = PRESET,
    state: str = "completed",
) -> dict:
    return {
        "campaign_id": campaign_id,
        "preset_name": preset,
        "state": state,
        "campaign_type": "daily_primary",
        "outcome": outcome,
        "lineage_root_campaign_id": campaign_id,
        "parent_campaign_id": None,
    }


def test_survivor_confirmation_spawned_when_parent_has_candidates(
    now_utc: datetime,
) -> None:
    parent = _parent_record()
    registry = {"campaigns": {"col-parent": parent}}
    spawns = derive_followups(
        parent_record=parent,
        registry=registry,
        events=[],
        paper_blocked_reason=None,
        paper_followup_weekly_cap=2,
        now_utc=now_utc,
    )
    assert len(spawns) == 1
    req = spawns[0]
    assert req.campaign_type == "survivor_confirmation"
    assert req.parent_campaign_id == "col-parent"
    assert req.priority_tier == 1


def test_survivor_confirmation_suppressed_if_child_exists(
    now_utc: datetime,
) -> None:
    parent = _parent_record()
    child = {
        "campaign_id": "col-child",
        "preset_name": PRESET,
        "state": "pending",
        "campaign_type": "survivor_confirmation",
        "parent_campaign_id": "col-parent",
    }
    registry = {"campaigns": {"col-parent": parent, "col-child": child}}
    spawns = derive_followups(
        parent_record=parent,
        registry=registry,
        events=[],
        paper_blocked_reason=None,
        paper_followup_weekly_cap=2,
        now_utc=now_utc,
    )
    assert spawns == []


def test_paper_followup_spawned_on_excessive_divergence(now_utc: datetime) -> None:
    parent = _parent_record(outcome="paper_blocked")
    registry = {"campaigns": {"col-parent": parent}}
    spawns = derive_followups(
        parent_record=parent,
        registry=registry,
        events=[],
        paper_blocked_reason="excessive_divergence",
        paper_followup_weekly_cap=2,
        now_utc=now_utc,
    )
    assert any(s.campaign_type == "paper_followup" for s in spawns)
    paper_req = [s for s in spawns if s.campaign_type == "paper_followup"][0]
    assert paper_req.subtype == "excessive_divergence"


def test_paper_followup_suppressed_for_technical_reason(now_utc: datetime) -> None:
    parent = _parent_record(outcome="paper_blocked")
    registry = {"campaigns": {"col-parent": parent}}
    spawns = derive_followups(
        parent_record=parent,
        registry=registry,
        events=[],
        paper_blocked_reason="malformed_return_stream",
        paper_followup_weekly_cap=2,
        now_utc=now_utc,
    )
    assert all(s.campaign_type != "paper_followup" for s in spawns)


def test_paper_followup_respects_weekly_cap(now_utc: datetime) -> None:
    """Two paper_followup spawns this ISO week → cap of 2 blocks a third."""
    parent = _parent_record(outcome="paper_blocked")
    registry = {"campaigns": {"col-parent": parent}}
    events = []
    for i in range(2):
        events.append(
            make_event(
                campaign_id=f"col-earlier-{i}",
                parent_campaign_id=f"col-earlier-parent-{i}",
                lineage_root_campaign_id=f"col-earlier-parent-{i}",
                preset_name=PRESET,
                campaign_type="paper_followup",
                event_type="campaign_spawned",
                at_utc=now_utc - timedelta(hours=(i + 1) * 24),
            ).to_payload()
        )
    spawns = derive_followups(
        parent_record=parent,
        registry=registry,
        events=events,
        paper_blocked_reason="excessive_divergence",
        paper_followup_weekly_cap=2,
        now_utc=now_utc,
    )
    assert all(s.campaign_type != "paper_followup" for s in spawns)


def test_weekly_controls_gated_by_primary_this_week(now_utc: datetime) -> None:
    registry: dict = {"campaigns": {}}
    events = [
        make_event(
            campaign_id="col-primary",
            parent_campaign_id=None,
            lineage_root_campaign_id="col-primary",
            preset_name=PRESET,
            campaign_type="daily_primary",
            event_type="campaign_completed",
            at_utc=now_utc - timedelta(hours=2),
            outcome="completed_with_candidates",
        ).to_payload()
    ]
    spawns = derive_weekly_controls(
        preset_names=[PRESET],
        registry=registry,
        events=events,
        now_utc=now_utc,
    )
    assert len(spawns) == 1
    assert spawns[0].campaign_type == "daily_control"
    assert spawns[0].subtype == "scrambled_returns"


def test_weekly_controls_skipped_when_already_spawned_this_week(
    now_utc: datetime,
) -> None:
    registry: dict = {"campaigns": {}}
    events = [
        make_event(
            campaign_id="col-primary",
            parent_campaign_id=None,
            lineage_root_campaign_id="col-primary",
            preset_name=PRESET,
            campaign_type="daily_primary",
            event_type="campaign_completed",
            at_utc=now_utc - timedelta(hours=12),
            outcome="completed_with_candidates",
        ).to_payload(),
        make_event(
            campaign_id="col-control",
            parent_campaign_id=None,
            lineage_root_campaign_id="col-control",
            preset_name=PRESET,
            campaign_type="daily_control",
            event_type="campaign_spawned",
            at_utc=now_utc - timedelta(hours=1),
        ).to_payload(),
    ]
    spawns = derive_weekly_controls(
        preset_names=[PRESET],
        registry=registry,
        events=events,
        now_utc=now_utc,
    )
    assert spawns == []


def test_weekly_controls_skipped_without_any_primary_this_week(
    now_utc: datetime,
) -> None:
    registry: dict = {"campaigns": {}}
    spawns = derive_weekly_controls(
        preset_names=[PRESET],
        registry=registry,
        events=[],
        now_utc=now_utc,
    )
    assert spawns == []


def test_spawn_request_carries_lineage(now_utc: datetime) -> None:
    parent = _parent_record()
    registry = {"campaigns": {"col-parent": parent}}
    spawns = derive_followups(
        parent_record=parent,
        registry=registry,
        events=[],
        paper_blocked_reason=None,
        paper_followup_weekly_cap=2,
        now_utc=now_utc,
    )
    survivor: SpawnRequest = spawns[0]
    assert survivor.lineage_root_campaign_id == "col-parent"
    assert survivor.parent_campaign_id == "col-parent"
