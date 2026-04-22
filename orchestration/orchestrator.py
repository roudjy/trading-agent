"""
Orchestrator entity for the v3.9 platform layer.

Phase 4 upgrades the Orchestrator from the phase-3 pass-through seam
into a real owner of dispatch: it coordinates `Scheduler`, `TaskQueue`,
and (for parallel mode) an `ExecutionBackend` to drive batch-level
execution. Both inline and parallel paths now flow through the
Orchestrator.

Design invariants (pinned by ADR-009):

- **Orchestrator owns dispatch flow.** The batch-dispatch loop
  (enqueue, pop, mark lifecycle state, invoke worker/callback,
  collect result, drive the next dispatch) lives here. Research
  supplies the per-batch work (either as a pickleable worker for
  parallel mode or as a closure for inline mode) plus lifecycle
  hooks; research does not drive the loop.
- **Queue is cache, artifacts are truth.** The Queue tracks
  in-memory pending/in-flight/completed/failed state for the
  current dispatch. It is rebuilt per dispatch call and discarded.
  Resume / recovery truth remains in
  `research/run_state.v1.json`, per-batch recovery artifacts, and
  the public output contract.
- **Determinism.** Inline dispatch is trivially deterministic
  (serial, insertion order). Parallel dispatch uses rolling-submit
  with result collection in batch-submission order, reproducing
  the v3.8 behavior bytewise when combined with the existing
  research `execute_screening_batch` / `execute_validation_batch`
  functions.
- **No engine ownership.** The Orchestrator never constructs a
  `BacktestEngine`. The engine is constructed inside
  `execute_screening_batch` / `execute_validation_batch` (fresh per
  call) which runs inside a worker process (parallel mode) or
  inside the caller-supplied closure (inline mode).
- **No artifact writes.** Artifact writes remain the runner's
  responsibility; the Orchestrator surfaces lifecycle hooks
  (`on_batch_starting`, `on_batch_complete`) so the runner can
  continue to own them.
- **No phase ordering enforcement.** Phase 4 still does not
  enforce screening-before-validation at the Orchestrator level;
  the runner calls `dispatch_*` methods in the correct order. A
  later phase may add typed phase gating.

Backward-compat surface:

- `run_screening_phase` and `run_validation_phase` from phase 3
  remain available as pure pass-through invokers; they are no
  longer used from `research/run_research.py` after phase 4 but
  are kept for back-compat until a later phase drops them.
"""

from __future__ import annotations

import copy
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Type, TypeVar

from orchestration.executor import (
    ExecutionBackend,
    InlineBackend,
    ProcessPoolBackend,
)
from orchestration.queue import TaskQueue
from orchestration.scheduler import FifoScheduler, Scheduler
from orchestration.task import (
    BatchOutcome,
    ReasonCode,
    Task,
    TaskFailure,
    TaskKind,
    TaskResult,
    classify_batch_reason,
)

T = TypeVar("T")

# Type aliases for readability.
Batch = MutableMapping[str, Any]
BatchResult = Mapping[str, Any]
BatchStartingHook = Callable[[Batch], None]
# Phase 5: on_batch_complete returns BatchOutcome. The dispatch layer
# consults outcome.is_failure() to drive stop_on_failure; it no longer
# reads batch["status"] directly. The hook owns the translation from
# research-semantic batch state to the typed orchestration outcome.
BatchCompleteHook = Callable[[Batch, "BatchResult | None"], BatchOutcome]
InlineBatchRunner = Callable[[Batch], BatchResult | None]
ParallelPayloadBuilder = Callable[[Batch], Mapping[str, Any]]


def _noop_start(_batch: Batch) -> None:
    return None


