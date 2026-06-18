from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Literal


REPORT_KIND: Final[str] = "qre_controlled_validation_adapter_result_materialization"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_controlled_validation_adapter_results")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_controlled_validation_adapter_results/"
RUNNER_REPORT_KIND: Final[str] = "qre_bounded_current_basket_generation_runner"
ADAPTER_REPORT_KIND: Final[str] = "qre_controlled_validation_adapter"
NON_AUTHORITATIVE_FLAG: Final[bool] = True
EVIDENCE_AUTHORITY: Final[str] = "materializer_context_until_verifier_acceptance"

MaterializationStatus = Literal[
    "materialized_accepted_structured_evidence",
    "materialized_provisional_only",
    "materialized_rejected_source",
    "materialized_no_safe_source",
    "blocked_invalid_runner_payload",
    "blocked_invalid_adapter_payload",
    "blocked_missing_required_fields",
]


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _unique_in_order(values: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))


def _default_input_path(repo_root: Path) -> Path | None:
    candidates = (
        repo_root / "logs" / "qre_bounded_current_basket_generation_runner" / "latest.json",
        repo_root / "logs" / "qre_controlled_validation_adapter" / "latest.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _is_runner_payload(payload: Mapping[str, Any]) -> bool:
    return str(payload.get("report_kind") or "") == RUNNER_REPORT_KIND or "adapter_result" in payload


def _is_adapter_payload(payload: Mapping[str, Any]) -> bool:
    return str(payload.get("report_kind") or "") == ADAPTER_REPORT_KIND or "adapter_status" in payload


def _source_refs(source: Mapping[str, Any], adapter_payload: Mapping[str, Any], source_kind: str) -> tuple[str, str]:
    if source_kind == "runner":
        return (
            str(source.get("report_kind") or RUNNER_REPORT_KIND),
            str(source.get("adapter_result_ref") or adapter_payload.get("report_kind") or ADAPTER_REPORT_KIND),
        )
    return ("", str(source.get("report_kind") or ADAPTER_REPORT_KIND))


def _materialization_status(
    *,
    adapter_status: str,
    required_fields_missing: bool,
) -> MaterializationStatus:
    if required_fields_missing:
        return "blocked_missing_required_fields"
    if adapter_status == "accepted_structured_evidence":
        return "materialized_accepted_structured_evidence"
    if adapter_status == "no_safe_controlled_validation_source":
        return "materialized_no_safe_source"
    if adapter_status.startswith("rejected_") or adapter_status == "blocked_source_not_structured":
        return "materialized_rejected_source"
    return "materialized_provisional_only"


def _canonical_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report.get("schema_version", SCHEMA_VERSION),
        "report_kind": report.get("report_kind", REPORT_KIND),
        "generated_at_utc": report.get("generated_at_utc", ""),
        "source_runner_ref": report.get("source_runner_ref", ""),
        "source_adapter_ref": report.get("source_adapter_ref", ""),
        "request_ref": report.get("request_ref", ""),
        "adapter_status": report.get("adapter_status", ""),
        "request_symbols": list(report.get("request_symbols", [])),
        "preset_id": report.get("preset_id", ""),
        "timeframe": report.get("timeframe", ""),
        "lineage_candidates": list(report.get("lineage_candidates", [])),
        "oos_candidates": list(report.get("oos_candidates", [])),
        "accepted_lineage_count": int(report.get("accepted_lineage_count", 0) or 0),
        "accepted_oos_count": int(report.get("accepted_oos_count", 0) or 0),
        "rejected_reasons": list(report.get("rejected_reasons", [])),
        "materialization_status": report.get("materialization_status", ""),
        "authority": dict(report.get("authority", {})),
    }


