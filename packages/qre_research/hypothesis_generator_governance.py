"""Governed QRE hypothesis prioritization.

This module orders synthetic hypothesis proposals through memory, rejection,
quality, budget, architecture, and maturity constraints. It does not generate
production hypotheses, increase throughput, or grant execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from packages.qre_research import rejection_reasons as reasons

BLOCKING_REASON_CODES: Final[frozenset[str]] = frozenset(
    {
        reasons.RejectionReasonCode.DATA_QUALITY_FAILED.value,
        reasons.RejectionReasonCode.SOURCE_IDENTITY_UNRESOLVED.value,
        reasons.RejectionReasonCode.DUPLICATE_HYPOTHESIS.value,
        reasons.RejectionReasonCode.DUPLICATE_ACTIVE_RESEARCH_PATH.value,
        reasons.RejectionReasonCode.MATURITY_GATE_FAILED.value,
        reasons.RejectionReasonCode.ARCHITECTURE_GATE_FAILED.value,
        reasons.RejectionReasonCode.OPERATOR_DECISION_REQUIRED.value,
        reasons.RejectionReasonCode.POLICY_DENIED.value,
    }
)


@dataclass(frozen=True, slots=True)
class HypothesisProposal:
    hypothesis_id: str
    mechanism: str
    source_id: str
    behavior_family: str
    expected_information_gain: float
    data_quality_ready: bool = True
    source_identity_resolved: bool = True
    budget_cost: int = 1
    operator_decision_required: bool = False
    architecture_gate_passed: bool = True
    maturity_gate_passed: bool = True


@dataclass(frozen=True, slots=True)
class PrioritizationRecord:
    hypothesis_id: str
    decision: str
    priority_score: float
    reason_codes: tuple[str, ...]
    rationale: str
    next_action: str

    def as_dict(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "decision": self.decision,
            "priority_score": self.priority_score,
            "reason_codes": list(self.reason_codes),
            "rationale": self.rationale,
            "next_action": self.next_action,
        }


def _memory_reason_codes(
    proposal: HypothesisProposal,
    rejection_records: tuple[reasons.ReasonRecord, ...],
) -> tuple[str, ...]:
    return tuple(
        record.code
        for record in rejection_records
        if record.object_id == proposal.hypothesis_id
    )


def _proposal_reason_codes(
    proposal: HypothesisProposal,
    rejection_records: tuple[reasons.ReasonRecord, ...],
) -> tuple[str, ...]:
    codes: list[str] = []
    if not proposal.data_quality_ready:
        codes.append(reasons.RejectionReasonCode.DATA_QUALITY_FAILED.value)
    if not proposal.source_identity_resolved:
        codes.append(reasons.RejectionReasonCode.SOURCE_IDENTITY_UNRESOLVED.value)
    if proposal.operator_decision_required:
        codes.append(reasons.RejectionReasonCode.OPERATOR_DECISION_REQUIRED.value)
    if not proposal.architecture_gate_passed:
        codes.append(reasons.RejectionReasonCode.ARCHITECTURE_GATE_FAILED.value)
    if not proposal.maturity_gate_passed:
        codes.append(reasons.RejectionReasonCode.MATURITY_GATE_FAILED.value)
    codes.extend(_memory_reason_codes(proposal, rejection_records))
    return tuple(dict.fromkeys(codes))


def _next_action(reason_codes: tuple[str, ...]) -> str:
    if reasons.RejectionReasonCode.DATA_QUALITY_FAILED.value in reason_codes:
        return "repair_source_data_quality"
    if reasons.RejectionReasonCode.SOURCE_IDENTITY_UNRESOLVED.value in reason_codes:
        return "resolve_source_identity"
    if reasons.RejectionReasonCode.OPERATOR_DECISION_REQUIRED.value in reason_codes:
        return "request_operator_decision"
    if reasons.RejectionReasonCode.ARCHITECTURE_GATE_FAILED.value in reason_codes:
        return "repair_architecture_registry_or_gate"
    if reasons.RejectionReasonCode.MATURITY_GATE_FAILED.value in reason_codes:
        return "repair_maturity_evidence_or_downgrade_claim"
    if reasons.RejectionReasonCode.DUPLICATE_HYPOTHESIS.value in reason_codes:
        return "wait_for_changed_condition"
    if reasons.RejectionReasonCode.DUPLICATE_ACTIVE_RESEARCH_PATH.value in reason_codes:
        return "wait_for_active_path_disposition"
    if reason_codes:
        return "collect_missing_evidence_or_update_memory"
    return "eligible_for_governed_queue"


def prioritize_hypotheses(
    proposals: tuple[HypothesisProposal, ...],
    *,
    rejection_records: tuple[reasons.ReasonRecord, ...] = (),
    candidate_budget: int,
) -> tuple[PrioritizationRecord, ...]:
    remaining_budget = candidate_budget
    records: list[PrioritizationRecord] = []
    for proposal in sorted(
        proposals,
        key=lambda item: (-item.expected_information_gain, item.budget_cost, item.hypothesis_id),
    ):
        reason_codes = _proposal_reason_codes(proposal, rejection_records)
        blocked = bool(set(reason_codes) & BLOCKING_REASON_CODES)
        over_budget = proposal.budget_cost > remaining_budget
        if over_budget:
            reason_codes = (*reason_codes, reasons.RejectionReasonCode.CAMPAIGN_BUDGET_EXCEEDED.value)
        decision = "blocked" if blocked or over_budget else "prioritize"
        if decision == "prioritize":
            remaining_budget -= proposal.budget_cost
        penalty = len(reason_codes) * 10.0
        score = proposal.expected_information_gain - penalty
        records.append(
            PrioritizationRecord(
                hypothesis_id=proposal.hypothesis_id,
                decision=decision,
                priority_score=score,
                reason_codes=reason_codes,
                rationale=(
                    "eligible: governed inputs and memory allow prioritization"
                    if decision == "prioritize"
                    else "blocked: governed inputs require next action before prioritization"
                ),
                next_action=_next_action(reason_codes),
            )
        )
    return tuple(records)


def prioritization_report(
    proposals: tuple[HypothesisProposal, ...],
    *,
    rejection_records: tuple[reasons.ReasonRecord, ...] = (),
    candidate_budget: int,
) -> dict[str, object]:
    records = prioritize_hypotheses(
        proposals,
        rejection_records=rejection_records,
        candidate_budget=candidate_budget,
    )
    return {
        "report_kind": "qre_hypothesis_generator_governance",
        "candidate_budget": candidate_budget,
        "records": [record.as_dict() for record in records],
        "summary": {
            "prioritized": sum(1 for record in records if record.decision == "prioritize"),
            "blocked": sum(1 for record in records if record.decision == "blocked"),
        },
        "safety": {
            "throughput_increased": False,
            "runtime_behavior_changed": False,
            "strategy_synthesis_authority": False,
            "shadow_authority": False,
            "paper_authority": False,
            "live_authority": False,
        },
    }


__all__ = [
    "BLOCKING_REASON_CODES",
    "HypothesisProposal",
    "PrioritizationRecord",
    "prioritization_report",
    "prioritize_hypotheses",
]
