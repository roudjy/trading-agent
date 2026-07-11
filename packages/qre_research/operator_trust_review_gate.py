"""Operator trust review gate for governed offline QRE evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from packages.qre_research import multiwindow_evidence_closure as closure
from packages.qre_research import rejection_reasons as reasons
from packages.qre_research import research_memory_feedback_loop as memory


class ReviewDecision(StrEnum):
    ELIGIBLE_FOR_MORE_OFFLINE_RESEARCH = "ELIGIBLE_FOR_MORE_OFFLINE_RESEARCH"
    BLOCKED_DATA_NOT_ADMITTED = "BLOCKED_DATA_NOT_ADMITTED"
    BLOCKED_SOURCE_NOT_APPROVED = "BLOCKED_SOURCE_NOT_APPROVED"
    BLOCKED_MISSING_EVIDENCE = "BLOCKED_MISSING_EVIDENCE"
    REJECTED_NEGATIVE_EVIDENCE = "REJECTED_NEGATIVE_EVIDENCE"
    REJECTED_COST_MODEL = "REJECTED_COST_MODEL"
    REJECTED_NULL_MODEL = "REJECTED_NULL_MODEL"
    REJECTED_INSUFFICIENT_TRADES = "REJECTED_INSUFFICIENT_TRADES"
    BLOCKED_ARCHITECTURE_GATE = "BLOCKED_ARCHITECTURE_GATE"
    BLOCKED_MATURITY_GATE = "BLOCKED_MATURITY_GATE"
    BLOCKED_OPERATOR_DECISION = "BLOCKED_OPERATOR_DECISION"
    DO_NOT_RETEST_UNLESS_CONDITIONS_CHANGE = "DO_NOT_RETEST_UNLESS_CONDITIONS_CHANGE"


@dataclass(frozen=True, slots=True)
class OperatorTrustReview:
    review_id: str
    inputs_reviewed: tuple[str, ...]
    evidence_summary: dict[str, object]
    rejection_reason_summary: dict[str, int]
    memory_feedback_summary: dict[str, object]
    next_action: str
    do_not_retest: tuple[str, ...]
    offline_eligibility_decision: ReviewDecision
    authority: dict[str, bool]
    operator_explanation: str
    machine_payload: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "review_id": self.review_id,
            "inputs_reviewed": list(self.inputs_reviewed),
            "evidence_summary": dict(self.evidence_summary),
            "rejection_reason_summary": dict(self.rejection_reason_summary),
            "memory_feedback_summary": dict(self.memory_feedback_summary),
            "next_action": self.next_action,
            "do_not_retest": list(self.do_not_retest),
            "offline_eligibility_decision": self.offline_eligibility_decision.value,
            "authority": dict(self.authority),
            "operator_explanation": self.operator_explanation,
            "machine_payload": dict(self.machine_payload),
        }


def _authority() -> dict[str, bool]:
    return {
        "eligible_for_shadow": False,
        "eligible_for_paper": False,
        "eligible_for_live": False,
        "broker_authority": False,
        "risk_authority": False,
        "order_authority": False,
        "capital_allocation_authority": False,
        "strategy_synthesis_authority": False,
    }


def _reason_distribution(closures: tuple[closure.MultiwindowEvidenceClosure, ...]) -> dict[str, int]:
    distribution: dict[str, int] = {}
    for item in closures:
        for record in item.reason_records:
            distribution[record.code] = distribution.get(record.code, 0) + 1
    return distribution


def _decision(reason_counts: dict[str, int], feedback: memory.ResearchMemoryFeedbackLoop) -> ReviewDecision:
    if reason_counts.get(reasons.RejectionReasonCode.ARCHITECTURE_GATE_FAILED.value):
        return ReviewDecision.BLOCKED_ARCHITECTURE_GATE
    if reason_counts.get(reasons.RejectionReasonCode.MATURITY_GATE_FAILED.value):
        return ReviewDecision.BLOCKED_MATURITY_GATE
    if reason_counts.get(reasons.RejectionReasonCode.OPERATOR_DECISION_REQUIRED.value):
        return ReviewDecision.BLOCKED_OPERATOR_DECISION
    if reason_counts.get(reasons.RejectionReasonCode.SOURCE_IDENTITY_UNRESOLVED.value):
        return ReviewDecision.BLOCKED_SOURCE_NOT_APPROVED
    if reason_counts.get(reasons.RejectionReasonCode.DATA_QUALITY_FAILED.value):
        return ReviewDecision.BLOCKED_DATA_NOT_ADMITTED
    if reason_counts.get(reasons.RejectionReasonCode.COST_MODEL_FAILED.value):
        return ReviewDecision.REJECTED_COST_MODEL
    if reason_counts.get(reasons.RejectionReasonCode.NULL_MODEL_NOT_BEATEN.value):
        return ReviewDecision.REJECTED_NULL_MODEL
    if reason_counts.get(reasons.RejectionReasonCode.INSUFFICIENT_TRADES.value):
        return ReviewDecision.REJECTED_INSUFFICIENT_TRADES
    if feedback.do_not_retest:
        return ReviewDecision.DO_NOT_RETEST_UNLESS_CONDITIONS_CHANGE
    if any(reasons.reason_polarity(code) == "negative_evidence" for code in reason_counts):
        return ReviewDecision.REJECTED_NEGATIVE_EVIDENCE
    if any(reasons.reason_polarity(code) == "missing_evidence" for code in reason_counts):
        return ReviewDecision.BLOCKED_MISSING_EVIDENCE
    return ReviewDecision.ELIGIBLE_FOR_MORE_OFFLINE_RESEARCH


def _next_action(decision: ReviewDecision) -> str:
    return {
        ReviewDecision.ELIGIBLE_FOR_MORE_OFFLINE_RESEARCH: "queue_more_governed_offline_research",
        ReviewDecision.BLOCKED_DATA_NOT_ADMITTED: "repair_or_replace_offline_dataset",
        ReviewDecision.BLOCKED_SOURCE_NOT_APPROVED: "approve_or_replace_offline_source",
        ReviewDecision.BLOCKED_MISSING_EVIDENCE: "collect_missing_evidence",
        ReviewDecision.REJECTED_NEGATIVE_EVIDENCE: "do_not_retest_without_changed_conditions",
        ReviewDecision.REJECTED_COST_MODEL: "review_cost_model_failure",
        ReviewDecision.REJECTED_NULL_MODEL: "review_null_model_failure",
        ReviewDecision.REJECTED_INSUFFICIENT_TRADES: "collect_more_trades_or_stop",
        ReviewDecision.BLOCKED_ARCHITECTURE_GATE: "repair_architecture_gate",
        ReviewDecision.BLOCKED_MATURITY_GATE: "repair_maturity_gate",
        ReviewDecision.BLOCKED_OPERATOR_DECISION: "request_operator_decision",
        ReviewDecision.DO_NOT_RETEST_UNLESS_CONDITIONS_CHANGE: "wait_for_changed_conditions",
    }[decision]


def build_operator_trust_review(
    *,
    review_id: str,
    closures: tuple[closure.MultiwindowEvidenceClosure, ...],
    feedback_loop: memory.ResearchMemoryFeedbackLoop,
) -> OperatorTrustReview:
    reason_counts = _reason_distribution(closures)
    decision = _decision(reason_counts, feedback_loop)
    evidence_windows = [
        window.as_dict()
        for item in closures
        for window in item.evidence_windows
    ]
    evidence_summary = {
        "closure_count": len(closures),
        "evidence_complete_count": sum(1 for item in closures if item.evidence_complete),
        "window_statuses": evidence_windows,
        "missing_reason_codes": sorted(code for code in reason_counts if reasons.reason_polarity(code) == "missing_evidence"),
        "negative_reason_codes": sorted(code for code in reason_counts if reasons.reason_polarity(code) == "negative_evidence"),
    }
    payload = {
        "decision": decision.value,
        "next_action": _next_action(decision),
        "eligible_for_more_offline_research": decision == ReviewDecision.ELIGIBLE_FOR_MORE_OFFLINE_RESEARCH,
        "eligible_for_shadow": False,
        "eligible_for_paper": False,
        "eligible_for_live": False,
    }
    return OperatorTrustReview(
        review_id=review_id,
        inputs_reviewed=tuple(item.closure_id for item in closures),
        evidence_summary=evidence_summary,
        rejection_reason_summary=reason_counts,
        memory_feedback_summary={
            "record_count": len(feedback_loop.records),
            "do_not_retest_count": len(feedback_loop.do_not_retest),
            "next_action_count": len(feedback_loop.next_action_queue),
        },
        next_action=_next_action(decision),
        do_not_retest=feedback_loop.do_not_retest,
        offline_eligibility_decision=decision,
        authority=_authority(),
        operator_explanation=f"{decision.value}: {_next_action(decision)}.",
        machine_payload=payload,
    )


__all__ = [
    "OperatorTrustReview",
    "ReviewDecision",
    "build_operator_trust_review",
]