def compute_materialization_hash(report: Mapping[str, Any]) -> str:
    payload = _canonical_payload(report)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _materialize_from_source(source: Mapping[str, Any]) -> dict[str, Any]:
    source = _mapping(source)
    request_payload = _mapping(source.get("request"))
    source_kind = "runner" if _is_runner_payload(source) else "adapter" if _is_adapter_payload(source) else "runner"
    adapter_payload = _mapping(source.get("adapter_result")) if source_kind == "runner" else source
    request_ref = str(source.get("request_ref") or adapter_payload.get("request_ref") or request_payload.get("request_id") or "").strip()
    adapter_status = str(adapter_payload.get("adapter_status") or "").strip()
    source_runner_ref, source_adapter_ref = _source_refs(source, adapter_payload, source_kind)
    generated_at_utc = str(
        source.get("generated_at_utc")
        or source.get("generated_at")
        or adapter_payload.get("generated_at_utc")
        or adapter_payload.get("generated_at")
        or ""
    ).strip()
    lineage_candidates = list(adapter_payload.get("lineage_candidates") or [])
    oos_candidates = list(adapter_payload.get("oos_candidates") or [])
    lineage_candidate_refs = _unique_in_order(adapter_payload.get("lineage_candidate_refs") or [])
    oos_candidate_refs = _unique_in_order(adapter_payload.get("oos_candidate_refs") or [])
    rejected_reasons = _unique_in_order(adapter_payload.get("rejected_reasons") or [])
    request_symbols = _unique_in_order(request_payload.get("symbols") or source.get("symbols") or [])
    preset_id = str(request_payload.get("preset_id") or source.get("preset_id") or adapter_payload.get("preset_id") or "").strip()
    timeframe = str(request_payload.get("timeframe") or source.get("timeframe") or adapter_payload.get("timeframe") or "").strip()

    source_missing_required_fields = not request_ref or not adapter_status
    if source_kind == "runner" and not source.get("adapter_result"):
        status = "blocked_invalid_runner_payload"
    elif source_kind == "adapter" and source_missing_required_fields:
        status = "blocked_invalid_adapter_payload"
    elif not request_ref or not adapter_status:
        status = "blocked_missing_required_fields"
    else:
        accepted_lineage_count = int(adapter_payload.get("accepted_lineage_count", 0) or 0)
        accepted_oos_count = int(adapter_payload.get("accepted_oos_count", 0) or 0)
        authority = {
            "non_authoritative": bool(adapter_payload.get("non_authoritative", NON_AUTHORITATIVE_FLAG)),
            "evidence_authority": str(adapter_payload.get("evidence_authority") or EVIDENCE_AUTHORITY),
            "can_clear_blockers": False,
            "can_authorize_execution": False,
            "can_promote_candidate": False,
        }
        required_fields_missing = False
        required_fields_missing = required_fields_missing or not lineage_candidate_refs and accepted_lineage_count > 0
        required_fields_missing = required_fields_missing or not oos_candidate_refs and accepted_oos_count > 0
        required_fields_missing = required_fields_missing or not rejected_reasons and adapter_status != "accepted_structured_evidence"
        required_fields_missing = required_fields_missing or not authority["non_authoritative"]
        required_fields_missing = required_fields_missing or authority["can_clear_blockers"] is not False
        required_fields_missing = required_fields_missing or authority["can_authorize_execution"] is not False
        required_fields_missing = required_fields_missing or authority["can_promote_candidate"] is not False
        status = _materialization_status(
            adapter_status=adapter_status,
            required_fields_missing=required_fields_missing,
        )
        if status == "materialized_accepted_structured_evidence":
            if accepted_lineage_count <= 0 or accepted_oos_count <= 0:
                status = "blocked_missing_required_fields"
            elif not lineage_candidate_refs or not oos_candidate_refs:
                status = "blocked_missing_required_fields"
        if status != "materialized_accepted_structured_evidence":
            accepted_lineage_count = 0
            accepted_oos_count = 0
            lineage_candidates = []
            oos_candidates = []
            lineage_candidate_refs = []
            oos_candidate_refs = []
        report = {
            "schema_version": SCHEMA_VERSION,
            "report_kind": REPORT_KIND,
            "generated_at_utc": generated_at_utc,
            "source_runner_ref": source_runner_ref,
            "source_adapter_ref": source_adapter_ref,
            "request_ref": request_ref,
            "adapter_status": adapter_status,
            "request_symbols": request_symbols,
            "preset_id": preset_id,
            "timeframe": timeframe,
            "lineage_candidates": lineage_candidates,
            "oos_candidates": oos_candidates,
            "accepted_lineage_count": accepted_lineage_count,
            "accepted_oos_count": accepted_oos_count,
            "rejected_reasons": rejected_reasons,
            "materialization_status": status,
            "authority": {
                "non_authoritative": True,
                "evidence_authority": EVIDENCE_AUTHORITY,
                "can_clear_blockers": False,
                "can_authorize_execution": False,
                "can_promote_candidate": False,
            },
        }
        report["hash"] = compute_materialization_hash(report)
        return report

    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "source_runner_ref": source_runner_ref,
        "source_adapter_ref": source_adapter_ref,
        "request_ref": request_ref,
        "adapter_status": adapter_status,
        "request_symbols": request_symbols,
        "preset_id": preset_id,
        "timeframe": timeframe,
        "lineage_candidates": [],
        "oos_candidates": [],
        "accepted_lineage_count": 0,
        "accepted_oos_count": 0,
        "rejected_reasons": rejected_reasons or [status],
        "materialization_status": status,
        "authority": {
            "non_authoritative": True,
            "evidence_authority": EVIDENCE_AUTHORITY,
            "can_clear_blockers": False,
            "can_authorize_execution": False,
            "can_promote_candidate": False,
        },
    }
    report["hash"] = compute_materialization_hash(report)
    return report


