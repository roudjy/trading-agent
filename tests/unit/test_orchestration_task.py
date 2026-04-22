"""
Unit tests for the v3.9 orchestration task data model.

Exercises `orchestration/task.py`:
- `Task`, `TaskResult`, `TaskFailure` are frozen and behave as
  value objects.
- `task_id` is deterministic in `(candidate_id, kind, attempt)`.
- `ReasonCode` is a closed enum; retriable / non-retriable
  classification is exhaustive and disjoint.
- All types survive pickle round-trip (required for
  ProcessPoolExecutor dispatch in phase 3).
"""

from __future__ import annotations

import dataclasses
import pickle

import pytest

from orchestration.task import (
    NON_RETRIABLE_REASONS,
    RETRIABLE_REASONS,
    ReasonCode,
    Task,
    TaskFailure,
    TaskKind,
    TaskResult,
    build_task_id,
    is_retriable,
)


# --------------------------------------------------------------------------
# task_id determinism
# --------------------------------------------------------------------------


def test_build_task_id_is_deterministic_in_inputs() -> None:
    """Same (candidate_id, kind, attempt) -> same task_id."""

    a = build_task_id("cand-001", TaskKind.SCREENING_CANDIDATE, 1)
    b = build_task_id("cand-001", TaskKind.SCREENING_CANDIDATE, 1)
    assert a == b


def test_build_task_id_differs_by_candidate_id() -> None:
    a = build_task_id("cand-001", TaskKind.SCREENING_CANDIDATE, 1)
    b = build_task_id("cand-002", TaskKind.SCREENING_CANDIDATE, 1)
    assert a != b


def test_build_task_id_differs_by_kind() -> None:
    a = build_task_id("cand-001", TaskKind.SCREENING_CANDIDATE, 1)
    b = build_task_id("cand-001", TaskKind.VALIDATION_CANDIDATE, 1)
    assert a != b


def test_build_task_id_differs_by_attempt() -> None:
    a = build_task_id("cand-001", TaskKind.SCREENING_CANDIDATE, 1)
    b = build_task_id("cand-001", TaskKind.SCREENING_CANDIDATE, 2)
    assert a != b


def test_build_task_id_rejects_zero_attempt() -> None:
    with pytest.raises(ValueError):
        build_task_id("cand-001", TaskKind.SCREENING_CANDIDATE, 0)


def test_build_task_id_rejects_negative_attempt() -> None:
    with pytest.raises(ValueError):
        build_task_id("cand-001", TaskKind.SCREENING_CANDIDATE, -1)


def test_build_task_id_sorts_by_attempt_under_string_sort() -> None:
    """Zero-padded attempt means string sort order matches numeric order."""

    ids = [
        build_task_id("cand-001", TaskKind.SCREENING_CANDIDATE, n)
        for n in (10, 2, 1, 100, 3)
    ]
    sorted_ids = sorted(ids)
    attempts_in_order = [int(i.rsplit("#", 1)[-1]) for i in sorted_ids]
    assert attempts_in_order == sorted(attempts_in_order)


# --------------------------------------------------------------------------
# Task / TaskResult / TaskFailure as frozen value objects
# --------------------------------------------------------------------------


def test_task_is_frozen_dataclass() -> None:
    task = Task.build(candidate_id="c1", kind=TaskKind.SCREENING_CANDIDATE)
    assert dataclasses.is_dataclass(task)
    with pytest.raises(dataclasses.FrozenInstanceError):
        task.candidate_id = "c2"  # type: ignore[misc]


def test_task_result_is_frozen_dataclass() -> None:
    result = TaskResult(
        task_id="c1#screening_candidate#001",
        candidate_id="c1",
        kind=TaskKind.SCREENING_CANDIDATE,
    )
    assert dataclasses.is_dataclass(result)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.candidate_id = "c2"  # type: ignore[misc]


def test_task_failure_is_frozen_dataclass() -> None:
    failure = TaskFailure(
        task_id="c1#screening_candidate#001",
        candidate_id="c1",
        kind=TaskKind.SCREENING_CANDIDATE,
        reason_code=ReasonCode.STRATEGY_ERROR,
    )
    assert dataclasses.is_dataclass(failure)
    with pytest.raises(dataclasses.FrozenInstanceError):
        failure.message = "changed"  # type: ignore[misc]


def test_task_build_factory_wires_task_id_deterministically() -> None:
    a = Task.build(candidate_id="cx", kind=TaskKind.VALIDATION_CANDIDATE, attempt=3)
    b = Task.build(candidate_id="cx", kind=TaskKind.VALIDATION_CANDIDATE, attempt=3)
    assert a.task_id == b.task_id == build_task_id("cx", TaskKind.VALIDATION_CANDIDATE, 3)
    assert a == b


