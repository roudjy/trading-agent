"""
Execution backends for the orchestration layer (v3.9 phase 3).

Provides the `ExecutionBackend` abstract interface with two concrete
implementations:

- `InlineBackend`: runs a task synchronously in the calling process.
  Used by tests and by any configuration that opts out of process-
  pool execution.
- `ProcessPoolBackend`: runs tasks across a pool of worker processes
  using `concurrent.futures.ProcessPoolExecutor`. Phase 3 exposes
  this backend and unit-tests it, but the Phase 3 `Orchestrator`
  does not dispatch through it yet - the existing `research/`
  batch-execution drivers continue to own their own pool, so
  behavior is bytewise preserved. Phase 4 will wire this backend
  into the Orchestrator's dispatch path.

Design invariants (pinned by ADR-009):

- The backend is the *only* place in `orchestration/` that knows how
  to invoke the worker. The Orchestrator does not spawn processes
  or submit futures directly; it goes through a backend.
- Backends are disposable. Calling `shutdown(wait=True)` releases
  all owned resources.
- Workers built on top of `ProcessPoolExecutor` exchange Tasks and
  TaskResults via pickle, which is why the Phase 2 data model is
  pickle-safe.
- No backend caches engine state across tasks.
"""

from __future__ import annotations

import abc
from concurrent.futures import Executor, Future, ProcessPoolExecutor
from typing import Type, Union

from orchestration.task import Task, TaskFailure, TaskResult
from orchestration.worker import run_task

TaskOutcome = Union[TaskResult, TaskFailure]


class ExecutionBackend(abc.ABC):
    """Abstract interface for a task-dispatch backend."""

    @abc.abstractmethod
    def submit(self, task: Task) -> "Future[TaskOutcome]":
        """Submit `task` and return a Future for its outcome.

        The returned Future resolves to either a `TaskResult` (success)
        or a `TaskFailure` (typed failure). Exceptions raised inside
        the worker propagate through the Future (caller may observe
        via `Future.exception()`) - they are not silently converted
        to TaskFailure here. The Orchestrator decides how to map
        uncaught exceptions to reason codes.
        """

    @abc.abstractmethod
    def shutdown(self, *, wait: bool = True) -> None:
        """Release backend-owned resources. Idempotent."""


class InlineBackend(ExecutionBackend):
    """Runs tasks synchronously in the calling process.

    Provides the same Future-based contract as other backends so
    callers do not branch on backend type. The returned Future is
    always in a completed state on return from `submit`.
    """

    def submit(self, task: Task) -> "Future[TaskOutcome]":
        fut: Future[TaskOutcome] = Future()
        try:
            outcome = run_task(task)
        except BaseException as exc:  # noqa: BLE001 - bubbling via Future
            fut.set_exception(exc)
        else:
            fut.set_result(outcome)
        return fut

    def shutdown(self, *, wait: bool = True) -> None:
        # No resources to release.
        return None


class ProcessPoolBackend(ExecutionBackend):
    """Runs tasks across a pool-based `concurrent.futures.Executor`.

    The pool is created at construction and owned by this backend.
    Worker processes (or threads, if `executor_class` is overridden
    for testing) invoke `orchestration.worker.run_task` with the
    dispatched Task. In the production configuration
    (`executor_class=ProcessPoolExecutor`), the Task and its outcome
    travel across process boundaries via pickle, which is why Phase
    2 constrains those types to be pickle-safe.

    `executor_class` is an escape hatch for tests that need to stay
    in-process (e.g., to keep monkey-patches visible to the worker);
    tests may pass `ThreadPoolExecutor`. Production code should
    continue to use the default `ProcessPoolExecutor` so engine
    calls run in isolated subprocesses.
    """

    def __init__(
        self,
        *,
        max_workers: int = 1,
        executor_class: Type[Executor] = ProcessPoolExecutor,
    ) -> None:
        if max_workers < 1:
            raise ValueError(f"max_workers must be >= 1, got {max_workers!r}")
        self._max_workers = max_workers
        self._executor_class = executor_class
        self._executor = executor_class(max_workers=max_workers)
        self._shutdown = False

    @property
    def max_workers(self) -> int:
        return self._max_workers

    def submit(self, task: Task) -> "Future[TaskOutcome]":
        if self._shutdown:
            raise RuntimeError("ProcessPoolBackend has been shut down")
        return self._executor.submit(run_task, task)

    def shutdown(self, *, wait: bool = True) -> None:
        if self._shutdown:
            return
        self._executor.shutdown(wait=wait)
        self._shutdown = True


__all__ = [
    "ExecutionBackend",
    "InlineBackend",
    "ProcessPoolBackend",
    "TaskOutcome",
]
