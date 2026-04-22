"""
Unit tests for the v3.9 orchestration ExecutionBackend implementations.

Exercises `orchestration/executor.py` and `orchestration/worker.py`:
- `InlineBackend` runs tasks synchronously and returns completed
  futures.
- `ProcessPoolBackend` runs tasks in a process pool and returns
  running futures that resolve to the same outcomes as the inline
  path for NOOP_PROBE tasks.
- Worker returns a `TaskResult` for `NOOP_PROBE` and a
  `TaskFailure(USER_CANCEL)` for kinds not yet wired to the engine
  in phase 3 (screening / validation candidates).
- Backends shut down cleanly and are idempotent under repeated
  shutdown.
"""

from __future__ import annotations

import concurrent.futures

import pytest

from orchestration.executor import (
    ExecutionBackend,
    InlineBackend,
    ProcessPoolBackend,
)
from orchestration.task import (
    ReasonCode,
    Task,
    TaskFailure,
    TaskKind,
    TaskResult,
)
from orchestration.worker import run_task


# --------------------------------------------------------------------------
# Worker contract
# --------------------------------------------------------------------------


def test_worker_returns_task_result_for_noop_probe() -> None:
    task = Task.build(candidate_id="c-probe", kind=TaskKind.NOOP_PROBE)
    outcome = run_task(task)
    assert isinstance(outcome, TaskResult)
    assert outcome.task_id == task.task_id
    assert outcome.candidate_id == "c-probe"
    assert outcome.kind is TaskKind.NOOP_PROBE


def test_worker_returns_typed_failure_for_unwired_per_candidate_kinds() -> None:
    """Per-candidate kinds remain unwired through phase 4; they will
    be wired in a later phase. Worker returns a typed failure so
    backend plumbing tests still complete with a typed outcome."""

    for kind in (TaskKind.SCREENING_CANDIDATE, TaskKind.VALIDATION_CANDIDATE):
        task = Task.build(candidate_id="c-1", kind=kind)
        outcome = run_task(task)
        assert isinstance(outcome, TaskFailure)
        assert outcome.reason_code is ReasonCode.USER_CANCEL


# --------------------------------------------------------------------------
# InlineBackend
# --------------------------------------------------------------------------


def test_inline_backend_is_executionbackend() -> None:
    assert isinstance(InlineBackend(), ExecutionBackend)


def test_inline_backend_runs_task_synchronously_returning_completed_future() -> None:
    backend = InlineBackend()
    task = Task.build(candidate_id="c-inline", kind=TaskKind.NOOP_PROBE)
    fut = backend.submit(task)
    assert fut.done()
    outcome = fut.result()
    assert isinstance(outcome, TaskResult)
    assert outcome.candidate_id == "c-inline"


def test_inline_backend_shutdown_is_idempotent() -> None:
    backend = InlineBackend()
    backend.shutdown()
    backend.shutdown()  # second call must not raise


# --------------------------------------------------------------------------
# ProcessPoolBackend
# --------------------------------------------------------------------------


def test_process_pool_backend_is_executionbackend() -> None:
    backend = ProcessPoolBackend(max_workers=1)
    try:
        assert isinstance(backend, ExecutionBackend)
    finally:
        backend.shutdown()


def test_process_pool_backend_rejects_zero_max_workers() -> None:
    with pytest.raises(ValueError):
        ProcessPoolBackend(max_workers=0)


def test_process_pool_backend_runs_noop_probe_across_processes() -> None:
    backend = ProcessPoolBackend(max_workers=2)
    try:
        tasks = [
            Task.build(candidate_id=f"c-{n}", kind=TaskKind.NOOP_PROBE)
            for n in range(4)
        ]
        futures = [backend.submit(t) for t in tasks]
        outcomes = [f.result(timeout=30) for f in futures]
    finally:
        backend.shutdown()

    assert all(isinstance(o, TaskResult) for o in outcomes)
    assert sorted(o.candidate_id for o in outcomes) == sorted(t.candidate_id for t in tasks)


def test_process_pool_backend_returns_failure_for_unwired_kind() -> None:
    backend = ProcessPoolBackend(max_workers=1)
    try:
        task = Task.build(candidate_id="c-val", kind=TaskKind.VALIDATION_CANDIDATE)
        fut = backend.submit(task)
        outcome = fut.result(timeout=30)
    finally:
        backend.shutdown()
    assert isinstance(outcome, TaskFailure)
    assert outcome.reason_code is ReasonCode.USER_CANCEL


def test_process_pool_backend_rejects_submit_after_shutdown() -> None:
    backend = ProcessPoolBackend(max_workers=1)
    backend.shutdown()
    with pytest.raises(RuntimeError, match="shut down"):
        backend.submit(Task.build(candidate_id="c-x", kind=TaskKind.NOOP_PROBE))


def test_process_pool_backend_shutdown_is_idempotent() -> None:
    backend = ProcessPoolBackend(max_workers=1)
    backend.shutdown()
    backend.shutdown()  # must not raise


def test_process_pool_backend_exposes_max_workers() -> None:
    backend = ProcessPoolBackend(max_workers=3)
    try:
        assert backend.max_workers == 3
    finally:
        backend.shutdown()


# --------------------------------------------------------------------------
# Future protocol conformance
# --------------------------------------------------------------------------


def test_inline_backend_returns_concurrent_futures_future() -> None:
    backend = InlineBackend()
    fut = backend.submit(Task.build(candidate_id="c-f", kind=TaskKind.NOOP_PROBE))
    assert isinstance(fut, concurrent.futures.Future)
