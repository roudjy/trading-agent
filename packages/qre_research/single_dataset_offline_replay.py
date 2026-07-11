"""Single-dataset governed offline QRE replay.

The replay admits or blocks exactly one offline dataset boundary and persists
the resulting governed dry-run artifact under a caller-provided directory. It
does not broaden datasets, run production research, mutate frozen outputs, or
grant execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from packages.qre_research import evidence_memory_accumulation as accumulation
from packages.qre_research import governed_candidate_batch as batch
from packages.qre_research import governed_offline_artifacts as artifacts
from packages.qre_research import hypothesis_generator_governance as governance
from packages.qre_research import offline_research_dry_run as dry_run
from packages.qre_research import operator_trust_multirun_report as trust_report
from packages.qre_research import rejection_reasons as reasons
from packages.qre_research import research_throughput_controls as throughput

DatasetSourceMode = Literal["offline_fixture", "offline_sample", "offline_cached"]


@dataclass(frozen=True, slots=True)
class OfflineDatasetBoundary:
    dataset_id: str
    source_id: str
    source_mode: DatasetSourceMode
    dataset_fingerprint: str
    source_provenance: str
    data_provenance: str
    source_approved: bool = True
    data_admitted: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "source_id": self.source_id,
            "source_mode": self.source_mode,
            "dataset_fingerprint": self.dataset_fingerprint,
            "source_provenance": self.source_provenance,
            "data_provenance": self.data_provenance,
            "source_approved": self.source_approved,
            "data_admitted": self.data_admitted,
        }


@dataclass(frozen=True, slots=True)
class SingleDatasetReplayResult:
    replay_id: str
    dataset: OfflineDatasetBoundary
    dry_run_result: dry_run.OfflineDryRunResult
    operator_report: trust_report.OperatorTrustMultirunReport
    artifact_envelope: dict[str, object]
    artifact_path: Path
    latest_path: Path
    safety: dict[str, bool]

    def as_dict(self) -> dict[str, object]:
        return {
            "replay_id": self.replay_id,
            "dataset": self.dataset.as_dict(),
            "dry_run_result": self.dry_run_result.as_dict(),
            "operator_report": self.operator_report.as_dict(),
            "artifact_envelope": dict(self.artifact_envelope),
            "artifact_path": self.artifact_path.as_posix(),
            "latest_path": self.latest_path.as_posix(),
            "safety": dict(self.safety),
        }


def _dataset_reason_records(
    dataset: OfflineDatasetBoundary,
    hypothesis_id: str,
) -> tuple[reasons.ReasonRecord, ...]:
    records: list[reasons.ReasonRecord] = []
    if not dataset.source_approved:
        records.append(
            reasons.make_reason_record(
                code=reasons.RejectionReasonCode.SOURCE_IDENTITY_UNRESOLVED.value,
                stage="SourceSnapshot",
                object_id=hypothesis_id,
                explanation="The single offline replay source is not approved.",
                next_action="approve_or_replace_offline_source",
                terminal=True,
            )
        )
    if not dataset.data_admitted:
        records.append(
            reasons.make_reason_record(
                code=reasons.RejectionReasonCode.DATA_QUALITY_FAILED.value,
                stage="DatasetFingerprint",
                object_id=hypothesis_id,
                explanation="The single offline replay dataset failed data admission.",
                next_action="repair_or_replace_offline_dataset",
                terminal=True,
            )
        )
    return tuple(records)


def _candidate_for_dataset(
    candidate: throughput.ThroughputCandidate,
    dataset: OfflineDatasetBoundary,
) -> throughput.ThroughputCandidate:
    proposal = replace(
        candidate.proposal,
        source_id=dataset.source_id,
        source_identity_resolved=dataset.source_approved,
        data_quality_ready=dataset.data_admitted,
    )
    return replace(
        candidate,
        proposal=proposal,
        data_quality_admitted=dataset.data_admitted,
    )


def run_single_dataset_offline_replay(
    *,
    replay_id: str,
    dataset: OfflineDatasetBoundary,
    candidate: throughput.ThroughputCandidate,
    budget: throughput.ThroughputBudget,
    artifact_dir: Path,
    created_at_utc: str,
) -> SingleDatasetReplayResult:
    replay_candidate = _candidate_for_dataset(candidate, dataset)
    reason_records = _dataset_reason_records(dataset, replay_candidate.proposal.hypothesis_id)
    dry_run_result = dry_run.run_offline_dry_run(
        replay_candidate,
        budget=budget,
        rejection_records=reason_records,
    )
    batch_result = batch.run_governed_candidate_batch(
        f"{replay_id}:batch",
        (replay_candidate,),
        budget=budget,
        rejection_records=reason_records,
    )
    report = trust_report.build_operator_trust_multirun_report(
        accumulation.accumulate_evidence_memory((batch_result,))
    )
    envelope = artifacts.build_artifact_envelope(
        run_id=replay_id,
        dry_run_result=dry_run_result,
        operator_report=report,
        created_at_utc=created_at_utc,
        source_mode=dataset.source_mode,
        fixture_fingerprint=dataset.dataset_fingerprint,
        source_provenance=dataset.source_provenance,
        data_provenance=dataset.data_provenance,
    )
    run_path, latest_path = artifacts.write_artifact(envelope, artifact_dir)
    return SingleDatasetReplayResult(
        replay_id=replay_id,
        dataset=dataset,
        dry_run_result=dry_run_result,
        operator_report=report,
        artifact_envelope=envelope,
        artifact_path=run_path,
        latest_path=latest_path,
        safety={
            "offline_only": True,
            "single_dataset_boundary": True,
            "runtime_behavior_changed": False,
            "research_latest_mutated": False,
            "strategy_matrix_mutated": False,
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


def synthetic_replay_candidate(hypothesis_id: str = "single-dataset-replay") -> throughput.ThroughputCandidate:
    return throughput.ThroughputCandidate(
        proposal=governance.HypothesisProposal(
            hypothesis_id=hypothesis_id,
            mechanism="offline replay route verification",
            source_id="offline_source",
            behavior_family="trend",
            expected_information_gain=10.0,
        ),
        timeframe="1h",
    )


def default_replay_budget() -> throughput.ThroughputBudget:
    return throughput.ThroughputBudget(1, 1, 1, 1, 1)


__all__ = [
    "OfflineDatasetBoundary",
    "SingleDatasetReplayResult",
    "default_replay_budget",
    "run_single_dataset_offline_replay",
    "synthetic_replay_candidate",
]