def test_task_build_defaults_attempt_to_one() -> None:
    t = Task.build(candidate_id="cx", kind=TaskKind.SCREENING_CANDIDATE)
    assert t.attempt == 1
    assert t.task_id.endswith("#001")


def test_task_build_accepts_payload() -> None:
    t = Task.build(
        candidate_id="cx",
        kind=TaskKind.SCREENING_CANDIDATE,
        payload={"strategy_name": "sma_crossover", "interval": "1d"},
    )
    assert t.payload["strategy_name"] == "sma_crossover"


def test_task_build_defensive_copies_payload() -> None:
    """Mutating the caller's dict must not affect the Task's payload."""

    raw = {"k": "v"}
    t = Task.build(candidate_id="c", kind=TaskKind.NOOP_PROBE, payload=raw)
    raw["k"] = "mutated"
    assert t.payload["k"] == "v"


# --------------------------------------------------------------------------
# ReasonCode classification
# --------------------------------------------------------------------------


def test_reason_code_is_closed_enum() -> None:
    # There are exactly 8 codes: 3 retriable, 5 non-retriable.
    assert len(list(ReasonCode)) == 8


def test_retriable_and_non_retriable_are_disjoint() -> None:
    assert RETRIABLE_REASONS.isdisjoint(NON_RETRIABLE_REASONS)


def test_retriable_and_non_retriable_cover_all_reasons() -> None:
    assert RETRIABLE_REASONS | NON_RETRIABLE_REASONS == set(ReasonCode)


def test_retriable_set_pinned() -> None:
    assert RETRIABLE_REASONS == frozenset(
        {
            ReasonCode.WORKER_CRASH,
            ReasonCode.TIMEOUT,
            ReasonCode.DATA_UNAVAILABLE,
        }
    )


def test_is_retriable_matches_set_membership() -> None:
    for code in ReasonCode:
        assert is_retriable(code) == (code in RETRIABLE_REASONS)


def test_task_failure_is_retriable_method_agrees_with_classification() -> None:
    f = TaskFailure(
        task_id="c1#screening_candidate#001",
        candidate_id="c1",
        kind=TaskKind.SCREENING_CANDIDATE,
        reason_code=ReasonCode.WORKER_CRASH,
    )
    assert f.is_retriable() is True

    g = TaskFailure(
        task_id="c1#screening_candidate#001",
        candidate_id="c1",
        kind=TaskKind.SCREENING_CANDIDATE,
        reason_code=ReasonCode.STRATEGY_ERROR,
    )
    assert g.is_retriable() is False


# --------------------------------------------------------------------------
# Pickle round-trip (required for ProcessPoolExecutor dispatch)
# --------------------------------------------------------------------------


def test_task_pickles_round_trip() -> None:
    t = Task.build(
        candidate_id="cxx",
        kind=TaskKind.SCREENING_CANDIDATE,
        attempt=2,
        payload={
            "interval": "1d",
            "lookback": 20,
            "flags": [True, False],
            "nested": {"a": 1, "b": 2.0},
        },
    )
    data = pickle.dumps(t)
    restored = pickle.loads(data)
    assert restored == t
    assert restored.task_id == t.task_id
    assert restored.payload["nested"]["b"] == 2.0


def test_task_result_pickles_round_trip() -> None:
    r = TaskResult(
        task_id="cxx#screening_candidate#001",
        candidate_id="cxx",
        kind=TaskKind.SCREENING_CANDIDATE,
        result_rows=({"k": "v", "score": 1.23},),
        walk_forward_report={"folds": 5},
        screening_runtime_record={"elapsed": 12.3},
        evaluation_streams={"events": []},
    )
    data = pickle.dumps(r)
    restored = pickle.loads(data)
    assert restored == r


def test_task_failure_pickles_round_trip() -> None:
    f = TaskFailure(
        task_id="cxx#screening_candidate#001",
        candidate_id="cxx",
        kind=TaskKind.SCREENING_CANDIDATE,
        reason_code=ReasonCode.TIMEOUT,
        message="exceeded 60s budget",
        traceback_str=None,
    )
    data = pickle.dumps(f)
    restored = pickle.loads(data)
    assert restored == f
    assert restored.is_retriable() is True


# --------------------------------------------------------------------------
# Public API surface
# --------------------------------------------------------------------------


def test_public_api_exports_task_types() -> None:
    """The orchestration package exposes the Phase 2 surface."""

    import orchestration

    for name in (
        "Task",
        "TaskResult",
        "TaskFailure",
        "TaskKind",
        "ReasonCode",
        "RETRIABLE_REASONS",
        "NON_RETRIABLE_REASONS",
        "is_retriable",
        "build_task_id",
        "ORCHESTRATION_LAYER_VERSION",
    ):
        assert hasattr(orchestration, name), f"orchestration.{name} not exported"
