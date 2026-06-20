from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_candidate_quality_framework as candidate_quality
from research import qre_evidence_complete_basket_closure as basket_closure
from research import qre_reason_records_v1 as reason_records_v1
from research import qre_shadow_readiness_gates as shadow_readiness
from research.qre_reason_record_contract import validate_reason_record_contract


REPORT_KIND: Final[str] = "qre_reason_record_normalization"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_reason_record_normalization")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_reason_record_normalization/"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bounded_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    out: list[str] = []
    for item in value:
        text = _text(item)
        if text and text not in out:
            out.append(text[:240])
    return out[:24]


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _payloads_from_reason_records_v1(repo_root: Path) -> list[dict[str, Any]]:
    snapshot = reason_records_v1.build_reason_records_snapshot(repo_root=repo_root)
    rows = snapshot.get("records") if isinstance(snapshot.get("records"), list) else []
    payloads: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        payloads.append(
            {
                "producer_id": "qre_reason_records_v1",
                "source_report": "logs/qre_reason_records/latest.meta.json",
                "source_ref": f"logs/qre_reason_records/latest.jsonl#line[{index}]",
                "payload": dict(row),
            }
        )
    return payloads


def _payloads_from_candidate_quality(repo_root: Path) -> list[dict[str, Any]]:
    report = candidate_quality.build_candidate_quality_framework(repo_root=repo_root)
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    payloads: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        record = row.get("reason_record")
        if not isinstance(record, Mapping):
            continue
        payloads.append(
            {
                "producer_id": "qre_candidate_quality_framework",
                "source_report": "logs/qre_candidate_quality_framework/latest.json",
                "source_ref": f"logs/qre_candidate_quality_framework/latest.json#rows[{index}].reason_record",
                "payload": dict(record),
            }
        )
    return payloads


def _payloads_from_shadow_readiness(repo_root: Path) -> list[dict[str, Any]]:
    report = shadow_readiness.build_shadow_readiness_gates(repo_root=repo_root)
    rows = report.get("reason_records") if isinstance(report.get("reason_records"), list) else []
    payloads: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        payloads.append(
            {
                "producer_id": "qre_shadow_readiness_gates",
                "source_report": "logs/qre_shadow_readiness_gates/latest.json",
                "source_ref": f"logs/qre_shadow_readiness_gates/latest.json#reason_records[{index}]",
                "payload": dict(row),
            }
        )
    return payloads


def _payloads_from_basket_closure(repo_root: Path) -> list[dict[str, Any]]:
    report = basket_closure.build_evidence_complete_basket_closure(repo_root=repo_root)
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    payloads: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        reasons = row.get("clearance_reason_records")
        if not isinstance(reasons, list):
            continue
        for reason_index, record in enumerate(reasons):
            if not isinstance(record, Mapping):
                continue
            payloads.append(
                {
                    "producer_id": "qre_evidence_complete_basket_closure",
                    "source_report": "logs/qre_evidence_complete_basket_closure/latest.json",
                    "source_ref": (
                        "logs/qre_evidence_complete_basket_closure/latest.json"
                        f"#rows[{row_index}].clearance_reason_records[{reason_index}]"
                    ),
                    "payload": dict(record),
                }
            )
    return payloads


