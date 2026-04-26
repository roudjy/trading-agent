"""v3.15.6 — v3.15.7 compatibility seam.

Pins the contract that v3.15.7 will rely on when it adds phase-
aware criteria dispatch:

- ``execute_screening_candidate_isolated`` accepts
  ``screening_phase`` as a keyword-only parameter.
- The annotation is ``str | None`` (NOT Literal) so v3.15.7 can
  extend the vocabulary without breaking the API.
- Both the four valid values (``"exploratory"``, ``"standard"``,
  ``"promotion_grade"``, plus ``None``) bind cleanly via
  ``inspect.Signature.bind_partial``.
- The screening_process module exposes the function in its public
  surface (importable by name).
"""

from __future__ import annotations

import inspect

import pytest

import research.screening_process as screening_process
from research.screening_process import execute_screening_candidate_isolated


def test_execute_screening_candidate_isolated_is_publicly_importable():
    assert hasattr(screening_process, "execute_screening_candidate_isolated")


def test_signature_has_screening_phase_keyword_only_parameter():
    sig = inspect.signature(execute_screening_candidate_isolated)
    assert "screening_phase" in sig.parameters
    p = sig.parameters["screening_phase"]
    assert p.kind == inspect.Parameter.KEYWORD_ONLY
    assert p.default is None


def test_signature_annotation_is_open_for_v3_15_7():
    """v3.15.7 may add new phase values. The boundary kwarg must
    NOT be a Literal so an additive vocab change does not break
    the API.
    """
    sig = inspect.signature(execute_screening_candidate_isolated)
    annotation = sig.parameters["screening_phase"].annotation
    annotation_str = str(annotation)
    assert "str" in annotation_str
    assert "None" in annotation_str
    assert "Literal" not in annotation_str


@pytest.mark.parametrize(
    "phase",
    ["exploratory", "standard", "promotion_grade", None],
)
def test_all_three_phases_plus_none_bind_cleanly(phase):
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


def test_kwarg_position_is_after_history_root_for_minimal_diff():
    """Pin that the new kwarg lives near the end of the signature so
    historical positional/test consumers stay compatible with the
    same kw-only ordering they had before v3.15.6.
    """
    sig = inspect.signature(execute_screening_candidate_isolated)
    names = list(sig.parameters.keys())
    assert names.index("history_root") < names.index("screening_phase"), (
        "screening_phase should be appended after history_root for stable "
        "kwarg ordering."
    )
