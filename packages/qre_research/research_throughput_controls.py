"""Governed QRE research throughput controls.

This module plans bounded research admission from already-governed hypothesis
prioritization records. It creates no candidates, strategies, campaigns, or
evidence and grants no synthesis, shadow, paper, live, broker, risk, order, or
capital authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from packages.qre_research import hypothesis_generator_governance as governance
from packages.qre_research import rejection_reasons as reasons

ThroughputDecision = Literal["admit", "blocked"]

BLOCKING_REASON_CODES: Final[frozenset[str]] = frozenset(
    {
        reasons.RejectionReasonCode.CAMPAIGN_BUDGET_EXCEEDED.value,
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
class ThroughputBudget:
    candidate_budget: int
    campaign_budget: int
    per_source_budget: int
    per_behavior_family_budget: int
    per_timeframe_budget: int


@dataclass(frozen=True, slots=True)
class ThroughputCandidate:
    proposal: governance.HypothesisProposal
    timeframe: str
    campaign_cost: int = 1
    duplicate_active_path: bool = False
    repeated_failure_mode: bool = False
    data_quality_admitted: bool = True
    architecture_gate_passed: bool = True
    maturity_gate_passed: bool = True
    operator_decision_required: bool = False


@dataclass(frozen=True, slots=True)
class ThroughputAdmissionRecord:
    hypothesis_id: str
    decision: ThroughputDecision
    reason_codes: tuple[str, ...]
    next_action: str
    source_id: str
    behavior_family: str
    timeframe: str
    budget_snapshot: dict[str, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "decision": self.decision,
            "reason_codes": list(self.reason_codes),
            "next_action": self.next_action,
            "source_id": self.source_id,
            "behavior_family": self.behavior_family,
            "timeframe": self.timeframe,
            "budget_snapshot": dict(self.budget_snapshot),
        }


def _next_action(reason_codes: tuple[str, ...]) -> str:
    if reasons.RejectionReasonCode.DATA_QUALITY_FAILED.value in reason_codes:
        return "repair_source_data_quality"
    if reasons.RejectionReasonCode.SOURCE_IDENTITY_UNRESOLVED.value in reason_codes:
        return "resolve_source_identity"
    if reasons.RejectionReasonCode.DUPLICATE_ACTIVE_RESEARCH_PATH.value in reason_codes:
        return "wait_for_active_path_disposition"
    if reasons.RejectionReasonCode.DUPLICATE_HYPOTHESIS.value in reason_codes:
        return "wait_for_changed_condition"
    if reasons.RejectionReasonCode.OPERATOR_DECISION_REQUIRED.value in reason_codes:
        return "request_operator_decision"
    if reasons.RejectionReasonCode.ARCHITECTURE_GATE_FAILED.value in reason_codes:
        return "repair_architecture_registry_or_gate"
    if reasons.RejectionReasonCode.MATURITY_GATE_FAILED.value in reason_codes:
        return "repair_maturity_evidence_or_downgrade_claim"
    if reasons.RejectionReasonCode.CAMPAIGN_BUDGET_EXCEEDED.value in reason_codes:
        return "reduce_scope_or_wait_for_budget"
    if reasons.RejectionReasonCode.POLICY_DENIED.value in reason_codes:
        return "respect_policy_denial"
    return "queue_for_governed_research_review"


def _candidate_reason_codes(
    candidate: ThroughputCandidate,
    prioritization: governance.PrioritizationRecord,
) -> tuple[str, ...]:
    codes = list(prioritization.reason_codes)
    if prioritization.decision != "prioritize":
        codes.extend(prioritization.reason_codes)
    if candidate.duplicate_active_path:
        codes.append(reasons.RejectionReasonCode.DUPLICATE_ACTIVE_RESEARCH_PATH.value)
    if candidate.repeated_failure_mode:
        codes.append(reasons.RejectionReasonCode.DUPLICATE_HYPOTHESIS.value)
    if not candidate.data_quality_admitted:
        codes.append(reasons.RejectionReasonCode.DATA_QUALITY_FAILED.value)
    if not candidate.proposal.source_identity_resolved:
        codes.append(reasons.RejectionReasonCode.SOURCE_IDENTITY_UNRESOLVED.value)
    if candidate.operator_decision_required or candidate.proposal.operator_decision_required:
        codes.append(reasons.RejectionReasonCode.OPERATOR_DECISION_REQUIRED.value)
    if not candidate.architecture_gate_passed or not candidate.proposal.architecture_gate_passed:
        codes.append(reasons.RejectionReasonCode.ARCHITECTURE_GATE_FAILED.value)
    if not candidate.maturity_gate_passed or not candidate.proposal.maturity_gate_passed:
        codes.append(reasons.RejectionReasonCode.MATURITY_GATE_FAILED.value)
    return tuple(dict.fromkeys(codes))


def plan_research_throughput(
    candidates: tuple[ThroughputCandidate, ...],
    *,
    budget: ThroughputBudget,
    rejection_records: tuple[reasons.ReasonRecord, ...] = (),
) -> tuple[ThroughputAdmissionRecord, ...]:
    prioritization = {
        record.hypothesis_id: record
        for record in governance.prioritize_hypotheses(
            tuple(candidate.proposal for candidate in candidates),
            rejection_records=rejection_records,
            candidate_budget=budget.candidate_budget,
        )
    }
    remaining_campaign = budget.campaign_budget
    source_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    timeframe_counts: dict[str, int] = {}
    records: list[ThroughputAdmissionRecord] = []

    for candidate in sorted(
        candidates,
        key=lambda item: (
            -item.proposal.expected_information_gain,
            item.proposal.budget_cost,
            item.proposal.hypothesis_id,
        ),
    ):
        proposal = candidate.proposal
        record = prioritization[proposal.hypothesis_id]
        codes = list(_candidate_reason_codes(candidate, record))
        if candidate.campaign_cost > remaining_campaign:
            codes.append(reasons.RejectionReasonCode.CAMPAIGN_BUDGET_EXCEEDED.value)
        if source_counts.get(proposal.source_id, 0) >= budget.per_source_budget:
            codes.append(reasons.RejectionReasonCode.CAMPAIGN_BUDGET_EXCEEDED.value)
        if family_counts.get(proposal.behavior_family, 0) >= budget.per_behavior_family_budget:
            codes.append(reasons.RejectionReasonCode.CAMPAIGN_BUDGET_EXCEEDED.value)
        if timeframe_counts.get(candidate.timeframe, 0) >= budget.per_timeframe_budget:
            codes.append(reasons.RejectionReasonCode.CAMPAIGN_BUDGET_EXCEEDED.value)

        reason_codes = tuple(dict.fromkeys(codes))
        decision: ThroughputDecision = "blocked" if set(reason_codes) & BLOCKING_REASON_CODES else "admit"
        if decision == "admit":
            remaining_campaign -= candidate.campaign_cost
            source_counts[proposal.source_id] = source_counts.get(proposal.source_id, 0) + 1
            family_counts[proposal.behavior_family] = family_counts.get(proposal.behavior_family, 0) + 1
            timeframe_counts[candidate.timeframe] = timeframe_counts.get(candidate.timeframe, 0) + 1

        records.append(
            ThroughputAdmissionRecord(
                hypothesis_id=proposal.hypothesis_id,
                decision=decision,
                reason_codes=reason_codes,
                next_action=_next_action(reason_codes),
                source_id=proposal.source_id,
                behavior_family=proposal.behavior_family,
                timeframe=candidate.timeframe,
                budget_snapshot={
                    "remaining_campaign_budget": remaining_campaign,
                    "source_used": source_counts.get(proposal.source_id, 0),
                    "behavior_family_used": family_counts.get(proposal.behavior_family, 0),
                    "timeframe_used": timeframe_counts.get(candidate.timeframe, 0),
                },
            )
        )
    return tuple(records)


def throughput_report(
    candidates: tuple[ThroughputCandidate, ...],
    *,
    budget: ThroughputBudget,
    rejection_records: tuple[reasons.ReasonRecord, ...] = (),
) -> dict[str, object]:
    records = plan_research_throughput(candidates, budget=budget, rejection_records=rejection_records)
    admitted = [record for record in records if record.decision == "admit"]
    blocked = [record for record in records if record.decision == "blocked"]
    return {
        "report_kind": "qre_governed_research_throughput",
        "budget": {
            "candidate_budget": budget.candidate_budget,
            "campaign_budget": budget.campaign_budget,
            "per_source_budget": budget.per_source_budget,
            "per_behavior_family_budget": budget.per_behavior_family_budget,
            "per_timeframe_budget": budget.per_timeframe_budget,
        },
        "records": [record.as_dict() for record in records],
        "next_action_queue": [record.as_dict() for record in blocked],
        "summary": {
            "admitted": len(admitted),
            "blocked": len(blocked),
        },
        "safety": {
            "runtime_behavior_changed": False,
            "research_execution": False,
            "created_candidates": False,
            "created_strategies": False,
            "created_campaigns": False,
            "strategy_synthesis_authority": False,
            "shadow_authority": False,
            "paper_authority": False,
            "live_authority": False,
            "broker_authority": False,
            "risk_authority": False,
            "order_authority": False,
            "capital_allocation_authority": False,
        },
    }


__all__ = [
    "BLOCKING_REASON_CODES",
    "ThroughputAdmissionRecord",
    "ThroughputBudget",
    "ThroughputCandidate",
    "plan_research_throughput",
    "throughput_report",
]
