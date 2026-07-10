"""Governed QRE evidence and memory accumulation."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from packages.qre_research import governed_candidate_batch as batch
from packages.qre_research import rejection_reasons as reasons


@dataclass(frozen=True, slots=True)
class EvidenceMemoryAccumulation:
    run_count: int
    tested_hypotheses: tuple[str, ...]
    disposition_trends: dict[str, int]
    reason_distribution: dict[str, int]
    missing_evidence_reasons: tuple[str, ...]
    negative_evidence_reasons: tuple[str, ...]
    repeated_failure_modes: tuple[str, ...]
    lineage: dict[str, tuple[str, ...]]
    memory_feedback_records: tuple[dict[str, object], ...]
    suppress_retest: tuple[str, ...]
    next_action_queue: tuple[dict[str, object], ...]
    safety: dict[str, bool]

    def as_dict(self) -> dict[str, object]:
        return {
            "run_count": self.run_count,
            "tested_hypotheses": list(self.tested_hypotheses),
            "disposition_trends": dict(self.disposition_trends),
            "reason_distribution": dict(self.reason_distribution),
            "missing_evidence_reasons": list(self.missing_evidence_reasons),
            "negative_evidence_reasons": list(self.negative_evidence_reasons),
            "repeated_failure_modes": list(self.repeated_failure_modes),
            "lineage": {key: list(value) for key, value in self.lineage.items()},
            "memory_feedback_records": list(self.memory_feedback_records),
            "suppress_retest": list(self.suppress_retest),
            "next_action_queue": list(self.next_action_queue),
            "safety": dict(self.safety),
        }


def accumulate_evidence_memory(
    results: tuple[batch.GovernedCandidateBatchResult, ...],
) -> EvidenceMemoryAccumulation:
    tested: list[str] = []
    dispositions: Counter[str] = Counter()
    reasons_seen: Counter[str] = Counter()
    lineage: dict[str, list[str]] = defaultdict(list)
    memory_feedback: list[dict[str, object]] = []
    next_actions: list[dict[str, object]] = []

    for result in results:
        for hypothesis_id in result.admitted_candidates:
            tested.append(hypothesis_id)
            lineage[hypothesis_id].append(result.batch_id)
        for blocked in result.blocked_candidates:
            hypothesis_id = str(blocked["hypothesis_id"])
            tested.append(hypothesis_id)
            lineage[hypothesis_id].append(result.batch_id)
            for code in blocked["reason_codes"]:
                reasons_seen[str(code)] += 1
        for summary in result.evidence_summaries:
            dispositions[str(summary["disposition"])] += 1
            for code in summary["reason_codes"]:
                reasons_seen[str(code)] += 1
        memory_feedback.extend(result.memory_feedback_records)
        next_actions.extend(result.next_action_queue)

    missing = tuple(sorted(code for code in reasons_seen if reasons.reason_polarity(code) == "missing_evidence"))
    negative = tuple(sorted(code for code in reasons_seen if reasons.reason_polarity(code) == "negative_evidence"))
    repeated = tuple(sorted(code for code, count in reasons_seen.items() if count > 1))
    suppress = tuple(
        sorted(
            str(item["hypothesis_id"])
            for item in next_actions
            if "duplicate_hypothesis" in item.get("reason_codes", ())
            or "duplicate_active_research_path" in item.get("reason_codes", ())
        )
    )
    return EvidenceMemoryAccumulation(
        run_count=len(results),
        tested_hypotheses=tuple(dict.fromkeys(tested)),
        disposition_trends=dict(dispositions),
        reason_distribution=dict(reasons_seen),
        missing_evidence_reasons=missing,
        negative_evidence_reasons=negative,
        repeated_failure_modes=repeated,
        lineage={key: tuple(value) for key, value in lineage.items()},
        memory_feedback_records=tuple(memory_feedback),
        suppress_retest=suppress,
        next_action_queue=tuple(next_actions),
        safety={
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


__all__ = ["EvidenceMemoryAccumulation", "accumulate_evidence_memory"]
