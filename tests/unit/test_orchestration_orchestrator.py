"""
Unit tests for the v3.9 Orchestrator entity.

Exercises `orchestration/orchestrator.py`:
- Orchestrator exposes `run_screening_phase` and `run_validation_phase`
  as the named seam.
- Both methods are pure pass-through in phase 3: they invoke the
  passed-in callable with the given kwargs and return its result
  unchanged.
- Exceptions raised in the driver propagate unchanged.
- Orchestrator holds an `ExecutionBackend` reference (default
  InlineBackend) and exposes a `shutdown` that delegates to the
  backend.
"""

from __future__ import annotations

import pytest

from orchestration.executor import InlineBackend, ProcessPoolBackend
from orchestration.orchestrator import Orchestrator


def test_orchestrator_constructs_with_default_inline_backend() -> None:
    o = Orchestrator()
    assert isinstance(o.backend, InlineBackend)
    assert o.run_id is None


def test_orchestrator_accepts_custom_backend_and_run_id() -> None:
    backend = ProcessPoolBackend(max_workers=1)
    try:
        o = Orchestrator(backend=backend, run_id="test-run-42")
        assert o.backend is backend
        assert o.run_id == "test-run-42"
    finally:
        backend.shutdown()


def test_run_screening_phase_is_pass_through() -> None:
    """The driver is invoked with the given kwargs and its return is returned."""

    captured: dict = {}

    def driver(*, a: int, b: str) -> tuple[int, str]:
        captured["a"] = a
        captured["b"] = b
        return (a + 1, b.upper())

    o = Orchestrator()
    result = o.run_screening_phase(driver, a=10, b="hello")
    assert result == (11, "HELLO")
    assert captured == {"a": 10, "b": "hello"}


def test_run_validation_phase_is_pass_through() -> None:
    def driver(*, payload: dict) -> dict:
        return {"echoed": payload}

    o = Orchestrator()
    out = o.run_validation_phase(driver, payload={"x": 1})
    assert out == {"echoed": {"x": 1}}


def test_run_screening_phase_propagates_driver_exceptions() -> None:
    def driver(**_kwargs: object) -> None:
        raise RuntimeError("boom")

    o = Orchestrator()
    with pytest.raises(RuntimeError, match="boom"):
        o.run_screening_phase(driver)


def test_run_validation_phase_propagates_driver_exceptions() -> None:
    def driver(**_kwargs: object) -> None:
        raise ValueError("validation exploded")

    o = Orchestrator()
    with pytest.raises(ValueError, match="validation exploded"):
        o.run_validation_phase(driver)


def test_orchestrator_has_no_ordering_enforcement_in_phase_3() -> None:
    """Phase 3 is a pure pass-through. Validation before screening
    is allowed; duplicate calls are allowed. Phase 4 will unify
    dispatch and re-introduce ordering enforcement."""

    o = Orchestrator()
    # Validation without prior screening must not raise:
    assert o.run_validation_phase(lambda **_kw: "ok") == "ok"
    # Calling screening twice must not raise:
    assert o.run_screening_phase(lambda **_kw: 1) == 1
    assert o.run_screening_phase(lambda **_kw: 2) == 2


def test_orchestrator_shutdown_delegates_to_backend() -> None:
    class _TrackingBackend(InlineBackend):
        def __init__(self) -> None:
            self.shutdown_calls = 0

        def shutdown(self, *, wait: bool = True) -> None:
            self.shutdown_calls += 1

    backend = _TrackingBackend()
    o = Orchestrator(backend=backend)
    o.shutdown()
    assert backend.shutdown_calls == 1
    o.shutdown()
    assert backend.shutdown_calls == 2  # delegated each time


def test_orchestrator_public_api() -> None:
    """The orchestration package exposes Orchestrator in its public API."""

    import orchestration

    assert hasattr(orchestration, "Orchestrator")
    assert orchestration.Orchestrator is Orchestrator
