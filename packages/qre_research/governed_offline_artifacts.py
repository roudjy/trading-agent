"""Persistence for governed offline QRE research artifacts.

The persistence contract is offline-only and caller-directed. It writes
versioned JSON envelopes only under the caller-provided artifact directory and
never mutates frozen research outputs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Final

from packages.qre_research import architecture_registry
from packages.qre_research import offline_research_dry_run as dry_run
from packages.qre_research import operator_trust_multirun_report as trust_report

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_governed_offline_research_artifact"
DEFAULT_ARTIFACT_DIR: Final[Path] = Path("logs/qre_governed_offline_research")
FROZEN_OUTPUTS: Final[frozenset[str]] = frozenset(architecture_registry.FROZEN_LEGACY_OUTPUTS)


def _authority() -> dict[str, bool]:
    return {
        "offline_only": True,
        "shadow_authority": False,
        "paper_authority": False,
        "live_authority": False,
        "broker_authority": False,
        "risk_authority": False,
        "order_authority": False,
        "capital_allocation_authority": False,
        "strategy_synthesis_authority": False,
    }


def _stage_records(result: dry_run.OfflineDryRunResult) -> list[dict[str, object]]:
    return [
        {
            "stage": record.stage,
            "status": "completed" if result.admitted else "blocked",
            "consumed_object": record.consumes,
            "emitted_object": record.emits,
            "reasons": list(record.reason_codes),
        }
        for record in result.stage_records
    ]


def build_artifact_envelope(
    *,
    run_id: str,
    dry_run_result: dry_run.OfflineDryRunResult,
    operator_report: trust_report.OperatorTrustMultirunReport,
    created_at_utc: str,
    source_mode: str = "offline_fixture",
    fixture_fingerprint: str = "fixture:v1:deterministic",
) -> dict[str, object]:
    reason_records = [record.as_dict() for record in dry_run_result.reason_records]
    missing_evidence = list(dry_run_result.evidence_pack.get("missing_evidence_reason_codes", []))
    negative_evidence = list(dry_run_result.evidence_pack.get("negative_evidence_reason_codes", []))
    governance_blockers = [
        record["code"]
        for record in reason_records
        if record["evidence_polarity"] in {"governance_rejection", "policy_rejection"}
    ]
    data_quality_blockers = [
        record["code"]
        for record in reason_records
        if record["code"] in {"data_quality_failed", "source_identity_unresolved"}
    ]
    report = operator_report.as_dict()
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "run_id": run_id,
        "created_at_utc": created_at_utc,
        "source_mode": source_mode,
        "authority": _authority(),
        "inputs": {
            "hypothesis_id": dry_run_result.hypothesis_id,
            "candidate_id": dry_run_result.hypothesis_id,
            "source_provenance": "offline_fixture",
            "data_provenance": "synthetic_fixture",
            "dataset_fingerprint": fixture_fingerprint,
        },
        "stage_records": _stage_records(dry_run_result),
        "evidence_pack": {
            "complete": dry_run_result.evidence_pack["complete"],
            "missing_evidence": missing_evidence,
            "negative_evidence": negative_evidence,
            "governance_blockers": governance_blockers,
            "data_source_quality_blockers": data_quality_blockers,
            "screening_result": dry_run_result.evidence_pack["screening_result"],
            "null_model_beaten": None,
            "cost_model_passed": None,
            "trade_count": None,
        },
        "disposition": {
            "decision": dry_run_result.disposition["disposition"],
            "reasons": list(dry_run_result.disposition["reason_codes"]),
            "next_action": (
                "eligible_for_governed_batch_consideration"
                if dry_run_result.admitted
                else "resolve_blocking_reasons"
            ),
        },
        "rejection_reasons": reason_records,
        "memory_feedback": {
            "lessons": [record["lesson_memory"] for record in dry_run_result.feedback_memory],
            "suppressions": report["do_not_retest"],
            "prioritization_hints": report["worth_testing_next"],
        },
        "operator_trust_summary": {
            "what_was_tested": report["tested_hypotheses"],
            "what_passed": report["admitted_count"],
            "what_failed": report["blocked_count"],
            "why_failed": report["rejection_reason_distribution"],
            "what_not_to_retest": report["do_not_retest"],
            "what_to_test_next": report["worth_testing_next"],
            "explicit_authority_denial_statement": report["authority_statement"],
        },
    }


def validate_artifact_envelope(envelope: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if envelope.get("schema_version") != SCHEMA_VERSION:
        errors.append("invalid_schema_version")
    if envelope.get("report_kind") != REPORT_KIND:
        errors.append("invalid_report_kind")
    if envelope.get("source_mode") not in {"offline_fixture", "offline_sample", "offline_cached"}:
        errors.append("invalid_source_mode")
    authority = envelope.get("authority")
    if not isinstance(authority, dict):
        errors.append("missing_authority")
        authority = {}
    if authority.get("offline_only") is not True:
        errors.append("offline_only_not_true")
    for key, value in authority.items():
        if key != "offline_only" and value is not False:
            errors.append(f"authority_not_denied:{key}")
    stages = envelope.get("stage_records")
    if not isinstance(stages, list) or not stages:
        errors.append("missing_stage_records")
    else:
        stage_order = tuple(str(record.get("stage")) for record in stages if isinstance(record, dict))
        if stage_order != dry_run.DRY_RUN_STAGE_ORDER:
            errors.append("stage_order_mismatch")
    for key in ("inputs", "evidence_pack", "disposition", "memory_feedback", "operator_trust_summary"):
        if not isinstance(envelope.get(key), dict):
            errors.append(f"missing_{key}")
    evidence = envelope.get("evidence_pack")
    if isinstance(evidence, dict):
        if "missing_evidence" not in evidence:
            errors.append("missing_evidence_not_explicit")
        if "negative_evidence" not in evidence:
            errors.append("negative_evidence_not_explicit")
        if "governance_blockers" not in evidence:
            errors.append("governance_blockers_not_explicit")
        if "data_source_quality_blockers" not in evidence:
            errors.append("data_source_quality_blockers_not_explicit")
    return errors


def _safe_output_paths(directory: Path, run_id: str) -> tuple[Path, Path]:
    run_path = directory / f"{run_id}.json"
    latest_path = directory / "latest.json"
    for path in (run_path, latest_path):
        normalized = path.as_posix()
        if normalized in FROZEN_OUTPUTS or any(normalized.endswith(output) for output in FROZEN_OUTPUTS):
            raise ValueError(f"unsafe_artifact_path:{normalized}")
    return run_path, latest_path


def write_artifact(envelope: dict[str, object], directory: Path) -> tuple[Path, Path]:
    errors = validate_artifact_envelope(envelope)
    if errors:
        raise ValueError(";".join(errors))
    run_id = str(envelope["run_id"])
    directory.mkdir(parents=True, exist_ok=True)
    run_path, latest_path = _safe_output_paths(directory, run_id)
    payload = json.dumps(envelope, indent=2, sort_keys=True) + "\n"
    for target in (run_path, latest_path):
        temp_path = target.with_suffix(f"{target.suffix}.tmp")
        temp_path.write_text(payload, encoding="utf-8")
        os.replace(temp_path, target)
    return run_path, latest_path


def read_artifact(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("artifact_must_be_object")
    errors = validate_artifact_envelope(payload)
    if errors:
        raise ValueError(";".join(errors))
    return payload


__all__ = [
    "DEFAULT_ARTIFACT_DIR",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "build_artifact_envelope",
    "read_artifact",
    "validate_artifact_envelope",
    "write_artifact",
]
