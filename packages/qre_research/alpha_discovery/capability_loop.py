from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from packages.qre_research import autonomous_opportunity_loop as aol

from .contracts import (
    GAP_STATUS_WAITING_FOR_ADE,
    GAP_STATUS_WAITING_FOR_OPERATOR,
    GAP_TYPE_CREDENTIAL,
    GAP_TYPE_EXECUTOR,
    GAP_TYPE_IDENTITY,
    GAP_TYPE_LICENSE,
    GAP_TYPE_ORCHESTRATION,
    GAP_TYPE_PRIMITIVE,
    GAP_TYPE_SOURCE_CERTIFICATION,
    BlockedExperiment,
    CapabilityGap,
    ExperimentAdmissionDecision,
    SourceResolution,
    content_id,
    write_json_atomic,
)

GAP_REGISTRY_PATH = Path("generated_research/alpha_discovery/capability_gaps/latest.json")
BLOCKED_EXPERIMENTS_PATH = Path("generated_research/alpha_discovery/blocked_experiments/latest.json")
RESOLUTION_FEEDBACK_PATH = Path("generated_research/alpha_discovery/resolution_feedback/latest.json")


def _iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _deduplication_key(*, experiment_id: str, gap_type: str, decision: str, reason_codes: tuple[str, ...]) -> str:
    reasons = ",".join(reason_codes) if reason_codes else "admission_requirements_met"
    return "|".join(
        [
            "qgapdedupe",
            f"experiment={experiment_id}",
            f"gap_type={gap_type}",
            f"decision={decision}",
            f"reasons={reasons}",
        ]
    )


