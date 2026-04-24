"""Tests for research.campaign_preset_policy (v3.15.2 failure memory)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from research.campaign_evidence_ledger import REASON_CODE_NONE, make_event
from research.campaign_preset_policy import (
    PRESET_POLICY_STATES,
    derive_preset_state,
)


PRESET = "trend_equities_4h_baseline"
BASE_COOLDOWN = 86_400


@pytest.fixture
def now_utc() -> datetime:
    return datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC)


def _completion(
    *,
    at_utc: datetime,
    outcome: str,
    reason_code: str = REASON_CODE_NONE,
    campaign_id: str = "col-x",
    preset: str = PRESET,
) -> dict:
    return make_event(
        campaign_id=campaign_id,
        parent_campaign_id=None,
        lineage_root_campaign_id=campaign_id,
        preset_name=preset,
        campaign_type="daily_primary",
        event_type="campaign_completed",
        at_utc=at_utc,
        reason_code=reason_code,
        outcome=outcome,
    ).to_payload()


def test_baseline_is_active(now_utc: datetime) -> None:
    state = derive_preset_state(
        [],
        preset_name=PRESET,
        template_cooldown_seconds=BASE_COOLDOWN,
        default_paper_followup_cap=2,
        now_utc=now_utc,
    )
    assert state.policy_state == "active"
    assert state.priority_tier_delta == 0
    assert state.effective_cooldown_seconds == BASE_COOLDOWN


def test_cooldown_doubles_after_three_no_survivor(now_utc: datetime) -> None:
    events = [
        _completion(
            at_utc=now_utc - timedelta(hours=24 - i),
            campaign_id=f"col-{i}",
            outcome="completed_no_survivor",
        )
        for i in range(3)
    ]
    state = derive_preset_state(
        events,
        preset_name=PRESET,
        template_cooldown_seconds=BASE_COOLDOWN,
        default_paper_followup_cap=2,
        now_utc=now_utc,
    )
    assert state.effective_cooldown_seconds == BASE_COOLDOWN * 2
    assert state.policy_state == "deprioritized"
    assert state.consecutive_event_count == 3


def test_priority_downgrade_on_repeated_screening_fail(now_utc: datetime) -> None:
    events = [
        _completion(
            at_utc=now_utc - timedelta(hours=i + 1),
            campaign_id=f"col-{i}",
            outcome="completed_no_survivor",
            reason_code="screening_criteria_not_met",
        )
        for i in range(3)
    ]
    state = derive_preset_state(
        events,
        preset_name=PRESET,
        template_cooldown_seconds=BASE_COOLDOWN,
        default_paper_followup_cap=2,
        now_utc=now_utc,
    )
    assert state.priority_tier_delta == 1
    assert state.policy_state == "deprioritized"


def test_freeze_on_five_non_technical_rejects(now_utc: datetime) -> None:
    events = [
        _completion(
            at_utc=now_utc - timedelta(hours=i + 1),
            campaign_id=f"col-{i}",
            outcome="completed_no_survivor",
        )
        for i in range(5)
    ]
    state = derive_preset_state(
        events,
        preset_name=PRESET,
        template_cooldown_seconds=BASE_COOLDOWN,
        default_paper_followup_cap=2,
        now_utc=now_utc,
    )
    assert state.policy_state == "frozen"
    assert state.paper_followup_weekly_cap == 0


def test_technical_reasons_do_not_count_toward_freeze(now_utc: datetime) -> None:
    events = [
        _completion(
            at_utc=now_utc - timedelta(hours=i + 1),
            campaign_id=f"col-{i}",
            outcome="completed_no_survivor",
            reason_code="worker_crash",
        )
        for i in range(5)
    ]
    state = derive_preset_state(
        events,
        preset_name=PRESET,
        template_cooldown_seconds=BASE_COOLDOWN,
        default_paper_followup_cap=2,
        now_utc=now_utc,
    )
    assert state.policy_state != "frozen"


def test_paper_followup_cap_drops_after_two_same_reason(now_utc: datetime) -> None:
    events = []
    for i in range(2):
        events.append(
            make_event(
                campaign_id=f"col-{i}",
                parent_campaign_id=None,
                lineage_root_campaign_id=f"col-{i}",
                preset_name=PRESET,
                campaign_type="daily_primary",
                event_type="paper_blocked",
                at_utc=now_utc - timedelta(hours=i + 1),
                reason_code="excessive_divergence",
                outcome="paper_blocked",
            ).to_payload()
        )
    state = derive_preset_state(
        events,
        preset_name=PRESET,
        template_cooldown_seconds=BASE_COOLDOWN,
        default_paper_followup_cap=2,
        now_utc=now_utc,
    )
    assert state.paper_followup_weekly_cap == 1


def test_explicit_preset_frozen_event_overrides(now_utc: datetime) -> None:
    events = [
        make_event(
            campaign_id="col-x",
            parent_campaign_id=None,
            lineage_root_campaign_id="col-x",
            preset_name=PRESET,
            campaign_type="daily_primary",
            event_type="preset_frozen",
            at_utc=now_utc - timedelta(hours=1),
        ).to_payload()
    ]
    state = derive_preset_state(
        events,
        preset_name=PRESET,
        template_cooldown_seconds=BASE_COOLDOWN,
        default_paper_followup_cap=2,
        now_utc=now_utc,
    )
    assert state.policy_state == "frozen"


def test_preset_policy_states_are_closed() -> None:
    assert set(PRESET_POLICY_STATES) == {"active", "deprioritized", "frozen"}
