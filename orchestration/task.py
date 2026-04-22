"""
Task data model for the orchestration layer.

This module defines the minimal, frozen, pickle-safe types used to
describe units of work that the orchestration layer dispatches. It
contains data structures only - no execution logic, no engine
imports, no research imports.

Design invariants (pinned by
`docs/adr/ADR-009-platform-layer-introduction.md`):

- All types are frozen dataclasses. Instances are immutable after
  construction.
- `task_id` is deterministic in `(candidate_id, kind, attempt)`: the
  same inputs always produce the same id. This is the precondition
  for dedup on retry and for reproducible resume.
- All types must be pickle-safe. Worker processes exchange them
  through `concurrent.futures.ProcessPoolExecutor`, which uses
  Python's default pickle protocol.
- The `ReasonCode` vocabulary is typed and closed. Adding a code
  requires a code change; you cannot pass an arbitrary string.
- Retriable vs non-retriable classification is fixed in this module.
  The exact retry budget per code is *not* fixed here - it is an
  implementation-time concern for later phases.

Phase history:
- Phase 2 introduced Task / TaskResult / TaskFailure / ReasonCode.
- Phase 4 added `TaskKind.SCREENING_BATCH` / `VALIDATION_BATCH` and a
  generic `TaskResult.payload` field for batch-level dispatch.
- Phase 5 adds `BatchOutcome` as the explicit, typed outcome contract
  that runner-supplied `on_batch_complete` hooks return to the
  Orchestrator dispatch loop. It replaces Phase 4's implicit coupling
  to `batch["status"]` at the dispatch layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class TaskKind(str, Enum):
    """The kind of work a Task represents.

    - SCREENING_CANDIDATE / VALIDATION_CANDIDATE: per-candidate kinds
      reserved for a later phase. Phase 4 does not produce such
      Tasks in production; the worker returns a typed failure if
      one is dispatched.
    - SCREENING_BATCH / VALIDATION_BATCH: phase 4 batch-level kinds.
      The worker invokes
      `research.batch_execution.execute_screening_batch` /
      `execute_validation_batch` with the task's payload.
    - NOOP_PROBE: test-only kind. Workers return an empty TaskResult
      without invoking any engine or research code. Used to exercise
      backend/worker plumbing without constructing a real engine.
    """

    SCREENING_CANDIDATE = "screening_candidate"
    VALIDATION_CANDIDATE = "validation_candidate"
    SCREENING_BATCH = "screening_batch"
    VALIDATION_BATCH = "validation_batch"
    NOOP_PROBE = "noop_probe"


class ReasonCode(str, Enum):
    """Typed vocabulary for task failures.

    Each code is classified as retriable or non-retriable. Retriable
    means the failure is plausibly transient (the same task might
    succeed on a second attempt); non-retriable means the failure is
    deterministic (a retry loops).

    The classification is fixed here. The exact max-attempts count
    per code is *not* fixed at architecture time; it is set at
    implementation time in a later phase.
    """

    # Retriable (plausibly transient)
    WORKER_CRASH = "worker_crash"
    TIMEOUT = "timeout"
    DATA_UNAVAILABLE = "data_unavailable"

    # Non-retriable (deterministic)
    STRATEGY_ERROR = "strategy_error"
    FEATURE_CONTRACT_VIOLATION = "feature_contract_violation"
    FOLD_LEAKAGE_ERROR = "fold_leakage_error"
    INTEGRITY_REJECTION = "integrity_rejection"
    USER_CANCEL = "user_cancel"


RETRIABLE_REASONS: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.WORKER_CRASH,
        ReasonCode.TIMEOUT,
        ReasonCode.DATA_UNAVAILABLE,
    }
)

NON_RETRIABLE_REASONS: frozenset[ReasonCode] = frozenset(
    set(ReasonCode) - set(RETRIABLE_REASONS)
)


def is_retriable(code: ReasonCode) -> bool:
    """True iff the given reason code is classified as retriable.

    Reason codes outside the `ReasonCode` enum are rejected by the
    type system at call sites; this function operates on valid
    enum members only.
    """

    return code in RETRIABLE_REASONS


def build_task_id(candidate_id: str, kind: TaskKind, attempt: int) -> str:
    """Build the deterministic task id for a task triple.

    Format: `"{candidate_id}#{kind.value}#{attempt}"`. Attempt is
    encoded as a zero-padded three-digit integer so that string sort
    also sorts by attempt.
    """

    if attempt < 1:
        raise ValueError(f"attempt must be >= 1, got {attempt!r}")
    return f"{candidate_id}#{kind.value}#{attempt:03d}"


@dataclass(frozen=True)
class Task:
    """A unit of work for the orchestration layer to dispatch.

    Fields:
    - `task_id`: deterministic; call `build_task_id` or let the
      factory method `Task.build` compute it.
    - `candidate_id`: the research-layer candidate this task targets.
    - `kind`: the phase (screening / validation) or probe.
    - `attempt`: 1-based attempt counter. Retries advance this; the
      underlying `task_id` advances with it.
    - `payload`: task-specific data. Must be pickle-safe. Phase 2
      does not constrain its shape beyond that; phase 3 consumers
      document what they expect.

    Pickle safety: this dataclass is pickle-safe as long as `payload`
    is. A round-trip unit test pins the contract for the common
    case.
    """

    task_id: str
    candidate_id: str
    kind: TaskKind
    attempt: int
    payload: Mapping[str, Any] = field(default_factory=dict)

    @staticmethod
    def build(
        *,
        candidate_id: str,
        kind: TaskKind,
        attempt: int = 1,
        payload: Mapping[str, Any] | None = None,
    ) -> "Task":
        """Factory that computes `task_id` from the inputs."""

        return Task(
            task_id=build_task_id(candidate_id, kind, attempt),
            candidate_id=candidate_id,
            kind=kind,
            attempt=attempt,
            payload=dict(payload or {}),
        )


@dataclass(frozen=True)
class TaskResult:
    """A successful task outcome.

    Fields:
    - `task_id` / `candidate_id` / `kind`: identity carried back
      from the dispatched Task.
    - `result_rows`: zero or more row-shaped dicts. Reserved for
      per-candidate kinds (follows `research.results` row schemas
      when populated).
    - `walk_forward_report`, `screening_runtime_record`,
      `evaluation_streams`: optional fields reserved for per-candidate
      kinds.
    - `payload`: generic carrier for task-specific return data
      (phase 4). Batch-level kinds (`SCREENING_BATCH`,
      `VALIDATION_BATCH`) place the raw batch-runner result dict
      under `payload["batch_result"]`. Must be pickle-safe.
    """

    task_id: str
    candidate_id: str
    kind: TaskKind
    result_rows: tuple[Mapping[str, Any], ...] = ()
    walk_forward_report: Mapping[str, Any] | None = None
    screening_runtime_record: Mapping[str, Any] | None = None
    evaluation_streams: Mapping[str, Any] | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskFailure:
    """A failed task outcome.

    Fields:
    - `task_id` / `candidate_id` / `kind`: identity carried back
      from the dispatched Task.
    - `reason_code`: typed failure classification; see `ReasonCode`.
    - `message`: short human-readable summary. Optional.
    - `traceback_str`: Python traceback string if the failure
      originated in an exception. Optional.
    """

    task_id: str
    candidate_id: str
    kind: TaskKind
    reason_code: ReasonCode
    message: str = ""
    traceback_str: str | None = None

    def is_retriable(self) -> bool:
        """Whether this failure is classified as retriable."""

        return is_retriable(self.reason_code)


# --------------------------------------------------------------------------
# Phase 5: BatchOutcome - explicit outcome contract for batch dispatch hooks
# --------------------------------------------------------------------------


class OutcomeKind(str, Enum):
    """Primary discriminator on BatchOutcome.

    - `SUCCESS`: the batch completed and the runner's hook considers
      the outcome acceptable. The Orchestrator will continue to
      dispatch subsequent batches.
    - `FAILURE`: the batch did not complete acceptably. The
      Orchestrator's parallel dispatch uses this to trigger the
      `stop_on_failure` gate; the inline dispatch continues to rely
      on the exception-propagation path for flow control.
    """

    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True)
class BatchOutcome:
    """Explicit, typed outcome of a batch-level dispatch attempt.

    This is what a runner-supplied `on_batch_complete` hook returns to
    the Orchestrator. Phase 5 made this the authoritative signal for
    the dispatch layer - the dispatch no longer inspects
    `batch["status"]` itself. The hook owns the translation from
    research-semantic batch state (`batch["status"]`,
    `batch["reason_code"]`, `batch["reason_detail"]`) into an
    orchestration-typed outcome.

    Invariants (enforced by `__post_init__`):
    - Success outcomes carry `reason_code=None`.
    - Failure outcomes carry a non-None `reason_code` from the
      `ReasonCode` enum.
    - `message` is always a string; empty string means "no detail".

    The outcome is pickle-safe by construction (only primitive /
    enum fields). It is intentionally *not* used in cross-process
    dispatch today - hooks run in the coordinator process after
    `future.result()` returns.
    """

    kind: OutcomeKind
    reason_code: ReasonCode | None = None
    message: str = ""

    def __post_init__(self) -> None:
        if self.kind is OutcomeKind.SUCCESS and self.reason_code is not None:
            raise ValueError(
                f"BatchOutcome.success must not carry a reason_code; got {self.reason_code!r}"
            )
        if self.kind is OutcomeKind.FAILURE and self.reason_code is None:
            raise ValueError(
                "BatchOutcome.failure must carry a reason_code"
            )
        if not isinstance(self.message, str):
            raise TypeError(
                f"BatchOutcome.message must be str, got {type(self.message).__name__}"
            )

    @staticmethod
    def success(*, message: str = "") -> "BatchOutcome":
        """Factory for a success outcome."""

        return BatchOutcome(kind=OutcomeKind.SUCCESS, reason_code=None, message=message)

    @staticmethod
    def failure(*, reason_code: ReasonCode, message: str = "") -> "BatchOutcome":
        """Factory for a failure outcome with a typed reason code."""

        if not isinstance(reason_code, ReasonCode):
            raise TypeError(
                f"reason_code must be a ReasonCode enum member, got "
                f"{type(reason_code).__name__}"
            )
        return BatchOutcome(
            kind=OutcomeKind.FAILURE,
            reason_code=reason_code,
            message=message,
        )

    def is_success(self) -> bool:
        return self.kind is OutcomeKind.SUCCESS

    def is_failure(self) -> bool:
        return self.kind is OutcomeKind.FAILURE

    def is_retriable(self) -> bool:
        """Whether the failure is classified retriable.

        Success outcomes return False (nothing to retry). Failure
        outcomes consult `RETRIABLE_REASONS`. Phase 5 does not act on
        this flag automatically; the surface is provided so a later
        phase can add bounded intra-run retry without widening the
        dispatch contract.
        """

        if self.is_success() or self.reason_code is None:
            return False
        return is_retriable(self.reason_code)


# Mapping of research-side `batch["reason_code"]` strings to
# orchestration-typed ReasonCode values. The mapping is conservative:
# every known research reason maps to an enum member; unknown reasons
# are handled by `classify_batch_reason` falling back to
# `ReasonCode.STRATEGY_ERROR` (a non-retriable default).
_BATCH_REASON_TO_CODE: dict[str, ReasonCode] = {
    "batch_execution_failed": ReasonCode.STRATEGY_ERROR,
    "isolated_candidate_execution_issues": ReasonCode.STRATEGY_ERROR,
    "upstream_batch_failed": ReasonCode.USER_CANCEL,
}


def classify_batch_reason(reason_str: str | None) -> ReasonCode:
    """Map a research-layer `batch['reason_code']` string to a typed
    orchestration `ReasonCode`.

    Unknown and empty strings map to `ReasonCode.STRATEGY_ERROR` - a
    non-retriable default chosen so that unrecognized failures do not
    silently inherit retriable semantics.
    """

    if not reason_str:
        return ReasonCode.STRATEGY_ERROR
    return _BATCH_REASON_TO_CODE.get(str(reason_str), ReasonCode.STRATEGY_ERROR)


__all__ = [
    "TaskKind",
    "ReasonCode",
    "OutcomeKind",
    "RETRIABLE_REASONS",
    "NON_RETRIABLE_REASONS",
    "is_retriable",
    "build_task_id",
    "Task",
    "TaskResult",
    "TaskFailure",
    "BatchOutcome",
    "classify_batch_reason",
]
