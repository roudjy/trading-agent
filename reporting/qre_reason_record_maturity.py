from __future__ import annotations

import argparse
import importlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final


REPORT_KIND: Final[str] = "qre_reason_record_maturity"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-017c-2026-06-25"
REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_reason_record_maturity")
LATEST_NAME: Final[str] = "latest.json"
DOC_PATH: Final[Path] = Path("docs/governance/qre_reason_record_maturity.md")
WRITE_PREFIX: Final[str] = "logs/qre_reason_record_maturity/"

_REASON_RECORDS_LOG: Final[Path] = Path("logs/qre_reason_records/latest.jsonl")
_REASON_RECORDS_META: Final[Path] = Path("logs/qre_reason_records/latest.meta.json")
_REASON_RECORD_AUDIT_LOG: Final[Path] = Path("logs/qre_reason_record_audit/latest.json")
_REASON_RECORD_NORMALIZATION_LOG: Final[Path] = Path(
    "logs/qre_reason_record_normalization/latest.json"
)

_MAX_EXAMPLES: Final[int] = 16


def _research_module(name: str) -> Any:
    return importlib.import_module(name)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bounded_list(value: Any, *, limit: int = 16, width: int = 240) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    out: list[str] = []
    for item in value:
        text = _text(item)
        if text and text not in out:
            out.append(text[:width])
    return out[:limit]


def _validate_write_target(path: Path) -> None:
    normalised = path.as_posix()
    if WRITE_PREFIX not in normalised:
        raise ValueError(
            f"qre_reason_record_maturity: refusing write outside allowlist: {path!r}"
        )


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _path_from_ref(ref: str) -> str:
    return ref.split("#", 1)[0].strip()


def _artifact_status(repo_root: Path, relpath: Path) -> dict[str, Any]:
    path = repo_root / relpath
    present = path.is_file()
    size_bytes = path.stat().st_size if present else 0
    return {
        "artifact_path": relpath.as_posix(),
        "present": present,
        "size_bytes": size_bytes,
        "status": "present" if present else "missing",
    }


