from __future__ import annotations

from pathlib import Path

import pytest

from research import candidate_lifecycle
from research import qre_candidate_identity_lifecycle as lifecycle_report


def test_qre_identity_is_deterministic() -> None:
    scope = {
        "hypothesis_id": "h1",
        "behavior_id": "b1",
        "preset_id": "p1",
        "timeframe": "1d",
        "universe_or_basket_scope": "basket-a",
    }
    first = candidate_lifecycle.build_qre_candidate_identity(scope)
    second = candidate_lifecycle.build_qre_candidate_identity(scope)

    assert first == second
    assert first["candidate_id"].startswith("qre_cand_")
    assert first["candidate_version"].startswith("qre_v_")


def test_qre_record_fails_closed_for_rejected_or_duplicate_scope() -> None:
    scope = {
        "hypothesis_id": "h1",
        "behavior_id": "b1",
        "preset_id": "p1",
        "timeframe": "1d",
        "universe_or_basket_scope": "basket-a",
    }
    rejected = candidate_lifecycle.build_qre_candidate_record(
        scope,
        context=candidate_lifecycle.QRETransitionContext(rejected_scope=True),
    )
    duplicate = candidate_lifecycle.build_qre_candidate_record(
        scope,
        context=candidate_lifecycle.QRETransitionContext(duplicate_scope=True),
    )

    assert rejected["status"] == "rejected"
    assert "rejected_scope_cannot_become_candidate" in rejected["blockers"]
    assert duplicate["status"] == "suppressed"
    assert "duplicate_scope_blocked" in duplicate["blockers"]


@pytest.mark.parametrize(
    ("from_status", "to_status", "context"),
    [
        (
            candidate_lifecycle.QRECandidateLifecycleStatus.EVIDENCE_INCOMPLETE,
            candidate_lifecycle.QRECandidateLifecycleStatus.EVIDENCE_COMPLETE,
            candidate_lifecycle.QRETransitionContext(
                accepted_lineage_count=1,
                accepted_oos_count=1,
                evidence_complete=True,
            ),
        ),
        (
            candidate_lifecycle.QRECandidateLifecycleStatus.EVIDENCE_COMPLETE,
            candidate_lifecycle.QRECandidateLifecycleStatus.QUALITY_REVIEW,
            candidate_lifecycle.QRETransitionContext(evidence_complete=True),
        ),
        (
            candidate_lifecycle.QRECandidateLifecycleStatus.QUALITY_REVIEW,
            candidate_lifecycle.QRECandidateLifecycleStatus.PROMOTION_REVIEW,
            candidate_lifecycle.QRETransitionContext(quality_gate_passed=True),
        ),
        (
            candidate_lifecycle.QRECandidateLifecycleStatus.PROMOTION_REVIEW,
            candidate_lifecycle.QRECandidateLifecycleStatus.SHADOW_READINESS_CANDIDATE,
            candidate_lifecycle.QRETransitionContext(
                promotion_gate_passed=True,
                readiness_gate_passed=True,
                operator_shadow_authority=True,
            ),
        ),
    ],
)
def test_qre_allowed_transitions(from_status, to_status, context) -> None:
    candidate_lifecycle.validate_qre_transition(from_status, to_status, context=context)


@pytest.mark.parametrize(
    ("from_status", "to_status", "context", "message"),
    [
        (
            candidate_lifecycle.QRECandidateLifecycleStatus.EVIDENCE_INCOMPLETE,
            candidate_lifecycle.QRECandidateLifecycleStatus.EVIDENCE_COMPLETE,
            candidate_lifecycle.QRETransitionContext(),
            "evidence_complete_requires_accepted_evidence",
        ),
        (
            candidate_lifecycle.QRECandidateLifecycleStatus.EVIDENCE_COMPLETE,
            candidate_lifecycle.QRECandidateLifecycleStatus.QUALITY_REVIEW,
            candidate_lifecycle.QRETransitionContext(evidence_complete=False),
            "quality_review_requires_evidence_complete",
        ),
        (
            candidate_lifecycle.QRECandidateLifecycleStatus.QUALITY_REVIEW,
            candidate_lifecycle.QRECandidateLifecycleStatus.PROMOTION_REVIEW,
            candidate_lifecycle.QRETransitionContext(quality_gate_passed=False),
            "promotion_review_requires_quality_gate",
        ),
        (
            candidate_lifecycle.QRECandidateLifecycleStatus.PROMOTION_REVIEW,
            candidate_lifecycle.QRECandidateLifecycleStatus.SHADOW_READINESS_CANDIDATE,
            candidate_lifecycle.QRETransitionContext(promotion_gate_passed=True, readiness_gate_passed=False),
            "shadow_readiness_requires_readiness_gate",
        ),
        (
            candidate_lifecycle.QRECandidateLifecycleStatus.DRAFT,
            candidate_lifecycle.QRECandidateLifecycleStatus.PROMOTION_REVIEW,
            candidate_lifecycle.QRETransitionContext(),
            "is not permitted",
        ),
    ],
)
def test_qre_forbidden_transitions(from_status, to_status, context, message) -> None:
    with pytest.raises(candidate_lifecycle.QREInvalidTransitionError, match=message):
        candidate_lifecycle.validate_qre_transition(from_status, to_status, context=context)


def test_duplicate_scope_detector_raises() -> None:
    scope = {
        "hypothesis_id": "h1",
        "behavior_id": "b1",
        "preset_id": "p1",
        "timeframe": "1d",
        "universe_or_basket_scope": "basket-a",
    }
    record = candidate_lifecycle.build_qre_candidate_record(
        scope,
        context=candidate_lifecycle.QRETransitionContext(),
    )
    with pytest.raises(candidate_lifecycle.QREDuplicateScopeError):
        candidate_lifecycle.assert_unique_qre_scope([record, dict(record)])


def test_qre_candidate_lifecycle_report_is_fail_closed_and_writable(tmp_path: Path) -> None:
    breadth_report = {
        "coverage_matrix": [
            {
                "dimension": "basket",
                "scope_key": "preset_rejected",
                "scope_label": "basket-rejected",
                "accepted_lineage_count": 1,
                "accepted_oos_count": 0,
                "hypothesis_id": "h1",
                "behavior_id": "b1",
                "timeframe": "1d",
            },
            {
                "dimension": "basket",
                "scope_key": "preset_candidate",
                "scope_label": "basket-candidate",
                "accepted_lineage_count": 0,
                "accepted_oos_count": 0,
                "hypothesis_id": "h2",
                "behavior_id": "b2",
                "timeframe": "1d",
            },
        ]
    }
    disposition_memory = {
        "record": {
            "preset_id": "preset_rejected",
            "disposition_scope": {"preset_id": "preset_rejected"},
        }
    }
    closure_report = {"evidence_complete_count": 0}

    report = lifecycle_report.build_qre_candidate_identity_lifecycle(
        breadth_report=breadth_report,
        disposition_memory=disposition_memory,
        closure_report=closure_report,
    )
    paths = lifecycle_report.write_outputs(report, repo_root=tmp_path)

    assert report["summary"]["candidate_count"] == 2
    assert report["summary"]["suppressed_count"] + report["summary"]["rejected_count"] >= 1
    assert all(row["authority"]["can_promote_candidate"] is False for row in report["rows"])
    assert paths["latest"] == "logs/qre_candidate_identity_lifecycle/latest.json"
    source = Path("research/qre_candidate_identity_lifecycle.py").read_text(encoding="utf-8")
    assert "AAPL" not in source
    assert "NVDA" not in source
