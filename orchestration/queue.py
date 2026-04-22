"""
In-memory task queue for the orchestration layer (v3.9 phase 4).

`TaskQueue` tracks tasks across four lifecycle states: pending,
in-flight, completed, failed. It is the orchestration layer's
transient coordination surface - not a source of truth.

Design invariants (pinned by ADR-009, phase 4):

- **Queue is cache, artifacts are truth.** Resume, recovery, and
  run-lifecycle state live in `research/*.v1.json` artifacts. This
  queue holds in-memory lifecycle pointers for the current dispatch
  loop only; it is rebuilt fresh on each Orchestrator invocation
  and discarded at shutdown. No durable persistence.
- **Insertion is idempotent by `task_id`.** Enqueuing a task with
  the same `task_id` as an existing pending/in-flight task raises;
  this catches accidental duplicate dispatch.
- **State transitions are monotonic.** pending -> in-flight ->
  (completed | failed). You cannot re-open a completed task; you
  cannot mark an in-flight task completed without first marking it
  in-flight.
- **Pending iteration is deterministic.** `peek_pending()` returns
  tasks in insertion order; the Scheduler layers additional
  deterministic ordering on top.
- **No threading primitives.** Phase 4 dispatch is single-threaded
  at the Orchestrator level; `ProcessPoolExecutor` provides
  cross-process workers but the Queue is only touched on the
  coordinator thread.
"""

from __future__ import annotations

from typing import Iterator

from orchestration.task import Task, TaskFailure, TaskResult


class TaskQueueError(RuntimeError):
    """Raised when a TaskQueue state transition is invalid."""


class TaskQueue:
    """In-memory queue tracking task lifecycle.

    The queue holds four disjoint sets keyed by `task_id`:
    - pending: enqueued, not yet dispatched
    - in_flight: dispatched, awaiting result
    - completed: finished with a `TaskResult`
    - failed: finished with a `TaskFailure`

    Transitions:
    - `enqueue(task)`: adds to pending (rejects duplicates across
      pending + in-flight).
    - `mark_in_flight(task)`: moves from pending to in-flight.
    - `mark_completed(task_id, result)`: moves from in-flight to
      completed.
    - `mark_failed(task_id, failure)`: moves from in-flight to failed.
    """

    def __init__(self) -> None:
        # Insertion-order dict for pending so peek_pending() is
        # deterministic without requiring a separate list.
        self._pending: dict[str, Task] = {}
        self._in_flight: dict[str, Task] = {}
        self._completed: dict[str, TaskResult] = {}
        self._failed: dict[str, TaskFailure] = {}

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def enqueue(self, task: Task) -> None:
        """Add `task` to pending. Rejects duplicate task_ids."""

        if task.task_id in self._pending:
            raise TaskQueueError(
                f"task_id {task.task_id!r} already pending"
            )
        if task.task_id in self._in_flight:
            raise TaskQueueError(
                f"task_id {task.task_id!r} already in flight"
            )
        self._pending[task.task_id] = task

    def mark_in_flight(self, task: Task) -> None:
        """Move `task` from pending to in-flight."""

        if task.task_id not in self._pending:
            raise TaskQueueError(
                f"task_id {task.task_id!r} is not pending"
            )
        del self._pending[task.task_id]
        self._in_flight[task.task_id] = task

    def mark_completed(self, task_id: str, result: TaskResult) -> None:
        """Move an in-flight task to completed with the given result."""

        if task_id not in self._in_flight:
            raise TaskQueueError(
                f"task_id {task_id!r} is not in flight"
            )
        del self._in_flight[task_id]
        self._completed[task_id] = result

    def mark_failed(self, task_id: str, failure: TaskFailure) -> None:
        """Move an in-flight task to failed with the given failure."""

        if task_id not in self._in_flight:
            raise TaskQueueError(
                f"task_id {task_id!r} is not in flight"
            )
        del self._in_flight[task_id]
        self._failed[task_id] = failure

    # ------------------------------------------------------------------
    # Read-only accessors (for Scheduler and test introspection)
    # ------------------------------------------------------------------

    def peek_pending(self) -> list[Task]:
        """Return pending tasks in insertion order (stable copy)."""

        return list(self._pending.values())

    def iter_pending(self) -> Iterator[Task]:
        """Iterate over pending tasks in insertion order.

        The Scheduler's `next_dispatch` consumes this view but does
        not mutate the queue directly; the Orchestrator calls
        `mark_in_flight` once a task is selected for dispatch.
        """

        return iter(self._pending.values())

    def has_pending(self) -> bool:
        return bool(self._pending)

    def pending_count(self) -> int:
        return len(self._pending)

    def in_flight_count(self) -> int:
        return len(self._in_flight)

    def completed_count(self) -> int:
        return len(self._completed)

    def failed_count(self) -> int:
        return len(self._failed)

    def total_count(self) -> int:
        return (
            len(self._pending)
            + len(self._in_flight)
            + len(self._completed)
            + len(self._failed)
        )

    def get_result(self, task_id: str) -> TaskResult | None:
        """Return the result for a completed task, or None."""

        return self._completed.get(task_id)

    def get_failure(self, task_id: str) -> TaskFailure | None:
        """Return the failure for a failed task, or None."""

        return self._failed.get(task_id)

    def contains(self, task_id: str) -> bool:
        """True iff `task_id` is tracked in any state."""

        return (
            task_id in self._pending
            or task_id in self._in_flight
            or task_id in self._completed
            or task_id in self._failed
        )


__all__ = ["TaskQueue", "TaskQueueError"]
