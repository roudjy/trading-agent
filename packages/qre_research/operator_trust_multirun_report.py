"""Operator trust report over governed offline QRE runs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from packages.qre_research import evidence_memory_accumulation as accumulation

GOVERNANCE_BLOCKERS = {
    "architecture_gate_failed",
    "maturity_gate_failed",
    "operator_decision_required",
    "policy_denied",
}


@dataclass(frozen=True, slots=True)
class OperatorTrustMultirunReport:
    tested_hypotheses: tuple[str, ...]
    admitted_count: int
    blocked_count: int
    rejection_reason_distribution: dict[str, int]
    evidence_completeness: dict[str, int]
    missing_vs_negative_evidence: dict[str, tuple[str, ...]]
    disposition_summary: dict[str, int]
    memory_feedback_summary: dict[str, int]
    repeated_failure_modes: tuple[str, ...]
    gate_blockers: dict[str, int]
    operator_decision_blockers: int
    next_action_queue: tuple[dict[str, object], ...]
    do_not_retest: tuple[str, ...]
    worth_testing_next: tuple[str, ...]
    authority_statement: dict[str, bool]

    def as_dict(self) -> dict[str, object]:
        return {
            "tested_hypotheses": list(self.tested_hypotheses),
            "admitted_count": self.admitted_count,
            "blocked_count": self.blocked_count,
            "rejection_reason_distribution": dict(self.rejection_reason_distribution),
            "evidence_completeness": dict(self.evidence_completeness),
            "missing_vs_negative_evidence": {
                key: list(value) for key, value in self.missing_vs_negative_evidence.items()
            },
            "disposition_summary": dict(self.disposition_summary),
            "memory_feedback_summary": dict(self.memory_feedback_summary),
            "repeated_failure_modes": list(self.repeated_failure_modes),
            "gate_blockers": dict(self.gate_blockers),
            "operator_decision_blockers": self.operator_decision_blockers,
            "next_action_queue": list(self.next_action_queue),
            "do_not_retest": list(self.do_not_retest),
            "worth_testing_next": list(self.worth_testing_next),
            "authority_statement": dict(self.authority_statement),
        }


def build_operator_trust_multirun_report(
    accumulated: accumulation.EvidenceMemoryAccumulation,
) -> OperatorTrustMultirunReport:
    gate_blockers = {
        code: count
        for code, count in accumulated.reason_distribution.items()
        if code in GOVERNANCE_BLOCKERS
    }
    admitted_count = accumulated.disposition_trends.get("accepted_for_research_memory", 0)
    blocked_count = sum(1 for item in accumulated.next_action_queue if item.get("reason_codes"))
    memory_codes = [
        str(record["research_memory"]["canonical_reason_code"])
        for record in accumulated.memory_feedback_records
        if "research_memory" in record
    ]
    worth_testing_next = tuple(
        hypothesis_id
        for hypothesis_id in accumulated.tested_hypotheses
        if hypothesis_id not in accumulated.suppress_retest
    )
    return OperatorTrustMultirunReport(
        tested_hypotheses=accumulated.tested_hypotheses,
        admitted_count=admitted_count,
        blocked_count=blocked_count,
        rejection_reason_distribution=accumulated.reason_distribution,
        evidence_completeness={
            "complete": admitted_count,
            "incomplete_or_blocked": blocked_count,
        },
        missing_vs_negative_evidence={
            "missing": accumulated.missing_evidence_reasons,
            "negative": accumulated.negative_evidence_reasons,
        },
        disposition_summary=accumulated.disposition_trends,
        memory_feedback_summary=dict(Counter(memory_codes)),
        repeated_failure_modes=accumulated.repeated_failure_modes,
        gate_blockers=gate_blockers,
        operator_decision_blockers=accumulated.reason_distribution.get("operator_decision_required", 0),
        next_action_queue=accumulated.next_action_queue,
        do_not_retest=accumulated.suppress_retest,
        worth_testing_next=worth_testing_next,
        authority_statement={
            "strategy_synthesis_execution_authority": False,
            "shadow_authority": False,
            "paper_authority": False,
            "live_authority": False,
            "broker_authority": False,
            "risk_authority": False,
            "order_authority": False,
            "capital_allocation_authority": False,
            "paper_ready_claim": False,
            "shadow_ready_claim": False,
            "live_ready_claim": False,
        },
    )


__all__ = ["OperatorTrustMultirunReport", "build_operator_trust_multirun_report"]
