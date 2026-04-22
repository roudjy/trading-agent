"""
Unit tests for `orchestration/scheduler.py` (v3.9 phase 4).

Exercises:
- `FifoScheduler` returns pending tasks in insertion order.
- Scheduler does not mutate the queue.
- Returns None when no pending tasks.
- Respects the `Scheduler` abstract surface.
"""

from __future__ import annotations

from orchestration.queue import TaskQueue
from orchestration.scheduler import FifoScheduler, Scheduler
from orchestration.task import Task, TaskKind


def _make(n: int) -> Task:
    return Task.build(candidate_id=f"batch-{n:03d}", kind=TaskKind.SCREENING_BATCH)


def test_fifo_scheduler_is_scheduler() -> None:
    assert isinstance(FifoScheduler(), Scheduler)


def test_fifo_returns_none_for_empty_queue() -> None:
    q = TaskQueue()
    s = FifoScheduler()
    assert s.next_dispatch(q) is None


def test_fifo_returns_first_enqueued_task() -> None:
    q = TaskQueue()
    t1 = _make(1)
    t2 = _make(2)
    q.enqueue(t1)
    q.enqueue(t2)
    s = FifoScheduler()
    assert s.next_dispatch(q) is t1


def test_fifo_does_not_mutate_queue() -> None:
    q = TaskQueue()
    t1 = _make(1)
    t2 = _make(2)
    q.enqueue(t1)
    q.enqueue(t2)
    s = FifoScheduler()
    _ = s.next_dispatch(q)
    # Queue state must be unchanged.
    assert q.pending_count() == 2
    assert [t.candidate_id for t in q.peek_pending()] == ["batch-001", "batch-002"]


def test_fifo_respects_insertion_order_not_numeric_order() -> None:
    q = TaskQueue()
    # Enqueue out-of-numeric-order to show FIFO respects insertion, not id sort.
    for n in (5, 1, 3, 2, 4):
        q.enqueue(_make(n))
    s = FifoScheduler()
    # First enqueued is batch-005.
    first = s.next_dispatch(q)
    assert first is not None
    assert first.candidate_id == "batch-005"


def test_fifo_progressively_returns_next_as_in_flight_is_marked() -> None:
    q = TaskQueue()
    tasks = [_make(n) for n in range(3)]
    for t in tasks:
        q.enqueue(t)
    s = FifoScheduler()

    t = s.next_dispatch(q)
    assert t is tasks[0]
    q.mark_in_flight(t)

    t = s.next_dispatch(q)
    assert t is tasks[1]
    q.mark_in_flight(t)

    t = s.next_dispatch(q)
    assert t is tasks[2]
    q.mark_in_flight(t)

    assert s.next_dispatch(q) is None


def test_scheduler_exposed_via_public_api() -> None:
    import orchestration

    assert hasattr(orchestration, "FifoScheduler")
    assert hasattr(orchestration, "Scheduler")
    assert orchestration.FifoScheduler is FifoScheduler
