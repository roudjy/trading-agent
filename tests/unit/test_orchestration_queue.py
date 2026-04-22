"""
Unit tests for `orchestration/queue.py` (v3.9 phase 4).

Exercises:
- `TaskQueue` state transitions (pending -> in-flight -> completed/failed).
- Insertion-order preservation for pending.
- Duplicate-id rejection.
- Invalid transitions raise `TaskQueueError`.
- Read-only accessors (counts, results, failures).
"""

from __future__ import annotations

import pytest

from orchestration.queue import TaskQueue, TaskQueueError
from orchestration.task import (
    ReasonCode,
    Task,
    TaskFailure,
    TaskKind,
    TaskResult,
)


def _make(n: int, kind: TaskKind = TaskKind.SCREENING_BATCH) -> Task:
    return Task.build(candidate_id=f"batch-{n:03d}", kind=kind)


def test_empty_queue_has_no_pending() -> None:
    q = TaskQueue()
    assert q.has_pending() is False
    assert q.pending_count() == 0
    assert q.total_count() == 0


def test_enqueue_adds_to_pending() -> None:
    q = TaskQueue()
    q.enqueue(_make(1))
    q.enqueue(_make(2))
    assert q.pending_count() == 2
    assert q.has_pending() is True


def test_enqueue_preserves_insertion_order() -> None:
    q = TaskQueue()
    tasks = [_make(n) for n in range(5)]
    for t in tasks:
        q.enqueue(t)
    peeked = q.peek_pending()
    assert [t.candidate_id for t in peeked] == [t.candidate_id for t in tasks]


def test_enqueue_rejects_duplicate_pending() -> None:
    q = TaskQueue()
    t = _make(1)
    q.enqueue(t)
    with pytest.raises(TaskQueueError, match="already pending"):
        q.enqueue(t)


def test_enqueue_rejects_duplicate_in_flight() -> None:
    q = TaskQueue()
    t = _make(1)
    q.enqueue(t)
    q.mark_in_flight(t)
    with pytest.raises(TaskQueueError, match="already in flight"):
        q.enqueue(t)


def test_mark_in_flight_moves_from_pending() -> None:
    q = TaskQueue()
    t = _make(1)
    q.enqueue(t)
    q.mark_in_flight(t)
    assert q.pending_count() == 0
    assert q.in_flight_count() == 1


def test_mark_in_flight_rejects_unknown_task() -> None:
    q = TaskQueue()
    with pytest.raises(TaskQueueError, match="not pending"):
        q.mark_in_flight(_make(99))


def test_mark_completed_moves_from_in_flight() -> None:
    q = TaskQueue()
    t = _make(1)
    q.enqueue(t)
    q.mark_in_flight(t)
    result = TaskResult(
        task_id=t.task_id,
        candidate_id=t.candidate_id,
        kind=t.kind,
    )
    q.mark_completed(t.task_id, result)
    assert q.in_flight_count() == 0
    assert q.completed_count() == 1
    assert q.get_result(t.task_id) == result


def test_mark_completed_rejects_non_in_flight_task() -> None:
    q = TaskQueue()
    with pytest.raises(TaskQueueError, match="not in flight"):
        q.mark_completed(
            "missing#screening_batch#001",
            TaskResult(
                task_id="missing#screening_batch#001",
                candidate_id="missing",
                kind=TaskKind.SCREENING_BATCH,
            ),
        )


def test_mark_failed_moves_from_in_flight() -> None:
    q = TaskQueue()
    t = _make(1)
    q.enqueue(t)
    q.mark_in_flight(t)
    failure = TaskFailure(
        task_id=t.task_id,
        candidate_id=t.candidate_id,
        kind=t.kind,
        reason_code=ReasonCode.STRATEGY_ERROR,
    )
    q.mark_failed(t.task_id, failure)
    assert q.in_flight_count() == 0
    assert q.failed_count() == 1
    assert q.get_failure(t.task_id) == failure


def test_mark_failed_rejects_non_in_flight_task() -> None:
    q = TaskQueue()
    with pytest.raises(TaskQueueError, match="not in flight"):
        q.mark_failed(
            "missing#screening_batch#001",
            TaskFailure(
                task_id="missing#screening_batch#001",
                candidate_id="missing",
                kind=TaskKind.SCREENING_BATCH,
                reason_code=ReasonCode.STRATEGY_ERROR,
            ),
        )


def test_contains_reports_across_all_states() -> None:
    q = TaskQueue()
    t_pending = _make(1)
    t_flight = _make(2)
    t_completed = _make(3)
    t_failed = _make(4)

    q.enqueue(t_pending)

    q.enqueue(t_flight)
    q.mark_in_flight(t_flight)

    q.enqueue(t_completed)
    q.mark_in_flight(t_completed)
    q.mark_completed(
        t_completed.task_id,
        TaskResult(
            task_id=t_completed.task_id,
            candidate_id=t_completed.candidate_id,
            kind=t_completed.kind,
        ),
    )

    q.enqueue(t_failed)
    q.mark_in_flight(t_failed)
    q.mark_failed(
        t_failed.task_id,
        TaskFailure(
            task_id=t_failed.task_id,
            candidate_id=t_failed.candidate_id,
            kind=t_failed.kind,
            reason_code=ReasonCode.STRATEGY_ERROR,
        ),
    )

    for t in (t_pending, t_flight, t_completed, t_failed):
        assert q.contains(t.task_id)
    assert not q.contains("unknown-task-id")


def test_total_count_is_sum_of_all_states() -> None:
    q = TaskQueue()
    q.enqueue(_make(1))
    q.enqueue(_make(2))
    t = _make(3)
    q.enqueue(t)
    q.mark_in_flight(t)
    assert q.total_count() == 3


def test_iter_pending_yields_in_insertion_order() -> None:
    q = TaskQueue()
    tasks = [_make(n) for n in (3, 1, 2, 10, 5)]
    for t in tasks:
        q.enqueue(t)
    ids = [t.candidate_id for t in q.iter_pending()]
    assert ids == [t.candidate_id for t in tasks]


def test_queue_exposed_via_public_api() -> None:
    import orchestration

    assert hasattr(orchestration, "TaskQueue")
    assert hasattr(orchestration, "TaskQueueError")
    assert orchestration.TaskQueue is TaskQueue
