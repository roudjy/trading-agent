"""Operator-invoked governed offline QRE research runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from packages.qre_research import multiwindow_evidence_closure as closure
from packages.qre_research import operator_trust_review_gate as review
from packages.qre_research import research_memory_feedback_loop as feedback
from packages.qre_research import single_dataset_offline_replay as replay

SCHEMA_VERSION = 1
REPORT_KIND = "qre_governed_offline_research_run"
SourceMode = Literal["offline_fixture", "offline_sample", "offline_cached"]


@dataclass(frozen=True, slots=True)
class GovernedOfflineResearchRun:
    payload: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return dict(self.payload)


def _authority() -> dict[str, bool]:
    return {
        "offline_only": True,
        "strategy_synthesis_authority": False,
        "shadow_authority": False,
        "paper_authority": False,
        "live_authority": False,
        "broker_authority": False,
        "risk_authority": False,
        "order_authority": False,
        "capital_allocation_authority": False,
    }


def _dataset(
    *,
    dataset_id: str,
    source_mode: SourceMode,
    dataset_admitted: bool,
    source_approved: bool,
) -> replay.OfflineDatasetBoundary:
    return replay.OfflineDatasetBoundary(
        dataset_id=dataset_id,
        source_id=f"source:{dataset_id}",
        source_mode=source_mode,
        dataset_fingerprint=f"{source_mode}:{dataset_id}:deterministic",
        source_provenance=f"{source_mode}:source_manifest:{dataset_id}",
        data_provenance=f"{source_mode}:dataset_boundary:{dataset_id}",
        source_approved=source_approved,
        data_admitted=dataset_admitted,
    )


def _default_window_statuses() -> dict[closure.WindowName, closure.WindowStatus]:
    return {name: "passed" for name in closure.REQUIRED_WINDOWS}


def run_governed_offline_research(
    *,
    hypothesis_id: str,
    dataset_id: str,
    output_dir: Path,
    run_id: str | None = None,
    source_mode: SourceMode = "offline_fixture",
    dataset_admitted: bool = True,
    source_approved: bool = True,
    window_statuses: dict[closure.WindowName, closure.WindowStatus] | None = None,
) -> GovernedOfflineResearchRun:
    resolved_run_id = run_id or f"qre-offline-{hypothesis_id}-{dataset_id}"
    dataset = _dataset(
        dataset_id=dataset_id,
        source_mode=source_mode,
        dataset_admitted=dataset_admitted,
        source_approved=source_approved,
    )
    replay_result = replay.run_single_dataset_offline_replay(
        replay_id=resolved_run_id,
        dataset=dataset,
        candidate=replay.synthetic_replay_candidate(hypothesis_id),
        budget=replay.default_replay_budget(),
        artifact_dir=output_dir,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    resolved_windows = _default_window_statuses()
    if window_statuses:
        resolved_windows.update(window_statuses)
    if not replay_result.dry_run_result.admitted:
        resolved_windows["data_quality"] = "failed" if not dataset_admitted else resolved_windows["data_quality"]
    closure_result = closure.run_multiwindow_evidence_closure(
        closure_id=f"{resolved_run_id}-closure",
        replay_result=replay_result,
        window_statuses=resolved_windows,
        artifact_dir=output_dir,
    )
    memory_feedback = feedback.build_research_memory_feedback_loop(
        (replay.synthetic_replay_candidate(hypothesis_id).proposal,),
        closures=(closure_result,),
    )
    operator_review = review.build_operator_trust_review(
        review_id=f"{resolved_run_id}-review",
        closures=(closure_result,),
        feedback_loop=memory_feedback,
    )
    envelope = closure_result.artifact_envelope
    evidence_pack = envelope["evidence_pack"]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "run_id": resolved_run_id,
        "hypothesis_id": hypothesis_id,
        "dataset_id": dataset_id,
        "source_mode": source_mode,
        "artifact_path": closure_result.artifact_path.as_posix(),
        "latest_path": closure_result.latest_path.as_posix(),
        "dataset_admission": {
            "dataset_admitted": dataset_admitted,
            "source_approved": source_approved,
            "decision": "admitted" if replay_result.dry_run_result.admitted else "blocked",
        },
        "dataset_fingerprint": dataset.dataset_fingerprint,
        "stage_records": envelope["stage_records"],
        "evidence_windows": [window.as_dict() for window in closure_result.evidence_windows],
        "evidence_summary": {
            "missing_evidence": evidence_pack["missing_evidence"],
            "negative_evidence": evidence_pack["negative_evidence"],
            "data_source_quality_blockers": evidence_pack["data_source_quality_blockers"],
            "complete": evidence_pack["complete"],
        },
        "disposition": envelope["disposition"],
        "rejection_reasons": envelope["rejection_reasons"],
        "memory_feedback": memory_feedback.as_dict(),
        "operator_review": operator_review.as_dict(),
        "next_action": operator_review.next_action,
        "do_not_retest": list(operator_review.do_not_retest),
        "eligible_for_more_offline_research": operator_review.machine_payload[
            "eligible_for_more_offline_research"
        ],
        "authority": _authority(),
    }
    return GovernedOfflineResearchRun(payload=payload)


__all__ = [
    "GovernedOfflineResearchRun",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "run_governed_offline_research",
]
