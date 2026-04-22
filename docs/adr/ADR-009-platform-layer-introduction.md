# ADR-009: Platform Layer Introduction

Status: Accepted
Date: 2026-04-21
Phase: v3.9 (orchestration hardening, phases 1-3)
Supersedes: -
Superseded by: -
Related: ADR-006 (thin contract v2.0 deferred), ADR-007 (fitted
feature abstraction), ADR-008 (execution realism & evaluation
hardening)

## Context

Up to and including v3.8, research orchestration concerns
(lifecycle, batch partitioning, scheduling, per-batch recovery,
resume policy, progress tracking) lived inside the `research/`
package alongside research-semantic concerns (candidate planning,
integrity checks, falsification gates, artifact row construction).
The division was conceptual, not enforced: `research/run_research.py`
(~2790 lines) imported both sets of concerns and glued them into a
single imperative driver.

That layout was sufficient through v3.8 because the execution model
was a single-run, single-process batch loop with coarse intra-batch
parallelism via `ProcessPoolExecutor` ([research/run_research.py:14](../../research/run_research.py),
[research/run_research.py:125](../../research/run_research.py)). It
became a ceiling for v3.9's goals:

1. A **named orchestrator** that owns run lifecycle and dispatch
   decisions, instead of those responsibilities being inlined in the
   runner.
2. A **typed task/result/failure model** so work units are first-class
   and the retry and dedup semantics have something to hook onto.
3. A **backend abstraction** that lets multi-process execution evolve
   (run-scoped pool, cross-Batch parallelism) without leaking
   concurrency primitives into the runner.
4. A **boundary that is enforceable** - not just conventional - so
   that future changes cannot silently dissolve the layering.

None of these required a large physical relocation of v3.8 code. All
of them required a dedicated package where the new entities land and
an enforceable rule that polices what may import what.

## Decision

Introduce a dedicated top-level package, `orchestration/`, that owns
the platform layer. New capability entities (Orchestrator,
ExecutionBackend, Worker, Task, TaskResult, TaskFailure, ReasonCode)
are created fresh inside `orchestration/`. Existing `research/`
modules stay where they are in phases 1-3 and are called through
narrow adapters.

### Package name

The v3.9 design brief names this layer "the platform". The package
is not named `platform/` for a single concrete reason: a top-level
Python package named `platform` conflicts with the Python standard
library's `platform` module. On Python 3.11+ with the frozen stdlib
(`python313.zip` at `sys.path[0]`), a local `platform/` package is
unimportable - stdlib wins. On installs without the frozen stdlib
(e.g., typical Linux packaging), a local `platform/` package wins -
stdlib `import platform` returns the project package, breaking any
library that uses stdlib `platform.system()`, `platform.python_version()`,
etc. Either way the name is hostile to the ecosystem.

The package is named `orchestration/`, matching the terminology
already used in `docs/orchestrator_brief.md` section 5
("Orchestration Layer"). The conceptual label "platform layer"
remains valid in prose; it is just not the package name.

### Dependency rules

The rules below are the complete and exclusive definition of what
may import what across the engine / research / orchestration /
dashboard boundary. They are enforced statically by
[tests/unit/test_orchestration_boundary.py](../../tests/unit/test_orchestration_boundary.py).

**Allowed.**

- `orchestration.*` → `agent.backtesting.*` (through the narrow
  ExecutionBackend / Worker / engine-construction surface only).
- `orchestration.*` → `research.*` for pure helpers: candidate
  planning (`research.candidate_pipeline`), integrity gates
  (`research.integrity`), falsification gates (`research.falsification`),
  artifact row construction (`research.results`), strategy registry
  (`research.registry`), universe builder (`research.universe`).
- `research.run_research` → `orchestration.*` (single permitted
  crossing from research into orchestration).
- `dashboard.*` → `orchestration.*` (launch API only, once added).

**Forbidden.**

- `agent.backtesting.*` → `orchestration.*` or `research.*`. The
  engine is the bottom of the stack; nothing orchestration-adjacent
  may leak into it.
- `agent.backtesting.*` → `multiprocessing`, `concurrent.futures`,
  `threading`, `asyncio`, `joblib`. The engine holds no parallelism;
  that is the orchestration layer's responsibility.
