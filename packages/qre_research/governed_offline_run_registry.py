"""Governed offline run registry and lineage index."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from packages.qre_research import architecture_registry
from packages.qre_research import governed_offline_artifacts as artifacts

SCHEMA_VERSION = 1
REPORT_KIND = "qre_governed_offline_run_registry"
FROZEN_OUTPUTS = frozenset(architecture_registry.FROZEN_LEGACY_OUTPUTS)


def _authority() -> dict[str, bool]:
    return {
        "offline_only": True,
        "production_empirical_evidence": False,
        "strategy_synthesis_authority": False,
        "shadow_authority": False,
        "paper_authority": False,
        "live_authority": False,
        "broker_authority": False,
        "risk_authority": False,
        "order_authority": False,
        "capital_allocation_authority": False,
    }


@dataclass(frozen=True, slots=True)
class OfflineRunRegistryEntry:
    payload: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return dict(self.payload)


@dataclass(frozen=True, slots=True)
class OfflineRunRegistry:
    entries: tuple[OfflineRunRegistryEntry, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "report_kind": REPORT_KIND,
            "entries": [entry.as_dict() for entry in self.entries],
            "authority": _authority(),
        }


def _dataset_id_from_fingerprint(fingerprint: str) -> str:
    parts = fingerprint.split(":")
    return parts[1] if len(parts) >= 3 else "unknown_dataset"


def _operator_decision(envelope: dict[str, object]) -> str:
    evidence = envelope["evidence_pack"]
    if not isinstance(evidence, dict):
        return "BLOCKED_MISSING_EVIDENCE"
    if evidence.get("complete") is True:
        return "ELIGIBLE_FOR_MORE_OFFLINE_RESEARCH"
    if evidence.get("negative_evidence"):
        return "REJECTED_NEGATIVE_EVIDENCE"
    return "BLOCKED_MISSING_EVIDENCE"


def _entry_from_envelope(envelope: dict[str, object], artifact_path: Path) -> OfflineRunRegistryEntry:
    inputs = envelope["inputs"]
    evidence = envelope["evidence_pack"]
    disposition = envelope["disposition"]
    memory = envelope["memory_feedback"]
    if not all(isinstance(section, dict) for section in (inputs, evidence, disposition, memory)):
        raise ValueError("invalid_artifact_sections")
    fingerprint = str(inputs["dataset_fingerprint"])
    source_mode = str(envelope["source_mode"])
    missing = list(evidence.get("missing_evidence", []))
    negative = list(evidence.get("negative_evidence", []))
    rejection_codes = sorted(set(missing) | set(negative) | set(disposition.get("reasons", [])))
    return OfflineRunRegistryEntry(
        {
            "run_id": envelope["run_id"],
            "artifact_path": artifact_path.as_posix(),
            "latest_path": str(artifact_path.with_name("latest.json").as_posix()),
            "hypothesis_id": inputs["hypothesis_id"],
            "dataset_id": _dataset_id_from_fingerprint(fingerprint),
            "dataset_fingerprint": fingerprint,
            "source_mode": source_mode,
            "dataset_admission_status": "ADMITTED" if not evidence.get("data_source_quality_blockers") else "BLOCKED",
            "disposition": disposition,
            "operator_review_decision": _operator_decision(envelope),
            "evidence_completeness": bool(evidence.get("complete")),
            "missing_evidence_count": len(missing),
            "negative_evidence_count": len(negative),
            "rejection_reason_codes": rejection_codes,
            "memory_feedback_summary": {
                "lesson_count": len(memory.get("lessons", [])),
                "suppression_count": len(memory.get("suppressions", [])),
                "prioritization_hint_count": len(memory.get("prioritization_hints", [])),
            },
            "do_not_retest": list(memory.get("suppressions", [])),
            "eligible_for_more_offline_research": _operator_decision(envelope)
            == "ELIGIBLE_FOR_MORE_OFFLINE_RESEARCH",
            "created_at_utc": envelope["created_at_utc"],
            "fixture_or_sample_not_production_evidence": source_mode in {"offline_fixture", "offline_sample"},
            "authority": _authority(),
        }
    )


def build_run_registry(artifact_paths: tuple[Path, ...]) -> OfflineRunRegistry:
    entries_by_run: dict[str, OfflineRunRegistryEntry] = {}
    for path in artifact_paths:
        envelope = artifacts.read_artifact(path)
        entry = _entry_from_envelope(envelope, path)
        run_id = str(entry.payload["run_id"])
        entries_by_run.setdefault(run_id, entry)
    return OfflineRunRegistry(entries=tuple(entries_by_run[key] for key in sorted(entries_by_run)))


def validate_registry(registry: OfflineRunRegistry) -> list[str]:
    errors: list[str] = []
    ids = [str(entry.payload.get("run_id")) for entry in registry.entries]
    if len(ids) != len(set(ids)):
        errors.append("duplicate_run_id")
    for entry in registry.entries:
        payload = entry.payload
        if payload.get("authority") != _authority():
            errors.append(f"authority_not_denied:{payload.get('run_id')}")
        if payload.get("source_mode") in {"offline_fixture", "offline_sample"} and not payload.get(
            "fixture_or_sample_not_production_evidence"
        ):
            errors.append(f"fixture_sample_marked_empirical:{payload.get('run_id')}")
    return errors


def write_run_registry(registry: OfflineRunRegistry, output_dir: Path) -> Path:
    errors = validate_registry(registry)
    if errors:
        raise ValueError(";".join(errors))
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "governed_offline_run_registry.json"
    normalized = path.as_posix()
    if normalized in FROZEN_OUTPUTS or any(normalized.endswith(output) for output in FROZEN_OUTPUTS):
        raise ValueError(f"unsafe_registry_path:{normalized}")
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(registry.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)
    return path


__all__ = [
    "OfflineRunRegistry",
    "OfflineRunRegistryEntry",
    "build_run_registry",
    "validate_registry",
    "write_run_registry",
]
