"""
Unit tests for the Phase-5 BatchOutcome type and classification helper.

Exercises `orchestration/task.py::BatchOutcome` +
`classify_batch_reason`:

- Factory invariants (success has no reason_code; failure requires
  one).
- Frozen immutability.
- `is_success` / `is_failure` / `is_retriable` semantics.
- Pickle round-trip (follows the Phase-2 invariant that all
  orchestration types are pickle-safe).
- `classify_batch_reason` mapping: known strings map to typed
  ReasonCode; unknown falls back to `STRATEGY_ERROR` (non-retriable).
- Public API surface.
"""

from __future__ import annotations

import dataclasses
import pickle

import pytest

from orchestration.task import (
    RETRIABLE_REASONS,
    BatchOutcome,
    OutcomeKind,
    ReasonCode,
    classify_batch_reason,
)


# --------------------------------------------------------------------------
# Factory invariants
# --------------------------------------------------------------------------


def test_success_has_no_reason_code() -> None:
    o = BatchOutcome.success()
    assert o.is_success()
    assert not o.is_failure()
    assert o.reason_code is None


def test_success_accepts_message() -> None:
    o = BatchOutcome.success(message="everything fine")
    assert o.message == "everything fine"


def test_failure_requires_reason_code() -> None:
    o = BatchOutcome.failure(reason_code=ReasonCode.STRATEGY_ERROR, message="boom")
    assert o.is_failure()
    assert not o.is_success()
    assert o.reason_code is ReasonCode.STRATEGY_ERROR
    assert o.message == "boom"


def test_failure_rejects_non_enum_reason() -> None:
    with pytest.raises(TypeError, match="ReasonCode enum"):
        BatchOutcome.failure(reason_code="strategy_error")  # type: ignore[arg-type]


def test_direct_construction_rejects_mismatched_kind_and_reason() -> None:
    # Success kind must not carry a reason_code.
    with pytest.raises(ValueError, match="must not carry"):
        BatchOutcome(
            kind=OutcomeKind.SUCCESS,
            reason_code=ReasonCode.STRATEGY_ERROR,
        )
    # Failure kind must carry a reason_code.
    with pytest.raises(ValueError, match="must carry"):
        BatchOutcome(kind=OutcomeKind.FAILURE, reason_code=None)


def test_message_must_be_string() -> None:
    with pytest.raises(TypeError, match="must be str"):
        BatchOutcome(kind=OutcomeKind.SUCCESS, reason_code=None, message=123)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Immutability
# --------------------------------------------------------------------------


def test_batch_outcome_is_frozen() -> None:
    o = BatchOutcome.success()
    assert dataclasses.is_dataclass(o)
    with pytest.raises(dataclasses.FrozenInstanceError):
        o.message = "changed"  # type: ignore[misc]


def test_batch_outcome_equality() -> None:
    a = BatchOutcome.failure(reason_code=ReasonCode.TIMEOUT, message="slow")
    b = BatchOutcome.failure(reason_code=ReasonCode.TIMEOUT, message="slow")
    assert a == b


# --------------------------------------------------------------------------
# Retriable classification
# --------------------------------------------------------------------------


def test_success_outcome_is_not_retriable() -> None:
    assert BatchOutcome.success().is_retriable() is False


def test_retriable_failure_matches_retriable_reasons() -> None:
    for code in RETRIABLE_REASONS:
        o = BatchOutcome.failure(reason_code=code)
        assert o.is_retriable() is True


def test_non_retriable_failure_is_not_retriable() -> None:
    from orchestration.task import NON_RETRIABLE_REASONS

    for code in NON_RETRIABLE_REASONS:
        o = BatchOutcome.failure(reason_code=code)
        assert o.is_retriable() is False


# --------------------------------------------------------------------------
# Pickle round-trip
# --------------------------------------------------------------------------


def test_success_outcome_round_trips_through_pickle() -> None:
    o = BatchOutcome.success(message="ok")
    restored = pickle.loads(pickle.dumps(o))
    assert restored == o
    assert restored.is_success()


def test_failure_outcome_round_trips_through_pickle() -> None:
    o = BatchOutcome.failure(
        reason_code=ReasonCode.FOLD_LEAKAGE_ERROR,
        message="leakage detected",
    )
    restored = pickle.loads(pickle.dumps(o))
    assert restored == o
    assert restored.is_failure()
    assert restored.reason_code is ReasonCode.FOLD_LEAKAGE_ERROR


# --------------------------------------------------------------------------
# classify_batch_reason
# --------------------------------------------------------------------------


def test_classify_known_batch_reason_strings() -> None:
    assert classify_batch_reason("batch_execution_failed") is ReasonCode.STRATEGY_ERROR
    assert (
        classify_batch_reason("isolated_candidate_execution_issues")
        is ReasonCode.STRATEGY_ERROR
    )
    assert classify_batch_reason("upstream_batch_failed") is ReasonCode.USER_CANCEL


def test_classify_unknown_reason_defaults_to_strategy_error() -> None:
    code = classify_batch_reason("some_unexpected_reason_code")
    assert code is ReasonCode.STRATEGY_ERROR
    # And that default is non-retriable, by design.
    assert code not in RETRIABLE_REASONS


def test_classify_none_or_empty_defaults_to_strategy_error() -> None:
    assert classify_batch_reason(None) is ReasonCode.STRATEGY_ERROR
    assert classify_batch_reason("") is ReasonCode.STRATEGY_ERROR


def test_classify_accepts_non_string_coercible_input() -> None:
    # `batch["reason_code"]` may occasionally be a bool or similar in
    # degenerate cases; classify should not crash, just fall back.
    assert classify_batch_reason(False) is ReasonCode.STRATEGY_ERROR  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def test_batch_outcome_exposed_via_public_api() -> None:
    import orchestration

    assert hasattr(orchestration, "BatchOutcome")
    assert hasattr(orchestration, "OutcomeKind")
    assert hasattr(orchestration, "classify_batch_reason")
    assert orchestration.BatchOutcome is BatchOutcome
