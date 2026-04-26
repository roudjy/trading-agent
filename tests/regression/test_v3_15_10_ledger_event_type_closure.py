"""v3.15.10 regression — pin the closed EventType set.

Adding a new event type without bumping LEDGER_SCHEMA_VERSION is
allowed (additive), but the closure must be intentional.
v3.15.10 adds 4 funnel event types; this test pins the new
closure so a silent drop or rename triggers immediately.
"""

from __future__ import annotations

from typing import get_args

from research.campaign_evidence_ledger import (
    EVENT_TYPES,
    EventType,
    LEDGER_SCHEMA_VERSION,
    make_event,
)
import pytest


_PRE_V3_15_10_EVENT_TYPES = frozenset(
    {
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
    }
)
_V3_15_10_NEW_EVENT_TYPES = frozenset(
    {
        "funnel_decision_emitted",
        "funnel_evidence_stale_or_mismatched",
        "funnel_technical_no_freeze",
        "funnel_policy_error",
    }
)


def test_event_type_closure_is_pre_v3_15_10_plus_4_funnel_types() -> None:
    expected = _PRE_V3_15_10_EVENT_TYPES | _V3_15_10_NEW_EVENT_TYPES
    assert set(EVENT_TYPES) == expected
    assert set(get_args(EventType)) == expected


def test_ledger_schema_version_unchanged_at_1_0() -> None:
    """Adding event-type Literal members is additive — no
    schema_version bump required. v3.15.10 keeps the ledger at
    1.0 because the on-disk JSONL row schema is unchanged.
    """
    assert LEDGER_SCHEMA_VERSION == "1.0"


def test_make_event_accepts_new_funnel_event_types() -> None:
    from datetime import UTC, datetime
    for ev_type in _V3_15_10_NEW_EVENT_TYPES:
        ev = make_event(
            campaign_id="x",
            parent_campaign_id=None,
            lineage_root_campaign_id="",
            preset_name="p",
            campaign_type="daily_primary",
            event_type=ev_type,  # type: ignore[arg-type]
            at_utc=datetime(2026, 4, 26, tzinfo=UTC),
        )
        assert ev.event_type == ev_type


def test_make_event_rejects_unknown_event_type() -> None:
    from datetime import UTC, datetime
    with pytest.raises(ValueError):
        make_event(
            campaign_id="x",
            parent_campaign_id=None,
            lineage_root_campaign_id="",
            preset_name="p",
            campaign_type="daily_primary",
            event_type="not_an_event_type",  # type: ignore[arg-type]
            at_utc=datetime(2026, 4, 26, tzinfo=UTC),
        )