def _producer_payloads(repo_root: Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for builder in (
        _payloads_from_reason_records_v1,
        _payloads_from_candidate_quality,
        _payloads_from_shadow_readiness,
        _payloads_from_basket_closure,
    ):
        payloads.extend(builder(repo_root))
    return payloads


def _normalize_record(
    *,
    producer_id: str,
    source_report: str,
    source_ref: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    contract_validation = validate_reason_record_contract(payload)
    normalized = {
        "producer_id": producer_id,
        "source_report": source_report,
        "source_ref": source_ref,
        "record_id": _text(payload.get("record_id")),
        "record_kind": _text(payload.get("record_kind")) or "reason_record_untyped",
        "record_family": _text(payload.get("record_family")) or producer_id,
        "subject_id": _text(payload.get("subject_id")),
        "reason_codes": _bounded_list(payload.get("reason_codes")),
        "reason_text": _text(payload.get("reason_text")),
        "evidence_refs": _bounded_list(payload.get("evidence_refs")),
        "inputs_digest": _text(payload.get("inputs_digest")),
        "accepted_evidence": bool(payload.get("accepted_evidence")),
        "recommended_next_action": _text(payload.get("recommended_next_action")),
        "contract_validation": contract_validation,
    }
    if not normalized["record_id"]:
        normalized["record_id"] = (
            "normalized::"
            + hashlib.sha256(
                f"{producer_id}\x1f{source_ref}\x1f{normalized['subject_id']}".encode("utf-8")
            ).hexdigest()[:16]
        )
    if not normalized["inputs_digest"]:
        normalized["inputs_digest"] = _digest(
            {
                "producer_id": producer_id,
                "source_ref": source_ref,
                "record_id": normalized["record_id"],
                "subject_id": normalized["subject_id"],
                "reason_codes": normalized["reason_codes"],
            }
        )
    normalized["deterministic_hash"] = _digest(normalized)
    return normalized


def _producer_summary(
    *,
    producer_id: str,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    valid_count = sum(
        1
        for row in rows
        if str(((row.get("contract_validation") or {}).get("validation_status")) or "") == "valid"
    )
    invalid_count = len(rows) - valid_count
    missing_counts: Counter[str] = Counter()
    for row in rows:
        reasons = (
            (row.get("contract_validation") or {}).get("rejection_reasons")
            if isinstance(row.get("contract_validation"), Mapping)
            else []
        )
        for reason in reasons if isinstance(reasons, list) else []:
            missing_counts.update([_text(reason)])
    return {
        "producer_id": producer_id,
        "record_count": len(rows),
        "valid_record_count": valid_count,
        "invalid_record_count": invalid_count,
        "status": "normalized_ready" if invalid_count == 0 else "normalized_with_contract_gaps",
        "top_rejection_reasons": dict(sorted(missing_counts.items())),
    }


def build_reason_record_normalization(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    payloads = _producer_payloads(repo_root)
    normalized_records = [
        _normalize_record(
            producer_id=_text(item.get("producer_id")),
            source_report=_text(item.get("source_report")),
            source_ref=_text(item.get("source_ref")),
            payload=item.get("payload") if isinstance(item.get("payload"), Mapping) else {},
        )
        for item in payloads
        if isinstance(item, Mapping)
    ]
    normalized_records.sort(
        key=lambda row: (
            str(row.get("producer_id") or ""),
            str(row.get("subject_id") or ""),
            str(row.get("record_id") or ""),
        )
    )
    by_producer: dict[str, list[dict[str, Any]]] = {}
    for row in normalized_records:
        by_producer.setdefault(str(row["producer_id"]), []).append(row)
    producer_rows = [
        _producer_summary(producer_id=producer_id, rows=rows)
        for producer_id, rows in sorted(by_producer.items())
    ]
    valid_count = sum(int(row["valid_record_count"]) for row in producer_rows)
    invalid_count = sum(int(row["invalid_record_count"]) for row in producer_rows)
    next_action = (
        "normalize_reason_record_contract_gaps_before_authority_upgrade"
        if invalid_count > 0
        else "preserve_normalized_reason_record_visibility"
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "reason_record_normalization_ready": True,
            "producer_count": len(producer_rows),
            "normalized_record_count": len(normalized_records),
            "valid_record_count": valid_count,
            "invalid_record_count": invalid_count,
            "producer_gap_count": sum(
                1 for row in producer_rows if int(row.get("invalid_record_count") or 0) > 0
            ),
            "exact_next_action": next_action,
            "final_recommendation": (
                "reason_record_normalization_ready"
                if invalid_count == 0
                else "reason_record_normalization_has_contract_gaps"
            ),
            "operator_summary": (
                "Reason-record producers are normalized into one deterministic read-only surface. "
                "Contract-invalid producers remain explicit and do not gain authority."
            ),
        },
        "producer_rows": producer_rows,
        "normalized_records": normalized_records,
        "authority_boundary": {
            "read_only": True,
            "context_only": True,
            "does_not_authorize_evidence": True,
            "does_not_mutate_producers": True,
        },
        "safety_invariants": {
            "no_fake_reason_records": True,
            "contract_gaps_remain_visible": True,
            "candidate_promotion_forbidden": True,
            "shadow_paper_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }
    report["deterministic_hash"] = _digest(report)
    return report


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    producer_rows = report.get("producer_rows") if isinstance(report.get("producer_rows"), list) else []
    return "\n".join(
        [
            "# QRE Reason Record Normalization",
            "",
            f"- reason_record_normalization_ready: {summary.get('reason_record_normalization_ready')}",
            f"- normalized_record_count: {summary.get('normalized_record_count') or 0}",
            f"- valid_record_count: {summary.get('valid_record_count') or 0}",
            f"- invalid_record_count: {summary.get('invalid_record_count') or 0}",
            f"- exact_next_action: {summary.get('exact_next_action') or ''}",
            "",
            "## Producer Status",
            _table(
                ["Producer", "Records", "Valid", "Invalid", "Status"],
                [
                    [
                        str(row.get("producer_id") or ""),
                        str(row.get("record_count") or 0),
                        str(row.get("valid_record_count") or 0),
                        str(row.get("invalid_record_count") or 0),
                        str(row.get("status") or ""),
                    ]
                    for row in producer_rows
                    if isinstance(row, Mapping)
                ],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_md, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_reason_record_normalization",
        description="Normalize QRE reason-record producers into a deterministic read-only surface.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_reason_record_normalization()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
