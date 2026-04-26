"""v3.15.7 — campaign outcome semantics for exploratory-only runs.

Per §10 of the v3.15.7 plan:

- A run with ALL candidates rejected (only exploratory failure
  reason codes) → ``research_rejection``. The reason codes are
  in v3.15.5 SCREENING_REASON_CODES so v3.15.5
  ``_classify_research_rejection`` accepts them.
- A run with only exploratory PASSES → outcome falls through to
  ``completed_no_survivor`` (paper_readiness reports
  ``insufficient_evidence`` because exploratory passes downgrade
  to needs_investigation in promotion).
- A mix of promotion_grade pass + exploratory pass → outcome
  follows the promotion_grade candidate path
  (completed_with_candidates / paper_blocked) — exploratory
  passes are invisible to research_rejection / promotion outcome.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.campaign_launcher import (
    _classify_outcome_from_paper,
    _classify_research_rejection,
)


CID = "col-test-v3-15-7-outcomes"
OTHER_CID = "col-other"


def _write_paper(path: Path, *, status: str, owner: str | None) -> None:
    path.write_text(json.dumps({
        "schema_version": "1.0",
        "status": status,
        "blocking_reasons": [],
        "col_campaign_id": owner,
    }), encoding="utf-8")


def _write_registry(path: Path, *, candidates: list[dict]) -> None:
    path.write_text(json.dumps({
        "version": "v1",
        "candidates": candidates,
        "summary": {"rejected": 0, "needs_investigation": 0,
                    "candidate": 0, "total": len(candidates)},
    }), encoding="utf-8")


# ---- exploratory-only-rejected → research_rejection ----------------------


def test_exploratory_only_rejected_run_classifies_as_research_rejection(tmp_path):
    paper = tmp_path / "paper.json"
    registry = tmp_path / "registry.json"
    _write_paper(paper, status="insufficient_evidence", owner=CID)
    _write_registry(registry, candidates=[
        {
            "strategy_id": "s1",
            "status": "rejected",
            "reasoning": {"failed": ["expectancy_not_positive"], "passed": [],
                          "escalated": []},
        },
        {
            "strategy_id": "s2",
            "status": "rejected",
            "reasoning": {"failed": ["profit_factor_below_floor"], "passed": [],
                          "escalated": []},
        },
    ])
    outcome, reason = _classify_research_rejection(
        paper, registry, expected_campaign_id=CID
    )
    assert outcome == "research_rejection"
    assert reason in {"expectancy_not_positive", "profit_factor_below_floor"}


# ---- exploratory-only-PASSED → completed_no_survivor (via fallback) ------


def test_exploratory_only_passed_run_falls_through_to_completed_no_survivor(tmp_path):
    """When all candidates exploratory-pass and downgrade to
    needs_investigation, paper_readiness sees insufficient_evidence
    and ``_classify_outcome_from_paper`` returns (None, None) →
    launcher fallback is ``completed_no_survivor``.
    """
    paper = tmp_path / "paper.json"
    _write_paper(paper, status="insufficient_evidence", owner=CID)
    outcome, reason = _classify_outcome_from_paper(
        paper, expected_campaign_id=CID
    )
    # Neither completed_with_candidates nor paper_blocked → fall
    # through to completed_no_survivor at the launcher level.
    assert outcome is None
    assert reason is None


def test_research_rejection_does_not_fire_on_needs_investigation_candidates(tmp_path):
    """Sanity: a registry with all candidates ``status=needs_investigation``
    (i.e. exploratory passes) must NOT classify as research_rejection.
    The classifier strictly requires status=='rejected'.
    """
    paper = tmp_path / "paper.json"
    registry = tmp_path / "registry.json"
    _write_paper(paper, status="insufficient_evidence", owner=CID)
    _write_registry(registry, candidates=[
        {
            "strategy_id": "s1",
            "status": "needs_investigation",
            "reasoning": {
                "failed": [], "passed": [],
                "escalated": ["exploratory_pass_requires_promotion_grade_confirmation"],
            },
        },
    ])
    outcome, reason = _classify_research_rejection(
        paper, registry, expected_campaign_id=CID
    )
    assert outcome is None
    assert reason is None


# ---- mixed: promotion_grade pass + exploratory pass ----------------------


def test_mixed_run_with_promotion_grade_candidate_follows_paper_readiness(tmp_path):
    """When at least one candidate reaches the paper readiness path
    via promotion_grade, the outcome is determined by paper readiness,
    not by the exploratory siblings.
    """
    paper = tmp_path / "paper.json"
    _write_paper(paper, status="ready_for_paper_promotion", owner=CID)
    outcome, reason = _classify_outcome_from_paper(
        paper, expected_campaign_id=CID
    )
    assert outcome == "completed_with_candidates"


def test_mixed_run_paper_blocked_path_unchanged(tmp_path):
    paper = tmp_path / "paper.json"
    paper.write_text(json.dumps({
        "schema_version": "1.0",
        "status": "blocked",
        "blocking_reasons": ["malformed_return_stream"],
        "col_campaign_id": CID,
    }), encoding="utf-8")
    outcome, reason = _classify_outcome_from_paper(
        paper, expected_campaign_id=CID
    )
    assert outcome == "paper_blocked"
    assert reason == "malformed_return_stream"


def test_owner_mismatch_still_falls_back_for_v3_15_7(tmp_path):
    """v3.15.4 owner-mismatch invariant unchanged."""
    paper = tmp_path / "paper.json"
    _write_paper(paper, status="ready_for_paper_promotion", owner=OTHER_CID)
    outcome, reason = _classify_outcome_from_paper(
        paper, expected_campaign_id=CID
    )
    assert outcome is None
    assert reason is None
