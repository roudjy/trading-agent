"""Tests for research.campaign_evidence_ledger (v3.15.2 COL)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from research.campaign_evidence_ledger import (
    EVENT_TYPES,
    REASON_CODE_NONE,
    append_events,
    build_event_id,
    consecutive_outcome_streak,
    family_outcome_counts,
    has_followup_for,
    is_preset_frozen,
    last_n_outcomes_for_preset,
    load_events,
    make_event,
    reason_code_frequency,
    time_since_last,
)


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "ledger.v1.jsonl"


@pytest.fixture
def now_utc() -> datetime:
    return datetime(2026, 4, 24, 8, 0, 0, tzinfo=UTC)


def _event(
    *,
    campaign_id: str = "col-test",
    preset: str = "trend_equities_4h_baseline",
    event_type: str = "campaign_completed",
    at_utc: datetime,
    reason_code: str = REASON_CODE_NONE,
    outcome: str | None = None,
    campaign_type: str = "daily_primary",
    lineage_root: str | None = None,
    parent: str | None = None,
    strategy_family: str | None = None,
    asset_class: str | None = None,
    run_id: str | None = None,
):
    return make_event(
        campaign_id=campaign_id,
        parent_campaign_id=parent,
        lineage_root_campaign_id=lineage_root or campaign_id,
        preset_name=preset,
        campaign_type=campaign_type,  # type: ignore[arg-type]
        event_type=event_type,  # type: ignore[arg-type]
        at_utc=at_utc,
        reason_code=reason_code,
        outcome=outcome,
        run_id=run_id,
        strategy_family=strategy_family,
        asset_class=asset_class,
    )


def test_build_event_id_is_deterministic() -> None:
    a = build_event_id(
        campaign_id="col-1",
        event_type="campaign_completed",
        at_utc="2026-04-24T08:00:00Z",
        reason_code="none",
        run_id="20260424T080000000000Z",
    )
    b = build_event_id(
        campaign_id="col-1",
        event_type="campaign_completed",
        at_utc="2026-04-24T08:00:00Z",
        reason_code="none",
        run_id="20260424T080000000000Z",
    )
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_build_event_id_changes_with_inputs() -> None:
    a = build_event_id(
        campaign_id="col-1",
        event_type="campaign_completed",
        at_utc="2026-04-24T08:00:00Z",
        reason_code="none",
        run_id=None,
    )
    b = build_event_id(
        campaign_id="col-2",
        event_type="campaign_completed",
        at_utc="2026-04-24T08:00:00Z",
        reason_code="none",
        run_id=None,
    )
    assert a != b


def test_make_event_rejects_unknown_event_type(now_utc: datetime) -> None:
    with pytest.raises(ValueError):
        make_event(
            campaign_id="col-1",
            parent_campaign_id=None,
            lineage_root_campaign_id="col-1",
            preset_name="p",
            campaign_type="daily_primary",
            event_type="not_a_real_event",  # type: ignore[arg-type]
            at_utc=now_utc,
        )


def test_append_events_is_idempotent_replay(
    ledger_path: Path, now_utc: datetime
) -> None:
    """Invariant P0: re-emitting the same event must not duplicate lines."""
    event = _event(at_utc=now_utc, outcome="completed_with_candidates")
    first = append_events(ledger_path, [event])
    assert len(first) == 1
    second = append_events(ledger_path, [event])
    assert second == []
    third = append_events(ledger_path, [event, event, event])
    assert third == []
    events_on_disk = load_events(ledger_path)
    assert len(events_on_disk) == 1


def test_append_events_preserves_distinct_events(
    ledger_path: Path, now_utc: datetime
) -> None:
    ev_a = _event(at_utc=now_utc, campaign_id="col-a")
    ev_b = _event(at_utc=now_utc + timedelta(minutes=1), campaign_id="col-b")
    append_events(ledger_path, [ev_a])
    append_events(ledger_path, [ev_b])
    events = load_events(ledger_path)
    assert {e["campaign_id"] for e in events} == {"col-a", "col-b"}


def test_last_n_outcomes_for_preset(now_utc: datetime) -> None:
    events = [
        _event(
            at_utc=now_utc + timedelta(minutes=i),
            campaign_id=f"col-{i}",
            outcome="completed_with_candidates" if i % 2 == 0 else "completed_no_survivor",
        ).to_payload()
        for i in range(5)
    ]
    last3 = last_n_outcomes_for_preset(events, "trend_equities_4h_baseline", 3)
    assert len(last3) == 3
    # Ordered by at_utc ascending → tail slice is the latest 3.
    assert [ev["campaign_id"] for ev in last3] == ["col-2", "col-3", "col-4"]


def test_reason_code_frequency_counts_correctly(now_utc: datetime) -> None:
    events = [
        _event(
            at_utc=now_utc + timedelta(minutes=i),
            campaign_id=f"col-{i}",
            outcome="completed_no_survivor",
            reason_code="insufficient_trades" if i < 3 else "screening_criteria_not_met",
        ).to_payload()
        for i in range(5)
    ]
    freq = reason_code_frequency(events, "trend_equities_4h_baseline", window=5)
    assert freq["insufficient_trades"] == 3
    assert freq["screening_criteria_not_met"] == 2


def test_consecutive_outcome_streak_counts_tail(now_utc: datetime) -> None:
    events = []
    for i in range(3):
        events.append(
            _event(
                at_utc=now_utc + timedelta(minutes=i),
                campaign_id=f"col-{i}",
                outcome="completed_with_candidates",
            ).to_payload()
        )
    for i in range(3, 7):
        events.append(
            _event(
                at_utc=now_utc + timedelta(minutes=i),
                campaign_id=f"col-{i}",
                outcome="completed_no_survivor",
            ).to_payload()
        )
    streak = consecutive_outcome_streak(
        events,
        "trend_equities_4h_baseline",
        ("completed_no_survivor",),
    )
    assert streak == 4


def test_has_followup_for_detects_spawn_events(now_utc: datetime) -> None:
    events = [
        _event(
            at_utc=now_utc,
            campaign_id="col-child",
            event_type="campaign_spawned",
            campaign_type="paper_followup",
            parent="col-parent",
        ).to_payload()
    ]
    assert has_followup_for(
        events,
        parent_campaign_id="col-parent",
        followup_campaign_type="paper_followup",
    )
    assert not has_followup_for(
        events,
        parent_campaign_id="col-parent",
        followup_campaign_type="survivor_confirmation",
    )


def test_time_since_last_returns_none_when_absent(now_utc: datetime) -> None:
    assert (
        time_since_last(
            [],
            preset_name="p",
            event_type="campaign_spawned",
            now_utc=now_utc,
        )
        is None
    )


def test_time_since_last_returns_delta_seconds(now_utc: datetime) -> None:
    evs = [
        _event(
            at_utc=now_utc - timedelta(hours=1),
            event_type="campaign_spawned",
        ).to_payload()
    ]
    delta = time_since_last(
        evs,
        preset_name="trend_equities_4h_baseline",
        event_type="campaign_spawned",
        now_utc=now_utc,
    )
    assert delta is not None
    assert abs(delta - 3600) < 1


def test_is_preset_frozen_respects_thaw(now_utc: datetime) -> None:
    evs = [
        _event(
            at_utc=now_utc - timedelta(hours=2),
            event_type="preset_frozen",
        ).to_payload(),
        _event(
            at_utc=now_utc - timedelta(hours=1),
            event_type="preset_thawed",
        ).to_payload(),
    ]
    assert not is_preset_frozen(evs, "trend_equities_4h_baseline")
    evs.append(
        _event(
            at_utc=now_utc,
            event_type="preset_frozen",
        ).to_payload()
    )
    assert is_preset_frozen(evs, "trend_equities_4h_baseline")


def test_family_outcome_counts_respects_window(now_utc: datetime) -> None:
    old = _event(
        at_utc=now_utc - timedelta(days=30),
        event_type="paper_blocked",
        reason_code="excessive_divergence",
        strategy_family="trend",
        asset_class="equities",
    ).to_payload()
    recent = _event(
        at_utc=now_utc - timedelta(days=2),
        event_type="paper_blocked",
        reason_code="excessive_divergence",
        strategy_family="trend",
        asset_class="equities",
    ).to_payload()
    counts = family_outcome_counts(
        [old, recent],
        strategy_family="trend",
        asset_class="equities",
        window_days=14,
        now_utc=now_utc,
    )
    assert counts["excessive_divergence"] == 1


def test_event_types_vocabulary_is_closed() -> None:
    assert "campaign_spawned" in EVENT_TYPES
    assert "duplicate_spawn_rejected" in EVENT_TYPES
    assert "budget_exceeded" in EVENT_TYPES
