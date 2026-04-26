"""v3.15.6 — propagation through run_research is source-verified.

We do NOT execute a full research run here (heavy fixtures). We
instead pin via static source-level guards that the propagation
chain is wired:

1. ``screening_phase_active`` event is emitted right after preset
   resolution.
2. ``screening_phase_observed`` event is emitted at the candidate
   loop, just before the screening call.
3. ``execute_screening_candidate_isolated`` is invoked with
   ``screening_phase=`` derived from the preset (or None).
4. ``build_run_meta_payload`` is invoked elsewhere with the run-
   meta sidecar receiving ``screening_phase`` (proven via
   ``run_meta.py`` payload tests in a separate file).

Source-grep is intentional: these are observability hooks that
are surgically narrow; full integration coverage would require a
heavy controlled fixture run, which is in scope for the
behavior-equivalent test suite, not here.
"""

from __future__ import annotations

import inspect

import research.run_research as run_research


def test_run_research_emits_screening_phase_active_event():
    src = inspect.getsource(run_research)
    assert '"screening_phase_active"' in src, (
        "run_research must emit screening_phase_active tracker event "
        "after preset resolution."
    )


def test_run_research_emits_screening_phase_observed_event():
    src = inspect.getsource(run_research)
    assert '"screening_phase_observed"' in src, (
        "run_research must emit screening_phase_observed tracker "
        "event per candidate at the screening boundary."
    )


def test_run_research_passes_screening_phase_to_screening_process():
    src = inspect.getsource(run_research)
    # The call site uses preset_obj.screening_phase via a conditional;
    # check the kwarg appears in the call.
    assert "screening_phase=" in src, (
        "run_research must pass screening_phase= to "
        "execute_screening_candidate_isolated."
    )


def test_run_research_imports_validate_preset():
    """Ensures the v3.15.6 strict-mode validation extension is wired."""
    assert hasattr(run_research, "validate_preset") or "validate_preset" in \
        inspect.getsource(run_research), (
            "run_research must import validate_preset for the v3.15.6 "
            "strict-mode screening_phase check."
        )


def test_screening_phase_active_emit_after_preset_validation():
    """The event must fire AFTER ``_enforce_preset_validation`` so a
    bad-phase preset under strict mode fails BEFORE the visibility
    event lies about an invalid value.
    """
    src = inspect.getsource(run_research)
    # Brittle but informative: assert event-emit appears after the
    # validation call site within the same source body.
    val_idx = src.find("_enforce_preset_validation(preset_obj, tracker)")
    event_idx = src.find('"screening_phase_active"')
    assert val_idx >= 0 and event_idx > val_idx, (
        "screening_phase_active must emit AFTER _enforce_preset_validation."
    )