def _linkage_status(
    *,
    repo_root: Path,
    records: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    rows: list[dict[str, Any]] = []
    missing_counter: Counter[str] = Counter()
    for record in records:
        refs = _bounded_list(record.get("evidence_refs"))
        missing_paths = [
            path_ref
            for path_ref in (_path_from_ref(ref) for ref in refs)
            if not (repo_root / path_ref).is_file()
        ]
        status = (
            "missing_evidence_refs"
            if not refs
            else "unlinked_evidence_refs"
            if missing_paths
            else "linked"
        )
        if status != "linked":
            missing_counter.update([status])
        rows.append(
            {
                "record_id": _text(record.get("record_id"))[:96],
                "record_family": _text(record.get("record_family"))[:96],
                "subject_id": _text(record.get("subject_id"))[:96],
                "evidence_ref_count": len(refs),
                "missing_paths": missing_paths[:8],
                "status": status,
            }
        )
    rows.sort(
        key=lambda row: (
            str(row["status"]),
            str(row["record_family"]),
            str(row["subject_id"]),
        )
    )
    return rows, missing_counter


def _normalization_gap_counts(normalized_records: Sequence[Mapping[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in normalized_records:
        contract = row.get("contract_validation")
        reasons = contract.get("rejection_reasons") if isinstance(contract, Mapping) else []
        for reason in reasons if isinstance(reasons, list) else []:
            text = _text(reason)
            if text:
                counter.update([text])
    return counter


def _producer_rows(
    value: Any,
    *,
    expected_status_key: str,
    count_key: str,
) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        out.append(
            {
                "producer_id": _text(row.get("producer_id")),
                "status": _text(row.get(expected_status_key)),
                "record_count": int(row.get(count_key) or 0),
                "valid_record_count": int(row.get("valid_record_count") or 0),
                "invalid_record_count": int(row.get("invalid_record_count") or 0),
                "subjects_with_evidence_refs": int(
                    row.get("subjects_with_evidence_refs") or 0
                ),
                "expected_subject_count": int(row.get("expected_subject_count") or 0),
                "top_rejection_reasons": dict(
                    sorted((row.get("top_rejection_reasons") or {}).items())
                )
                if isinstance(row.get("top_rejection_reasons"), Mapping)
                else {},
            }
        )
    return out


def _final_recommendation(
    *,
    record_count: int,
    durable_missing_count: int,
    linked_record_count: int,
    invalid_record_count: int,
) -> tuple[str, str]:
    if record_count == 0:
        return (
            "reason_record_maturity_missing_real_evidence_records",
            "materialize_reason_records_from_real_evidence",
        )
    if durable_missing_count > 0:
        return (
            "reason_record_maturity_not_durable",
            "write_reason_record_artifacts_and_reaudit",
        )
    if linked_record_count < record_count:
        return (
            "reason_record_maturity_unlinked_evidence",
            "repair_missing_evidence_refs_before_authority_upgrade",
        )
    if invalid_record_count > 0:
        return (
            "reason_record_maturity_contract_gaps",
            "normalize_reason_record_contract_gaps_before_authority_upgrade",
        )
    return (
        "reason_record_maturity_ready",
        "preserve_reason_record_maturity_visibility",
    )


def collect_snapshot(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
    materialize_supporting_outputs: bool = False,
) -> dict[str, Any]:
    reason_records = _research_module("research.qre_reason_records_v1")
    reason_audit = _research_module("research.qre_reason_record_audit")
    normalization = _research_module("research.qre_reason_record_normalization")

    reason_snapshot = reason_records.build_reason_records_snapshot(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    audit_report = reason_audit.build_reason_record_audit(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    normalization_report = normalization.build_reason_record_normalization(
        repo_root=repo_root,
    )

    if materialize_supporting_outputs:
        reason_records.write_outputs(reason_snapshot, repo_root=repo_root)
        reason_audit.write_outputs(audit_report, repo_root=repo_root)
        normalization.write_outputs(normalization_report, repo_root=repo_root)

    records = [
        row
        for row in (reason_snapshot.get("records") or [])
        if isinstance(row, Mapping)
    ]
    linkage_rows, linkage_counter = _linkage_status(repo_root=repo_root, records=records)
    linked_record_count = sum(1 for row in linkage_rows if row["status"] == "linked")
    durable_artifacts = [
        _artifact_status(repo_root, _REASON_RECORDS_LOG),
        _artifact_status(repo_root, _REASON_RECORDS_META),
        _artifact_status(repo_root, _REASON_RECORD_AUDIT_LOG),
        _artifact_status(repo_root, _REASON_RECORD_NORMALIZATION_LOG),
    ]
    durable_missing_count = sum(1 for row in durable_artifacts if not row["present"])

    normalization_summary = (
        normalization_report.get("summary")
        if isinstance(normalization_report.get("summary"), Mapping)
        else {}
    )
    audit_summary = (
        audit_report.get("summary")
        if isinstance(audit_report.get("summary"), Mapping)
        else {}
    )
    surface_counts = dict(
        sorted((reason_snapshot.get("meta") or {}).get("records_by_surface", {}).items())
    )
    invalid_record_count = int(normalization_summary.get("invalid_record_count") or 0)
    final_recommendation, exact_next_action = _final_recommendation(
        record_count=len(records),
        durable_missing_count=durable_missing_count,
        linked_record_count=linked_record_count,
        invalid_record_count=invalid_record_count,
    )
    contract_gap_counts = dict(
        sorted(_normalization_gap_counts(normalization_report.get("normalized_records") or []).items())
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "summary": {
            "record_count": len(records),
            "records_by_surface": surface_counts,
            "durable_artifact_count": len(durable_artifacts),
            "durable_artifact_missing_count": durable_missing_count,
            "linked_record_count": linked_record_count,
            "unlinked_record_count": len(records) - linked_record_count,
            "invalid_record_count": invalid_record_count,
            "audit_manifest_total": int(
                audit_summary.get("reason_records_manifest_total") or 0
            ),
            "audit_coverage_pct": audit_summary.get("reason_record_coverage_pct"),
            "normalization_ready": bool(
                normalization_summary.get("reason_record_normalization_ready")
            ),
            "normalization_producer_gap_count": int(
                normalization_summary.get("producer_gap_count") or 0
            ),
            "final_recommendation": final_recommendation,
            "exact_next_action": exact_next_action,
            "operator_summary": (
                "Reason-record maturity stays fail-closed until records are durable, "
                "linked to real evidence, and contract-valid across producers."
            ),
        },
        "durable_artifacts": durable_artifacts,
        "audit_producer_rows": _producer_rows(
            audit_report.get("producer_rows"),
            expected_status_key="status",
            count_key="expected_subject_count",
        ),
        "normalization_producer_rows": _producer_rows(
            normalization_report.get("producer_rows"),
            expected_status_key="status",
            count_key="record_count",
        ),
        "contract_gap_counts": contract_gap_counts,
        "linkage_status_counts": dict(sorted(linkage_counter.items())),
        "linkage_examples_top": [
            row for row in linkage_rows if row["status"] != "linked"
        ][: _MAX_EXAMPLES],
        "safety_invariants": {
            "read_only_evaluation": True,
            "materialize_supporting_outputs_writes_logs_only": True,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "no_fake_reasons": True,
        },
    }
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    durable_artifacts = (
        report.get("durable_artifacts") if isinstance(report.get("durable_artifacts"), list) else []
    )
    audit_rows = (
        report.get("audit_producer_rows")
        if isinstance(report.get("audit_producer_rows"), list)
        else []
    )
    normalization_rows = (
        report.get("normalization_producer_rows")
        if isinstance(report.get("normalization_producer_rows"), list)
        else []
    )
    linkage_examples = (
        report.get("linkage_examples_top")
        if isinstance(report.get("linkage_examples_top"), list)
        else []
    )
    contract_gap_counts = (
        report.get("contract_gap_counts")
        if isinstance(report.get("contract_gap_counts"), Mapping)
        else {}
    )
    lines = [
        "# QRE Reason Record Maturity",
        "",
        f"- record_count: {summary.get('record_count') or 0}",
        f"- linked_record_count: {summary.get('linked_record_count') or 0}",
        f"- invalid_record_count: {summary.get('invalid_record_count') or 0}",
        f"- durable_artifact_missing_count: {summary.get('durable_artifact_missing_count') or 0}",
        f"- audit_manifest_total: {summary.get('audit_manifest_total') or 0}",
        f"- audit_coverage_pct: {summary.get('audit_coverage_pct')}",
        f"- final_recommendation: {summary.get('final_recommendation') or ''}",
        f"- exact_next_action: {summary.get('exact_next_action') or ''}",
        "",
        "## Durable Artifacts",
        "| Artifact | Status | Size bytes |",
        "| --- | --- | ---: |",
    ]
    for row in durable_artifacts:
        lines.append(
            f"| {row.get('artifact_path') or ''} | {row.get('status') or ''} | {row.get('size_bytes') or 0} |"
        )
    lines.extend(
        [
            "",
            "## Audit Producers",
            "| Producer | Status | With refs | Expected |",
            "| --- | --- | ---: | ---: |",
        ]
    )
    for row in audit_rows:
        lines.append(
            f"| {row.get('producer_id') or ''} | {row.get('status') or ''} | "
            f"{row.get('subjects_with_evidence_refs') or 0} | {row.get('expected_subject_count') or 0} |"
        )
    lines.extend(
        [
            "",
            "## Normalization Producers",
            "| Producer | Status | Records | Invalid |",
            "| --- | --- | ---: | ---: |",
        ]
    )
    for row in normalization_rows:
        lines.append(
            f"| {row.get('producer_id') or ''} | {row.get('status') or ''} | "
            f"{row.get('record_count') or 0} | {row.get('invalid_record_count') or 0} |"
        )
    lines.extend(
        [
            "",
            "## Contract Gap Counts",
            "| Rejection reason | Count |",
            "| --- | ---: |",
        ]
    )
    if contract_gap_counts:
        for key, value in sorted(contract_gap_counts.items()):
            lines.append(f"| {key} | {value} |")
    else:
        lines.append("| none | 0 |")
    lines.extend(
        [
            "",
            "## Linkage Examples",
            "| Record family | Subject | Status | Missing paths |",
            "| --- | --- | --- | --- |",
        ]
    )
    if linkage_examples:
        for row in linkage_examples:
            missing = ", ".join(row.get("missing_paths") or []) or "-"
            lines.append(
                f"| {row.get('record_family') or ''} | {row.get('subject_id') or ''} | "
                f"{row.get('status') or ''} | {missing} |"
            )
    else:
        lines.append("| none | none | linked | - |")
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    doc_path = repo_root / DOC_PATH
    _validate_write_target(latest)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_md = doc_path.with_suffix(doc_path.suffix + ".tmp")
    tmp_md.write_text(render_markdown(report) + "\n", encoding="utf-8")
    os.replace(tmp_md, doc_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "doc": DOC_PATH.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_reason_record_maturity",
        description="Build the ADE-QRE-017C reason-record maturity report.",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--max-candidates", type=int, default=15)
    args = parser.parse_args(argv)
    report = collect_snapshot(
        max_candidates=args.max_candidates,
        materialize_supporting_outputs=args.write,
    )
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
