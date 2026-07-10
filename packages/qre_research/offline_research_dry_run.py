"""Governed offline QRE research dry run.

The dry run is deterministic and in-memory. It verifies route correctness and
evidence/memory completeness for a single governed candidate without running
production research, creating production artifacts, mutating frozen outputs, or
granting execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from packages.qre_research import canonical_funnel_verification as funnel
from packages.qre_research import rejection_reasons as reasons
from packages.qre_research import research_throughput_controls as throughput

DryRunDisposition = Literal["accepted_for_research_memory", "blocked_before_screening"]

DRY_RUN_STAGE_ORDER: Final[tuple[str, ...]] = (
    "Hypothesis",
    "CandidateSpec",
    "StrategySpec",
    "StrategyIR",
    "PresetSpec",
    "CampaignSpec",
    "ScreeningResult",
    "EvidencePack",
    "Disposition",
    "FeedbackRecord",
    "LessonMemory",
)


@dataclass(frozen=True, slots=True)
class DryRunStageRecord:
    stage: str
    object_id: str
    consumes: str | None
    emits: str
    reason_codes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "object_id": self.object_id,
            "consumes": self.consumes,
            "emits": self.emits,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class OfflineDryRunResult:
    hypothesis_id: str
    offline_only: bool
    deterministic: bool
    admitted: bool
    stage_records: tuple[DryRunStageRecord, ...]
    reason_records: tuple[reasons.ReasonRecord, ...]
    evidence_pack: dict[str, object]
    disposition: dict[str, object]
    feedback_memory: tuple[dict[str, object], ...]
    safety: dict[str, bool]

    def as_dict(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "offline_only": self.offline_only,
            "deterministic": self.deterministic,
            "admitted": self.admitted,
            "stage_records": [record.as_dict() for record in self.stage_records],
            "reason_records": [record.as_dict() for record in self.reason_records],
            "evidence_pack": dict(self.evidence_pack),
            "disposition": dict(self.disposition),
            "feedback_memory": list(self.feedback_memory),
            "safety": dict(self.safety),
        }


def _stage_records(hypothesis_id: str, reason_codes: tuple[str, ...]) -> tuple[DryRunStageRecord, ...]:
    records: list[DryRunStageRecord] = []
    prior: str | None = None
    for stage in DRY_RUN_STAGE_ORDER:
        records.append(
            DryRunStageRecord(
                stage=stage,
                object_id=f"offline-dry-run:{hypothesis_id}:{stage}",
                consumes=prior,
                emits=stage,
                reason_codes=reason_codes if stage in {"ScreeningResult", "EvidencePack", "Disposition"} else (),
            )
        )
        prior = stage
    return tuple(records)


def _reason_records(hypothesis_id: str, admission: throughput.ThroughputAdmissionRecord) -> tuple[reasons.ReasonRecord, ...]:
    return tuple(
        reasons.make_reason_record(
            code=code,
            stage="ScreeningResult",
            object_id=hypothesis_id,
            explanation=f"Governed offline dry run carried reason code {code}.",
            next_action=admission.next_action,
            terminal=admission.decision == "blocked",
        )
        for code in admission.reason_codes
    )


def run_offline_dry_run(
    candidate: throughput.ThroughputCandidate,
    *,
    budget: throughput.ThroughputBudget,
    rejection_records: tuple[reasons.ReasonRecord, ...] = (),
) -> OfflineDryRunResult:
    architecture_errors = tuple(funnel.verify_canonical_funnel())
    admission = throughput.plan_research_throughput(
        (candidate,),
        budget=budget,
        rejection_records=rejection_records,
    )[0]
    reason_records = _reason_records(candidate.proposal.hypothesis_id, admission)
    missing_reasons = [
        record.code
        for record in reason_records
        if record.evidence_polarity == "missing_evidence"
    ]
    negative_reasons = [
        record.code
        for record in reason_records
        if record.evidence_polarity == "negative_evidence"
    ]
    admitted = admission.decision == "admit" and not architecture_errors
    disposition: DryRunDisposition = "accepted_for_research_memory" if admitted else "blocked_before_screening"
    evidence_pack = {
        "artifact_kind": "offline_fixture_evidence_pack",
        "hypothesis_id": candidate.proposal.hypothesis_id,
        "complete": admitted,
        "architecture_errors": list(architecture_errors),
        "missing_evidence_reason_codes": missing_reasons,
        "negative_evidence_reason_codes": negative_reasons,
        "screening_result": "offline_route_verified" if admitted else "offline_route_blocked",
    }
    feedback_memory = tuple(reasons.feedback_memory_payload(record) for record in reason_records)
    if admitted:
        feedback_memory = (
            {
                "feedback_record": {
                    "code": "offline_route_verified",
                    "stage": "Disposition",
                    "object_id": candidate.proposal.hypothesis_id,
                    "severity": "info",
                    "explanation": "Governed offline dry run followed the canonical route.",
                    "next_action": "eligible_for_governed_batch_consideration",
                    "evidence_polarity": "missing_evidence",
                    "terminal": False,
                },
                "lesson_memory": {
                    "object_id": candidate.proposal.hypothesis_id,
                    "stage": "Disposition",
                    "reason_code": "offline_route_verified",
                    "failure_mode": "none",
                    "next_action": "eligible_for_governed_batch_consideration",
                },
                "research_memory": {
                    "suppress_if_unchanged": False,
                    "requires_changed_condition": False,
                    "canonical_reason_code": "offline_route_verified",
                },
            },
        )
    return OfflineDryRunResult(
        hypothesis_id=candidate.proposal.hypothesis_id,
        offline_only=True,
        deterministic=True,
        admitted=admitted,
        stage_records=_stage_records(candidate.proposal.hypothesis_id, admission.reason_codes),
        reason_records=reason_records,
        evidence_pack=evidence_pack,
        disposition={
            "object_id": f"offline-dry-run:{candidate.proposal.hypothesis_id}:Disposition",
            "disposition": disposition,
            "reason_codes": list(admission.reason_codes),
        },
        feedback_memory=feedback_memory,
        safety={
            "runtime_behavior_changed": False,
            "research_latest_mutated": False,
            "strategy_matrix_mutated": False,
            "broker_authority": False,
            "risk_authority": False,
            "order_authority": False,
            "capital_allocation_authority": False,
            "shadow_authority": False,
            "paper_authority": False,
            "live_authority": False,
            "strategy_synthesis_authority": False,
        },
    )


__all__ = [
    "DRY_RUN_STAGE_ORDER",
    "DryRunStageRecord",
    "OfflineDryRunResult",
    "run_offline_dry_run",
]
