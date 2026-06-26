from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from research import qre_behavior_thesis_registry as thesis_registry


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_behavior_thesis_evidence"
MODULE_VERSION: Final[str] = "ade-qre-017m-2026-06-26"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_behavior_thesis_evidence")
LATEST_NAME: Final[str] = "latest.json"
DOC_PATH: Final[Path] = Path("docs/governance/qre_behavior_thesis_evidence.md")
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_behavior_thesis_evidence/",
    "docs/governance/qre_behavior_thesis_evidence.md",
)
DEFAULT_DISCOVERY_DIGEST_PATH: Final[Path] = Path(
    "logs/hypothesis_discovery_minimal/latest.json"
)
DEFAULT_VALIDATION_RESULTS_PATH: Final[Path] = Path(
    "logs/qre_hypothesis_validation_results/latest.json"
)
DEFAULT_EVIDENCE_UPDATES_PATH: Final[Path] = Path(
    "logs/qre_hypothesis_evidence_updates/latest.json"
)

STANCE_VALUES: Final[tuple[str, ...]] = (
    "supporting",
    "contradicting",
    "unresolved",
)
ITEM_STATUS_VALUES: Final[tuple[str, ...]] = (
    "present",
    "missing",
    "blocked",
)
EVIDENCE_KIND_VALUES: Final[tuple[str, ...]] = (
    "strategy_hypothesis_catalog",
    "behavior_catalog",
    "roadmap_manifest",
    "discovery_behavior_catalog",
    "discovery_digest_item",
    "discovery_digest_seed",
    "disposition_memory",
    "validation_result",
    "evidence_update",
    "blocked_plan",
    "blocked_requirement",
    "blocked_scalar_state",
    "missing_validation_result",
    "missing_evidence_update",
)
SUMMARY_STATUS_VALUES: Final[tuple[str, ...]] = (
    "support_visible",
    "support_and_unresolved_visible",
    "support_and_contradiction_visible",
    "support_contradiction_and_unresolved_visible",
)
ROW_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "thesis_id",
    "source_hypothesis_id",
    "behavior_family",
    "thesis_status",
    "summary_status",
    "supporting_evidence_count",
    "contradicting_evidence_count",
    "unresolved_evidence_count",
    "evidence_items",
    "provenance_refs",
    "schema_version",
)
ITEM_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "evidence_id",
    "thesis_id",
    "stance",
    "evidence_kind",
    "evidence_ref",
    "status",
    "linked_by",
    "provenance_refs",
)


