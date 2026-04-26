"""v3.15.7 — classify_candidate pass_kind guard."""

from __future__ import annotations

from typing import Any

import pytest

from research.promotion import (
    STATUS_CANDIDATE,
    STATUS_NEEDS_INVESTIGATION,
    STATUS_REJECTED,
    classify_candidate,
    normalize_promotion_config,
)


def _good_oos() -> dict[str, Any]:
    # Mirrors tests/unit/test_candidate_promotion.py::_good_oos.
    return {
        "totaal_trades": 80,
        "sharpe": 1.5,
        "max_drawdown": 0.15,
    }


def _good_defensibility() -> dict[str, Any]:
    return {
        "psr": 0.95,
        "dsr_canonical": 0.5,
        "bootstrap_sharpe_ci_lower": 0.1,
        "noise_warning_fired": False,
    }


def test_positional_4_arg_call_still_works():
    """Backward compat: existing positional 4-arg call sites work."""
    status, _ = classify_candidate(
        _good_oos(), True, _good_defensibility(), normalize_promotion_config(None)
    )
    assert status in (STATUS_CANDIDATE, STATUS_NEEDS_INVESTIGATION, STATUS_REJECTED)


def test_pass_kind_none_byte_identical_to_pre_v3_15_7():
    status_none, reasoning_none = classify_candidate(
        _good_oos(), True, _good_defensibility(), normalize_promotion_config(None),
        pass_kind=None,
    )
    status_legacy, reasoning_legacy = classify_candidate(
        _good_oos(), True, _good_defensibility(), normalize_promotion_config(None),
    )
    assert status_none == status_legacy
    assert reasoning_none == reasoning_legacy


@pytest.mark.parametrize("pass_kind", ["standard", "promotion_grade"])
def test_legacy_pass_kinds_byte_identical(pass_kind):
    status_with, reasoning_with = classify_candidate(
        _good_oos(), True, _good_defensibility(), normalize_promotion_config(None),
        pass_kind=pass_kind,
    )
    status_without, reasoning_without = classify_candidate(
        _good_oos(), True, _good_defensibility(), normalize_promotion_config(None),
    )
    assert status_with == status_without
    assert reasoning_with == reasoning_without


def test_pass_kind_exploratory_returns_needs_investigation():
    status, reasoning = classify_candidate(
        _good_oos(),  # would pass legacy clean
        True,
        _good_defensibility(),
        normalize_promotion_config(None),
        pass_kind="exploratory",
    )
    assert status == STATUS_NEEDS_INVESTIGATION
    assert reasoning == {
        "passed": [],
        "failed": [],
        "escalated": ["exploratory_pass_requires_promotion_grade_confirmation"],
    }


def test_pass_kind_exploratory_short_circuits_legacy_rejection_rules():
    """Even a legacy-rejected oos_summary becomes
    needs_investigation under exploratory pass_kind. The exploratory
    branch fires before any rejection rule runs.
    """
    bad_oos = {"totaal_trades": 5, "sharpe": -1.0, "max_drawdown": 0.99}
    status, reasoning = classify_candidate(
        bad_oos, True, None, normalize_promotion_config(None),
        pass_kind="exploratory",
    )
    assert status == STATUS_NEEDS_INVESTIGATION
    # Single escalated reason; failed list is empty.
    assert reasoning["failed"] == []
    assert reasoning["escalated"] == [
        "exploratory_pass_requires_promotion_grade_confirmation"
    ]


def test_unknown_pass_kind_does_not_short_circuit():
    """Defensive: a future pass_kind value falls through to legacy
    classification; preset validation catches typos upstream.
    """
    status_unknown, _ = classify_candidate(
        _good_oos(), True, _good_defensibility(), normalize_promotion_config(None),
        pass_kind="future_kind",
    )
    status_none, _ = classify_candidate(
        _good_oos(), True, _good_defensibility(), normalize_promotion_config(None),
        pass_kind=None,
    )
    assert status_unknown == status_none
