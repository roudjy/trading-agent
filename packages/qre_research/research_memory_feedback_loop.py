"""Governed offline evidence-to-memory feedback loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from packages.qre_research import hypothesis_generator_governance as governance
from packages.qre_research import multiwindow_evidence_closure as closure
from packages.qre_research import rejection_reasons as reasons

FeedbackDecision = Literal["prioritize", "next_action_required", "suppressed", "blocked"]

HARD_BLOCKERS = {
    reasons.RejectionReasonCode.DATA_QUALITY_FAILED.value,
    reasons.RejectionReasonCode.SOURCE_IDENTITY_UNRESOLVED.value,
    reasons.RejectionReasonCode.ARCHITECTURE_GATE_FAILED.value,
    reasons.RejectionReasonCode.MATURITY_GATE_FAILED.value,
    reasons.RejectionReasonCode.OPERATOR_DECISION_REQUIRED.value,
    reasons.RejectionReasonCode.POLICY_DENIED.value,
}


@dataclass(frozen=True, slots=True)
class MemoryFeedbackRecord:
    hypothesis_id: str
    decision: FeedbackDecision
    priority_score: float
    reason_codes: tuple[str, ...]
    rationale: str
    next_action: str
    suppress_if_unchanged: bool
    changed_condition_applied: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "decision": self.decision,
            "priority_score": self.priority_score,
            "reason_codes": list(self.reason_codes),
            "rationale": self.rationale,
            "next_action": self.next_action,
            "suppress_if_unchanged": self.suppress_if_unchanged,
            "changed_condition_applied": self.changed_condition_applied,
        }


@dataclass(frozen=True, slots=True)
class ResearchMemoryFeedbackLoop:
    records: tuple[MemoryFeedbackRecord, ...]
    do_not_retest: tuple[str, ...]
    next_action_queue: tuple[dict[str, object], ...]
    prioritization_records: tuple[dict[str, object], ...]
    safety: dict[str, bool]

    def as_dict(self) -> dict[str, object]:
        return {
            "records": [record.as_dict() for record in self.records],
            "do_not_retest": list(self.do_not_retest),
            "next_action_queue": list(self.next_action_queue),
            "prioritization_records": list(self.prioritization_records),
            "safety": dict(self.safety),
        }


def _records_from_artifacts(artifact_envelopes: tuple[dict[str, object], ...]) -> tuple[reasons.ReasonRecord, ...]:
    records: list[reasons.ReasonRecord] = []
    for envelope in artifact_envelopes:
        for payload in envelope.get("rejection_reasons", ()):
            if isinstance(payload, dict):
                records.append(
                    reasons.make_reason_record(
                        code=str(payload["code"]),
                        stage=str(payload["stage"]),
                        object_id=str(payload["object_id"]),
                        explanation=str(payload["explanation"]),
                        next_action=str(payload["next_action"]),
                        severity=str(payload.get("severity", "blocking")),  # type: ignore[arg-type]
                        terminal=bool(payload.get("terminal", False)),
                    )
                )
    return tuple(records)


def _records_from_closures(
    closures: tuple[closure.MultiwindowEvidenceClosure, ...],
) -> tuple[reasons.ReasonRecord, ...]:
    return tuple(record for item in closures for record in item.reason_records)


def _changed(hypothesis_id: str, codes: tuple[str, ...], changed_conditions: frozenset[str]) -> bool:
    if hypothesis_id in changed_conditions:
        return True
    return any(code in changed_conditions or f"{hypothesis_id}:{code}" in changed_conditions for code in codes)


def _next_action(codes: tuple[str, ...]) -> str:
    if reasons.RejectionReasonCode.DATA_QUALITY_FAILED.value in codes:
        return "repair_source_data_quality"
    if reasons.RejectionReasonCode.SOURCE_IDENTITY_UNRESOLVED.value in codes:
        return "resolve_source_identity"
    if reasons.RejectionReasonCode.ARCHITECTURE_GATE_FAILED.value in codes:
        return "repair_architecture_gate"
    if reasons.RejectionReasonCode.MATURITY_GATE_FAILED.value in codes:
        return "repair_maturity_gate"
    if reasons.RejectionReasonCode.OPERATOR_DECISION_REQUIRED.value in codes:
        return "request_operator_decision"
    if any(reasons.reason_polarity(code) == "missing_evidence" for code in codes):
        return "collect_missing_evidence"
    if any(reasons.reason_polarity(code) == "negative_evidence" for code in codes):
        return "do_not_retest_unless_conditions_change"
    return "eligible_for_governed_prioritization"


def build_research_memory_feedback_loop(
    proposals: tuple[governance.HypothesisProposal, ...],
    *,
    closures: tuple[closure.MultiwindowEvidenceClosure, ...] = (),
    artifact_envelopes: tuple[dict[str, object], ...] = (),
    changed_conditions: tuple[str, ...] = (),
) -> ResearchMemoryFeedbackLoop:
    memory_records = (
        *_records_from_closures(closures),
        *_records_from_artifacts(artifact_envelopes),
    )
    changed_set = frozenset(changed_conditions)
    by_hypothesis: dict[str, list[str]] = {proposal.hypothesis_id: [] for proposal in proposals}
    for record in memory_records:
        for proposal in proposals:
            if record.object_id in {proposal.hypothesis_id, proposal.source_id} or record.object_id.startswith("closure-"):
                by_hypothesis[proposal.hypothesis_id].append(record.code)

    feedback: list[MemoryFeedbackRecord] = []
    for proposal in sorted(proposals, key=lambda item: (-item.expected_information_gain, item.hypothesis_id)):
        codes = tuple(dict.fromkeys(by_hypothesis.get(proposal.hypothesis_id, ())))
        changed = _changed(proposal.hypothesis_id, codes, changed_set)
        has_negative = any(reasons.reason_polarity(code) == "negative_evidence" for code in codes)
        has_missing = any(reasons.reason_polarity(code) == "missing_evidence" for code in codes)
        hard_blocked = bool(set(codes) & HARD_BLOCKERS) or not proposal.architecture_gate_passed or not proposal.maturity_gate_passed
        suppress = has_negative and not changed
        if hard_blocked:
            decision: FeedbackDecision = "blocked"
            rationale = "blocked: source/data, architecture, maturity, policy, or operator constraints remain unresolved"
        elif suppress:
            decision = "suppressed"
            rationale = "suppressed: negative evidence should not be retested without changed conditions"
        elif has_missing and not changed:
            decision = "next_action_required"
            rationale = "next_action_required: missing evidence must be collected before prioritization"
        else:
            decision = "prioritize"
            rationale = "prioritize: governed memory allows reconsideration"
        penalty = 25.0 if suppress else 10.0 * len(codes)
        if changed:
            penalty = penalty / 2
        feedback.append(
            MemoryFeedbackRecord(
                hypothesis_id=proposal.hypothesis_id,
                decision=decision,
                priority_score=proposal.expected_information_gain - penalty,
                reason_codes=codes,
                rationale=rationale,
                next_action=_next_action(codes),
                suppress_if_unchanged=suppress,
                changed_condition_applied=changed,
            )
        )

    do_not_retest = tuple(record.hypothesis_id for record in feedback if record.decision == "suppressed")
    next_actions = tuple(
        {
            "hypothesis_id": record.hypothesis_id,
            "reason_codes": list(record.reason_codes),
            "next_action": record.next_action,
        }
        for record in feedback
        if record.decision in {"blocked", "next_action_required", "suppressed"}
    )
    return ResearchMemoryFeedbackLoop(
        records=tuple(feedback),
        do_not_retest=do_not_retest,
        next_action_queue=next_actions,
        prioritization_records=tuple(record.as_dict() for record in feedback),
        safety={
            "offline_only": True,
            "runtime_behavior_changed": False,
            "created_production_artifacts": False,
            "strategy_synthesis_authority": False,
            "shadow_authority": False,
            "paper_authority": False,
            "live_authority": False,
            "broker_authority": False,
            "risk_authority": False,
            "order_authority": False,
            "capital_allocation_authority": False,
        },
    )


__all__ = [
    "MemoryFeedbackRecord",
    "ResearchMemoryFeedbackLoop",
    "build_research_memory_feedback_loop",
]
