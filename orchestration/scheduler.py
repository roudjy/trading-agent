"""
Scheduler for the orchestration layer (v3.9 phase 4).

The Scheduler decides which pending Task from a `TaskQueue` should
be dispatched next. It is a pure decision function: given the
queue's current pending set, it returns one Task (or None if no
pending tasks exist). It does not mutate the queue, does not submit
to the backend, and does not know what a Task "means".

Design invariants (pinned by ADR-009, phase 4):

- **Scheduling is deterministic.** Given the same queue state, the
  Scheduler returns the same next-Task. In phase 4 this is achieved
  by insertion-order FIFO; subsequent phases may layer dependency
  or priority on top, still deterministic.
- **No business logic.** The Scheduler deals only in Tasks. It does
  not understand candidate semantics, screening vs validation phase
  ordering, or failure classification.
- **No I/O.** No artifact reads, no config reads, no logging.
"""

from __future__ import annotations

import abc

from orchestration.queue import TaskQueue
from orchestration.task import Task


class Scheduler(abc.ABC):
    """Abstract scheduling decision surface."""

    @abc.abstractmethod
    def next_dispatch(self, queue: TaskQueue) -> Task | None:
        """Return the next pending task to dispatch, or None.

        Must not mutate `queue`. The Orchestrator is responsible for
        moving the returned task to in-flight via
        `queue.mark_in_flight(task)` once it commits to dispatching.
        """


class FifoScheduler(Scheduler):
    """Deterministic first-in-first-out scheduler.

    Returns the pending task in insertion order (the order in which
    `enqueue` was called). This preserves batch-submission order
    across dispatch, which is required for bytewise-deterministic
    artifact ordering when combined with the Orchestrator's
    in-submission-order result collection.
    """

    def next_dispatch(self, queue: TaskQueue) -> Task | None:
        for task in queue.iter_pending():
            return task
        return None


__all__ = ["Scheduler", "FifoScheduler"]
