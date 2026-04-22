"""
Unit tests for phase-4 Orchestrator dispatch methods.

Exercises:
- `Orchestrator.dispatch_serial_batches`: serial in-order dispatch,
  lifecycle hooks called in expected order, Queue state transitions,
  exception propagation.
- `Orchestrator.dispatch_parallel_batches`: rolling-submit up to
  max_workers, result collection in submission order, failure-stop
  gate, Queue state transitions.
- Worker handles `SCREENING_BATCH` and `VALIDATION_BATCH` kinds
  by invoking the research batch runners (via module-level monkey
  patches so these tests stay unit-level).
"""

from __future__ import annotations

from typing import Any

import pytest

from orchestration.orchestrator import Orchestrator
from orchestration.queue import TaskQueue
from orchestration.scheduler import FifoScheduler
from orchestration.task import (
    BatchOutcome,
    ReasonCode,
    Task,
    TaskFailure,
    TaskKind,
    TaskResult,
)


def _ok(batch: dict, result: object) -> BatchOutcome:
    """Phase 5: test-only success hook. Replaces the phase-4 `lambda
    b, r: None` pattern now that hooks must return BatchOutcome."""

    return BatchOutcome.success()


# --------------------------------------------------------------------------
# dispatch_serial_batches
# --------------------------------------------------------------------------


def test_serial_dispatch_runs_batches_in_order() -> None:
    batches = [{"batch_id": f"b-{n:03d}", "status": "pending"} for n in range(5)]
    seen_order: list[str] = []

    def execute_batch(batch: dict) -> dict:
        seen_order.append(batch["batch_id"])
        return {"completed": True, "batch_id": batch["batch_id"]}

    o = Orchestrator()
    o.dispatch_serial_batches(
        batches=batches,
        kind=TaskKind.SCREENING_BATCH,
        execute_batch=execute_batch,
    )

    assert seen_order == [b["batch_id"] for b in batches]


def test_serial_dispatch_invokes_hooks_in_order() -> None:
    batches = [{"batch_id": f"b-{n}", "status": "pending"} for n in range(3)]
    events: list[tuple[str, str]] = []

    def on_start(batch: dict) -> None:
        events.append(("start", batch["batch_id"]))

    def execute_batch(batch: dict) -> dict:
        events.append(("exec", batch["batch_id"]))
        return {}

    def on_complete(batch: dict, result: Any) -> None:
        events.append(("complete", batch["batch_id"]))

    Orchestrator().dispatch_serial_batches(
        batches=batches,
        kind=TaskKind.SCREENING_BATCH,
        execute_batch=execute_batch,
        on_batch_starting=on_start,
        on_batch_complete=on_complete,
    )
    expected: list[tuple[str, str]] = []
    for b in batches:
        expected.extend(
            [
                ("start", b["batch_id"]),
                ("exec", b["batch_id"]),
                ("complete", b["batch_id"]),
            ]
        )
    assert events == expected


def test_serial_dispatch_tracks_queue_lifecycle() -> None:
    batches = [{"batch_id": f"b-{n}", "status": "pending"} for n in range(2)]
    queue = TaskQueue()
    o = Orchestrator(queue=queue)
    o.dispatch_serial_batches(
        batches=batches,
        kind=TaskKind.SCREENING_BATCH,
        execute_batch=lambda b: {"ok": True},
    )
    assert queue.pending_count() == 0
    assert queue.in_flight_count() == 0
    assert queue.completed_count() == 2
    assert queue.failed_count() == 0


def test_serial_dispatch_propagates_exception_after_marking_failed() -> None:
    batches = [{"batch_id": "b-fail", "status": "pending"}]
    queue = TaskQueue()
    o = Orchestrator(queue=queue)
    completed_hook_called = {"count": 0}

    def on_complete(batch: dict, result: Any) -> None:
        completed_hook_called["count"] += 1
        assert result is None  # failure indicated via None

    def explode(batch: dict) -> dict:
        raise RuntimeError("synthetic failure")

    with pytest.raises(RuntimeError, match="synthetic failure"):
        o.dispatch_serial_batches(
            batches=batches,
            kind=TaskKind.SCREENING_BATCH,
            execute_batch=explode,
            on_batch_complete=on_complete,
        )
    assert queue.failed_count() == 1
    assert queue.completed_count() == 0
    assert completed_hook_called["count"] == 1


def test_serial_dispatch_with_empty_batches_is_noop() -> None:
    queue = TaskQueue()
    Orchestrator(queue=queue).dispatch_serial_batches(
        batches=[],
        kind=TaskKind.SCREENING_BATCH,
        execute_batch=lambda b: {},
    )
    assert queue.total_count() == 0


def test_serial_dispatch_result_none_is_allowed() -> None:
    """execute_batch may return None; on_batch_complete sees None."""

    batches = [{"batch_id": "b-1", "status": "pending"}]
    received: list[Any] = []

    Orchestrator().dispatch_serial_batches(
        batches=batches,
        kind=TaskKind.SCREENING_BATCH,
        execute_batch=lambda b: None,
        on_batch_complete=lambda b, r: received.append(r),
    )
    assert received == [None]