@dataclass(frozen=True)
class ThesisEvidenceItem:
    evidence_id: str
    thesis_id: str
    stance: str
    evidence_kind: str
    evidence_ref: str
    status: str
    linked_by: str
    provenance_refs: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "thesis_id": self.thesis_id,
            "stance": self.stance,
            "evidence_kind": self.evidence_kind,
            "evidence_ref": self.evidence_ref,
            "status": self.status,
            "linked_by": self.linked_by,
            "provenance_refs": list(self.provenance_refs),
            "authority": {
                "can_generate_executable_strategy": False,
                "can_register_strategy": False,
                "can_promote_candidate": False,
                "can_launch_campaign": False,
                "can_activate_paper_shadow_live": False,
                "evidence_authority": "context_only",
            },
        }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique(values: list[Any] | tuple[Any, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in out:
            out.append(text)
    return tuple(out)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in WRITE_PREFIXES):
        raise ValueError(
            f"qre_behavior_thesis_evidence: refusing write outside allowlist: {path!r}"
        )


def _sha(value: Any) -> str:
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _evidence_id(
    *,
    thesis_id: str,
    stance: str,
    evidence_kind: str,
    evidence_ref: str,
) -> str:
    digest = _sha(
        {
            "thesis_id": thesis_id,
            "stance": stance,
            "evidence_kind": evidence_kind,
            "evidence_ref": evidence_ref,
        }
    )
    return f"qte_{digest[:16]}"


def _support_kind(ref: str) -> str:
    if ref.startswith("research/strategy_hypothesis_catalog.py#"):
        return "strategy_hypothesis_catalog"
    if ref.startswith("research/qre_behavior_catalog.py#"):
        return "behavior_catalog"
    if ref.startswith("research/hypothesis_discovery/behavior_catalog.py#"):
        return "discovery_behavior_catalog"
    return "roadmap_manifest"


def _item(
    *,
    thesis_id: str,
    stance: str,
    evidence_kind: str,
    evidence_ref: str,
    status: str,
    linked_by: str,
    provenance_refs: list[str] | tuple[str, ...],
) -> ThesisEvidenceItem:
    return ThesisEvidenceItem(
        evidence_id=_evidence_id(
            thesis_id=thesis_id,
            stance=stance,
            evidence_kind=evidence_kind,
            evidence_ref=evidence_ref,
        ),
        thesis_id=thesis_id,
        stance=stance,
        evidence_kind=evidence_kind,
        evidence_ref=evidence_ref,
        status=status,
        linked_by=linked_by,
        provenance_refs=_unique(provenance_refs),
    )


def _summary_status(
    *,
    supporting_count: int,
    contradicting_count: int,
    unresolved_count: int,
) -> str:
    if contradicting_count and unresolved_count:
        return "support_contradiction_and_unresolved_visible"
    if contradicting_count:
        return "support_and_contradiction_visible"
    if unresolved_count:
        return "support_and_unresolved_visible"
    return "support_visible"


def _read_rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get(field)
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _registry_row_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        _text(row.get("thesis_id")): row
        for row in rows
        if _text(row.get("thesis_id"))
    }


def _discovery_links(
    discovery_payload: dict[str, Any] | None,
    *,
    source_hypothesis_id: str,
) -> tuple[list[str], list[str]]:
    item_refs: list[str] = []
    seed_refs: list[str] = []
    for index, row in enumerate(_read_rows(discovery_payload, "items")):
        if _text(row.get("hypothesis_id")) == source_hypothesis_id:
            item_refs.append(f"{DEFAULT_DISCOVERY_DIGEST_PATH.as_posix()}#items[{index}]")
    for index, row in enumerate(_read_rows(discovery_payload, "seeds")):
        if _text(row.get("strategy_mapping_ref")) == (
            f"strategy_hypothesis_catalog:{source_hypothesis_id}"
        ):
            seed_refs.append(f"{DEFAULT_DISCOVERY_DIGEST_PATH.as_posix()}#seeds[{index}]")
    return (item_refs, seed_refs)


def _validation_links(
    validation_payload: dict[str, Any] | None,
    *,
    source_hypothesis_id: str,
) -> list[str]:
    refs: list[str] = []
    for index, row in enumerate(_read_rows(validation_payload, "validation_results")):
        if _text(row.get("hypothesis_id")) == source_hypothesis_id:
            refs.append(f"{DEFAULT_VALIDATION_RESULTS_PATH.as_posix()}#validation_results[{index}]")
    return refs


def _update_links(
    update_payload: dict[str, Any] | None,
    *,
    source_hypothesis_id: str,
) -> list[str]:
    refs: list[str] = []
    for index, row in enumerate(_read_rows(update_payload, "evidence_updates")):
        if _text(row.get("hypothesis_id")) == source_hypothesis_id:
            refs.append(f"{DEFAULT_EVIDENCE_UPDATES_PATH.as_posix()}#evidence_updates[{index}]")
    return refs


