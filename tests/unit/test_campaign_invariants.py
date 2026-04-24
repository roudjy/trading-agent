"""Tests for research.campaign_invariants (v3.15.2 runtime invariants)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from research.campaign_evidence_ledger import make_event
from research.campaign_invariants import (
    CampaignInvariantViolation,
    assert_invariants,
)


NOW = datetime(2026, 4, 24, 8, 0, 0, tzinfo=UTC)


def _record(
    *,
    campaign_id: str,
    state: str = "pending",
    parent_campaign_id: str | None = None,
    lineage_root: str | None = None,
    input_fingerprint: str = "fp",
    campaign_type: str = "daily_primary",
    preset: str = "trend_equities_4h_baseline",
) -> dict:
    return {
        "campaign_id": campaign_id,
        "state": state,
        "campaign_type": campaign_type,
        "preset_name": preset,
        "parent_campaign_id": parent_campaign_id,
        "lineage_root_campaign_id": lineage_root or campaign_id,
        "input_artifact_fingerprint": input_fingerprint,
    }


def _queue_entry(*, campaign_id: str, state: str = "pending") -> dict:
    return {
        "campaign_id": campaign_id,
        "state": state,
        "priority_tier": 2,
        "spawned_at_utc": "2026-04-24T08:00:00Z",
        "estimated_runtime_seconds": 1800,
    }


def _event(*, campaign_id: str, event_type: str, run_id: str | None = None) -> dict:
    return make_event(
        campaign_id=campaign_id,
        parent_campaign_id=None,
        lineage_root_campaign_id=campaign_id,
        preset_name="p",
        campaign_type="daily_primary",
        event_type=event_type,  # type: ignore[arg-type]
        at_utc=NOW,
        run_id=run_id,
    ).to_payload()


def test_happy_empty_state_passes() -> None:
    report = assert_invariants(
        registry={"campaigns": {}},
        queue={"queue": []},
        events=[],
        max_concurrent_campaigns=1,
    )
    assert "I1_single_active" in report.passed
    assert "I9_followup_idempotency" in report.passed


def test_i1_single_active_violation() -> None:
    registry = {
        "campaigns": {
            "col-a": _record(campaign_id="col-a", state="leased"),
            "col-b": _record(campaign_id="col-b", state="running"),
        }
    }
    queue = {
        "queue": [
            _queue_entry(campaign_id="col-a", state="leased"),
            _queue_entry(campaign_id="col-b", state="running"),
        ]
    }
    with pytest.raises(CampaignInvariantViolation, match="I1"):
        assert_invariants(
            registry=registry,
            queue=queue,
            events=[],
            max_concurrent_campaigns=1,
        )


def test_i2_duplicate_violation() -> None:
    registry = {
        "campaigns": {
            "col-a": _record(campaign_id="col-a"),
            "col-b": _record(campaign_id="col-b"),
        }
    }
    queue = {
        "queue": [
            _queue_entry(campaign_id="col-a"),
            _queue_entry(campaign_id="col-b"),
        ]
    }
    with pytest.raises(CampaignInvariantViolation, match="I2"):
        assert_invariants(
            registry=registry,
            queue=queue,
            events=[],
            max_concurrent_campaigns=1,
        )


def test_i3_orphan_queue_entry() -> None:
    registry = {"campaigns": {}}
    queue = {"queue": [_queue_entry(campaign_id="col-a")]}
    with pytest.raises(CampaignInvariantViolation, match="I3"):
        assert_invariants(
            registry=registry,
            queue=queue,
            events=[],
            max_concurrent_campaigns=1,
        )


def test_i3_orphan_registry_active_entry() -> None:
    registry = {
        "campaigns": {
            "col-a": _record(campaign_id="col-a", state="pending"),
        }
    }
    queue = {"queue": []}
    with pytest.raises(CampaignInvariantViolation, match="I3"):
        assert_invariants(
            registry=registry,
            queue=queue,
            events=[],
            max_concurrent_campaigns=1,
        )


def test_i4_state_mismatch() -> None:
    registry = {
        "campaigns": {
            "col-a": _record(campaign_id="col-a", state="pending"),
        }
    }
    queue = {"queue": [_queue_entry(campaign_id="col-a", state="leased")]}
    with pytest.raises(CampaignInvariantViolation, match="I4"):
        assert_invariants(
            registry=registry,
            queue=queue,
            events=[],
            max_concurrent_campaigns=1,
        )


def test_i5_missing_completion_event() -> None:
    registry = {
        "campaigns": {
            "col-a": _record(campaign_id="col-a", state="completed"),
        }
    }
    queue = {"queue": []}
    with pytest.raises(CampaignInvariantViolation, match="I5"):
        assert_invariants(
            registry=registry,
            queue=queue,
            events=[],
            max_concurrent_campaigns=1,
        )


def test_i5_completion_event_present() -> None:
    registry = {
        "campaigns": {
            "col-a": _record(campaign_id="col-a", state="completed"),
        }
    }
    queue = {"queue": []}
    events = [_event(campaign_id="col-a", event_type="campaign_completed")]
    # Duplicate fingerprint + parent_campaign_id key is only one entry, so I2
    # passes; I5 is satisfied by the completion event.
    registry["campaigns"]["col-a"]["input_artifact_fingerprint"] = "unique"
    assert_invariants(
        registry=registry,
        queue=queue,
        events=events,
        max_concurrent_campaigns=1,
    )


def test_i8_lineage_integrity_violation() -> None:
    registry = {
        "campaigns": {
            "col-child": _record(
                campaign_id="col-child",
                parent_campaign_id="col-missing",
            ),
        }
    }
    queue = {"queue": [_queue_entry(campaign_id="col-child")]}
    with pytest.raises(CampaignInvariantViolation, match="I8"):
        assert_invariants(
            registry=registry,
            queue=queue,
            events=[],
            max_concurrent_campaigns=1,
        )


def test_i9_followup_idempotency_violation() -> None:
    registry = {
        "campaigns": {
            "col-parent": _record(
                campaign_id="col-parent",
                state="completed",
                input_fingerprint="root",
            ),
            "col-child-a": _record(
                campaign_id="col-child-a",
                parent_campaign_id="col-parent",
                campaign_type="paper_followup",
                state="pending",
                input_fingerprint="a",
            ),
            "col-child-b": _record(
                campaign_id="col-child-b",
                parent_campaign_id="col-parent",
                campaign_type="paper_followup",
                state="pending",
                input_fingerprint="b",
            ),
        }
    }
    queue = {
        "queue": [
            _queue_entry(campaign_id="col-child-a"),
            _queue_entry(campaign_id="col-child-b"),
        ]
    }
    events = [_event(campaign_id="col-parent", event_type="campaign_completed")]
    with pytest.raises(CampaignInvariantViolation, match="I9"):
        assert_invariants(
            registry=registry,
            queue=queue,
            events=events,
            max_concurrent_campaigns=1,
        )
