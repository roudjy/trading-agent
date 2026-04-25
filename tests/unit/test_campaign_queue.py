"""Tests for research.campaign_queue (v3.15.2 COL execution view)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from research.campaign_queue import (
    QueueEntry,
    active_lease_count,
    clear_lease,
    find_entry,
    load_queue,
    queue_entry_from_record,
    rebuild_queue_from_registry,
    remove_entry,
    set_lease,
    upsert_entry,
    write_queue,
)


@pytest.fixture
def now_utc() -> datetime:
    return datetime(2026, 4, 24, 8, 0, 0, tzinfo=UTC)


def _registry_record(
    *,
    campaign_id: str,
    state: str = "pending",
    priority_tier: int = 2,
    spawned_at_utc: str = "2026-04-24T08:00:00Z",
) -> dict:
    return {
        "campaign_id": campaign_id,
        "state": state,
        "priority_tier": priority_tier,
        "spawned_at_utc": spawned_at_utc,
        "estimated_runtime_seconds": 1800,
    }


def test_rebuild_queue_from_registry_only_active_states() -> None:
    registry = {
        "campaigns": {
            "col-a": _registry_record(campaign_id="col-a", state="pending"),
            "col-b": _registry_record(campaign_id="col-b", state="completed"),
            "col-c": _registry_record(campaign_id="col-c", state="leased"),
            "col-d": _registry_record(campaign_id="col-d", state="archived"),
        }
    }
    queue = rebuild_queue_from_registry(registry)
    ids = {e["campaign_id"] for e in queue["queue"]}
    assert ids == {"col-a", "col-c"}


def test_queue_is_sorted_deterministically() -> None:
    registry = {
        "campaigns": {
            "col-b": _registry_record(campaign_id="col-b", priority_tier=2),
            "col-a": _registry_record(campaign_id="col-a", priority_tier=1),
            "col-c": _registry_record(
                campaign_id="col-c",
                priority_tier=1,
                spawned_at_utc="2026-04-24T07:00:00Z",
            ),
        }
    }
    queue = rebuild_queue_from_registry(registry)
    # priority_tier=1 entries come first, ordered by spawned_at_utc ASC.
    assert [e["campaign_id"] for e in queue["queue"]] == [
        "col-c",
        "col-a",
        "col-b",
    ]


def test_queue_entry_from_record_projects_lease() -> None:
    record = {
        "campaign_id": "col-x",
        "state": "leased",
        "priority_tier": 1,
        "spawned_at_utc": "2026-04-24T08:00:00Z",
        "estimated_runtime_seconds": 1800,
        "lease": {
            "lease_id": "abc",
            "worker_id": "w-1",
            "leased_at_utc": "2026-04-24T08:05:00Z",
            "expires_utc": "2026-04-24T10:05:00Z",
            "attempt": 1,
        },
    }
    entry = queue_entry_from_record(record)
    assert entry.state == "leased"
    assert isinstance(entry.lease, dict)
    assert entry.lease["lease_id"] == "abc"


def test_set_lease_then_clear_lease_cycle(now_utc: datetime) -> None:
    registry = {
        "campaigns": {
            "col-x": _registry_record(campaign_id="col-x", state="pending"),
        }
    }
    queue = rebuild_queue_from_registry(registry)
    lease_payload = {
        "lease_id": "abc",
        "worker_id": "w",
        "leased_at_utc": "2026-04-24T08:05:00Z",
        "expires_utc": "2026-04-24T10:05:00Z",
        "attempt": 1,
    }
    queue = set_lease(queue, campaign_id="col-x", lease_payload=lease_payload)
    assert active_lease_count(queue) == 1
    queue = clear_lease(queue, campaign_id="col-x", to_state="pending")
    assert active_lease_count(queue) == 0


def test_find_entry_returns_none_when_absent() -> None:
    assert find_entry({"queue": []}, "col-absent") is None


def test_upsert_replaces_same_id() -> None:
    queue: dict = {"queue": []}
    queue = upsert_entry(
        queue,
        QueueEntry(
            campaign_id="col-x",
            priority_tier=2,
            spawned_at_utc="2026-04-24T08:00:00Z",
            state="pending",
            earliest_retry_utc=None,
            lease=None,
            estimated_runtime_seconds=1800,
        ),
    )
    queue = upsert_entry(
        queue,
        QueueEntry(
            campaign_id="col-x",
            priority_tier=1,  # changed
            spawned_at_utc="2026-04-24T08:00:00Z",
            state="pending",
            earliest_retry_utc=None,
            lease=None,
            estimated_runtime_seconds=900,
        ),
    )
    assert len(queue["queue"]) == 1
    assert queue["queue"][0]["priority_tier"] == 1


def test_remove_entry_is_noop_when_absent() -> None:
    queue = remove_entry({"queue": []}, "col-absent")
    assert queue["queue"] == []


def test_write_queue_is_byte_reproducible(
    tmp_path: Path, now_utc: datetime
) -> None:
    registry = {
        "campaigns": {
            "col-x": _registry_record(campaign_id="col-x"),
        }
    }
    queue = rebuild_queue_from_registry(registry)
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    write_queue(queue, generated_at_utc=now_utc, path=path_a)
    write_queue(queue, generated_at_utc=now_utc, path=path_b)
    assert path_a.read_bytes() == path_b.read_bytes()


def test_load_queue_returns_skeleton_on_missing(tmp_path: Path) -> None:
    queue = load_queue(tmp_path / "missing.json")
    assert queue == {"queue": []}
