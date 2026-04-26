"""v3.15.6 — propagation reaches the screening_process boundary.

Direct tests on ``execute_screening_candidate_isolated``:
- Accepts ``screening_phase`` kwarg with all three values + None.
- Returned outcome dict does NOT contain ``screening_phase``
  (Optie B; prevents stealth schema-drift via
  ``runtime_record.update(outcome)`` on the batch path).
"""

from __future__ import annotations

import inspect

import pytest

from research.screening_process import execute_screening_candidate_isolated


VALID_PHASES = ["exploratory", "standard", "promotion_grade"]


def test_signature_accepts_screening_phase_kwarg():
    sig = inspect.signature(execute_screening_candidate_isolated)
    assert "screening_phase" in sig.parameters
    param = sig.parameters["screening_phase"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY
    assert param.default is None


def test_annotation_is_str_or_none_not_literal():
    """v3.15.7 must be free to extend the vocabulary in-place. The
    Literal lives on the preset side; the boundary is intentionally
    looser.
    """
    sig = inspect.signature(execute_screening_candidate_isolated)
    annotation = sig.parameters["screening_phase"].annotation
    # Stringified annotation due to ``from __future__ import annotations``.
    assert "str" in str(annotation)
    assert "Literal" not in str(annotation)


@pytest.mark.parametrize("phase", VALID_PHASES + [None])
def test_kwarg_accepted_via_inspect_only(phase):
    """We do not run the engine here — that would be a heavy fixture
    setup. We instead check that the signature binds ``screening_phase``
    correctly so the kwarg is plumbed.
    """
    sig = inspect.signature(execute_screening_candidate_isolated)
    bound = sig.bind_partial(
        strategy={"name": "x", "params": {}},
        candidate={"candidate_id": "c1", "asset": "A", "interval": "1d",
                   "strategy_name": "x"},
        interval_range={"start": "2024-01-01", "end": "2024-12-31"},
        evaluation_config={},
        regime_config=None,
        budget_seconds=1,
        max_samples=1,
        screening_phase=phase,
    )
    assert bound.arguments["screening_phase"] == phase


def test_outcome_dict_must_not_contain_screening_phase_key():
    """v3.15.6 invariant — preserved across v3.15.7.

    The literal key ``"screening_phase"`` must NEVER appear in the
    aggregate outcome dict returned by
    ``screening_runtime.execute_screening_candidate_samples``. v3.15.7
    introduced ``pass_kind`` (which mirrors the phase on a
    successful pass) but the literal ``screening_phase`` key remains
    forbidden — keeping the v3.15.6 contract intact protects
    downstream artifacts from stealth schema drift via
    ``runtime_record.update(outcome)`` on
    ``research/batch_execution.py:191``.

    v3.15.7 supersedes the original ``del screening_phase`` /
    ``screening_phase,`` indirect heuristic with a direct check on
    the screening_runtime aggregate construction site.
    """
    import research.screening_runtime as runtime_module

    samples_src = inspect.getsource(runtime_module.execute_screening_candidate_samples)
    # The aggregate outcome dict is the only place where we'd add a
    # ``"screening_phase"`` key. We forbid that key string literal
    # appearing as a dict key inside this function body.
    assert '"screening_phase":' not in samples_src, (
        "v3.15.6 invariant violated: screening_runtime aggregate outcome "
        "must NOT carry a ``screening_phase`` key. v3.15.7 introduces "
        "``pass_kind`` instead, which is intentionally a different field."
    )
    # Defensive: the boundary function (execute_screening_candidate_isolated)
    # must also not introduce ``"screening_phase":`` in its result.
    boundary_src = inspect.getsource(execute_screening_candidate_isolated)
    assert '"screening_phase":' not in boundary_src