def build_controlled_validation_adapter_result_materialization(
    source: Mapping[str, Any] | None = None,
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    if source is None:
        path = _default_input_path(repo_root)
        source = _read_json(path) if path is not None else {}
    return _materialize_from_source(source or {})


def validate_materialization_result(result: Mapping[str, Any]) -> dict[str, Any]:
    rejection_reasons: list[str] = []
    canonical = _canonical_payload(result)
    if canonical["authority"].get("non_authoritative") is not True:
        rejection_reasons.append("non_authoritative_must_be_true")
    if canonical["authority"].get("can_clear_blockers") is not False:
        rejection_reasons.append("can_clear_blockers_must_be_false")
    if canonical["authority"].get("can_authorize_execution") is not False:
        rejection_reasons.append("can_authorize_execution_must_be_false")
    if canonical["authority"].get("can_promote_candidate") is not False:
        rejection_reasons.append("can_promote_candidate_must_be_false")
    if canonical["materialization_status"] == "materialized_accepted_structured_evidence":
        if canonical["accepted_lineage_count"] <= 0 or canonical["accepted_oos_count"] <= 0:
            rejection_reasons.append("accepted_materialization_requires_lineage_and_oos_counts")
        if not canonical["lineage_candidates"] or not canonical["oos_candidates"]:
            rejection_reasons.append("accepted_materialization_requires_candidate_records")
    computed_hash = compute_materialization_hash(result)
    if str(result.get("hash") or "") and str(result.get("hash")) != computed_hash:
        rejection_reasons.append("hash_mismatch")
    return {
        "valid": not rejection_reasons,
        "rejection_reasons": list(_unique_in_order(rejection_reasons)),
        "hash": computed_hash,
        "schema_version": SCHEMA_VERSION,
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    authority = report.get("authority") if isinstance(report.get("authority"), Mapping) else {}
    return "\n".join(
        [
            "# QRE Controlled Validation Adapter Result Materialization",
            "",
            _table(
                ["Field", "Value"],
                [
                    ["request_ref", str(report.get("request_ref") or "")],
                    ["adapter_status", str(report.get("adapter_status") or "")],
                    ["materialization_status", str(report.get("materialization_status") or "")],
                    ["accepted_lineage_count", str(int(report.get("accepted_lineage_count") or 0))],
                    ["accepted_oos_count", str(int(report.get("accepted_oos_count") or 0))],
                    ["non_authoritative", str(bool(authority.get("non_authoritative"))).lower()],
                    ["can_clear_blockers", str(bool(authority.get("can_clear_blockers"))).lower()],
                ],
            ),
            "",
            _table(
                ["Field", "Value"],
                [
                    ["source_runner_ref", str(report.get("source_runner_ref") or "")],
                    ["source_adapter_ref", str(report.get("source_adapter_ref") or "")],
                    ["preset_id", str(report.get("preset_id") or "")],
                    ["timeframe", str(report.get("timeframe") or "")],
                    ["generated_at_utc", str(report.get("generated_at_utc") or "")],
                ],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_controlled_validation_adapter_result_materialization: refusing write outside allowlist: {path!r}"
        )


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
        prog="python -m research.qre_controlled_validation_adapter_result_materialization",
        description="Build the controlled validation adapter result materialization report.",
    )
    parser.add_argument("--input-file")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    input_payload = _read_json(Path(args.input_file)) if args.input_file else None
    report = build_controlled_validation_adapter_result_materialization(input_payload, repo_root=Path("."))
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
