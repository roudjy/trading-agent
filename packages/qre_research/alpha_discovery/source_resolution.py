from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.external_intelligence.source_manifest_registry import build_source_manifest_registry

from .contracts import (
    SOURCE_TIER_BLOCKED,
    SOURCE_TIER_SCREENING_ELIGIBLE,
    SOURCE_TIER_SMOKE_ONLY,
    SOURCE_TIER_VALIDATION_ELIGIBLE,
    DataRequirement,
    SourceResolution,
    content_id,
    write_json_atomic,
)
from .snapshot_lineage import coherent_snapshots, load_snapshot_lineage

SOURCE_RESOLUTION_PATH = Path("generated_research/alpha_discovery/source_resolution/latest.json")
SOURCE_QUALIFICATIONS_PATH = Path("generated_research/alpha_discovery/source_qualifications/latest.json")


def _registry_rows() -> list[dict[str, Any]]:
    payload = build_source_manifest_registry()
    return [dict(row) for row in payload.get("rows") or [] if isinstance(row, dict)]


def _provider_candidates() -> list[dict[str, Any]]:
    rows = _registry_rows()
    ranked: list[dict[str, Any]] = []
    for row in rows:
        status = str(row.get("source_status") or "")
        if status in {"quality_gated", "candidate", "staging", "manual_research_only"}:
            ranked.append(row)
    ranked.sort(
        key=lambda row: (
            0 if str(row.get("source_status") or "") == "quality_gated" else 1,
            0 if bool(row.get("authentication_required")) else 1,
            str(row.get("provider_id") or ""),
        )
    )
    return ranked


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def resolve_source(
    *,
    repo_root: Path,
    requirement: DataRequirement,
    target_source_tier: str,
) -> SourceResolution:
    lineage = load_snapshot_lineage(repo_root)
    qualifications = _read_json(repo_root / SOURCE_QUALIFICATIONS_PATH) or {}
    candidates = _provider_candidates()
    qualification_rows = [
        dict(row)
        for row in qualifications.get("rows") or []
        if isinstance(row, dict) and str(row.get("dataset_snapshot_id") or "")
    ]
    qualified_by_snapshot = {str(row.get("dataset_snapshot_id") or ""): row for row in qualification_rows}
    if qualification_rows:
        coherent = [
            row
            for row in coherent_snapshots(lineage)
            if str(row.get("dataset_snapshot_id") or "") in qualified_by_snapshot
        ]
        selected_snapshot = None
        for row in coherent:
            qualification = qualified_by_snapshot.get(str(row.get("dataset_snapshot_id") or ""))
            if qualification is None:
                continue
            if target_source_tier == SOURCE_TIER_SCREENING_ELIGIBLE and str(qualification.get("allowed_evidence_tier") or "") in {SOURCE_TIER_SCREENING_ELIGIBLE, SOURCE_TIER_VALIDATION_ELIGIBLE}:
                selected_snapshot = row
                break
            if target_source_tier == SOURCE_TIER_SMOKE_ONLY and str(qualification.get("allowed_evidence_tier") or "") in {SOURCE_TIER_SMOKE_ONLY, SOURCE_TIER_SCREENING_ELIGIBLE, SOURCE_TIER_VALIDATION_ELIGIBLE}:
                selected_snapshot = row
                break
            if target_source_tier == SOURCE_TIER_VALIDATION_ELIGIBLE and str(qualification.get("allowed_evidence_tier") or "") == SOURCE_TIER_VALIDATION_ELIGIBLE:
                selected_snapshot = row
                break
    else:
        coherent = coherent_snapshots(lineage)
        selected_snapshot = coherent[0] if coherent else None
    selected_source = str(selected_snapshot.get("source_id") or "") if selected_snapshot is not None else None
    qualification_actions: list[str] = []
    credential_requirements: list[str] = []
    license_requirements: list[str] = []
    cross_source_requirements: list[str] = []
    blockers: list[str] = []
    current_tier = SOURCE_TIER_BLOCKED

    if selected_snapshot is not None:
        qualification = qualified_by_snapshot.get(str(selected_snapshot.get("dataset_snapshot_id") or ""))
        if qualification is None and qualification_rows:
            blockers.append("SOURCE_RESOLUTION_STALE")
        elif qualification is not None:
            current_tier = str(qualification.get("allowed_evidence_tier") or SOURCE_TIER_SMOKE_ONLY)
            if target_source_tier == SOURCE_TIER_VALIDATION_ELIGIBLE and current_tier != SOURCE_TIER_VALIDATION_ELIGIBLE:
                blockers.append("validation_authority_missing")
            if target_source_tier == SOURCE_TIER_SCREENING_ELIGIBLE and current_tier == SOURCE_TIER_SMOKE_ONLY:
                blockers.append("screening_authority_missing")
        else:
            current_tier = str(selected_snapshot.get("allowed_source_tier") or SOURCE_TIER_SMOKE_ONLY)
            if target_source_tier == SOURCE_TIER_SCREENING_ELIGIBLE:
                blockers.append("source_qualification_missing")
        qualification_actions.append("use_existing_coherent_snapshot")
    elif candidates and not qualification_rows:
        qualification_actions.append("attempt_clean_snapshot_acquisition")
        selected_source = str(candidates[0].get("provider_id") or candidates[0].get("source_id") or "")
        current_tier = SOURCE_TIER_SMOKE_ONLY if selected_source else SOURCE_TIER_BLOCKED
        if bool(candidates[0].get("authentication_required")):
            credential_requirements.append(f"{selected_source.upper()}_API_KEY")
            blockers.append("credential_required")
        if str(candidates[0].get("license_terms_status") or "").lower() not in {"reviewed", "reviewed_restricted"}:
            license_requirements.append(str(candidates[0].get("license_terms_reference") or "license_review_required"))
            blockers.append("license_review_required")
    else:
        blockers.append("no_configured_source")

    if target_source_tier == SOURCE_TIER_SCREENING_ELIGIBLE and current_tier == SOURCE_TIER_SMOKE_ONLY:
        qualification_actions.append("evaluate_snapshot_scoped_screening_qualification")
        cross_source_requirements.append("cross_source_agreement_if_available")
    if current_tier == SOURCE_TIER_BLOCKED:
        blockers.append("no_screening_eligible_snapshot")
    if selected_snapshot is not None and str(selected_snapshot.get("dataset_snapshot_id") or "") not in qualified_by_snapshot:
        blockers.append("SOURCE_RESOLUTION_STALE")

    resolution = SourceResolution(
        resolution_id=content_id(
            "qsr",
            {
                "requirement_id": requirement.requirement_id,
                "selected_source": selected_source,
                "selected_snapshot": selected_snapshot.get("dataset_snapshot_id") if selected_snapshot else None,
                "target_source_tier": target_source_tier,
                "blockers": blockers,
                "qualification_set_id": qualifications.get("qualification_set_id") or qualifications.get("content_identity"),
            },
        ),
        requirement_id=requirement.requirement_id,
        candidate_sources=tuple(
            str(row.get("provider_id") or row.get("source_id") or "")
            for row in candidates[:5]
            if str(row.get("provider_id") or row.get("source_id") or "")
        ),
        selected_source=selected_source,
        selected_snapshot=str(selected_snapshot.get("dataset_snapshot_id") or "") if selected_snapshot else None,
        current_source_tier=current_tier,
        target_source_tier=target_source_tier,
        qualification_actions=tuple(qualification_actions),
        credential_requirements=tuple(credential_requirements),
        license_requirements=tuple(license_requirements),
        cross_source_requirements=tuple(cross_source_requirements),
        unresolved_blockers=tuple(dict.fromkeys(blockers)),
        operator_action_required=bool(credential_requirements or license_requirements),
        automatic_actions_allowed=not bool(credential_requirements or license_requirements),
        content_identity=content_id(
            "qsrc",
            {
                "requirement_id": requirement.requirement_id,
                "blockers": blockers,
                "snapshot": selected_snapshot,
                "qualification_set_id": qualifications.get("qualification_set_id") or qualifications.get("content_identity"),
            },
        ),
    )
    return resolution


def persist_source_resolution(*, repo_root: Path, resolution: SourceResolution) -> dict[str, Any]:
    payload = {
        "schema_version": "1.0",
        "report_kind": "qre_alpha_source_resolution",
        "rows": [asdict(resolution)],
        "content_identity": content_id("qsrset", asdict(resolution)),
    }
    write_json_atomic(repo_root / SOURCE_RESOLUTION_PATH, payload)
    return payload


__all__ = ["SOURCE_RESOLUTION_PATH", "persist_source_resolution", "resolve_source"]