def _default_complete(batch: Batch, _result: BatchResult | None) -> BatchOutcome:
    """**Legacy/test fallback only.** Default `on_batch_complete` hook.

    Scope (pinned by Phase 6):

    - This hook exists solely as a safety net for callers that dispatch
      batches through the Orchestrator without supplying an explicit
      `on_batch_complete` hook. Production code in
      `research/run_research.py` always supplies its own hooks that
      return explicit `BatchOutcome` values; this default is therefore
      exercised only by unit tests that construct `Orchestrator`
      directly and by any ad-hoc caller that forgets the hook.
    - The translation it performs (inspecting `batch["status"]`) is
      deliberately narrow and conservative: `"failed"` maps to a typed
      failure with the reason code derived via
      `classify_batch_reason`; any other status maps to success. A
      `"partial"` status legitimately indicates isolated candidate
      timeouts/errors that the v3.8 rolling-submit path treated as
      continue-able; this hook preserves that semantic.
    - `tests/unit/test_orchestration_default_complete_scope.py` pins
      the rule that production code in `research/run_research.py` does
      not rely on this default. If that test fails, production code
      has started to implicitly depend on the fallback, which is a
      regression in hygiene even if it happens to be correct in
      behavior.

    This hook does **not** emit a deprecation warning at runtime
    because unit tests legitimately rely on it as a no-op success
    hook when constructing `Orchestrator` in isolation. The
    Phase-6-added boundary test above is the explicit guardrail.

    Returns:
        `BatchOutcome.failure(reason_code=..., message=...)` when
        `batch["status"] == "failed"`; `BatchOutcome.success()`
        otherwise.
    """

    if batch.get("status") == "failed":
        return BatchOutcome.failure(
            reason_code=classify_batch_reason(batch.get("reason_code")),
            message=str(batch.get("reason_detail") or ""),
        )
    return BatchOutcome.success()