def build_gap_from_admission(
    *,
    experiment_id: str,
    hypothesis_id: str,
    strategy_spec_id: str,
    preregistration_id: str,
    admission: ExperimentAdmissionDecision,
    source_resolution: SourceResolution | None,
    blocking_stage: str,
) -> tuple[list[CapabilityGap], list[BlockedExperiment]]:
    gaps: list[CapabilityGap] = []
    blocked: list[BlockedExperiment] = []
    now = _iso_now()
    if admission.decision in {"ADMIT_EMPIRICAL_SCREENING", "ADMIT_LOCKED_OOS_VALIDATION", "ADMIT_EXECUTOR_SMOKE", "ADMIT_COMPILER_ONLY"}:
        return gaps, blocked
    mappings = {
        "SOURCE_QUALITY_BLOCKED": GAP_TYPE_SOURCE_CERTIFICATION,
        "IDENTITY_BLOCKED": GAP_TYPE_IDENTITY,
        "REQUIRES_PRIMITIVE_EXTENSION": GAP_TYPE_PRIMITIVE,
        "REQUIRES_EXECUTOR_EXTENSION": GAP_TYPE_EXECUTOR,
        "POLICY_BLOCKED": GAP_TYPE_ORCHESTRATION,
    }
    gap_type = mappings.get(admission.decision, GAP_TYPE_SOURCE_CERTIFICATION)
    if source_resolution is not None:
        if source_resolution.credential_requirements:
            gap_type = GAP_TYPE_CREDENTIAL
        elif source_resolution.license_requirements:
            gap_type = GAP_TYPE_LICENSE
    gap = CapabilityGap(
        gap_id=content_id("qgap", {"experiment_id": experiment_id, "gap_type": gap_type, "decision": admission.decision}),
        experiment_id=experiment_id,
        gap_type=gap_type,
        summary=f"Blocked at {blocking_stage}: {admission.decision}",
        required_capability=str(source_resolution.target_source_tier if source_resolution is not None else admission.requested_tier),
        current_capability=str(source_resolution.current_source_tier if source_resolution is not None else admission.admitted_tier),
        blocking_stage=blocking_stage,
        risk_class="LOW",
        code_change_required=gap_type in {GAP_TYPE_PRIMITIVE, GAP_TYPE_EXECUTOR, GAP_TYPE_ORCHESTRATION},
        external_configuration_required=gap_type in {GAP_TYPE_CREDENTIAL, GAP_TYPE_LICENSE, GAP_TYPE_SOURCE_CERTIFICATION},
        credential_required=gap_type == GAP_TYPE_CREDENTIAL,
        license_required=gap_type == GAP_TYPE_LICENSE,
        suggested_owner="packages/qre_research/**" if gap_type in {GAP_TYPE_PRIMITIVE, GAP_TYPE_EXECUTOR, GAP_TYPE_ORCHESTRATION} else "human_operator",
        resolution_criteria=tuple(admission.reason_codes) or ("admission_requirements_met",),
        status=GAP_STATUS_WAITING_FOR_ADE if gap_type in {GAP_TYPE_PRIMITIVE, GAP_TYPE_EXECUTOR, GAP_TYPE_ORCHESTRATION} else GAP_STATUS_WAITING_FOR_OPERATOR,
        created_at_utc=now,
        resolved_at_utc=None,
        resolution_refs=(),
        deduplication_key=_deduplication_key(
            experiment_id=experiment_id,
            gap_type=gap_type,
            decision=admission.decision,
            reason_codes=admission.reason_codes,
        ),
        content_identity=content_id("qgapc", {"experiment_id": experiment_id, "gap_type": gap_type, "status": admission.decision}),
    )
    gaps.append(gap)
    blocked.append(
        BlockedExperiment(
            experiment_id=experiment_id,
            hypothesis_id=hypothesis_id,
            strategy_spec_id=strategy_spec_id,
            preregistration_id=preregistration_id,
            blocked_stage=blocking_stage,
            gap_ids=(gap.gap_id,),
            required_data_snapshot=str(source_resolution.selected_snapshot) if source_resolution is not None else None,
            required_source_tier=str(source_resolution.target_source_tier) if source_resolution is not None else admission.requested_tier,
            required_primitive="generic_primitive_extension" if gap_type == GAP_TYPE_PRIMITIVE else None,
            required_executor="research_executor_extension" if gap_type == GAP_TYPE_EXECUTOR else None,
            current_status="BLOCKED",
            resume_token=content_id("qresume", {"experiment_id": experiment_id, "gap_id": gap.gap_id}),
            last_attempt_at_utc=now,
            next_retry_after_utc=(datetime.now(UTC) + timedelta(minutes=15)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            content_identity=content_id("qblocked", {"experiment_id": experiment_id, "gap": gap.gap_id}),
        )
    )
    return gaps, blocked


def persist_gap_state(
    *,
    repo_root: Path,
    gaps: list[CapabilityGap],
    blocked: list[BlockedExperiment],
) -> dict[str, Any]:
    previous_gaps = (_read_json(repo_root / GAP_REGISTRY_PATH) or {}).get("rows") or []
    previous_blocked = (_read_json(repo_root / BLOCKED_EXPERIMENTS_PATH) or {}).get("rows") or []
    merged_gaps = {str(row.get("deduplication_key") or ""): dict(row) for row in previous_gaps if isinstance(row, dict)}
    for gap in gaps:
        merged_gaps[gap.deduplication_key] = asdict(gap)
    gap_payload = {
        "schema_version": "1.0",
        "report_kind": "qre_alpha_capability_gaps",
        "rows": sorted(merged_gaps.values(), key=lambda row: (str(row.get("experiment_id") or ""), str(row.get("gap_type") or ""))),
        "content_identity": content_id("qgapset", sorted(merged_gaps.values(), key=lambda row: str(row.get("gap_id") or ""))),
    }
    blocked_map = {str(row.get("resume_token") or ""): dict(row) for row in previous_blocked if isinstance(row, dict)}
    for row in blocked:
        blocked_map[row.resume_token] = asdict(row)
    blocked_payload = {
        "schema_version": "1.0",
        "report_kind": "qre_alpha_blocked_experiments",
        "rows": sorted(blocked_map.values(), key=lambda row: (str(row.get("experiment_id") or ""), str(row.get("resume_token") or ""))),
        "content_identity": content_id("qblockedset", sorted(blocked_map.values(), key=lambda row: str(row.get("resume_token") or ""))),
    }
    write_json_atomic(repo_root / GAP_REGISTRY_PATH, gap_payload)
    write_json_atomic(repo_root / BLOCKED_EXPERIMENTS_PATH, blocked_payload)
    return {"gaps": gap_payload, "blocked_experiments": blocked_payload}


def route_code_gaps_to_ade(*, repo_root: Path, gap_payload: dict[str, Any], run_id: str) -> dict[str, Any]:
    request_bundle = aol.build_ade_requests(repo_root=repo_root, gap_registry={"rows": gap_payload.get("rows", [])}, run_id=run_id)
    if request_bundle.get("active_requests"):
        aol._write_ade_bridge_artifacts(repo_root=repo_root, proposal_intake_payload=request_bundle["proposal_intake_payload"])
    return request_bundle


def consume_resolution_feedback(*, repo_root: Path) -> dict[str, Any]:
    gap_payload = _read_json(repo_root / GAP_REGISTRY_PATH) or {"rows": []}
    request_rows = [
        {
            "request_id": row.get("request_id"),
            "deduplication_key": row.get("deduplication_key"),
            "gap_class": row.get("gap_type"),
        }
        for row in gap_payload.get("rows", [])
        if isinstance(row, dict) and row.get("request_id")
    ]
    ade_feedback = aol.consume_resolution_feedback(repo_root=repo_root, request_rows=request_rows)
    payload = {
        "schema_version": "1.0",
        "report_kind": "qre_alpha_resolution_feedback",
        "rows": ade_feedback.get("resolved_requests", []),
        "content_identity": content_id("qresfeed", ade_feedback.get("resolved_requests", [])),
    }
    write_json_atomic(repo_root / RESOLUTION_FEEDBACK_PATH, payload)
    return payload


__all__ = [
    "BLOCKED_EXPERIMENTS_PATH",
    "GAP_REGISTRY_PATH",
    "RESOLUTION_FEEDBACK_PATH",
    "build_gap_from_admission",
    "consume_resolution_feedback",
    "persist_gap_state",
    "route_code_gaps_to_ade",
]
