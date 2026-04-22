"""
Unit tests for Phase-5 failure-taxonomy hardening.

Focus areas:
- `dispatch_parallel_batches` drives `stop_on_failure` from the
  returned `BatchOutcome`, not from `batch["status"]`. This is the
  primary Phase-5 decoupling from Phase-4's implicit dict coupling.
- Default `on_batch_complete` hook translates `batch["status"]` into
  a typed BatchOutcome (backward-compat translation).
- Retriable vs non-retriable classification is observable on the
  outcome without executing any retry (Phase 5 does not add
  automatic retry; the surface exists for a later phase).
- Idempotency: the Queue rejects duplicate task_ids within a single
  Orchestrator instance, catching accidental double-dispatch.

These tests are orthogonal to Phase 4's `test_orchestration_dispatch.py`
which focuses on lifecycle plumbing; here we focus on the failure
taxonomy as Phase 5's explicit contract.
"""

from __future__ import annotations

import pytest

from orchestration.orchestrator import Orchestrator, _default_complete
from orchestration.queue import TaskQueue, TaskQueueError
from orchestration.task import (
    BatchOutcome,
    OutcomeKind,
    ReasonCode,
    Task,
    TaskKind,
    classify_batch_reason,
)


# --------------------------------------------------------------------------
# Default hook translation (preserves Phase-4 behavior as a fallback)
# --------------------------------------------------------------------------


def test_default_complete_translates_failed_status_to_failure_outcome() -> None:
    batch = {
        "batch_id": "b-1",
        "status": "failed",
        "reason_code": "batch_execution_failed",
        "reason_detail": "something blew up",
    }
    out = _default_complete(batch, {"ok": False})
    assert out.is_failure()
    assert out.reason_code is ReasonCode.STRATEGY_ERROR
    assert out.message == "something blew up"


def test_default_complete_maps_non_failed_statuses_to_success() -> None:
    for status in ("running", "completed", "partial", "pending", "skipped"):
        out = _default_complete({"batch_id": "b-1", "status": status}, {})
        assert out.is_success(), f"{status!r} should map to success"


def test_default_complete_unknown_reason_maps_to_strategy_error() -> None:
    batch = {
        "batch_id": "b-x",
        "status": "failed",
        "reason_code": "some_new_reason_we_do_not_know_about",
    }
    out = _default_complete(batch, None)
    assert out.reason_code is ReasonCode.STRATEGY_ERROR


def test_default_complete_handles_missing_reason_fields() -> None:
    out = _default_complete({"batch_id": "b-x", "status": "failed"}, None)
    assert out.is_failure()
    assert out.reason_code is ReasonCode.STRATEGY_ERROR
    assert out.message == ""


# --------------------------------------------------------------------------
# Dispatch drives stop_on_failure from outcome, not batch["status"]
# --------------------------------------------------------------------------


def test_dispatch_honors_outcome_even_when_batch_status_disagrees() -> None:
    """If the hook returns a failure outcome while batch['status']
    remains 'pending', the dispatch still treats the run as having
    observed a failure (stop_on_failure kicks in). This pins the
    Phase-5 decoupling from `batch["status"]` at the dispatch layer.
    """

    batches = [{"batch_id": f"b-{n}", "status": "pending"} for n in range(4)]
    completed_ids: list[str] = []

    def _hook(batch: dict, result: object) -> BatchOutcome:
        completed_ids.append(batch["batch_id"])
        # Hook declares failure without touching batch["status"].
        if batch["batch_id"] == "b-1":
            return BatchOutcome.failure(
                reason_code=ReasonCode.STRATEGY_ERROR,
                message="hook-level failure",
            )
        return BatchOutcome.success()

    Orchestrator().dispatch_parallel_batches(
        batches=batches,
        kind=TaskKind.NOOP_PROBE,
        max_workers=2,
        task_payload_for=lambda b: {},
        on_batch_complete=_hook,
        stop_on_failure=True,
    )

    # Dispatch stopped after b-1's failure outcome - fewer than 4
    # batches completed. batch["status"] values remain "pending"
    # because the hook never mutated them. The stop decision is
    # entirely outcome-driven.
    assert len(completed_ids) < 4
    assert all(b["status"] == "pending" for b in batches)