def _blocked_items(row: dict[str, Any]) -> list[ThesisEvidenceItem]:
    thesis_id = _text(row.get("thesis_id"))
    provenance = list(row.get("provenance_refs") or [])
    items: list[ThesisEvidenceItem] = []
    for field in (
        "falsification_plan",
        "screening_plan",
        "validation_plan",
        "oos_plan",
        "null_controls",
        "source_requirements",
    ):
        for value in row.get(field) or []:
            text = _text(value)
            if not text.startswith("blocked:"):
                continue
            evidence_kind = "blocked_requirement" if field == "source_requirements" else "blocked_plan"
            items.append(
                _item(
                    thesis_id=thesis_id,
                    stance="unresolved",
                    evidence_kind=evidence_kind,
                    evidence_ref=f"state:{field}:{text}",
                    status="blocked",
                    linked_by=field,
                    provenance_refs=provenance,
                )
            )
    for field in ("minimum_sample", "universe", "regime_context"):
        text = _text(row.get(field))
        if not text.startswith("blocked:"):
            continue
        items.append(
            _item(
                thesis_id=thesis_id,
                stance="unresolved",
                evidence_kind="blocked_scalar_state",
                evidence_ref=f"state:{field}:{text}",
                status="blocked",
                linked_by=field,
                provenance_refs=provenance,
            )
        )
    return items


def _dedupe_items(items: list[ThesisEvidenceItem]) -> tuple[list[ThesisEvidenceItem], int]:
    unique: list[ThesisEvidenceItem] = []
    seen: set[tuple[str, str, str, str]] = set()
    duplicates = 0
    for item in items:
        key = (item.thesis_id, item.stance, item.evidence_kind, item.evidence_ref)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(item)
    unique.sort(key=lambda row: row.evidence_id)
    return (unique, duplicates)