# --------------------------------------------------------------------------
# dispatch_parallel_batches
# --------------------------------------------------------------------------
#
# These tests exercise the rolling-submit dispatch end-to-end through
# ProcessPoolBackend + worker.run_task. The worker handles
# SCREENING_BATCH / VALIDATION_BATCH by importing
# `research.batch_execution`. To keep these tests unit-level and fast,
# we dispatch NOOP_PROBE tasks - which do not touch research at all -
# and verify the dispatch machinery (rolling-submit, in-order
# collection, hook order, Queue transitions) is correct. A separate
# integration test covers the SCREENING_BATCH / VALIDATION_BATCH
# worker path against small real fixtures.


def test_parallel_dispatch_rejects_max_workers_zero() -> None:
    with pytest.raises(ValueError):
        Orchestrator().dispatch_parallel_batches(
            batches=[{"batch_id": "b-1", "status": "pending"}],
            kind=TaskKind.NOOP_PROBE,
            max_workers=0,
            task_payload_for=lambda b: {},
        )


def test_parallel_dispatch_with_empty_batches_is_noop() -> None:
    Orchestrator().dispatch_parallel_batches(
        batches=[],
        kind=TaskKind.NOOP_PROBE,
        max_workers=2,
        task_payload_for=lambda b: {},
    )


def test_parallel_dispatch_noop_probe_completes_all_batches() -> None:
    batches = [{"batch_id": f"b-{n}", "status": "pending"} for n in range(4)]
    queue = TaskQueue()
    completed: list[str] = []

    def _on_complete(b: dict, r: object) -> BatchOutcome:
        completed.append(b["batch_id"])
        return BatchOutcome.success()

    Orchestrator(queue=queue).dispatch_parallel_batches(
        batches=batches,
        kind=TaskKind.NOOP_PROBE,
        max_workers=2,
        task_payload_for=lambda b: {},
        on_batch_complete=_on_complete,
    )
    # Completion order must match submission order.
    assert completed == [b["batch_id"] for b in batches]
    # All tasks marked completed in the queue.
    assert queue.completed_count() == 4


def test_parallel_dispatch_invokes_on_batch_starting_before_submit() -> None:
    batches = [{"batch_id": f"b-{n}", "status": "pending"} for n in range(3)]
    started: list[str] = []
    completed: list[str] = []

    def _on_complete(b: dict, r: object) -> BatchOutcome:
        completed.append(b["batch_id"])
        return BatchOutcome.success()

    Orchestrator().dispatch_parallel_batches(
        batches=batches,
        kind=TaskKind.NOOP_PROBE,
        max_workers=2,
        task_payload_for=lambda b: {},
        on_batch_starting=lambda b: started.append(b["batch_id"]),
        on_batch_complete=_on_complete,
    )
    # All batches started before any completion ordering, and every
    # started batch eventually completes in submission order.
    assert set(started) == {b["batch_id"] for b in batches}
    assert completed == [b["batch_id"] for b in batches]


def test_parallel_dispatch_stops_on_failure_when_hook_returns_failure_outcome() -> None:
    """Phase 5: the dispatch layer drives stop_on_failure from the
    hook's returned BatchOutcome, not from batch['status']. If the
    hook returns a failure outcome for one batch, no further batches
    are submitted after that."""

    batches = [{"batch_id": f"b-{n}", "status": "pending"} for n in range(5)]
    completed: list[str] = []

    def on_complete(batch: dict, result: Any) -> BatchOutcome:
        completed.append(batch["batch_id"])
        # Simulate the runner's real hook returning a typed failure
        # outcome for one batch. The dispatch layer stops after this.
        if batch["batch_id"] == "b-1":
            return BatchOutcome.failure(
                reason_code=ReasonCode.STRATEGY_ERROR,
                message="simulated",
            )
        return BatchOutcome.success()

    Orchestrator().dispatch_parallel_batches(
        batches=batches,
        kind=TaskKind.NOOP_PROBE,
        max_workers=2,
        task_payload_for=lambda b: {},
        on_batch_complete=on_complete,
        stop_on_failure=True,
    )
    # We should have completed b-0 and b-1 (which was in-flight when
    # failure was observed), but not all 5. Exactly how many get
    # processed depends on rolling-submit timing, but we should see
    # strictly fewer than 5 completions.
    assert len(completed) < 5
    assert "b-0" in completed
    assert "b-1" in completed


def test_parallel_dispatch_does_not_stop_when_hook_returns_success_despite_batch_status() -> None:
    """Phase 5: the hook is authoritative. If the hook returns
    BatchOutcome.success() even though batch['status']='failed',
    dispatch should NOT stop (the hook owns the translation). This
    documents the decoupling from the Phase-4 implicit coupling to
    batch['status']."""

    batches = [{"batch_id": f"b-{n}", "status": "pending"} for n in range(4)]
    completed: list[str] = []

    def on_complete(batch: dict, result: Any) -> BatchOutcome:
        completed.append(batch["batch_id"])
        # Set batch['status'] = 'failed' but return a success outcome.
        # A Phase-4 dispatch would have stopped; Phase-5 dispatch
        # respects the typed outcome and continues.
        if batch["batch_id"] == "b-1":
            batch["status"] = "failed"
        return BatchOutcome.success()

    Orchestrator().dispatch_parallel_batches(
        batches=batches,
        kind=TaskKind.NOOP_PROBE,
        max_workers=2,
        task_payload_for=lambda b: {},
        on_batch_complete=on_complete,
        stop_on_failure=True,
    )
    # All four batches should have completed because the hook never
    # returned a failure outcome.
    assert completed == [b["batch_id"] for b in batches]


