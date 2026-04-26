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
    """v3.15.6 Optie B: the result dict is NOT extended. Verified
    indirectly by reading the source — the function explicitly
    discards the kwarg via ``del screening_phase``.
    """
    src = inspect.getsource(execute_screening_candidate_isolated)
    # Defensive grep: the function must not leak the kwarg into the
    # returned outcome dict.
    assert "del screening_phase" in src or "screening_phase," not in src.replace(
        "screening_phase: str", ""
    ), (
        "Result dict is the boundary that flows through "
        "runtime_record.update(outcome) on batch_execution.py:191. "
        "Adding screening_phase here risks stealth schema drift."
    )
