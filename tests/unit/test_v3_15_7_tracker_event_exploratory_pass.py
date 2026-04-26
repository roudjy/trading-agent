"""v3.15.7 — exploratory_screening_pass tracker event discipline.

Source-level guards:

- ``research/run_research.py`` is the only module that emits the
  ``exploratory_screening_pass`` event.
- ``research/screening_runtime.py``, ``research/screening_process.py``,
  and ``research/batch_execution.py`` do NOT emit it.
- The emit site lives behind ``outcome.get("pass_kind") ==
  "exploratory"`` so non-exploratory passes never trigger.

These checks are deliberately source-level: spinning up a full
screening engine for an integration test is heavy, and the emit
trigger condition is statically verifiable.
"""

from __future__ import annotations

import inspect

import research.batch_execution as batch_execution
import research.run_research as run_research
import research.screening_process as screening_process
import research.screening_runtime as screening_runtime


def test_run_research_emits_exploratory_screening_pass():
    src = inspect.getsource(run_research)
    assert '"exploratory_screening_pass"' in src, (
        "run_research must emit the exploratory_screening_pass tracker "
        "event after execute_screening_candidate_isolated."
    )


def test_run_research_emit_is_gated_on_pass_kind_exploratory():
    src = inspect.getsource(run_research)
    # The emit site must be guarded by pass_kind == "exploratory".
    assert 'outcome.get("pass_kind") == "exploratory"' in src or \
        'pass_kind == "exploratory"' in src, (
        "exploratory_screening_pass emit must be gated on "
        'outcome.get("pass_kind") == "exploratory".'
    )


def test_screening_runtime_does_not_emit_event():
    src = inspect.getsource(screening_runtime)
    assert "exploratory_screening_pass" not in src


def test_screening_process_does_not_emit_event():
    src = inspect.getsource(screening_process)
    assert "exploratory_screening_pass" not in src


def test_batch_execution_does_not_emit_event():
    src = inspect.getsource(batch_execution)
    assert "exploratory_screening_pass" not in src


def test_emit_payload_carries_diagnostic_metrics_keys():
    src = inspect.getsource(run_research)
    # The payload must thread through diagnostic_metrics, not random
    # keys. Check the four metric fields appear near the emit.
    snippet_start = src.find('"exploratory_screening_pass"')
    assert snippet_start > 0
    window = src[snippet_start:snippet_start + 800]
    for key in ("expectancy", "profit_factor", "win_rate", "max_drawdown"):
        assert key in window, (
            f"{key} expected in exploratory_screening_pass payload window"
        )
