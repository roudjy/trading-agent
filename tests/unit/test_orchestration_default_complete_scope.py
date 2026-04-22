"""
Phase-6 scope pin: production code never relies on `_default_complete`.

`orchestration.orchestrator._default_complete` is a legacy/test
fallback that translates `batch["status"]` into a typed `BatchOutcome`.
It is documented as "unit-test / ad-hoc caller only" - production
code in `research/run_research.py` must always supply an explicit
`on_batch_complete` hook when calling `dispatch_parallel_batches`
or `dispatch_serial_batches`.

This test statically parses `research/run_research.py` and asserts
that every call to the two dispatch methods includes an
`on_batch_complete=` keyword argument. This prevents production code
from silently falling back to the legacy default translation, which
would weaken the Phase-5 "outcome-not-status" decoupling.

If this test fails, the remedy is to supply an explicit hook (the
runner already has the pattern for screening and validation
adapters). The remedy is NOT to weaken this assertion.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _call_keywords(call: ast.Call) -> set[str]:
    """Return the set of keyword-argument names at `call`."""

    return {kw.arg for kw in call.keywords if kw.arg is not None}


def _attr_name(node: ast.AST) -> str | None:
    """Return the trailing attribute name if `node` is an Attribute
    chain, else None."""

    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def test_run_research_always_supplies_explicit_on_batch_complete() -> None:
    """Every dispatch_serial_batches / dispatch_parallel_batches call
    in research/run_research.py must pass on_batch_complete=...
    explicitly. This pins that production code does not silently
    depend on `_default_complete`."""

    runner = REPO_ROOT / "research" / "run_research.py"
    tree = ast.parse(runner.read_text(encoding="utf-8"), filename=str(runner))

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _attr_name(node.func)
        if name not in {"dispatch_serial_batches", "dispatch_parallel_batches"}:
            continue
        kwargs = _call_keywords(node)
        if "on_batch_complete" not in kwargs:
            # Walk up to find the enclosing function for a helpful
            # error message.
            offenders.append(
                f"call to .{name}(...) at line {node.lineno} missing "
                f"on_batch_complete="
            )

    assert not offenders, (
        "Production code in research/run_research.py relies on the "
        "`_default_complete` fallback at the following call sites, "
        "which weakens the Phase-5 outcome-not-status decoupling. "
        "Supply an explicit on_batch_complete hook returning BatchOutcome:\n  "
        + "\n  ".join(offenders)
    )


def test_default_complete_is_documented_as_fallback_only() -> None:
    """Static check: `_default_complete`'s docstring explicitly
    describes it as a legacy/test fallback, not a production
    contract. This is a weak check (it only inspects the docstring)
    but it catches accidental wording drift that would undermine
    the Phase-6 scope."""

    from orchestration.orchestrator import _default_complete

    doc = _default_complete.__doc__ or ""
    assert "fallback" in doc.lower(), (
        f"_default_complete docstring no longer contains 'fallback': "
        f"{doc[:200]}..."
    )


def test_default_complete_still_translates_failed_status() -> None:
    """The legacy behavior must remain correct - tests depend on it.
    If it's exercised (only by tests), it must correctly translate
    `batch["status"]=='failed'` into a typed failure outcome."""

    from orchestration.orchestrator import _default_complete
    from orchestration.task import ReasonCode

    batch_failed = {
        "status": "failed",
        "reason_code": "batch_execution_failed",
        "reason_detail": "x",
    }
    out = _default_complete(batch_failed, None)
    assert out.is_failure()
    assert out.reason_code is ReasonCode.STRATEGY_ERROR

    batch_ok = {"status": "completed"}
    assert _default_complete(batch_ok, None).is_success()