def _build_row(
    row: dict[str, Any],
    *,
    discovery_payload: dict[str, Any] | None,
    validation_payload: dict[str, Any] | None,
    update_payload: dict[str, Any] | None,
) -> tuple[dict[str, Any], int]:
    thesis_id = _text(row.get("thesis_id"))
    source_hypothesis_id = _text(row.get("source_hypothesis_id"))
    provenance = list(row.get("provenance_refs") or [])
    items: list[ThesisEvidenceItem] = []

    for ref in row.get("supporting_evidence") or []:
        text = _text(ref)
        if not text:
            continue
        items.append(
            _item(
                thesis_id=thesis_id,
                stance="supporting",
                evidence_kind=_support_kind(text),
                evidence_ref=text,
                status="present",
                linked_by="behavior_thesis_registry",
                provenance_refs=provenance or [text],
            )
        )

    for ref in row.get("contradicting_evidence") or []:
        text = _text(ref)
        if not text:
            continue
        items.append(
            _item(
                thesis_id=thesis_id,
                stance="contradicting",
                evidence_kind="disposition_memory",
                evidence_ref=(
                    f"state:{text}" if text.startswith("none_recorded:") else text
                ),
                status="missing" if text.startswith("none_recorded:") else "present",
                linked_by="behavior_thesis_registry",
                provenance_refs=provenance
                + [thesis_registry.DEFAULT_DISPOSITION_MEMORY_PATH.as_posix()],
            )
        )

    discovery_item_refs, discovery_seed_refs = _discovery_links(
        discovery_payload,
        source_hypothesis_id=source_hypothesis_id,
    )
    for ref in discovery_item_refs:
        items.append(
            _item(
                thesis_id=thesis_id,
                stance="supporting",
                evidence_kind="discovery_digest_item",
                evidence_ref=ref,
                status="present",
                linked_by="source_hypothesis_id",
                provenance_refs=provenance + [DEFAULT_DISCOVERY_DIGEST_PATH.as_posix()],
            )
        )
    for ref in discovery_seed_refs:
        items.append(
            _item(
                thesis_id=thesis_id,
                stance="supporting",
                evidence_kind="discovery_digest_seed",
                evidence_ref=ref,
                status="present",
                linked_by="strategy_mapping_ref",
                provenance_refs=provenance + [DEFAULT_DISCOVERY_DIGEST_PATH.as_posix()],
            )
        )

    validation_refs = _validation_links(
        validation_payload,
        source_hypothesis_id=source_hypothesis_id,
    )
    if validation_refs:
        for ref in validation_refs:
            items.append(
                _item(
                    thesis_id=thesis_id,
                    stance="supporting",
                    evidence_kind="validation_result",
                    evidence_ref=ref,
                    status="present",
                    linked_by="source_hypothesis_id",
                    provenance_refs=provenance + [DEFAULT_VALIDATION_RESULTS_PATH.as_posix()],
                )
            )
    else:
        items.append(
            _item(
                thesis_id=thesis_id,
                stance="unresolved",
                evidence_kind="missing_validation_result",
                evidence_ref=f"state:missing_validation_result:{source_hypothesis_id}",
                status="missing",
                linked_by="source_hypothesis_id",
                provenance_refs=provenance + [DEFAULT_VALIDATION_RESULTS_PATH.as_posix()],
            )
        )

    update_refs = _update_links(update_payload, source_hypothesis_id=source_hypothesis_id)
    if update_refs:
        for ref in update_refs:
            items.append(
                _item(
                    thesis_id=thesis_id,
                    stance="supporting",
                    evidence_kind="evidence_update",
                    evidence_ref=ref,
                    status="present",
                    linked_by="source_hypothesis_id",
                    provenance_refs=provenance + [DEFAULT_EVIDENCE_UPDATES_PATH.as_posix()],
                )
            )
    else:
        items.append(
            _item(
                thesis_id=thesis_id,
                stance="unresolved",
                evidence_kind="missing_evidence_update",
                evidence_ref=f"state:missing_evidence_update:{source_hypothesis_id}",
                status="missing",
                linked_by="source_hypothesis_id",
                provenance_refs=provenance + [DEFAULT_EVIDENCE_UPDATES_PATH.as_posix()],
            )
        )

    items.extend(_blocked_items(row))
    if not any(item.stance == "unresolved" for item in items):
        items.append(
            _item(
                thesis_id=thesis_id,
                stance="unresolved",
                evidence_kind="missing_evidence_update",
                evidence_ref=f"state:none_recorded:unresolved_evidence:{source_hypothesis_id}",
                status="missing",
                linked_by="fail_closed_unresolved_state",
                provenance_refs=provenance,
            )
        )
    unique_items, duplicates = _dedupe_items(items)
    payload_items = [item.to_payload() for item in unique_items]
    supporting_count = sum(1 for item in unique_items if item.stance == "supporting")
    contradicting_count = sum(1 for item in unique_items if item.stance == "contradicting")
    unresolved_count = sum(1 for item in unique_items if item.stance == "unresolved")
    payload = {
        "thesis_id": thesis_id,
        "source_hypothesis_id": source_hypothesis_id,
        "behavior_family": _text(row.get("behavior_family")),
        "thesis_status": _text(row.get("status")),
        "summary_status": _summary_status(
            supporting_count=supporting_count,
            contradicting_count=contradicting_count,
            unresolved_count=unresolved_count,
        ),
        "supporting_evidence_count": supporting_count,
        "contradicting_evidence_count": contradicting_count,
        "unresolved_evidence_count": unresolved_count,
        "evidence_items": payload_items,
        "provenance_refs": list(_unique(provenance)),
        "schema_version": SCHEMA_VERSION,
    }
    return (payload, duplicates)