- `research/` (excluding `research/run_research.py`) → `orchestration.*`.
- `orchestration.*` → `research.run_research` or any strategy-
  defining module (`agent.backtesting.strategies`, `.features`,
  `.fitted_features`, `.thin_strategy`).
- Circular imports between `orchestration/` and `research/`.
- `dashboard.*` → `agent.backtesting.*` or research orchestration
  modules for execution purposes.

### No early relocation

Phases 1-3 of v3.9 do not move any file from `research/` to
`orchestration/`. The existing `research/run_state.py`,
`research/batching.py`, `research/batch_execution.py`,
`research/recovery.py`, `research/orchestration_policy.py`,
`research/observability.py`, and `research/screening_process.py`
stay where they are. The Orchestrator invokes them through narrow
named-symbol imports. Any selective relocation is deferred to a
later v3.9 phase and must be justified by a specific capability
need, done one file at a time, with its own bytewise regression
evidence.

### Worker defaults

The safe default for worker-side engine instantiation is **fresh
engine per task**. No warm engine reuse across tasks. No module-level
engine cache. Worker processes themselves may persist across tasks
(a ProcessPool keeps them alive) but the `BacktestEngine` instance
is constructed inside the task body and goes out of scope at task
end. Any future cross-task caching is gated behind explicit proof
of (a) immutability of the cached object, (b) bytewise regression
with and without the cache enabled, (c) deterministic eviction, and
(d) measurable wall-clock justification.

## Consequences

### Preserved bytewise

- Engine behavior. No change to `agent/backtesting/*`. Tier 1
  bytewise digest pins (SMA crossover, z-score mean reversion, pairs
  z-score, multi-asset parity, fitted-feature pins) continue to hold.
- All public artifact schemas. `research_latest.json` top-level,
  19-column CSV, integrity and falsification sidecars, run manifest,
  run state, batch state, candidate state artifacts are all
  unchanged.
- `candidate_id` hashing inputs.
- Walk-forward `FoldLeakageError` semantics.
- Fitted-feature determinism.
- Resume-integrity gate.

### Added

- `orchestration/` package with a minimal public surface defined in
  `orchestration/__init__.py`. Phase 1 exposes only
  `ORCHESTRATION_LAYER_VERSION` as a semver-shaped string. Phases 2
  and 3 add Task/TaskResult/TaskFailure/ReasonCode (phase 2) and
  Orchestrator/ExecutionBackend/InlineBackend/ProcessPoolBackend
  (phase 3).
- Static boundary-enforcement tests at
  `tests/unit/test_orchestration_boundary.py`.
- This ADR and the v3.9 addendum in `docs/orchestrator_brief.md`.

### Deferred

- Scheduler and Queue as separate entities (v3.9 phase 4).
- Cross-Batch parallelism (v3.9 phase 4, gated on bytewise regression).
- Task-level resume (v3.9 phase 5).
- Platform event log (v3.9 phase 5, provisional).
- Retry-count tables for retriable reason codes (v3.9 phase 5, set at
  implementation).
- Selective file relocation from `research/` (v3.9 phase 6, zero to
  two files, each with its own PR).
- Dashboard launch API (v3.9 phase 7).
- Run-level rollup artifacts for cost sensitivity and exit
  diagnostics (v4+).

## Rejected alternatives

- **Engine-internal extension.** Rejected. Violates the architectural
  constraint that the engine remains pure and deterministic.
- **Separate repo or microservice.** Rejected per explicit scope and
  on merit. Reproducibility (Tier 1 bytewise pins) depends on one
  `pytest` invocation covering engine + orchestration + research.
- **Package named `platform`.** Rejected for the stdlib name-shadow
  reason documented above.
- **Large relocation of research/ modules into orchestration/ as
  phase 2.** Rejected. Optimizes for repo aesthetics at the cost of
  structural risk on a layer landing on top of a freshly-stabilized
  engine. v3.9 is capability-first; relocation is deferred.
- **Warm engine cache per worker.** Rejected as default. Too easy a
  path to hidden cross-task coupling. Fresh engine per task is the
  safety-first default; any caching landing later must clear a
  four-point proof bar.
