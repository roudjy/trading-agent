"""v3.15.9 — pin two-step stage_result resolution (REV 3 §6.7).

Step 1: base state from screening promotion.
Step 2: downstream override applies ONLY to a screening pass.

Pinned conflicts:
  - rejected + near-pass true   -> near_pass
  - rejected + near-pass false  -> screening_reject
  - rejected + paper_blocked    -> still near_pass / screening_reject
  - pass + needs_investigation  -> needs_investigation
  - pass + promotion_grade      -> promotion_candidate
  - pass + paper_blocked        -> paper_blocked
  - pass alone                  -> screening_pass
  - screening_promoted is None  -> unknown
"""

from __future__ import annotations

from research.screening_evidence import (
    STAGE_RESULT_BASE_NEAR,
    STAGE_RESULT_BASE_PASS,
    STAGE_RESULT_BASE_REJECT,
    STAGE_RESULT_DOWNSTREAM_NEEDS_INV,
    STAGE_RESULT_DOWNSTREAM_PAPER_BLOCK,
    STAGE_RESULT_DOWNSTREAM_PROMOTION,
    STAGE_RESULT_UNKNOWN,
    resolve_stage_result,
)


def test_rejected_with_near_pass_true_is_near_pass() -> None:
    assert resolve_stage_result(
        screening_promoted=False, is_near=True,
        pass_kind=None, promotion_status=None, paper_blocked=False,
    ) == STAGE_RESULT_BASE_NEAR


def test_rejected_without_near_pass_is_screening_reject() -> None:
    assert resolve_stage_result(
        screening_promoted=False, is_near=False,
        pass_kind=None, promotion_status=None, paper_blocked=False,
    ) == STAGE_RESULT_BASE_REJECT


def test_rejected_with_paper_blocked_argument_still_near_pass_or_reject() -> None:
    """Paper-blocked is conceptually invalid on a rejection (it
    only fires after a promotion). The two-step resolver must
    NOT escalate a rejection to paper_blocked even if the input
    is degenerate.
    """
    assert resolve_stage_result(
        screening_promoted=False, is_near=True,
        pass_kind="exploratory", promotion_status="needs_investigation",
        paper_blocked=True,
    ) == STAGE_RESULT_BASE_NEAR
    assert resolve_stage_result(
        screening_promoted=False, is_near=False,
        pass_kind="promotion_grade", promotion_status=None,
        paper_blocked=True,
    ) == STAGE_RESULT_BASE_REJECT


def test_pass_with_needs_investigation_is_needs_investigation() -> None:
    assert resolve_stage_result(
        screening_promoted=True, is_near=False,
        pass_kind="exploratory", promotion_status="needs_investigation",
        paper_blocked=False,
    ) == STAGE_RESULT_DOWNSTREAM_NEEDS_INV


def test_pass_with_promotion_grade_is_promotion_candidate() -> None:
    assert resolve_stage_result(
        screening_promoted=True, is_near=False,
        pass_kind="promotion_grade", promotion_status=None,
        paper_blocked=False,
    ) == STAGE_RESULT_DOWNSTREAM_PROMOTION


def test_pass_with_standard_pass_kind_is_promotion_candidate() -> None:
    assert resolve_stage_result(
        screening_promoted=True, is_near=False,
        pass_kind="standard", promotion_status=None,
        paper_blocked=False,
    ) == STAGE_RESULT_DOWNSTREAM_PROMOTION


def test_pass_with_paper_blocked_is_paper_blocked() -> None:
    """paper_blocked has highest downstream priority on a pass."""
    assert resolve_stage_result(
        screening_promoted=True, is_near=False,
        pass_kind="promotion_grade", promotion_status=None,
        paper_blocked=True,
    ) == STAGE_RESULT_DOWNSTREAM_PAPER_BLOCK


def test_pass_alone_is_screening_pass() -> None:
    assert resolve_stage_result(
        screening_promoted=True, is_near=False,
        pass_kind=None, promotion_status=None, paper_blocked=False,
    ) == STAGE_RESULT_BASE_PASS


def test_unknown_when_promoted_is_none() -> None:
    assert resolve_stage_result(
        screening_promoted=None, is_near=False,
        pass_kind=None, promotion_status=None, paper_blocked=False,
    ) == STAGE_RESULT_UNKNOWN


def test_unknown_does_not_promote_to_paper_blocked() -> None:
    """Even with paper_blocked=True the unknown base must not
    silently flip to paper_blocked.
    """
    assert resolve_stage_result(
        screening_promoted=None, is_near=False,
        pass_kind="promotion_grade", promotion_status=None,
        paper_blocked=True,
    ) == STAGE_RESULT_UNKNOWN
