from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import qre_ade018_common as common

REPORT_KIND: Final[str] = "qre_evidence_reason_record_completion"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-018f-2026-06-29"
ARTIFACT_DIR: Final[Path] = Path("logs/qre_evidence_reason_record_completion")
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = Path("docs/governance/qre_evidence_reason_record_completion.md")
DEFAULT_REGISTRY_PATH: Final[Path] = Path("logs/qre_behavior_thesis_registry/latest.json")
DEFAULT_EVIDENCE_PATH: Final[Path] = Path("logs/qre_behavior_thesis_evidence/latest.json")
DEFAULT_REASON_MATURITY_PATH: Final[Path] = Path("logs/qre_reason_record_maturity/latest.json")
DEFAULT_REASON_AUDIT_PATH: Final[Path] = Path("logs/qre_reason_record_audit/latest.json")
DEFAULT_DECAY_PATH: Final[Path] = Path("logs/qre_evidence_decay/latest.json")
DEFAULT_OPERATOR_PATH: Final[Path] = Path("logs/qre_operator_decision_report/latest.json")
DEFAULT_WHY_PATH: Final[Path] = Path("logs/qre_why_surfaces/latest.json")
DEFAULT_LINEAGE_PATH: Final[Path] = Path("logs/qre_contradiction_hypothesis_lineage/latest.json")
VALID_STATES: Final[tuple[str, ...]] = (
    "PRESENT_AUTHORITATIVE",
    "PRESENT_CONTEXT_ONLY",
    "PRESENT_STALE",
    "PRESENT_CONTRADICTED",
    "MISSING",
    "BLOCKED",
    "NOT_APPLICABLE",
)
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_evidence_reason_record_completion/",
    "docs/governance/qre_evidence_reason_record_completion.md",
)


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(normalized.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def _state_for(
    *,
    has_visible_evidence: bool,
    has_visible_reasons: bool,
    stale_visible: bool,
    contradiction_visible: bool,
    blocked_visible: bool,
    authoritative_ready: bool,
) -> str:
    if authoritative_ready:
        return "PRESENT_AUTHORITATIVE"
    if stale_visible:
        return "PRESENT_STALE"
    if contradiction_visible:
        return "PRESENT_CONTRADICTED"
    if blocked_visible:
        return "BLOCKED"
    if has_visible_evidence or has_visible_reasons:
        return "PRESENT_CONTEXT_ONLY"
    return "MISSING"


def collect_snapshot(
    *,
    repo_root: Path | None = None,
    registry_path: Path | None = None,
    evidence_path: Path | None = None,
    reason_maturity_path: Path | None = None,
    reason_audit_path: Path | None = None,
    decay_path: Path | None = None,
    operator_path: Path | None = None,
    why_path: Path | None = None,
    lineage_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    registry = common.read_json(root / (registry_path or DEFAULT_REGISTRY_PATH)) or {}
    evidence = common.read_json(root / (evidence_path or DEFAULT_EVIDENCE_PATH)) or {}
    reason_maturity = common.read_json(root / (reason_maturity_path or DEFAULT_REASON_MATURITY_PATH)) or {}
    reason_audit = common.read_json(root / (reason_audit_path or DEFAULT_REASON_AUDIT_PATH)) or {}
    decay = common.read_json(root / (decay_path or DEFAULT_DECAY_PATH)) or {}
    operator = common.read_json(root / (operator_path or DEFAULT_OPERATOR_PATH)) or {}
    why = common.read_json(root / (why_path or DEFAULT_WHY_PATH)) or {}
    lineage = common.read_json(root / (lineage_path or DEFAULT_LINEAGE_PATH)) or {}

    registry_rows = common.rows(registry, "rows")
    evidence_by_thesis = common.index_by(common.rows(evidence, "rows"), "thesis_id")
    decay_by_thesis = common.index_by(common.rows(decay, "rows"), "thesis_id")
    operator_by_hypothesis = common.index_by(common.rows(operator, "rows"), "source_hypothesis_id")
    why_by_hypothesis = common.index_by(common.rows(why, "rows"), "source_hypothesis_id")
    lineage_by_hypothesis = common.index_by(common.rows(lineage, "rows"), "source_hypothesis_id")
    reason_maturity_summary = dict(reason_maturity.get("summary") or {})
    reason_audit_summary = dict(reason_audit.get("summary") or {})
    manifest_total = int(reason_audit_summary.get("reason_records_manifest_total") or 0)
    missing_ref_count = int((reason_audit_summary.get("missing_ref_class_counts") or {}).get("evidence_refs_missing") or 0)

    rows_out: list[dict[str, Any]] = []
    for registry_row in sorted(registry_rows, key=lambda item: common.text(item.get("source_hypothesis_id"))):
        thesis_id = common.text(registry_row.get("thesis_id"))
        source_hypothesis_id = common.text(registry_row.get("source_hypothesis_id"))
        evidence_row = evidence_by_thesis.get(thesis_id, {})
        decay_row = decay_by_thesis.get(thesis_id, {})
        operator_row = operator_by_hypothesis.get(source_hypothesis_id, {})
        why_row = why_by_hypothesis.get(source_hypothesis_id, {})
        lineage_row = lineage_by_hypothesis.get(source_hypothesis_id, {})
        blocking_reasons = common.normalize_list(decay_row.get("blocking_reasons"))
        has_visible_evidence = (
            int(evidence_row.get("supporting_evidence_count") or 0) > 0
            or int(evidence_row.get("contradicting_evidence_count") or 0) > 0
            or int(evidence_row.get("unresolved_evidence_count") or 0) > 0
        )
        has_visible_reasons = bool(common.normalize_list(operator_row.get("primary_reasons")))
        stale_visible = "stale_or_superseded_artifacts_visible" in blocking_reasons
        contradiction_visible = "contradicting_evidence_visible" in blocking_reasons or int(evidence_row.get("contradicting_evidence_count") or 0) > 0
        blocked_visible = bool(common.normalize_list(lineage_row.get("missing_lineage_fields"))) or any(
            token in blocking_reasons
            for token in ("missing_source_identity", "missing_data_snapshot_identity", "missing_campaign_identity")
        )
        authoritative_ready = (
            manifest_total > 0
            and missing_ref_count == 0
            and not bool(decay_row.get("decay_blocks_readiness"))
            and bool(lineage_row.get("lineage_complete"))
        )
        evidence_state = _state_for(
            has_visible_evidence=has_visible_evidence,
            has_visible_reasons=has_visible_reasons,
            stale_visible=stale_visible,
            contradiction_visible=contradiction_visible,
            blocked_visible=blocked_visible,
            authoritative_ready=authoritative_ready,
        )
        reason_record_state = (
            "PRESENT_AUTHORITATIVE"
            if manifest_total > 0 and missing_ref_count == 0 and has_visible_reasons
            else "PRESENT_CONTEXT_ONLY"
            if has_visible_reasons or int(reason_maturity_summary.get("record_count") or 0) > 0
            else "MISSING"
        )
        operator_report_state = (
            "PRESENT_CONTEXT_ONLY"
            if operator_row and common.text(operator_row.get("next_action")) and has_visible_reasons
            else "MISSING"
        )
        row = {
            "stable_id": f"qrec_{common.stable_digest({'hypothesis': source_hypothesis_id})[:16]}",
            "thesis_id": thesis_id,
            "source_hypothesis_id": source_hypothesis_id,
            "final_decision": common.text(operator_row.get("final_decision")),
            "reason_record_state": reason_record_state,
            "evidence_state": evidence_state,
            "freshness_state": common.text((decay_row.get("dimension_statuses") or {}).get("source_freshness")) or "not_visible",
            "reproducibility_state": common.text((decay_row.get("dimension_statuses") or {}).get("reproducibility")) or "not_visible",
            "validation_state": "PRESENT_CONTEXT_ONLY" if common.text((operator_row.get("funnel_result") or {}).get("status")) else "MISSING",
            "operator_report_state": operator_report_state,
            "contradiction_linkage_state": "PRESENT_CONTEXT_ONLY" if has_visible_evidence else "MISSING",
            "evidence_authority_classification": evidence_state,
            "exact_blocker": (
                common.text(common.normalize_list(blocking_reasons)[0])
                or common.text(common.normalize_list(lineage_row.get("missing_lineage_fields"))[0])
                or "none"
            ),
            "next_action": common.text(operator_row.get("next_action")) or "collect_missing_evidence",
            "provenance_refs": common.dedupe(
                common.normalize_list(registry_row.get("provenance_refs"))
                + common.normalize_list(evidence_row.get("provenance_refs"))
                + common.normalize_list(lineage_row.get("provenance_refs"))
                + common.normalize_list(operator_row.get("provenance_refs"))
                + common.normalize_list(why_row.get("provenance_refs"))
                + [
                    common.rel(root / DEFAULT_REASON_MATURITY_PATH, root),
                    common.rel(root / DEFAULT_REASON_AUDIT_PATH, root),
                    common.rel(root / DEFAULT_DECAY_PATH, root),
                ]
            ),
        }
        for field in ("reason_record_state", "evidence_state", "validation_state", "operator_report_state", "contradiction_linkage_state", "evidence_authority_classification"):
            if row[field] not in VALID_STATES:
                raise ValueError(f"invalid completion state: {field}={row[field]}")
        rows_out.append(row)

    rows_out.sort(key=lambda item: item["source_hypothesis_id"])
    snapshot_core = {"rows": rows_out}
    completion_identity = f"qrec_{common.stable_digest(snapshot_core)[:16]}"
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "completion_identity": completion_identity,
        "rows": rows_out,
        "summary": {
            "thesis_count": len(rows_out),
            "authoritative_count": sum(1 for row in rows_out if row["evidence_state"] == "PRESENT_AUTHORITATIVE"),
            "context_only_count": sum(1 for row in rows_out if row["evidence_state"] == "PRESENT_CONTEXT_ONLY"),
            "blocked_count": sum(1 for row in rows_out if row["evidence_state"] == "BLOCKED"),
            "stale_or_contradicted_count": sum(1 for row in rows_out if row["evidence_state"] in {"PRESENT_STALE", "PRESENT_CONTRADICTED"}),
            "exact_next_action": "complete_validation_reproducibility_and_operator_surfaces",
        },
    }


def _render_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        "# QRE Evidence And Reason-Record Completion",
        "",
        f"- completion_identity: `{common.text(snapshot.get('completion_identity'))}`",
        "",
    ]
    for row in snapshot.get("rows", []):
        if isinstance(row, dict):
            lines.append(
                f"- `{common.text(row.get('source_hypothesis_id'))}`: `{common.text(row.get('evidence_state'))}` / `{common.text(row.get('reason_record_state'))}` -> `{common.text(row.get('next_action'))}`"
            )
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, payload: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_018f.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(snapshot: dict[str, Any]) -> None:
    _atomic_write(ARTIFACT_LATEST, json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    markdown = _render_markdown(snapshot)
    _atomic_write(ARTIFACT_MARKDOWN, markdown)
    _atomic_write(DOC_PATH, markdown)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m reporting.qre_evidence_reason_record_completion")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    snapshot = collect_snapshot()
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
