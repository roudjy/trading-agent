"""
Static import-direction lint for the v3.9 orchestration boundary.

Enforces the dependency rules documented in
`docs/adr/ADR-009-platform-layer-introduction.md` and referenced by
`orchestration/__init__.py`. The rules are checked by parsing every
`.py` file under `agent/`, `orchestration/`, `research/`, and
`dashboard/` with `ast` (no imports executed) and asserting that the
collected import statements conform to the allowed matrix.

Rules enforced here:

1. `agent/backtesting/` must not import `orchestration.*` or `research.*`.
   (The engine is the bottom of the stack.)

2. `agent/backtesting/` must not import `multiprocessing`,
   `concurrent.futures`, `threading`, `asyncio`, `joblib`, or any
   similar concurrency primitive. (The engine owns no parallelism;
   that responsibility sits above the engine in `orchestration/`.)

3. `research/` must not import `orchestration.*`, with one exception:
   `research/run_research.py` is the single permitted crossing point
   and may import `orchestration.*` freely.

4. `orchestration/` must not import `research.run_research` or any
   strategy-defining module (`agent.backtesting.strategies`,
   `agent.backtesting.features`, `agent.backtesting.fitted_features`,
   `agent.backtesting.thin_strategy`). (Strategies live inside
   engine invocations, not in platform code.)

5. `dashboard/` must not import `agent.backtesting.*` or `research.*`
   directly for orchestration purposes. Data-read imports from
   `research.results` (artifact row schemas) remain allowed because
   the dashboard legitimately consumes artifacts.

These rules exist so that the package separation does not stay
superficial. If a future change needs to break a rule, the test
failure forces an explicit justification - either update the rule
with rationale, or fix the import.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _collect_imports(py_path: Path) -> list[str]:
    """Return the fully-qualified module names imported by `py_path`.

    Only top-level module names are returned (the first dotted segment
    and its full string are both recorded - callers filter).
    """

    source = py_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(py_path))
    except SyntaxError:
        return []

    collected: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                collected.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                # relative import - resolve against the file's package
                rel_base = _package_for(py_path)
                if rel_base is None:
                    continue
                parts = rel_base.split(".")
                if node.level > len(parts):
                    continue
                base = ".".join(parts[: len(parts) - node.level + 1])
                if module:
                    resolved = f"{base}.{module}" if base else module
                else:
                    resolved = base
                collected.append(resolved)
            else:
                collected.append(module)
    return collected


def _package_for(py_path: Path) -> str | None:
    """Return the dotted module name `py_path` belongs to, if any."""

    try:
        rel = py_path.relative_to(REPO_ROOT)
    except ValueError:
        return None
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    else:
        return None
    return ".".join(parts)


def _iter_py_files(root: Path) -> list[Path]:
    """Return a stable-sorted list of .py files under `root`.

    Skips caches and virtualenvs that may live inside the tree.
    """

    if not root.exists():
        return []
    files: list[Path] = []
    for p in root.rglob("*.py"):
        parts = p.parts
        if "__pycache__" in parts:
            continue
        if ".venv" in parts or "site-packages" in parts:
            continue
        files.append(p)
    files.sort()
    return files


def _starts_with_any(mod: str, prefixes: tuple[str, ...]) -> bool:
    return any(mod == pfx or mod.startswith(pfx + ".") for pfx in prefixes)


CONCURRENCY_MODULES: tuple[str, ...] = (
    "multiprocessing",
    "concurrent.futures",
    "threading",
    "asyncio",
    "joblib",
)

# Exceptions: files under agent/backtesting/ that are known data-helper
# libraries, not part of the engine fold loop. They may import async
# primitives for external I/O (not for engine parallelism).
#
# `strategies.py` hosts `laad_fear_greed` which runs an async aiohttp
# fetch against alternative.me for the Fear & Greed index - a data
# source, not an engine execution mechanism. If that helper ever gets
# migrated or removed, drop this exception.
ENGINE_CONCURRENCY_EXCEPTIONS: tuple[str, ...] = (
    "agent/backtesting/strategies.py",
)


def test_engine_does_not_import_orchestration_or_research() -> None:
    """agent/backtesting/ must not import orchestration.* or research.*."""

    offenders: list[tuple[str, str]] = []
    for py in _iter_py_files(REPO_ROOT / "agent" / "backtesting"):
        for imp in _collect_imports(py):
            if _starts_with_any(imp, ("orchestration", "research")):
                offenders.append((str(py.relative_to(REPO_ROOT)), imp))
    assert not offenders, (
        "agent/backtesting/ must not import from orchestration/ or research/. "
        f"Offenders: {offenders}"
    )


def test_engine_uses_no_concurrency_primitives() -> None:
    """agent/backtesting/ must contain no parallelism imports.

    `ENGINE_CONCURRENCY_EXCEPTIONS` lists files that are data-helper
    libraries (not engine execution) and may legitimately use async
    I/O. Any new file or import path falls under the strict rule.
    """

    offenders: list[tuple[str, str]] = []
    for py in _iter_py_files(REPO_ROOT / "agent" / "backtesting"):
        rel = py.relative_to(REPO_ROOT).as_posix()
        if rel in ENGINE_CONCURRENCY_EXCEPTIONS:
            continue
        for imp in _collect_imports(py):
            if _starts_with_any(imp, CONCURRENCY_MODULES):
                offenders.append((rel, imp))
    assert not offenders, (
        "agent/backtesting/ must not import concurrency primitives. "
        f"Offenders: {offenders}"
    )


def test_research_does_not_import_orchestration_except_runner() -> None:
    """research/ must not import orchestration.*, except research/run_research.py."""

    offenders: list[tuple[str, str]] = []
    runner = (REPO_ROOT / "research" / "run_research.py").resolve()
    for py in _iter_py_files(REPO_ROOT / "research"):
        if py.resolve() == runner:
            continue
        for imp in _collect_imports(py):
            if _starts_with_any(imp, ("orchestration",)):
                offenders.append((str(py.relative_to(REPO_ROOT)), imp))
    assert not offenders, (
        "research/ may not import orchestration/* outside of run_research.py. "
        f"Offenders: {offenders}"
    )


def test_orchestration_does_not_import_runner_or_strategies() -> None:
    """orchestration/ must not import research.run_research or any strategy-defining module."""

    forbidden_prefixes = (
        "research.run_research",
        "agent.backtesting.strategies",
        "agent.backtesting.features",
        "agent.backtesting.fitted_features",
        "agent.backtesting.thin_strategy",
    )
    offenders: list[tuple[str, str]] = []
    for py in _iter_py_files(REPO_ROOT / "orchestration"):
        for imp in _collect_imports(py):
            if _starts_with_any(imp, forbidden_prefixes):
                offenders.append((str(py.relative_to(REPO_ROOT)), imp))
    assert not offenders, (
        "orchestration/ must not import research.run_research or strategy/feature modules. "
        f"Offenders: {offenders}"
    )


def test_dashboard_does_not_reach_into_engine_or_research_orchestration() -> None:
    """dashboard/ must not drive engine or research-orchestration logic.

    The dashboard is a legitimate artifact consumer and may also
    perform read-checks against run state (so it can decide whether
    a new run can be launched). It must not reach into execution
    drive paths (`batch_execution`, `batching`, `orchestration_policy`,
    `recovery`, `screening_process`) or call `run_research` as if it
    owned the scheduling.

    `research.run_state` is explicitly allowed as a read surface here:
    it is the authoritative PID/heartbeat store, and querying it is
    the correct pre-launch check.
    """

    forbidden_prefixes = (
        "agent.backtesting",
        "research.run_research",
        "research.batch_execution",
        "research.orchestration_policy",
        "research.recovery",
        "research.batching",
        "research.screening_process",
        "research.screening_runtime",
    )
    offenders: list[tuple[str, str]] = []
    for py in _iter_py_files(REPO_ROOT / "dashboard"):
        for imp in _collect_imports(py):
            if _starts_with_any(imp, forbidden_prefixes):
                offenders.append((str(py.relative_to(REPO_ROOT)), imp))
    assert not offenders, (
        "dashboard/ may not reach into engine or research drive-path modules. "
        f"Offenders: {offenders}"
    )


def test_no_circular_imports_between_orchestration_and_research() -> None:
    """`orchestration/` and `research/` must not import each other both ways.

    `research/run_research.py -> orchestration` is allowed (one way).
    `orchestration -> research.*` (pure helpers) is allowed.
    But cycles are forbidden.
    """

    orch_imports_from_research: list[str] = []
    for py in _iter_py_files(REPO_ROOT / "orchestration"):
        for imp in _collect_imports(py):
            if _starts_with_any(imp, ("research",)):
                orch_imports_from_research.append(imp)

    research_imports_from_orch: list[tuple[str, str]] = []
    for py in _iter_py_files(REPO_ROOT / "research"):
        rel = py.relative_to(REPO_ROOT).as_posix()
        if rel == "research/run_research.py":
            continue
        for imp in _collect_imports(py):
            if _starts_with_any(imp, ("orchestration",)):
                research_imports_from_orch.append((rel, imp))

    assert not research_imports_from_orch, (
        "research/ (excluding run_research.py) imports from orchestration/, which, "
        "combined with orchestration/ -> research/ imports, would form a cycle. "
        f"Offenders: {research_imports_from_orch}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