def validate_thesis_evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    rejections: list[str] = []
    missing = [field for field in ROW_REQUIRED_FIELDS if not row.get(field)]
    if missing:
        rejections.append("missing_required_fields")
    if _text(row.get("summary_status")) not in SUMMARY_STATUS_VALUES:
        rejections.append("invalid_summary_status")
    if _text(row.get("schema_version")) != SCHEMA_VERSION:
        rejections.append("invalid_schema_version")
    items = row.get("evidence_items") if isinstance(row.get("evidence_items"), list) else []
    if not items:
        rejections.append("missing_evidence_items")
    supporting = 0
    contradicting = 0
    unresolved = 0
    seen_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            rejections.append("invalid_evidence_item_shape")
            continue
        if any(not item.get(field) for field in ITEM_REQUIRED_FIELDS):
            rejections.append("missing_item_fields")
        if _text(item.get("stance")) not in STANCE_VALUES:
            rejections.append("invalid_stance")
        if _text(item.get("evidence_kind")) not in EVIDENCE_KIND_VALUES:
            rejections.append("invalid_evidence_kind")
        if _text(item.get("status")) not in ITEM_STATUS_VALUES:
            rejections.append("invalid_item_status")
        if _text(item.get("evidence_id")) in seen_ids:
            rejections.append("duplicate_evidence_id")
        seen_ids.add(_text(item.get("evidence_id")))
        authority = item.get("authority") if isinstance(item.get("authority"), dict) else {}
        if authority.get("can_generate_executable_strategy") is not False:
            rejections.append("strategy_generation_authority_forbidden")
        if authority.get("can_register_strategy") is not False:
            rejections.append("strategy_registration_authority_forbidden")
        if authority.get("can_launch_campaign") is not False:
            rejections.append("campaign_authority_forbidden")
        stance = _text(item.get("stance"))
        if stance == "supporting":
            supporting += 1
        elif stance == "contradicting":
            contradicting += 1
        elif stance == "unresolved":
            unresolved += 1
    if supporting == 0:
        rejections.append("missing_supporting_evidence_visibility")
    if contradicting == 0:
        rejections.append("missing_contradicting_evidence_visibility")
    if unresolved == 0:
        rejections.append("missing_unresolved_evidence_visibility")
    return {
        "valid": not rejections,
        "rejection_reasons": list(dict.fromkeys(rejections)),
        "thesis_id": _text(row.get("thesis_id")),
    }


