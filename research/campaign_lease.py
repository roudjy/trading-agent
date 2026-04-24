"""Cross-platform file-lock primitive for the v3.15.2 Campaign OS.

The COL queue + ledger append are mutated under a single OS-level file
lock (``research/.locks/campaign_queue.lock``). This guarantees two
properties:

1. **Mutual exclusion across processes.** A second launcher invocation
   is serialised, even when they share the same host. The lock is held
   for the entire critical section that updates registry, queue, and
   ledger — matching the R3.3.2 transition contract.

2. **Crash safety.** All writers use ``_sidecar_io.write_sidecar_atomic``
   (tempfile + os.replace) inside the lock, so ``kill -9`` at any step
   leaves the prior artifact intact.

The lease token itself is a pure value object — ``build_lease`` returns
a deterministic id given its inputs, so the lease layer is unit-testable
without the lock.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from research.campaign_os_artifacts import iso_utc

DEFAULT_LOCK_DIR = Path("research/.locks")
DEFAULT_QUEUE_LOCK_FILENAME = "campaign_queue.lock"
_LOCK_ACQUIRE_BACKOFF_S = 0.05
_LOCK_ACQUIRE_MAX_WAIT_S = 60.0


class CampaignLockTimeoutError(RuntimeError):
    """Raised when the queue lock cannot be acquired within the wait budget."""


@dataclass(frozen=True)
class Lease:
    lease_id: str
    worker_id: str
    leased_at_utc: str
    expires_utc: str
    attempt: int

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _hostname() -> str:
    try:
        import socket

        return socket.gethostname() or "unknown-host"
    except Exception:  # pragma: no cover - defensive
        return "unknown-host"


def build_worker_id(*, pid: int | None = None) -> str:
    """Return a deterministic worker identifier for the current process."""
    pid_value = int(pid if pid is not None else os.getpid())
    return f"launcher-{_hostname()}-{pid_value}"


def build_lease_id(
    *,
    campaign_id: str,
    worker_id: str,
    leased_at_utc: str,
) -> str:
    raw = f"{campaign_id}|{worker_id}|{leased_at_utc}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_lease(
    *,
    campaign_id: str,
    worker_id: str,
    leased_at: datetime,
    ttl_seconds: int,
    attempt: int,
) -> Lease:
    leased_iso = iso_utc(leased_at)
    expires_iso = iso_utc(leased_at + timedelta(seconds=int(ttl_seconds)))
    return Lease(
        lease_id=build_lease_id(
            campaign_id=campaign_id,
            worker_id=worker_id,
            leased_at_utc=leased_iso,
        ),
        worker_id=worker_id,
        leased_at_utc=leased_iso,
        expires_utc=expires_iso,
        attempt=int(attempt),
    )


def is_lease_expired(lease_payload: dict[str, Any], now_utc: datetime) -> bool:
    """True iff ``now_utc`` is past the lease's ``expires_utc``."""
    expires = lease_payload.get("expires_utc")
    if not isinstance(expires, str) or not expires:
        return True
    try:
        expires_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    except ValueError:
        return True
    return now_utc.astimezone(UTC) >= expires_dt.astimezone(UTC)


# ---------------------------------------------------------------------------
# OS file lock — blocking acquire, guaranteed release, no leakage across
# processes.
# ---------------------------------------------------------------------------


def _lock_path(
    lock_dir: Path = DEFAULT_LOCK_DIR,
    filename: str = DEFAULT_QUEUE_LOCK_FILENAME,
) -> Path:
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / filename


if sys.platform == "win32":  # pragma: no cover - platform-specific
    import msvcrt

    def _acquire_exclusive(handle) -> None:  # type: ignore[no-untyped-def]
        # Byte-range lock on byte 0. Non-blocking so our retry loop (not
        # msvcrt's builtin 1s*10 blocking behaviour) controls the wait.
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _release_exclusive(handle) -> None:  # type: ignore[no-untyped-def]
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _acquire_exclusive(handle) -> None:  # type: ignore[no-untyped-def]
        # Non-blocking so our retry loop governs the wait deadline.
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release_exclusive(handle) -> None:  # type: ignore[no-untyped-def]
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def acquire_queue_lock(
    *,
    lock_dir: Path = DEFAULT_LOCK_DIR,
    filename: str = DEFAULT_QUEUE_LOCK_FILENAME,
    max_wait_seconds: float = _LOCK_ACQUIRE_MAX_WAIT_S,
) -> Iterator[None]:
    """Acquire the COL queue lock for the lifetime of the with-block.

    Blocking, polling (with backoff) up to ``max_wait_seconds``. Raises
    ``CampaignLockTimeoutError`` if the deadline passes; callers should
    treat that as an abort of the current tick, not a retry.
    """
    path = _lock_path(lock_dir=lock_dir, filename=filename)
    deadline = time.monotonic() + max_wait_seconds
    handle = path.open("a+b")
    try:
        while True:
            try:
                _acquire_exclusive(handle)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise CampaignLockTimeoutError(
                        f"queue lock at {path} unreachable after "
                        f"{max_wait_seconds:.1f}s"
                    )
                time.sleep(_LOCK_ACQUIRE_BACKOFF_S)
        try:
            yield
        finally:
            try:
                _release_exclusive(handle)
            except OSError:
                pass
    finally:
        handle.close()


__all__ = [
    "CampaignLockTimeoutError",
    "DEFAULT_LOCK_DIR",
    "DEFAULT_QUEUE_LOCK_FILENAME",
    "Lease",
    "acquire_queue_lock",
    "build_lease",
    "build_lease_id",
    "build_worker_id",
    "is_lease_expired",
]
