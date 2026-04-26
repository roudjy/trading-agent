"""v3.15.6 — batch_execution must NOT infer screening_phase.

batch_execution has no preset/tracker context (see
``execute_screening_batch`` signature on
``research/batch_execution.py:106``). v3.15.6 forbids it from
inferring the phase from screening_mode / preset_class /
hypothesis_id / diagnostic flags. The call to
``execute_screening_candidate_isolated`` must pass
``screening_phase=None`` literally.
"""

from __future__ import annotations

import inspect

import research.batch_execution as batch_execution


def test_batch_execution_passes_explicit_none_to_screening_phase():
    """Source-level check that the kwarg is ``None``, not inferred."""
    src = inspect.getsource(batch_execution.execute_screening_batch)
    # Must contain literal ``screening_phase=None`` — no inference.
    assert "screening_phase=None" in src, (
        "batch_execution must pass screening_phase=None explicitly. "
        "Inference from screening_mode/preset_class/hypothesis_id/"
        "diagnostic flags is forbidden in v3.15.6."
    )


def test_batch_execution_does_not_emit_tracker_events():
    """batch_execution has no tracker — must not import or call one."""
    src = inspect.getsource(batch_execution)
    forbidden_substrings = [
        "tracker.emit_event",
        "from research.observability",
    ]
    for needle in forbidden_substrings:
        assert needle not in src, (
            f"batch_execution must not use tracker (found {needle!r}); "
            f"observability is run_research's responsibility in v3.15.6."
        )


def test_batch_execution_signature_unchanged():
    """Pin the kwargs on ``execute_screening_batch`` — adding a
    ``preset`` or ``tracker`` here is out of scope.
    """
    sig = inspect.signature(batch_execution.execute_screening_batch)
    expected = {
        "batch",
        "batch_candidates",
        "interval_ranges",
        "evaluation_config",
        "regime_config",
        "screening_candidate_budget_seconds",
        "screening_param_sample_limit",
    }
    assert set(sig.parameters.keys()) == expected, (
        f"v3.15.6 must not extend execute_screening_batch signature. "
        f"Got {set(sig.parameters.keys())!r}, expected {expected!r}."
    )


def test_batch_execution_does_not_reference_screening_mode_for_inference():
    """Defensive: batch_execution must not read preset.screening_mode
    or similar to derive screening_phase.
    """
    src = inspect.getsource(batch_execution.execute_screening_batch)
    # We accept that screening_mode literal may not appear. Strengthen
    # the guard: the function must not branch on any preset attribute.
    forbidden = [
        ".screening_mode",
        ".preset_class",
        ".hypothesis_id",
        ".diagnostic_only",
    ]
    for needle in forbidden:
        assert needle not in src, (
            f"batch_execution must not read {needle!r} — no inference."
        )
