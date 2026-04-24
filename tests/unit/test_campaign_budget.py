"""Tests for research.campaign_budget (v3.15.2 COL allocator)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from research.campaign_budget import (
    BudgetState,
    add_reservation,
    dynamic_followup_reservation,
    estimate_runtime_seconds,
    increment_low_value_rerun,
    remaining_for_tier,
    rollover_if_new_day,
    settle_reservation,
    tier1_fairness_engaged,
)
from research.campaign_evidence_ledger import make_event


@pytest.fixture
def now_utc() -> datetime:
    return datetime(2026, 4, 24, 8, 0, 0, tzinfo=UTC)


def _state(**overrides) -> BudgetState:
    defaults = dict(
        date="2026-04-24",
        daily_compute_budget_seconds=57_600,
        reserved_for_followups_seconds=17_280,
        max_low_value_reruns_per_day=2,
        tier1_fairness_cap=4,
    )
    defaults.update(overrides)
    return BudgetState(**defaults)


def test_dynamic_reservation_zero_when_no_followups() -> None:
    assert (
        dynamic_followup_reservation(
            _state(), active_followup_candidate_estimates=[]
        )
        == 0
    )


def test_dynamic_reservation_caps_at_config() -> None:
    reserved = dynamic_followup_reservation(
        _state(), active_followup_candidate_estimates=[10_000, 10_000, 10_000]
    )
    # 30,000 requested capped at 17,280.
    assert reserved == 17_280


def test_remaining_for_tier_tier2_starved_when_followups_exist() -> None:
    state = _state()
    tier2_remaining = remaining_for_tier(
        state, tier=2, active_followup_candidate_estimates=[5_000]
    )
    tier1_remaining = remaining_for_tier(
        state, tier=1, active_followup_candidate_estimates=[5_000]
    )
    assert tier1_remaining > tier2_remaining
    assert tier2_remaining == 57_600 - 5_000


def test_remaining_for_tier_no_followups_no_reservation() -> None:
    state = _state()
    tier2_remaining = remaining_for_tier(
        state, tier=2, active_followup_candidate_estimates=[]
    )
    # No follow-ups => tier-2 gets the full budget.
    assert tier2_remaining == 57_600


def test_tier1_fairness_engaged_after_cap() -> None:
    state = _state(consecutive_tier1_count=4)
    assert tier1_fairness_engaged(state) is True


def test_add_reservation_updates_state(now_utc: datetime) -> None:
    state = _state()
    updated = add_reservation(
        state,
        campaign_id="col-1",
        estimate_seconds=1_800,
        priority_tier=1,
        is_followup=True,
        reserved_at_utc=now_utc,
    )
    assert updated.reserved_seconds == 1_800
    assert updated.remaining_total_seconds == 57_600 - 1_800


def test_settle_reservation_adds_consumed_and_resets_fairness(
    now_utc: datetime,
) -> None:
    state = _state(consecutive_tier1_count=2)
    state = add_reservation(
        state,
        campaign_id="col-1",
        estimate_seconds=1_800,
        priority_tier=1,
        is_followup=True,
        reserved_at_utc=now_utc,
    )
    settled = settle_reservation(
        state,
        campaign_id="col-1",
        actual_runtime_seconds=1_200,
        priority_tier=1,
        template_id="t1",
    )
    assert settled.reserved_seconds == 0
    assert settled.consumed_seconds == 1_200
    assert settled.consecutive_tier1_count == 3
    assert settled.per_template_used_today["t1"] == 1


def test_settle_tier2_resets_consecutive_tier1(now_utc: datetime) -> None:
    state = _state(consecutive_tier1_count=5)
    state = add_reservation(
        state,
        campaign_id="col-1",
        estimate_seconds=1_800,
        priority_tier=2,
        is_followup=False,
        reserved_at_utc=now_utc,
    )
    settled = settle_reservation(
        state,
        campaign_id="col-1",
        actual_runtime_seconds=1_200,
        priority_tier=2,
        template_id="t1",
    )
    assert settled.consecutive_tier1_count == 0


def test_increment_low_value_rerun_counter() -> None:
    state = _state()
    state = increment_low_value_rerun(state)
    state = increment_low_value_rerun(state)
    assert state.low_value_reruns_today == 2


def test_rollover_clears_per_day_but_keeps_reservations(
    now_utc: datetime,
) -> None:
    state = _state(
        consumed_seconds=1_000,
        low_value_reruns_today=1,
        per_template_used_today={"t1": 1},
        consecutive_tier1_count=3,
    )
    state = add_reservation(
        state,
        campaign_id="col-x",
        estimate_seconds=1_800,
        priority_tier=1,
        is_followup=True,
        reserved_at_utc=now_utc,
    )
    next_day = now_utc + timedelta(days=1)
    rolled = rollover_if_new_day(state, now_utc=next_day)
    assert rolled.date == "2026-04-25"
    assert rolled.consumed_seconds == 0
    assert rolled.low_value_reruns_today == 0
    assert rolled.per_template_used_today == {}
    assert rolled.consecutive_tier1_count == 0
    # Reservation carries over.
    assert len(rolled.reservations) == 1


def test_estimate_runtime_seconds_fallback_with_few_points(
    now_utc: datetime,
) -> None:
    assert (
        estimate_runtime_seconds(
            [],
            preset_name="p",
            campaign_type="daily_primary",
            fallback_seconds=1_800,
        )
        == 1_800
    )


def test_estimate_runtime_seconds_mean_from_history(now_utc: datetime) -> None:
    events = []
    # Three matched start/complete pairs: 600s, 1200s, 1800s → mean 1200s.
    for i, runtime in enumerate((600, 1200, 1800)):
        cid = f"col-{i}"
        start_ts = now_utc - timedelta(hours=i + 1)
        events.append(
            make_event(
                campaign_id=cid,
                parent_campaign_id=None,
                lineage_root_campaign_id=cid,
                preset_name="p",
                campaign_type="daily_primary",
                event_type="campaign_started",
                at_utc=start_ts,
            ).to_payload()
        )
        events.append(
            make_event(
                campaign_id=cid,
                parent_campaign_id=None,
                lineage_root_campaign_id=cid,
                preset_name="p",
                campaign_type="daily_primary",
                event_type="campaign_completed",
                at_utc=start_ts + timedelta(seconds=runtime),
                outcome="completed_with_candidates",
            ).to_payload()
        )
    est = estimate_runtime_seconds(
        events,
        preset_name="p",
        campaign_type="daily_primary",
        fallback_seconds=1_800,
    )
    assert est == 1_200