def test_dispatch_ignores_batch_status_failed_when_outcome_is_success() -> None:
    """Symmetric check: if `batch["status"]='failed'` but hook
    returns success, dispatch continues. The outcome, not the dict,
    is authoritative."""

    batches = [{"batch_id": f"b-{n}", "status": "pending"} for n in range(3)]
    completed_ids: list[str] = []

    def _hook(batch: dict, result: object) -> BatchOutcome:
        completed_ids.append(batch["batch_id"])
        # Set batch failed but return success - dispatch must honor
        # the outcome.
        if batch["batch_id"] == "b-1":
            batch["status"] = "failed"
        return BatchOutcome.success()

    Orchestrator().dispatch_parallel_batches(
        batches=batches,
        kind=TaskKind.NOOP_PROBE,
        max_workers=2,
        task_payload_for=lambda b: {},
        on_batch_complete=_hook,
        stop_on_failure=True,
    )

    assert completed_ids == [b["batch_id"] for b in batches]


# --------------------------------------------------------------------------
# Retriable / non-retriable classification is observable
# --------------------------------------------------------------------------


def test_retriable_outcomes_do_not_auto_retry_in_phase_5() -> None:
    """Phase 5 does not add automatic intra-run retry. A retriable
    failure still stops dispatch; the surface `is_retriable()` exists
    for a later phase to consult."""

    batches = [{"batch_id": f"b-{n}", "status": "pending"} for n in range(4)]
    completed_ids: list[str] = []

    def _hook(batch: dict, result: object) -> BatchOutcome:
        completed_ids.append(batch["batch_id"])
        if batch["batch_id"] == "b-0":
            # Retriable failure - but Phase 5 treats it the same as
            # a non-retriable failure for flow control (stop).
            return BatchOutcome.failure(reason_code=ReasonCode.TIMEOUT)
        return BatchOutcome.success()

    Orchestrator().dispatch_parallel_batches(
        batches=batches,
        kind=TaskKind.NOOP_PROBE,
        max_workers=1,
        task_payload_for=lambda b: {},
        on_batch_complete=_hook,
        stop_on_failure=True,
    )

    # Only b-0 was attempted; subsequent batches were not submitted.
    # b-0 was not retried automatically.
    assert completed_ids == ["b-0"]


def test_failure_outcome_carries_retriable_bit_when_reason_is_retriable() -> None:
    """Direct observation: a failure with TIMEOUT is retriable, and a
    failure with FOLD_LEAKAGE_ERROR is not. The dispatch layer does
    not act on this yet, but the information is typed and available
    for a later phase."""

    retriable = BatchOutcome.failure(reason_code=ReasonCode.TIMEOUT)
    non_retriable = BatchOutcome.failure(reason_code=ReasonCode.FOLD_LEAKAGE_ERROR)

    assert retriable.is_retriable() is True
    assert non_retriable.is_retriable() is False


# --------------------------------------------------------------------------
# Idempotency / dedup at the Queue boundary
# --------------------------------------------------------------------------


def test_queue_rejects_duplicate_task_ids_within_single_orchestrator() -> None:
    """Idempotency guard: enqueuing the same task_id twice raises.
    This catches accidental double-dispatch within one Orchestrator
    lifecycle."""

    queue = TaskQueue()
    task = Task.build(candidate_id="b-dup", kind=TaskKind.SCREENING_BATCH)
    queue.enqueue(task)
    with pytest.raises(TaskQueueError, match="already pending"):
        queue.enqueue(task)


def test_fresh_orchestrator_has_fresh_queue() -> None:
    """Two Orchestrator instances do NOT share Queue state. This is
    the structural basis for artifact-truth: each run gets a fresh
    in-memory lifecycle surface, so nothing from a prior run leaks."""

    o1 = Orchestrator()
    task = Task.build(candidate_id="b-1", kind=TaskKind.SCREENING_BATCH)
    o1.queue.enqueue(task)
    assert o1.queue.pending_count() == 1

    o2 = Orchestrator()
    assert o2.queue.pending_count() == 0
    # o2's queue is not o1's queue.
    assert o2.queue is not o1.queue


def test_task_id_is_deterministic_across_orchestrators() -> None:
    """A task_id for the same (candidate_id, kind, attempt) is
    identical across Orchestrator instances. This is the precondition
    for artifact-backed dedup on resume."""

    t1 = Task.build(candidate_id="b-xyz", kind=TaskKind.VALIDATION_BATCH)
    t2 = Task.build(candidate_id="b-xyz", kind=TaskKind.VALIDATION_BATCH)
    assert t1.task_id == t2.task_id
