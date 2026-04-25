"""Tests for research.campaign_lease (v3.15.2 COL lock primitive)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from research.campaign_lease import (
    CampaignLockTimeoutError,
    acquire_queue_lock,
    build_lease,
    build_lease_id,
    build_worker_id,
    is_lease_expired,
)


@pytest.fixture
def now_utc() -> datetime:
    return datetime(2026, 4, 24, 8, 0, 0, tzinfo=UTC)


def test_build_worker_id_contains_hostname_and_pid() -> None:
    worker_id = build_worker_id(pid=12345)
    assert worker_id.startswith("launcher-")
    assert worker_id.endswith("-12345")


def test_build_lease_id_is_deterministic() -> None:
    a = build_lease_id(
        campaign_id="col-1",
        worker_id="launcher-host-1",
        leased_at_utc="2026-04-24T08:00:00Z",
    )
    b = build_lease_id(
        campaign_id="col-1",
        worker_id="launcher-host-1",
        leased_at_utc="2026-04-24T08:00:00Z",
    )
    assert a == b


def test_build_lease_computes_ttl(now_utc: datetime) -> None:
    lease = build_lease(
        campaign_id="col-1",
        worker_id="launcher-host-1",
        leased_at=now_utc,
        ttl_seconds=3600,
        attempt=1,
    )
    assert lease.lease_id
    assert lease.attempt == 1
    # Expiry is 1h past leased_at.
    assert lease.expires_utc == "2026-04-24T09:00:00Z"


def test_is_lease_expired_past_ttl(now_utc: datetime) -> None:
    lease_payload = {
        "expires_utc": (now_utc - timedelta(hours=1)).astimezone(UTC).isoformat().replace(
            "+00:00", "Z"
        ),
    }
    assert is_lease_expired(lease_payload, now_utc)


def test_is_lease_expired_future_ttl(now_utc: datetime) -> None:
    lease_payload = {
        "expires_utc": (now_utc + timedelta(hours=1)).astimezone(UTC).isoformat().replace(
            "+00:00", "Z"
        ),
    }
    assert not is_lease_expired(lease_payload, now_utc)


def test_is_lease_expired_malformed(now_utc: datetime) -> None:
    assert is_lease_expired({"expires_utc": "not-a-date"}, now_utc)
    assert is_lease_expired({}, now_utc)


def test_acquire_queue_lock_is_reentrant_within_process(tmp_path: Path) -> None:
    """Sanity check: the context manager releases cleanly after the with."""
    with acquire_queue_lock(lock_dir=tmp_path):
        pass
    # A second acquire should succeed — previous one released.
    with acquire_queue_lock(lock_dir=tmp_path):
        pass


def _lock_holder_entrypoint(
    lock_dir: str, ready_event, stop_event
) -> None:  # pragma: no cover - executes in child process
    from research.campaign_lease import acquire_queue_lock

    with acquire_queue_lock(lock_dir=Path(lock_dir)):
        ready_event.set()
        stop_event.wait(timeout=5.0)


def test_acquire_queue_lock_timeout_raises(tmp_path: Path) -> None:
    """Simulate contention by holding the lock in another process."""
    import multiprocessing as mp

    ctx = mp.get_context("spawn")
    ready = ctx.Event()
    stop = ctx.Event()
    proc = ctx.Process(
        target=_lock_holder_entrypoint,
        args=(str(tmp_path), ready, stop),
        daemon=True,
    )
    proc.start()
    try:
        assert ready.wait(timeout=5.0), "holder failed to acquire"
        with pytest.raises(CampaignLockTimeoutError):
            with acquire_queue_lock(
                lock_dir=tmp_path, max_wait_seconds=1.0
            ):
                pass
    finally:
        stop.set()
        proc.join(timeout=5.0)
        if proc.is_alive():
            proc.terminate()
