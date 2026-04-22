"""
Worker-side entry point for the orchestration layer.

This module hosts the process-local function that ExecutionBackend
dispatches Tasks through. In phase 4 it handles four kinds:

- `NOOP_PROBE`: returns an empty TaskResult (used by unit tests to
  exercise backend plumbing without invoking any research code).
- `SCREENING_BATCH`: invokes
  `research.batch_execution.execute_screening_batch(**payload)` and
  returns the full batch result dict inside `TaskResult.payload`
  under key `"batch_result"`.
- `VALIDATION_BATCH`: invokes
  `research.batch_execution.execute_validation_batch(**payload)`
  similarly.
- `SCREENING_CANDIDATE` / `VALIDATION_CANDIDATE`: reserved for a
  later phase. Returns a typed `TaskFailure(USER_CANCEL)` so backend
  plumbing remains observable but nothing real executes.

Design invariants (pinned by ADR-009):

- **Fresh engine per task.** The engine is never memoized across
  tasks. `execute_screening_batch` and `execute_validation_batch`
  each construct a fresh `BacktestEngine` internally (via
  `research.batch_execution._build_engine`). The worker does not
  cache engine instances or hold any state between invocations.
- **Top-level functions only.** `run_task` is a module-level
  function so `ProcessPoolExecutor`'s pickle-based dispatch can
  resolve it by fully-qualified name in subprocesses.
- **No shared mutable state between tasks.** Anything a task needs
  flows through its payload. The worker reads the payload and the
  Task's identity; nothing else.
- **Exceptions propagate.** If the batch runner raises, the
  exception bubbles out of `run_task` and (in process-pool mode)
  surfaces on `Future.result()`. Phase 4 preserves the v3.8 /
  phase-3 behavior of letting the Orchestrator convert the
  exception into a dispatch-loop abort. Typed failure
  classification (per reason code) is a later-phase concern.
"""

from __future__ import annotations

from orchestration.task import (
    ReasonCode,
    Task,
    TaskFailure,
    TaskKind,
    TaskResult,
)


def run_task(task: Task) -> TaskResult | TaskFailure:
    """Run one task and return its outcome.

    Phase 4 dispatch:
    - `NOOP_PROBE` -> empty `TaskResult`.
    - `SCREENING_BATCH` -> `execute_screening_batch(**payload)`, wrap
      result in `TaskResult.payload["batch_result"]`.
    - `VALIDATION_BATCH` -> `execute_validation_batch(**payload)`,
      wrap result in `TaskResult.payload["batch_result"]`.
    - Per-candidate kinds -> `TaskFailure(USER_CANCEL)` (reserved
      for a later phase).

    Exceptions raised by the research-batch runners propagate
    unchanged. The Orchestrator dispatch loop catches them at the
    `future.result()` boundary and raises, matching v3.8 /
    phase-3 behavior.
    """

    if task.kind is TaskKind.NOOP_PROBE:
        return TaskResult(
            task_id=task.task_id,
            candidate_id=task.candidate_id,
            kind=task.kind,
        )

    if task.kind is TaskKind.SCREENING_BATCH:
        # Lazy import so that the orchestration package does not
        # pull research.batch_execution at module-import time for
        # contexts that never need it (e.g., boundary lint tests).
        from research.batch_execution import execute_screening_batch

        batch_result = execute_screening_batch(**dict(task.payload))
        return TaskResult(
            task_id=task.task_id,
            candidate_id=task.candidate_id,
            kind=task.kind,
            payload={"batch_result": batch_result},
        )

    if task.kind is TaskKind.VALIDATION_BATCH:
        from research.batch_execution import execute_validation_batch

        batch_result = execute_validation_batch(**dict(task.payload))
        return TaskResult(
            task_id=task.task_id,
            candidate_id=task.candidate_id,
            kind=task.kind,
            payload={"batch_result": batch_result},
        )

    # Per-candidate kinds are reserved for a later phase.
    return TaskFailure(
        task_id=task.task_id,
        candidate_id=task.candidate_id,
        kind=task.kind,
        reason_code=ReasonCode.USER_CANCEL,
        message=(
            f"task kind {task.kind.value!r} is not wired to an engine "
            f"in v3.9 phase 4; scheduled for a later phase"
        ),
    )


__all__ = ["run_task"]
