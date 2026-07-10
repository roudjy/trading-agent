"""Governed offline QRE candidate batch planning.

This module batches already-governed offline candidates through throughput
controls and the offline dry-run route. It is deterministic, in-memory, and
does not create production research artifacts or grant execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass

from packages.qre_research import offline_research_dry_run as dry_run
from packages.qre_research import rejection_reasons as reasons
from packages.qre_research import research_throughput_controls as throughput


@dataclass(frozen=True, slots=True)
class GovernedCandidateBatchResult:
    batch_id: str
    plan: tuple[throughput.ThroughputAdmissionRecord, ...]
    admitted_candidates: tuple[str, ...]
    blocked_candidates: tuple[dict[str, object], ...]
    dry_run_results: tuple[dry_run.OfflineDryRunResult, ...]
    evidence_summaries: tuple[dict[str, object], ...]
    memory_feedback_records: tuple[dict[str, object], ...]
    next_action_queue: tuple[dict[str, object], ...]
    safety: dict[str, bool]

    def as_dict(self) -> dict[str, object]:
        return {
            "batch_id": self.batch_id,
            "plan": [record.as_dict() for record in self.plan],
            "admitted_candidates": list(self.admitted_candidates),
            "blocked_candidates": list(self.blocked_candidates),
            "dry_run_results": [result.as_dict() for result in self.dry_run_results],
            "evidence_summaries": list(self.evidence_summaries),
            "memory_feedback_records": list(self.memory_feedback_records),
            "next_action_queue": list(self.next_action_queue),
            "safety": dict(self.safety),
        }


def run_governed_candidate_batch(
    batch_id: str,
    candidates: tuple[throughput.ThroughputCandidate, ...],
    *,
    budget: throughput.ThroughputBudget,
    rejection_records: tuple[reasons.ReasonRecord, ...] = (),
) -> GovernedCandidateBatchResult:
    plan = throughput.plan_research_throughput(
        candidates,
        budget=budget,
        rejection_records=rejection_records,
    )
    by_id = {candidate.proposal.hypothesis_id: candidate for candidate in candidates}
    admitted_ids = tuple(record.hypothesis_id for record in plan if record.decision == "admit")
    blocked = tuple(record.as_dict() for record in plan if record.decision == "blocked")
    dry_runs = tuple(
        dry_run.run_offline_dry_run(
            by_id[hypothesis_id],
            budget=budget,
            rejection_records=rejection_records,
        )
        for hypothesis_id in admitted_ids
    )
    evidence_summaries = tuple(
        {
            "hypothesis_id": result.hypothesis_id,
            "complete": result.evidence_pack["complete"],
            "disposition": result.disposition["disposition"],
            "reason_codes": result.disposition["reason_codes"],
        }
        for result in dry_runs
    )
    memory_feedback = tuple(
        payload
        for result in dry_runs
        for payload in result.feedback_memory
    )
    next_actions = tuple(
        {
            "hypothesis_id": record.hypothesis_id,
            "reason_codes": list(record.reason_codes),
            "next_action": record.next_action,
        }
        for record in plan
        if record.decision == "blocked"
    )
    return GovernedCandidateBatchResult(
        batch_id=batch_id,
        plan=plan,
        admitted_candidates=admitted_ids,
        blocked_candidates=blocked,
        dry_run_results=dry_runs,
        evidence_summaries=evidence_summaries,
        memory_feedback_records=memory_feedback,
        next_action_queue=next_actions,
        safety={
            "runtime_behavior_changed": False,
            "research_execution": False,
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
    "GovernedCandidateBatchResult",
    "run_governed_candidate_batch",
]