def test_parallel_dispatch_marks_all_queue_states_correctly() -> None:
    batches = [{"batch_id": f"b-{n}", "status": "pending"} for n in range(3)]
    queue = TaskQueue()
    Orchestrator(queue=queue).dispatch_parallel_batches(
        batches=batches,
        kind=TaskKind.NOOP_PROBE,
        max_workers=2,
        task_payload_for=lambda b: {},
    )
    assert queue.pending_count() == 0
    assert queue.in_flight_count() == 0
    assert queue.completed_count() == 3
    assert queue.failed_count() == 0


def test_parallel_dispatch_determinism_bytewise_across_worker_counts() -> None:
    """Dispatch the same batches with max_workers=1 and max_workers=4;
    results should arrive in the same submission order in both cases."""

    batches_1 = [{"batch_id": f"b-{n:03d}", "status": "pending"} for n in range(8)]
    batches_4 = [{"batch_id": f"b-{n:03d}", "status": "pending"} for n in range(8)]

    order_1: list[str] = []
    order_4: list[str] = []

    def _on_complete_1(b: dict, r: object) -> BatchOutcome:
        order_1.append(b["batch_id"])
        return BatchOutcome.success()

    def _on_complete_4(b: dict, r: object) -> BatchOutcome:
        order_4.append(b["batch_id"])
        return BatchOutcome.success()

    Orchestrator().dispatch_parallel_batches(
        batches=batches_1,
        kind=TaskKind.NOOP_PROBE,
        max_workers=1,
        task_payload_for=lambda b: {},
        on_batch_complete=_on_complete_1,
    )
    Orchestrator().dispatch_parallel_batches(
        batches=batches_4,
        kind=TaskKind.NOOP_PROBE,
        max_workers=4,
        task_payload_for=lambda b: {},
        on_batch_complete=_on_complete_4,
    )

    assert order_1 == order_4 == [b["batch_id"] for b in batches_1]


# --------------------------------------------------------------------------
# Worker batch-kind plumbing (monkey-patch research to keep unit-level)
# --------------------------------------------------------------------------


def test_worker_dispatches_screening_batch_kind(monkeypatch) -> None:
    """Worker calls research.batch_execution.execute_screening_batch
    with the task's payload and returns the result in payload.batch_result."""

    seen_kwargs: dict = {}

    def fake_execute_screening_batch(**kwargs: Any) -> dict[str, Any]:
        seen_kwargs.update(kwargs)
        return {"batch": "stub-result"}

    import research.batch_execution as be

    monkeypatch.setattr(be, "execute_screening_batch", fake_execute_screening_batch)

    from orchestration.worker import run_task

    task = Task.build(
        candidate_id="b-42",
        kind=TaskKind.SCREENING_BATCH,
        payload={
            "batch": {"batch_id": "b-42"},
            "batch_candidates": [{"candidate_id": "c-1"}],
        },
    )
    outcome = run_task(task)

    assert isinstance(outcome, TaskResult)
    assert outcome.kind is TaskKind.SCREENING_BATCH
    assert outcome.payload["batch_result"] == {"batch": "stub-result"}
    assert seen_kwargs["batch"] == {"batch_id": "b-42"}


def test_worker_dispatches_validation_batch_kind(monkeypatch) -> None:
    """Worker calls research.batch_execution.execute_validation_batch
    similarly."""

    def fake_execute_validation_batch(**kwargs: Any) -> dict[str, Any]:
        return {"rows": 3}

    import research.batch_execution as be

    monkeypatch.setattr(be, "execute_validation_batch", fake_execute_validation_batch)

    from orchestration.worker import run_task

    task = Task.build(
        candidate_id="b-99",
        kind=TaskKind.VALIDATION_BATCH,
        payload={"batch": {"batch_id": "b-99"}},
    )
    outcome = run_task(task)

    assert isinstance(outcome, TaskResult)
    assert outcome.kind is TaskKind.VALIDATION_BATCH
    assert outcome.payload["batch_result"] == {"rows": 3}


def test_worker_still_returns_failure_for_per_candidate_kinds() -> None:
    """SCREENING_CANDIDATE and VALIDATION_CANDIDATE remain unwired in phase 4."""

    from orchestration.worker import run_task

    for kind in (TaskKind.SCREENING_CANDIDATE, TaskKind.VALIDATION_CANDIDATE):
        outcome = run_task(Task.build(candidate_id="c-1", kind=kind))
        assert isinstance(outcome, TaskFailure)
        assert outcome.reason_code is ReasonCode.USER_CANCEL
        assert "phase 4" in outcome.message
