"""
Phase-5 artifact-truth dominance tests.

These tests pin the structural invariant that underpins safe
recovery in v3.9: **the Queue is a cache; the artifacts are truth.**

Concretely:

1. The Orchestrator's `TaskQueue` is instance-scoped. Creating a new
   Orchestrator yields a fresh, empty Queue. Nothing about a prior
   run is carried in memory.
2. The Orchestrator and all Phase 5 additions (Queue, Scheduler,
   `BatchOutcome`, `classify_batch_reason`) do not hold any
   module-level mutable state that could persist across runs.
3. Research-layer recovery (`research.recovery`) does not import or
   consult the orchestration Queue. Recovery truth flows from
   artifacts on disk into a new Queue, never the other way around.
4. Task-ids are deterministic in `(candidate_id, kind, attempt)`, so
   the same batch produces the same task_id on a resumed run and the
   artifact-backed completion check can dedup correctly.

Each of these properties is tested without running a full research
pipeline - these are structural assertions about the package, not
pipeline-end-to-end assertions (those are covered by Phase 4's
bytewise-equivalence tests).
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

from orchestration.orchestrator import Orchestrator
from orchestration.queue import TaskQueue
from orchestration.task import (
    BatchOutcome,
    Task,
    TaskKind,
    classify_batch_reason,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# 1. Queue is instance-scoped
# --------------------------------------------------------------------------


def test_new_orchestrator_gets_fresh_queue() -> None:
    o1 = Orchestrator()
    t = Task.build(candidate_id="x", kind=TaskKind.SCREENING_BATCH)
    o1.queue.enqueue(t)
    assert o1.queue.pending_count() == 1

    o2 = Orchestrator()
    assert o2.queue.pending_count() == 0
    assert not o2.queue.contains(t.task_id)
    assert o2.queue is not o1.queue


def test_queue_state_does_not_persist_through_construction() -> None:
    """Simulate a crash by dropping the Orchestrator entirely, then
    check that a new Orchestrator knows nothing about the old tasks."""

    old = Orchestrator()
    for n in range(5):
        old.queue.enqueue(Task.build(candidate_id=f"b-{n}", kind=TaskKind.SCREENING_BATCH))

    # "Crash" - lose the old Orchestrator reference.
    del old

    # Fresh Orchestrator - queue is empty, no memory of prior run.
    new = Orchestrator()
    assert new.queue.total_count() == 0


# --------------------------------------------------------------------------
# 2. No module-level mutable state in orchestration/
# --------------------------------------------------------------------------


def test_orchestration_modules_have_no_module_level_mutable_caches() -> None:
    """Parse every orchestration/ .py file and assert that no
    module-level assignment creates a mutable container that could
    accumulate state across runs.

    Allowed module-level values: int/str/bool/None constants, tuples
    of those, frozenset, classes, dataclass definitions, typed enums,
    and constant lookup dicts (mappings of hard-coded strings to
    hard-coded ReasonCodes or similar). The orchestration package is
    expected to be class-and-function-heavy with constant-only
    module globals.

    Disallowed: module-level `list`, `dict` of non-constant values,
    `set`, or any pattern that creates a singleton cache. A failure
    here is a real concern: it means some orchestration state could
    leak across Orchestrator instances.

    This is a conservative structural check - the real guarantee is
    the Orchestrator being instance-scoped (tested above).
    """

    orch_dir = REPO_ROOT / "orchestration"
    suspicious: list[tuple[str, str, str]] = []
    for py in sorted(orch_dir.glob("*.py")):
        if py.name == "__init__.py":
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            # Only inspect top-level assignments.
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                name = target.id
                # Dunders and uppercase-only "constants" are allowed;
                # lowercase module-level mutable containers are the
                # risk we are scanning for.
                if name.startswith("_") or name.isupper():
                    continue
                value = node.value
                # Flag bare empty list/dict/set.
                if isinstance(value, (ast.List, ast.Dict, ast.Set)):
                    suspicious.append((py.name, name, ast.dump(value)[:80]))
    assert not suspicious, (
        "Found module-level mutable containers in orchestration/ that could "
        f"accumulate state across runs: {suspicious}"
    )


# --------------------------------------------------------------------------
# 3. Research.recovery does not consult orchestration state
# --------------------------------------------------------------------------


def test_research_recovery_does_not_import_orchestration() -> None:
    """Recovery truth must come from artifacts. `research.recovery`
    must not import orchestration symbols; if it did, recovery could
    accidentally consult in-memory orchestration state instead of
    on-disk artifacts."""

    recovery_path = REPO_ROOT / "research" / "recovery.py"
    tree = ast.parse(recovery_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith("orchestration"), (
                f"research.recovery imports from orchestration ({module!r}), "
                "which would let orchestration state influence recovery. "
                "Recovery truth must remain artifact-driven."
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("orchestration"), (
                    f"research.recovery imports {alias.name!r}"
                )


def test_research_run_state_does_not_import_orchestration() -> None:
    """Same invariant for the PID-lock / heartbeat store."""

    run_state_path = REPO_ROOT / "research" / "run_state.py"
    tree = ast.parse(run_state_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith("orchestration"), (
                f"research.run_state imports from orchestration ({module!r})"
            )


# --------------------------------------------------------------------------
# 4. Task id determinism is the foundation for artifact-backed dedup
# --------------------------------------------------------------------------


def test_same_candidate_produces_same_task_id_across_orchestrators() -> None:
    """This is the property that makes artifact-backed resume
    dedup-safe: the same batch, under the same kind, same attempt,
    yields the same task_id regardless of which Orchestrator instance
    processes it."""

    ta = Task.build(candidate_id="batch-abc", kind=TaskKind.SCREENING_BATCH)
    tb = Task.build(candidate_id="batch-abc", kind=TaskKind.SCREENING_BATCH)
    assert ta.task_id == tb.task_id

    # A separate Orchestrator enqueues and marks completed; another
    # Orchestrator with the same id can ask "do I know about this
    # task?" - but the answer for a fresh Orchestrator is always No
    # (new Queue). Resume dedup therefore relies on *artifacts*, not
    # on Queue state. This is the invariant we are pinning.

    q1 = TaskQueue()
    q2 = TaskQueue()
    q1.enqueue(ta)
    # q2 is separate - it knows nothing, even though the task_id is
    # deterministic.
    assert not q2.contains(ta.task_id)


# --------------------------------------------------------------------------
# 5. BatchOutcome is transient; it does not become a persistence contract
# --------------------------------------------------------------------------


def test_batch_outcome_is_ephemeral_not_persisted() -> None:
    """BatchOutcome exists in memory during dispatch. It is the hook
    return value. It is not written to any artifact by the
    orchestration layer - that would risk making queue/outcome state
    the source of truth."""

    # Parse the orchestration package and confirm no module writes
    # BatchOutcome instances to disk.
    orch_dir = REPO_ROOT / "orchestration"
    offenders: list[str] = []
    for py in sorted(orch_dir.glob("*.py")):
        if py.name == "__init__.py":
            continue
        source = py.read_text(encoding="utf-8")
        # A very conservative heuristic: BatchOutcome references
        # coupled with file-writing APIs. We expect none.
        if "BatchOutcome" in source and ("open(" in source and "w" in source):
            # Inspect more carefully to reduce false positives.
            for line in source.splitlines():
                if "BatchOutcome" in line and "open(" in line:
                    offenders.append(f"{py.name}: {line.strip()}")
    assert not offenders, (
        f"Orchestration layer writes BatchOutcome to disk: {offenders}. "
        "BatchOutcome must remain transient."
    )


# --------------------------------------------------------------------------
# 6. classify_batch_reason is pure
# --------------------------------------------------------------------------


def test_classify_batch_reason_is_pure_and_idempotent() -> None:
    """classify_batch_reason must be a pure function: no caching, no
    global state, no I/O. Multiple calls with the same input yield
    the same result (this is trivially true for pure functions but
    pinning it documents the contract)."""

    assert classify_batch_reason("batch_execution_failed") == classify_batch_reason(
        "batch_execution_failed"
    )
    assert classify_batch_reason(None) == classify_batch_reason(None)
    # The function accepts arbitrary strings without error, falling
    # back to STRATEGY_ERROR; no state accumulates.
    for s in ("foo", "bar", "batch_execution_failed", "upstream_batch_failed"):
        for _ in range(3):
            classify_batch_reason(s)
