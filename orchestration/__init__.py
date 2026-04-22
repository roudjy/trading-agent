"""
Orchestration layer for the research platform (v3.9).

This package owns work coordination around the backtest engine: run
lifecycle, task dispatch, and (in later phases) scheduling, queueing,
and failure handling. It is deliberately kept small in v3.9 phase 1 -
only the public surface and boundary contract are established here.

Design invariants (see docs/adr/ADR-009-platform-layer-introduction.md):

- The engine (`agent/backtesting/`) must not import this package.
- This package may import narrow pure helpers from `research/` where
  explicitly justified (e.g. `research.candidate_pipeline`,
  `research.integrity`, `research.falsification`, `research.results`,
  `research.registry`, `research.universe`).
- This package must not import `research.run_research` or any module
  that transitively imports a strategy definition.
- `research.run_research` is the single research-side module permitted
  to import this package's public entry surface.
- Boundary rules are enforced by `tests/unit/test_orchestration_boundary.py`.

Package-name rationale: the v3.9 design brief calls this "the platform
layer", but the package is named `orchestration` because a top-level
Python package named `platform` is shadowed by the stdlib `platform`
module on some installs (the Python 3.11+ frozen stdlib in
`python313.zip` resolves ahead of any project-root package). The name
`orchestration` aligns with the layer already described in
`docs/orchestrator_brief.md` section 5 ("Orchestration Layer") and
avoids the shadow entirely.

Phase 1 public surface: empty. Named entities (Orchestrator, Task,
TaskResult, TaskFailure, ExecutionBackend, InlineBackend,
ProcessPoolBackend, ReasonCode) are added in phases 2 and 3 as they
land. Imports from this package fail with a clear ImportError until
the corresponding phase lands.
"""

from __future__ import annotations

from orchestration.executor import (
    ExecutionBackend,
    InlineBackend,
    ProcessPoolBackend,
    TaskOutcome,
)
from orchestration.orchestrator import Orchestrator, deepcopy_batch
from orchestration.queue import TaskQueue, TaskQueueError
from orchestration.scheduler import FifoScheduler, Scheduler
from orchestration.task import (
    NON_RETRIABLE_REASONS,
    RETRIABLE_REASONS,
    BatchOutcome,
    OutcomeKind,
    ReasonCode,
    Task,
    TaskFailure,
    TaskKind,
    TaskResult,
    build_task_id,
    classify_batch_reason,
    is_retriable,
)

__all__ = [
    "ORCHESTRATION_LAYER_VERSION",
    "BatchOutcome",
    "ExecutionBackend",
    "FifoScheduler",
    "InlineBackend",
    "NON_RETRIABLE_REASONS",
    "Orchestrator",
    "OutcomeKind",
    "ProcessPoolBackend",
    "RETRIABLE_REASONS",
    "ReasonCode",
    "Scheduler",
    "Task",
    "TaskFailure",
    "TaskKind",
    "TaskOutcome",
    "TaskQueue",
    "TaskQueueError",
    "TaskResult",
    "build_task_id",
    "classify_batch_reason",
    "deepcopy_batch",
    "is_retriable",
]

ORCHESTRATION_LAYER_VERSION = "3.9.0"