@dataclass
class Orchestrator:
    """Named entity that owns run-phase dispatch coordination.

    Fields:
    - `backend`: default `ExecutionBackend` used when a phase-4
      dispatch method does not receive an explicit backend. For
      `dispatch_parallel_batches`, the Orchestrator constructs an
      internal `ProcessPoolBackend(max_workers=N)` sized to the
      dispatch call and discards it at the end of the call; the
      field-level backend is preserved as a phase-5+ hook.
    - `scheduler`: decides dispatch order. Default `FifoScheduler`.
    - `queue`: transient in-memory state. Default fresh
      `TaskQueue`.
    - `run_id`: optional identifier for logging / tracing.

    The Queue is *not* reset automatically between dispatch calls.
    Callers that reuse an Orchestrator across screening and
    validation phases share a single Queue - which is fine because
    task_ids are deterministic in `(candidate_id, kind, attempt)`
    and the two kinds produce disjoint ids.
    """

    backend: ExecutionBackend = field(default_factory=InlineBackend)
    scheduler: Scheduler = field(default_factory=FifoScheduler)
    queue: TaskQueue = field(default_factory=TaskQueue)
    run_id: str | None = None

    # ------------------------------------------------------------------
    # Phase 3 back-compat surface (unchanged)
    # ------------------------------------------------------------------

    def run_screening_phase(
        self,
        driver: Callable[..., T],
        /,
        **driver_kwargs: Any,
    ) -> T:
        """Phase-3 pass-through retained for back-compat.

        Not used by `research/run_research.py` after phase 4.
        """

        return driver(**driver_kwargs)

    def run_validation_phase(
        self,
        driver: Callable[..., T],
        /,
        **driver_kwargs: Any,
    ) -> T:
        """Phase-3 pass-through retained for back-compat."""

        return driver(**driver_kwargs)

    def shutdown(self, *, wait: bool = True) -> None:
        """Release backend-owned resources. Idempotent."""

        self.backend.shutdown(wait=wait)

    # ------------------------------------------------------------------
    # Phase 4 dispatch (Orchestrator-owned)
    # ------------------------------------------------------------------

    def dispatch_serial_batches(
        self,
        *,
        batches: Iterable[Batch],
        kind: TaskKind,
        execute_batch: InlineBatchRunner,
        on_batch_starting: BatchStartingHook = _noop_start,
        on_batch_complete: BatchCompleteHook = _default_complete,
    ) -> None:
        """Dispatch `batches` serially, one at a time, in insertion order.

        The intended use is inline mode (`max_workers == 1`). The
        caller-supplied `execute_batch` runs the whole per-batch work
        in-process and returns whatever result the runner wants to
        hand back to `on_batch_complete` (or `None` when the runner
        manages its state entirely inside the callback).

        Lifecycle per batch:
        1. Enqueue a Task (kind as given) for this batch.
        2. Ask the Scheduler for the next dispatch.
        3. Mark in-flight, call `on_batch_starting(batch)`.
        4. Invoke `execute_batch(batch)` synchronously.
        5. Mark completed, call `on_batch_complete(batch, result)`.

        Exceptions raised inside `execute_batch` propagate unchanged,
        after marking the Task failed with a generic reason code.
        (Typed classification is a later-phase concern.)
        """

        batch_list = list(batches)
        batches_by_id: dict[str, Batch] = {}
        for batch in batch_list:
            batch_id = str(batch["batch_id"])
            batches_by_id[batch_id] = batch
            task = Task.build(
                candidate_id=batch_id,
                kind=kind,
                payload={"batch_id": batch_id},
            )
            self.queue.enqueue(task)

        # Drain the subset we just enqueued. We stop when no further
        # pending task matches one of our batch ids; this prevents
        # interleaving if the Orchestrator is shared across phases.
        enqueued_ids = {str(b["batch_id"]) for b in batch_list}
        while True:
            task = self.scheduler.next_dispatch(self.queue)
            if task is None:
                break
            if task.candidate_id not in enqueued_ids:
                # A task from another dispatch call (e.g. a prior
                # phase's leftovers) is ahead of us in FIFO order.
                # Phase 4 does not support interleaving dispatches;
                # break defensively.
                break

            batch = batches_by_id[task.candidate_id]
            self.queue.mark_in_flight(task)
            on_batch_starting(batch)
            try:
                result = execute_batch(batch)
            except BaseException as exc:
                self.queue.mark_failed(
                    task.task_id,
                    TaskFailure(
                        task_id=task.task_id,
                        candidate_id=task.candidate_id,
                        kind=task.kind,
                        reason_code=ReasonCode.STRATEGY_ERROR,
                        message=str(exc),
                    ),
                )
                # The hook receives the failure via the None result.
                # The hook returns a BatchOutcome describing what
                # happened; the serial dispatch does not use the
                # outcome for flow control (failures propagate via
                # the raise below), but the hook runs for side
                # effects (state updates, sidecar persistence).
                try:
                    on_batch_complete(batch, None)
                finally:
                    raise

            self.queue.mark_completed(
                task.task_id,
                TaskResult(
                    task_id=task.task_id,
                    candidate_id=task.candidate_id,
                    kind=task.kind,
                    payload={"batch_result": dict(result)} if result else {},
                ),
            )
            # The hook returns a BatchOutcome. Serial dispatch
            # currently does not act on it (failures propagate via
            # the closure's own except-raise path), but we still
            # invoke the hook so the typed outcome surface remains
            # consistent between serial and parallel dispatch.
            on_batch_complete(batch, result)

    def dispatch_parallel_batches(
        self,
        *,
        batches: Iterable[Batch],
        kind: TaskKind,
        max_workers: int,
        task_payload_for: ParallelPayloadBuilder,
        on_batch_starting: BatchStartingHook = _noop_start,
        on_batch_complete: BatchCompleteHook = _default_complete,
        stop_on_failure: bool = True,
        executor_class: Type[Executor] = ProcessPoolExecutor,
    ) -> None:
        """Dispatch `batches` with rolling-submit up to `max_workers`.

        This method reproduces the v3.8 rolling-submit pattern that
        previously lived in `research/run_research.py:_run_parallel_*_batches`:
        initial submit of up to `max_workers` batches, then for each
        batch in submission order, await its result, call
        `on_batch_complete`, and submit the next pending batch (unless
        `stop_on_failure` is set and we have already observed a
        failure).

        The Orchestrator builds one `Task` per batch, enqueues all
        pending tasks, and delegates actual execution to the
        `ProcessPoolBackend` + `orchestration.worker.run_task`.
        `task_payload_for(batch)` returns the keyword-argument dict
        that the worker will splat into
        `research.batch_execution.execute_screening_batch` /
        `execute_validation_batch`.

        Lifecycle per batch:
        1. (Pre-submit) `on_batch_starting(batch)` - the runner uses
           this to set batch state, persist sidecars, emit tracker
           events.
        2. Submit the Task via the backend.
        3. (On completion, in submission order) unwrap the
           `TaskResult.payload["batch_result"]`, call
           `on_batch_complete(batch, batch_result)`.

        Failure model for phase 4:
        - Worker exceptions surface as exceptions from
          `future.result()`. They propagate out of this method,
          matching v3.8 `raise RuntimeError` behavior at the call
          site. The runner retains its existing failure-detection
          path via `batch["status"]` which `execute_*_batch` sets
          internally.
        - `stop_on_failure`: when True, after `on_batch_complete`
          reports a failed batch (the runner sets
          `batch["status"] == "failed"` inside its hook), no further
          batches are submitted. Matches v3.8 `if not failed_batch_ids`
          guard in the rolling-submit loop.
        """

        if max_workers < 1:
            raise ValueError(
                f"max_workers must be >= 1, got {max_workers!r}"
            )

        batch_list = list(batches)
        if not batch_list:
            return

        # Build deterministic task ordering: insertion order reflects
        # the batch list we were given.
        batches_by_id: dict[str, Batch] = {}
        task_by_batch_id: dict[str, Task] = {}
        for batch in batch_list:
            batch_id = str(batch["batch_id"])
            batches_by_id[batch_id] = batch
            task = Task.build(
                candidate_id=batch_id,
                kind=kind,
                # The full per-batch payload is built lazily at
                # submit time (via task_payload_for) so that any
                # deep-copy work only happens when the Orchestrator
                # actually submits. A small payload on the Task
                # itself keeps the Queue snapshot light.
                payload={"batch_id": batch_id},
            )
            self.queue.enqueue(task)
            task_by_batch_id[batch_id] = task

        # Use a scoped ProcessPoolBackend. We do not reuse
        # `self.backend` for parallel dispatch because (a) the pool
        # size is call-specific and (b) we want pool shutdown to
        # happen at end-of-dispatch, not end-of-run.
        #
        # `executor_class` defaults to ProcessPoolExecutor (production
        # config) but may be overridden to ThreadPoolExecutor when
        # tests need monkey-patches visible to the worker.
        pool = ProcessPoolBackend(
            max_workers=max_workers,
            executor_class=executor_class,
        )
        in_flight: dict[str, Any] = {}  # batch_id -> Future
        submitted_ids: set[str] = set()
        pending_batch_iter = iter(batch_list)
        observed_failure = False

        def _submit_next() -> bool:
            """Submit the next batch (if any) and return True if submitted."""

            if observed_failure and stop_on_failure:
                return False
            for batch in pending_batch_iter:
                batch_id = str(batch["batch_id"])
                if batch_id in submitted_ids:
                    continue
                # Build the full per-batch task payload (worker
                # kwargs). This is where `deepcopy(batch)` happens
                # (same as v3.8 `_submit_parallel_batch`).
                runner_kwargs = dict(task_payload_for(batch))
                task_with_payload = Task.build(
                    candidate_id=batch_id,
                    kind=kind,
                    payload=runner_kwargs,
                )
                # The queue is already tracking the "light" task;
                # mark it in flight before submitting.
                self.queue.mark_in_flight(task_by_batch_id[batch_id])
                on_batch_starting(batch)
                future = pool.submit(task_with_payload)
                in_flight[batch_id] = future
                submitted_ids.add(batch_id)
                return True
            return False

        try:
            # Initial submits: up to max_workers in flight.
            for _ in range(max_workers):
                if not _submit_next():
                    break

            # Collect in submission order. This matches the v3.8
            # `_run_parallel_*_batches` pattern exactly: even though
            # futures may complete out of order, we process them in
            # the original batch list order. Combined with FIFO
            # scheduling, this yields deterministic artifact order.
            for batch in batch_list:
                batch_id = str(batch["batch_id"])
                future = in_flight.pop(batch_id, None)
                if future is None:
                    # Skipped because stop_on_failure already kicked
                    # in; fall through and do not submit more.
                    continue
                future_outcome = future.result()
                task_id = task_by_batch_id[batch_id].task_id
                if isinstance(future_outcome, TaskResult):
                    self.queue.mark_completed(task_id, future_outcome)
                    batch_result = future_outcome.payload.get("batch_result")
                    # Phase 5: the hook returns a typed BatchOutcome.
                    # The dispatch layer drives stop_on_failure from
                    # outcome.is_failure(), not from batch["status"].
                    # The hook owns the translation.
                    batch_outcome = on_batch_complete(batch, batch_result)
                    if batch_outcome.is_failure():
                        observed_failure = True
                else:
                    # Phase 4/5 workers do not emit TaskFailure for
                    # real batches (exceptions propagate from
                    # future.result() instead). This branch covers
                    # the per-candidate kinds which still return
                    # TaskFailure(USER_CANCEL).
                    self.queue.mark_failed(task_id, future_outcome)
                    # Phase 5: also consult the hook for symmetry -
                    # the hook receives the None result and returns
                    # an outcome. Regardless of the hook's return,
                    # we mark observed_failure because the worker
                    # explicitly refused the task.
                    on_batch_complete(batch, None)
                    observed_failure = True

                # Submit the next pending batch unless we are
                # stopping on failure.
                _submit_next()
        finally:
            pool.shutdown(wait=True)


# Re-export a copy helper the runner uses to defensively deepcopy
# batches before they enter the worker payload. Keeping it co-located
# with the Orchestrator (instead of having the runner import `copy`
# at a new site) keeps the boundary narrow.
def deepcopy_batch(batch: Batch) -> Batch:
    """Defensive deepcopy for batch dicts passed to workers."""

    return copy.deepcopy(batch)


__all__ = [
    "Orchestrator",
    "deepcopy_batch",
]