def build_behavior_thesis_evidence(
    *,
    repo_root: Path = Path("."),
    registry_report: dict[str, Any] | None = None,
    discovery_digest_path: Path = DEFAULT_DISCOVERY_DIGEST_PATH,
    validation_results_path: Path = DEFAULT_VALIDATION_RESULTS_PATH,
    evidence_updates_path: Path = DEFAULT_EVIDENCE_UPDATES_PATH,
) -> dict[str, Any]:
    upstream = registry_report or thesis_registry.build_behavior_thesis_registry(
        repo_root=repo_root
    )
    registry_rows = _read_rows(upstream, "rows")
    discovery_payload = _read_json(repo_root / discovery_digest_path)
    validation_payload = _read_json(repo_root / validation_results_path)
    update_payload = _read_json(repo_root / evidence_updates_path)
    rows: list[dict[str, Any]] = []
    duplicate_count = 0
    for row in sorted(registry_rows, key=lambda item: _text(item.get("thesis_id"))):
        payload, duplicates = _build_row(
            row,
            discovery_payload=discovery_payload,
            validation_payload=validation_payload,
            update_payload=update_payload,
        )
        duplicate_count += duplicates
        rows.append(payload)
    validations = [validate_thesis_evidence_row(row) for row in rows]
    invalid_rows = [row for row in validations if not row["valid"]]
    supporting_item_count = sum(int(row["supporting_evidence_count"]) for row in rows)
    contradicting_item_count = sum(int(row["contradicting_evidence_count"]) for row in rows)
    unresolved_item_count = sum(int(row["unresolved_evidence_count"]) for row in rows)
    contradiction_visible_count = sum(
        1 for row in rows if int(row["contradicting_evidence_count"]) > 0
    )
    unresolved_visible_count = sum(
        1 for row in rows if int(row["unresolved_evidence_count"]) > 0
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "rows": rows,
        "summary": {
            "status": "ready" if not invalid_rows else "not_ready",
            "thesis_count": len(rows),
            "invalid_row_count": len(invalid_rows),
            "supporting_item_count": supporting_item_count,
            "contradicting_item_count": contradicting_item_count,
            "unresolved_item_count": unresolved_item_count,
            "duplicate_item_count": duplicate_count,
            "thesises_with_visible_contradictions": contradiction_visible_count,
            "thesises_with_unresolved_evidence": unresolved_visible_count,
            "blocking_reasons": sorted(
                {reason for row in invalid_rows for reason in row["rejection_reasons"]}
            ),
            "operator_summary": (
                "Behavior-thesis evidence stays read-only and context-only. "
                "Supporting evidence, contradictions, and unresolved states "
                "remain explicit per thesis with provenance."
            ),
            "final_recommendation": (
                "behavior_thesis_evidence_ready"
                if not invalid_rows
                else "repair_behavior_thesis_evidence_contract_gaps"
            ),
        },
        "validations": validations,
        "artifact_references": {
            "behavior_thesis_registry": "logs/qre_behavior_thesis_registry/latest.json",
            "hypothesis_discovery_digest": discovery_digest_path.as_posix(),
            "validation_results": validation_results_path.as_posix(),
            "evidence_updates": evidence_updates_path.as_posix(),
        },
        "safety_invariants": {
            "read_only": True,
            "uses_local_artifacts_only": True,
            "uses_network": False,
            "uses_subprocess": False,
            "can_generate_executable_strategy": False,
            "can_register_strategy": False,
            "can_promote_candidate": False,
            "can_launch_campaign": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    lines = [
        "# QRE Behavior Thesis Evidence",
        "",
        "This surface is read-only. It keeps supporting evidence, contradictions, and unresolved evidence explicit per thesis and does not generate strategies, register strategies, or launch campaigns.",
        "",
        f"- status: `{_text(summary.get('status'))}`",
        f"- thesis_count: `{int(summary.get('thesis_count') or 0)}`",
        f"- invalid_row_count: `{int(summary.get('invalid_row_count') or 0)}`",
        f"- supporting_item_count: `{int(summary.get('supporting_item_count') or 0)}`",
        f"- contradicting_item_count: `{int(summary.get('contradicting_item_count') or 0)}`",
        f"- unresolved_item_count: `{int(summary.get('unresolved_item_count') or 0)}`",
        f"- final_recommendation: `{_text(summary.get('final_recommendation'))}`",
        "",
        "| thesis_id | behavior_family | thesis_status | support | contradict | unresolved |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _text(row.get("thesis_id")),
                    _text(row.get("behavior_family")),
                    _text(row.get("thesis_status")),
                    str(int(row.get("supporting_evidence_count") or 0)),
                    str(int(row.get("contradicting_evidence_count") or 0)),
                    str(int(row.get("unresolved_evidence_count") or 0)),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Contradictions stay visible even when the current state is `none_recorded:*`, and unresolved items stay explicit when validation or evidence-update linkage is still missing.",
        ]
    )
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    doc_path: Path = DOC_PATH,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    latest = repo_root / output_dir / LATEST_NAME
    doc = repo_root / doc_path
    latest.parent.mkdir(parents=True, exist_ok=True)
    doc.parent.mkdir(parents=True, exist_ok=True)
    _validate_write_target(latest)
    _validate_write_target(doc)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_doc = doc.with_suffix(doc.suffix + ".tmp")
    tmp_doc.write_text(render_markdown(report) + "\n", encoding="utf-8")
    os.replace(tmp_doc, doc)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "doc": doc.relative_to(repo_root).as_posix(),
    }


def read_behavior_thesis_evidence_status(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    path = repo_root / output_dir / LATEST_NAME
    payload = _read_json(path)
    if not payload:
        return {
            "status": "missing_behavior_thesis_evidence",
            "path": path.relative_to(repo_root).as_posix(),
            "fails_closed": True,
        }
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "status": _text(summary.get("status")) or "unknown",
        "path": path.relative_to(repo_root).as_posix(),
        "fails_closed": _text(summary.get("status")) != "ready",
        "schema_version": _text(payload.get("schema_version")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_behavior_thesis_evidence",
        description="Build the deterministic QRE behavior thesis evidence surface.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_behavior_thesis_evidence()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
