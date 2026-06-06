from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_real_basket_diagnosis as basket_diagnosis
from research import qre_routing_readiness_from_basket as routing_readiness
from research import qre_sampling_readiness_from_basket as sampling_readiness


REPORT_KIND: Final[str] = "qre_reason_record_audit"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_reason_record_audit")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
_WRITE_PREFIX: Final[str] = "logs/qre_reason_record_audit/"
_SOURCE_QUALITY_PATH: Final[Path] = Path("logs/qre_data_source_quality_readiness/latest.json")
_FAILURE_ACTION_PATH: Final[Path] = Path("logs/failure_action_mapping_minimal/latest.json")
_REASON_RECORD_MANIFEST_PATH: Final[Path] = Path("logs/reason_records/manifest.v1.json")
_PAPER_READINESS_PATH: Final[Path] = Path("research/paper_readiness_latest.v1.json")
_MAX_EXAMPLES: Final[int] = 8


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _bounded_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text and text not in out:
            out.append(text[:160])
    return out[:16]


def _producer_rows_from_basket(repo_root: Path, max_candidates: int) -> list[dict[str, Any]]:
    report = basket_diagnosis.build_real_basket_diagnosis(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    rows = report.get("rows")
    return list(rows) if isinstance(rows, list) else []


def _producer_rows_from_routing(repo_root: Path, max_candidates: int) -> list[dict[str, Any]]:
    report = routing_readiness.build_routing_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    rows = report.get("rows")
    return list(rows) if isinstance(rows, list) else []


def _producer_rows_from_sampling(repo_root: Path, max_candidates: int) -> list[dict[str, Any]]:
    report = sampling_readiness.build_sampling_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    rows = report.get("rows")
    return list(rows) if isinstance(rows, list) else []


def _producer_rows_from_source_quality(repo_root: Path) -> list[dict[str, Any]]:
    payload = _read_json(repo_root / _SOURCE_QUALITY_PATH)
    rows = payload.get("rows") if isinstance(payload, Mapping) else None
    return list(rows) if isinstance(rows, list) else []


def _producer_rows_from_failure_action(repo_root: Path) -> list[dict[str, Any]]:
    payload = _read_json(repo_root / _FAILURE_ACTION_PATH)
    rows = payload.get("items") if isinstance(payload, Mapping) else None
    return list(rows) if isinstance(rows, list) else []


def _producer_rows_from_paper_readiness(repo_root: Path) -> list[dict[str, Any]]:
    payload = _read_json(repo_root / _PAPER_READINESS_PATH)
    rows = payload.get("entries") if isinstance(payload, Mapping) else None
    return list(rows) if isinstance(rows, list) else []


def _manifest_total_records(repo_root: Path) -> int:
    payload = _read_json(repo_root / _REASON_RECORD_MANIFEST_PATH)
    return int(payload.get("total_records") or 0) if isinstance(payload, Mapping) else 0


def _subject_id_for(producer_id: str, row: Mapping[str, Any], index: int) -> str:
    if producer_id == "real_basket_diagnosis":
        return str(row.get("candidate_id") or f"basket:{index}")
    if producer_id in {"routing_readiness_from_basket", "sampling_readiness_from_basket"}:
        return str(row.get("candidate_id") or f"readiness:{index}")
    if producer_id == "source_quality_readiness":
        instrument = str(row.get("instrument") or "unknown")
        timeframe = str(row.get("timeframe") or "unknown")
        return f"{instrument}:{timeframe}"
    if producer_id == "failure_action_mapping":
        return str(row.get("subject_id") or f"failure:{index}")
    if producer_id == "paper_readiness_blockers":
        return str(row.get("candidate_id") or f"paper:{index}")
    return f"{producer_id}:{index}"


def _reason_codes_for(producer_id: str, row: Mapping[str, Any]) -> list[str]:
    if producer_id == "real_basket_diagnosis":
        return [str(row.get("reason_code") or "")] if row.get("reason_code") else []
    if producer_id in {"routing_readiness_from_basket", "sampling_readiness_from_basket"}:
        return [str(row.get("primary_reason_code") or "")] if row.get("primary_reason_code") else []
    if producer_id == "source_quality_readiness":
        return [str(row.get("quality_status") or "")] if row.get("quality_status") else []
    if producer_id == "failure_action_mapping":
        reason_record = row.get("reason_record")
        return _bounded_list(reason_record.get("reason_codes")) if isinstance(reason_record, Mapping) else []
    if producer_id == "paper_readiness_blockers":
        return _bounded_list(row.get("blocking_reasons"))
    return []


def _reason_text_for(producer_id: str, row: Mapping[str, Any]) -> str:
    if producer_id == "source_quality_readiness":
        return str(row.get("operator_explanation") or "")
    if producer_id == "failure_action_mapping":
        reason_record = row.get("reason_record")
        return str(reason_record.get("reason_text") or "") if isinstance(reason_record, Mapping) else ""
    if producer_id == "paper_readiness_blockers":
        warnings = _bounded_list(row.get("warnings"))
        return ", ".join(warnings)
    return ""


def _evidence_refs_for(producer_id: str, row: Mapping[str, Any]) -> list[str]:
    if producer_id == "source_quality_readiness":
        path = str(row.get("path") or "").strip()
        return [path] if path else []
    if producer_id == "failure_action_mapping":
        reason_record = row.get("reason_record")
        return _bounded_list(reason_record.get("evidence_refs")) if isinstance(reason_record, Mapping) else []
    if producer_id == "paper_readiness_blockers":
        evidence = row.get("evidence")
        if not isinstance(evidence, Mapping):
            return []
        return _bounded_list(evidence.get("source_artifacts"))
    return []


def _producer_audit(
    *,
    producer_id: str,
    source_artifact: str,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected = len(rows)
    with_codes = 0
    with_text = 0
    with_refs = 0
    missing_examples: list[dict[str, Any]] = []
    missing_counter: Counter[str] = Counter()
    for index, row in enumerate(rows):
        subject_id = _subject_id_for(producer_id, row, index)
        reason_codes = _reason_codes_for(producer_id, row)
        reason_text = _reason_text_for(producer_id, row).strip()
        evidence_refs = _evidence_refs_for(producer_id, row)
        missing: list[str] = []
        if reason_codes:
            with_codes += 1
        else:
            missing.append("reason_codes_missing")
        if reason_text:
            with_text += 1
        else:
            missing.append("reason_text_missing")
        if evidence_refs:
            with_refs += 1
        else:
            missing.append("evidence_refs_missing")
        missing_counter.update(missing)
        if missing and len(missing_examples) < _MAX_EXAMPLES:
            missing_examples.append(
                {
                    "subject_id": subject_id,
                    "missing_fields": missing,
                    "reason_codes": reason_codes,
                }
            )
    coverage_pct = round((with_refs / expected) * 100, 2) if expected else None
    return {
        "producer_id": producer_id,
        "source_artifact": source_artifact,
        "expected_subject_count": expected,
        "subjects_with_reason_codes": with_codes,
        "subjects_with_reason_text": with_text,
        "subjects_with_evidence_refs": with_refs,
        "reason_record_coverage_pct": coverage_pct,
        "missing_ref_classes": dict(sorted(missing_counter.items())),
        "missing_examples_top": missing_examples,
        "status": (
            "no_subjects"
            if expected == 0
            else "coverage_complete"
            if with_refs == expected and with_codes == expected and with_text == expected
            else "coverage_partial"
            if with_refs > 0
            else "coverage_missing"
        ),
    }


def build_reason_record_audit(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    producers = [
        (
            "real_basket_diagnosis",
            "research/qre_real_basket_diagnosis.py",
            _producer_rows_from_basket(repo_root, max_candidates),
        ),
        (
            "routing_readiness_from_basket",
            "research/qre_routing_readiness_from_basket.py",
            _producer_rows_from_routing(repo_root, max_candidates),
        ),
        (
            "sampling_readiness_from_basket",
            "research/qre_sampling_readiness_from_basket.py",
            _producer_rows_from_sampling(repo_root, max_candidates),
        ),
        (
            "source_quality_readiness",
            "logs/qre_data_source_quality_readiness/latest.json",
            _producer_rows_from_source_quality(repo_root),
        ),
        (
            "failure_action_mapping",
            "logs/failure_action_mapping_minimal/latest.json",
            _producer_rows_from_failure_action(repo_root),
        ),
        (
            "paper_readiness_blockers",
            "research/paper_readiness_latest.v1.json",
            _producer_rows_from_paper_readiness(repo_root),
        ),
    ]
    producer_rows = [
        _producer_audit(producer_id=producer_id, source_artifact=artifact, rows=rows)
        for producer_id, artifact, rows in producers
    ]
    total_expected = sum(int(row["expected_subject_count"]) for row in producer_rows)
    total_with_refs = sum(int(row["subjects_with_evidence_refs"]) for row in producer_rows)
    total_with_text = sum(int(row["subjects_with_reason_text"]) for row in producer_rows)
    total_with_codes = sum(int(row["subjects_with_reason_codes"]) for row in producer_rows)
    manifest_total = _manifest_total_records(repo_root)
    missing_class_counter: Counter[str] = Counter()
    for row in producer_rows:
        missing_class_counter.update(row.get("missing_ref_classes") or {})
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "max_candidates": max_candidates,
        "summary": {
            "producer_count": len(producer_rows),
            "reason_records_manifest_total": manifest_total,
            "expected_subject_count": total_expected,
            "subjects_with_reason_codes": total_with_codes,
            "subjects_with_reason_text": total_with_text,
            "subjects_with_evidence_refs": total_with_refs,
            "reason_record_coverage_pct": round((total_with_refs / total_expected) * 100, 2)
            if total_expected
            else None,
            "missing_ref_class_counts": dict(sorted(missing_class_counter.items())),
            "final_recommendation": (
                "reason_record_audit_no_records_present"
                if manifest_total == 0
                else "reason_record_audit_records_present_but_gaps_remain"
                if total_with_refs < total_expected
                else "reason_record_audit_coverage_complete"
            ),
            "operator_summary": (
                "Reason-record audit inventories where read-only QRE decisions already "
                "carry reason/evidence context and where explicit evidence refs are still missing."
            ),
        },
        "producer_rows": producer_rows,
        "safety_invariants": {
            "read_only": True,
            "emits_reason_records": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    rows = report.get("producer_rows") if isinstance(report.get("producer_rows"), list) else []
    count_table = _table(
        ["Field", "Value"],
        [
            ["producer count", str(summary.get("producer_count") or 0)],
            ["reason-record manifest total", str(summary.get("reason_records_manifest_total") or 0)],
            ["expected subjects", str(summary.get("expected_subject_count") or 0)],
            ["subjects with evidence refs", str(summary.get("subjects_with_evidence_refs") or 0)],
            ["coverage pct", str(summary.get("reason_record_coverage_pct") or "n/a")],
        ],
    )
    producer_table = _table(
        ["Producer", "Expected", "With refs", "With text", "With codes", "Status"],
        [
            [
                str(row.get("producer_id") or ""),
                str(row.get("expected_subject_count") or 0),
                str(row.get("subjects_with_evidence_refs") or 0),
                str(row.get("subjects_with_reason_text") or 0),
                str(row.get("subjects_with_reason_codes") or 0),
                str(row.get("status") or ""),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Reason Record Audit",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Coverage counts",
            count_table,
            "",
            "## 3. Producer audit",
            producer_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if _WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_reason_record_audit: refusing write outside allowlist: {path!r}")


def write_outputs(
    report: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    latest_payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(latest_payload, encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_reason_record_audit",
        description="Build a read-only reason-record coverage audit for QRE producers.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_reason_record_audit(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
