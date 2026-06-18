from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_bounded_first_batch_generation_decision as decision
from research import qre_controlled_validation_adapter_result_materialization as adapter_materialization


REPORT_KIND: Final[str] = "qre_bounded_generation_artifact_acceptance_verifier"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_bounded_generation_artifact_acceptance_verifier")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_bounded_generation_artifact_acceptance_verifier/"
SCAN_ROOTS: Final[tuple[str, ...]] = ("logs", "artifacts", "archived", "backup", "local_quarantine")
SOURCE_ARTIFACT_PREFIXES: Final[tuple[str, ...]] = ("artifacts/",)


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _read_json(path: Path) -> Any | None:
    if path.suffix.lower() not in {".json", ".jsonl"}:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _mapping_has_key(payload: Any, key: str) -> bool:
    return isinstance(payload, Mapping) and key in payload


def _text(value: Any) -> str:
    return str(value or "").strip()


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [text for item in value if (text := _text(item))]


def _source_ref_reason(source_ref: str, *, allowlisted_paths: Sequence[str]) -> str | None:
    normalized = source_ref.replace("\\", "/").strip()
    lowered = normalized.lower()
    if not normalized:
        return "missing_source_artifact_ref"
    if lowered.startswith("tests/") or "fixture" in lowered:
        return "fixture_only_source_ref"
    if lowered.startswith("logs/") or lowered.endswith(".md") or "operator_summary" in lowered:
        return "generated_report_only_source_ref"
    if "stdout" in lowered:
        return "stdout_only_source_ref"
    if "legacy_alias" in lowered or "alias_only" in lowered:
        return "legacy_alias_only_source_ref"
    if any(normalized.startswith(prefix) for prefix in SOURCE_ARTIFACT_PREFIXES):
        return None
    if any(normalized.startswith(prefix) for prefix in allowlisted_paths):
        return None
    return "source_artifact_path_not_allowlisted"


def _validate_materialized_authority(authority: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if authority.get("non_authoritative") is not True:
        reasons.append("non_authoritative_must_be_true")
    if not _text(authority.get("evidence_authority")):
        reasons.append("missing_evidence_authority")
    if authority.get("can_clear_blockers") is not False:
        reasons.append("can_clear_blockers_must_be_false")
    if authority.get("can_authorize_execution") is not False:
        reasons.append("can_authorize_execution_must_be_false")
    if authority.get("can_promote_candidate") is not False:
        reasons.append("can_promote_candidate_must_be_false")
    return reasons


def _validate_lineage_candidate(
    candidate: Mapping[str, Any],
    *,
    request_ref: str,
    allowlisted_paths: Sequence[str],
) -> list[str]:
    reasons: list[str] = []
    if _text(candidate.get("request_id")) != request_ref:
        reasons.append("missing_request_ref")
    if not _text(candidate.get("candidate_id")):
        reasons.append("missing_candidate_id")
    if not (
        _text(candidate.get("campaign_id"))
        or _text(candidate.get("generation_id"))
        or _text(candidate.get("controlled_generation_id"))
        or _text(candidate.get("grid_run_id"))
    ):
        reasons.append("missing_campaign_or_generation_id")
    if not _text(candidate.get("preset_id")):
        reasons.append("missing_preset_id")
    if not _text(candidate.get("timeframe")):
        reasons.append("missing_timeframe")
    source_ref_reason = _source_ref_reason(_text(candidate.get("source_ref")), allowlisted_paths=allowlisted_paths)
    if source_ref_reason:
        reasons.append(source_ref_reason)
    if not _text_list(candidate.get("reason_record_refs")):
        reasons.append("missing_reason_records")
    if candidate.get("accepted_by_adapter") is not True or candidate.get("accepted_for_campaign_lineage") is not True:
        reasons.append("not_marked_accepted_for_campaign_lineage")
    if _text_list(candidate.get("rejection_reasons")):
        reasons.append("lineage_candidate_has_rejection_reasons")
    return reasons


def _validate_oos_candidate(
    candidate: Mapping[str, Any],
    *,
    request_ref: str,
    allowlisted_paths: Sequence[str],
) -> list[str]:
    reasons: list[str] = []
    if _text(candidate.get("request_id")) != request_ref:
        reasons.append("missing_request_ref")
    if not _text(candidate.get("candidate_id")):
        reasons.append("missing_candidate_id")
    if not _text(candidate.get("preset_id")):
        reasons.append("missing_preset_id")
    if not _text(candidate.get("timeframe")):
        reasons.append("missing_timeframe")
    source_ref_reason = _source_ref_reason(_text(candidate.get("source_ref")), allowlisted_paths=allowlisted_paths)
    if source_ref_reason:
        reasons.append(source_ref_reason)
    oos_window = candidate.get("oos_window")
    if not isinstance(oos_window, Mapping) or not _text(oos_window.get("start")) or not _text(oos_window.get("end")):
        reasons.append("missing_oos_window")
    metrics = candidate.get("oos_metric_fields")
    if not isinstance(metrics, Mapping) or not metrics:
        reasons.append("missing_oos_metrics")
    if not _text_list(candidate.get("cost_slippage_assumption_refs")):
        reasons.append("missing_cost_slippage_refs")
    if not _text_list(candidate.get("reason_record_refs")):
        reasons.append("missing_reason_records")
    if candidate.get("accepted_by_adapter") is not True or candidate.get("accepted_for_oos_evidence") is not True:
        reasons.append("not_marked_accepted_for_oos_evidence")
    if _text_list(candidate.get("rejection_reasons")):
        reasons.append("oos_candidate_has_rejection_reasons")
    return reasons


def _accepted_lineage_record(candidate: Mapping[str, Any], *, request_ref: str, verifier_ref: str) -> dict[str, Any]:
    return {
        "request_ref": request_ref,
        "candidate_id": _text(candidate.get("candidate_id")),
        "campaign_id": _text(candidate.get("campaign_id")),
        "generation_id": _text(candidate.get("generation_id")),
        "controlled_generation_id": _text(candidate.get("controlled_generation_id")),
        "grid_run_id": _text(candidate.get("grid_run_id")),
        "preset_id": _text(candidate.get("preset_id")),
        "timeframe": _text(candidate.get("timeframe")),
        "source_ref": _text(candidate.get("source_ref")),
        "reason_record_refs": _text_list(candidate.get("reason_record_refs")),
        "verifier_ref": verifier_ref,
    }


def _accepted_oos_record(candidate: Mapping[str, Any], *, request_ref: str, verifier_ref: str) -> dict[str, Any]:
    return {
        "request_ref": request_ref,
        "candidate_id": _text(candidate.get("candidate_id")),
        "preset_id": _text(candidate.get("preset_id")),
        "timeframe": _text(candidate.get("timeframe")),
        "source_ref": _text(candidate.get("source_ref")),
        "oos_window": dict(candidate.get("oos_window")) if isinstance(candidate.get("oos_window"), Mapping) else {},
        "oos_metric_fields": dict(candidate.get("oos_metric_fields")) if isinstance(candidate.get("oos_metric_fields"), Mapping) else {},
        "cost_slippage_assumption_refs": _text_list(candidate.get("cost_slippage_assumption_refs")),
        "reason_record_refs": _text_list(candidate.get("reason_record_refs")),
        "verifier_ref": verifier_ref,
    }


def _classify_materialized_record(
    payload: Mapping[str, Any],
    *,
    relative_path: str,
    allowlisted_paths: Sequence[str],
) -> dict[str, Any]:
    materialization_status = _text(payload.get("materialization_status"))
    authority = payload.get("authority") if isinstance(payload.get("authority"), Mapping) else {}
    lineage_candidates = payload.get("lineage_candidates") if isinstance(payload.get("lineage_candidates"), list) else []
    oos_candidates = payload.get("oos_candidates") if isinstance(payload.get("oos_candidates"), list) else []
    request_ref = _text(payload.get("request_ref"))
    source_metadata_status = _text(payload.get("source_metadata_status"))
    source_metadata_reasons = _text_list(payload.get("source_metadata_reasons"))
    metadata_valid = not source_metadata_status or source_metadata_status == "metadata_complete"
    authority_reasons = _validate_materialized_authority(authority)
    lineage_reasons: list[str] = []
    oos_reasons: list[str] = []
    accepted_lineage_records: list[dict[str, Any]] = []
    accepted_oos_records: list[dict[str, Any]] = []

    accepted_lineage_count = 0
    accepted_oos_count = 0
    if materialization_status == "materialized_accepted_structured_evidence" and not authority_reasons:
        for candidate in lineage_candidates:
            if isinstance(candidate, Mapping):
                candidate_reasons = _validate_lineage_candidate(
                    candidate,
                    request_ref=request_ref,
                    allowlisted_paths=allowlisted_paths,
                )
                lineage_reasons.extend(candidate_reasons)
                if not candidate_reasons:
                    accepted_lineage_count += 1
                    accepted_lineage_records.append(
                        _accepted_lineage_record(
                            candidate,
                            request_ref=request_ref,
                            verifier_ref=f"{relative_path}#lineage:{_text(candidate.get('candidate_id'))}",
                        )
                    )
        for candidate in oos_candidates:
            if isinstance(candidate, Mapping):
                candidate_reasons = _validate_oos_candidate(
                    candidate,
                    request_ref=request_ref,
                    allowlisted_paths=allowlisted_paths,
                )
                oos_reasons.extend(candidate_reasons)
                if not candidate_reasons:
                    accepted_oos_count += 1
                    accepted_oos_records.append(
                        _accepted_oos_record(
                            candidate,
                            request_ref=request_ref,
                            verifier_ref=f"{relative_path}#oos:{_text(candidate.get('candidate_id'))}",
                        )
                    )

    payload_lineage_count = int(payload.get("accepted_lineage_count") or 0)
    payload_oos_count = int(payload.get("accepted_oos_count") or 0)
    rejection_reasons = list(
        dict.fromkeys(
            [
                *authority_reasons,
                *(
                    [source_metadata_status, *source_metadata_reasons]
                    if source_metadata_status and source_metadata_status != "metadata_complete"
                    else []
                ),
                *lineage_reasons,
                *oos_reasons,
                *(
                    ["accepted_lineage_count_mismatch"]
                    if materialization_status == "materialized_accepted_structured_evidence"
                    and payload_lineage_count != accepted_lineage_count
                    else []
                ),
                *(
                    ["accepted_oos_count_mismatch"]
                    if materialization_status == "materialized_accepted_structured_evidence"
                    and payload_oos_count != accepted_oos_count
                    else []
                ),
            ]
        )
    )
    lineage_accepted = accepted_lineage_count > 0 and metadata_valid and not authority_reasons and not lineage_reasons
    oos_accepted = accepted_oos_count > 0 and metadata_valid and not authority_reasons and not oos_reasons
    if materialization_status == "materialized_accepted_structured_evidence" and lineage_accepted and oos_accepted:
        classification = "accepted_for_campaign_lineage"
    elif materialization_status == "materialized_accepted_structured_evidence" and lineage_accepted:
        classification = "accepted_for_campaign_lineage_only"
    elif materialization_status == "materialized_accepted_structured_evidence" and oos_accepted:
        classification = "accepted_for_oos_evidence_only"
    elif materialization_status == "materialized_accepted_structured_evidence":
        classification = "rejected_materialized_missing_required_fields"
    elif materialization_status == "materialized_no_safe_source":
        classification = "rejected_materialized_no_safe_source"
    elif materialization_status == "materialized_rejected_source":
        classification = "rejected_materialized_rejected_source"
    elif materialization_status == "materialized_provisional_only":
        classification = "rejected_materialized_provisional_only"
    elif materialization_status in {
        "blocked_invalid_runner_payload",
        "blocked_invalid_adapter_payload",
        "blocked_missing_required_fields",
    }:
        classification = "rejected_materialized_missing_required_fields"
    else:
        classification = "rejected_context_only"
    return {
        "path": str(relative_path),
        "relative_path": relative_path,
        "classification": classification,
        "accepted_for_campaign_lineage": lineage_accepted,
        "accepted_for_oos_evidence": oos_accepted,
        "accepted_lineage_count": accepted_lineage_count,
        "accepted_oos_count": accepted_oos_count,
        "accepted_lineage_records": accepted_lineage_records,
        "accepted_oos_records": accepted_oos_records,
        "accepted_for_screening_evidence": False,
        "materialization_status": materialization_status,
        "lineage_rejection_reasons": lineage_reasons,
        "oos_rejection_reasons": oos_reasons,
        "rejection_reasons": rejection_reasons,
        "request_ref": request_ref,
    }


def _iter_paths(repo_root: Path) -> list[Path]:
    paths: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = repo_root / root_name
        if not root.exists():
            continue
        paths.extend(sorted(path for path in root.rglob("*.json") if path.is_file()))
    return paths


def classify_artifact(
    path: Path,
    *,
    repo_root: Path = Path("."),
    allowlisted_paths: Sequence[str],
) -> dict[str, Any]:
    payload = _read_json(path)
    relative_path = path.relative_to(repo_root).as_posix()
    text = json.dumps(payload, sort_keys=True, default=str).lower() if payload is not None else ""
    report_kind = str(payload.get("report_kind") or "") if isinstance(payload, Mapping) else ""
    if report_kind == adapter_materialization.REPORT_KIND:
        return _classify_materialized_record(payload, relative_path=relative_path, allowlisted_paths=allowlisted_paths)
    target_symbols = {"aapl", "nvda"}
    has_target_symbol = any(symbol in text for symbol in target_symbols)
    has_target_preset = "trend_pullback_continuation_daily_v1" in text
    has_target_timeframe = "daily_v1" in text
    has_candidate_id = _mapping_has_key(payload, "candidate_id")
    has_generation_identity = _mapping_has_key(payload, "campaign_id") or _mapping_has_key(payload, "generation_run_id")
    has_grid_run_identity = _mapping_has_key(payload, "grid_run_id") or _mapping_has_key(payload, "controlled_generation_id")
    has_oos_fields = _mapping_has_key(payload, "oos_metric_fields")
    has_screening_fields = _mapping_has_key(payload, "screening_evidence_fields")
    has_lineage_fields = _mapping_has_key(payload, "lineage_fields")
    has_validation_status = _mapping_has_key(payload, "validation_status")
    has_artifact_timestamp = _mapping_has_key(payload, "artifact_timestamp") or _mapping_has_key(payload, "generated_at")
    has_source_artifact_path = _mapping_has_key(payload, "source_artifact_path")
    has_reason_record_refs = _mapping_has_key(payload, "reason_record_refs")
    has_policy_version = _mapping_has_key(payload, "policy_version")
    has_operator_approval = _mapping_has_key(payload, "operator_approval_id") or _mapping_has_key(payload, "approval_manifest_ref")
    if report_kind.startswith("qre_"):
        classification = "rejected_context_only"
    elif relative_path.startswith(".tmp/") or "stdout_tail" in text:
        classification = "rejected_stdout_only"
    elif "trend_pullback_v1" in text and "trend_pullback_continuation_daily_v1" not in text:
        classification = "rejected_context_only"
    elif not has_target_symbol:
        classification = "rejected_preset_mismatch"
    elif "trend_pullback_continuation_daily_v1" not in text:
        classification = "rejected_preset_mismatch"
    elif not has_target_timeframe:
        classification = "rejected_timeframe_mismatch"
    elif not any(relative_path.startswith(prefix) for prefix in allowlisted_paths):
        classification = "rejected_path_not_allowlisted"
    elif not (has_candidate_id and has_generation_identity and has_grid_run_identity):
        classification = "rejected_missing_identity"
    elif not has_operator_approval:
        classification = "rejected_unapproved_run"
    elif not (
        has_oos_fields
        and has_screening_fields
        and has_lineage_fields
        and has_validation_status
        and has_artifact_timestamp
        and has_source_artifact_path
        and has_reason_record_refs
        and has_policy_version
    ):
        classification = "rejected_missing_identity"
    else:
        classification = "accepted_for_campaign_lineage"
    return {
        "path": str(path),
        "relative_path": relative_path,
        "classification": classification,
        "accepted_for_campaign_lineage": classification == "accepted_for_campaign_lineage",
        "accepted_for_oos_evidence": classification == "accepted_for_campaign_lineage" and has_oos_fields,
        "accepted_for_screening_evidence": classification == "accepted_for_campaign_lineage" and has_screening_fields,
    }


def build_bounded_generation_artifact_acceptance_verifier(
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    allowlisted_paths = list(
        (
            decision.build_bounded_first_batch_generation_decision(repo_root=repo_root)
            .get("acceptance_contract", {})
            .get("allowlisted_paths", [])
        )
    )
    rows = [
        classify_artifact(path, repo_root=repo_root, allowlisted_paths=allowlisted_paths)
        for path in _iter_paths(repo_root)
    ]
    counts = Counter(str(row["classification"]) for row in rows)
    accepted_lineage_candidate_count = sum(int(row.get("accepted_lineage_count") or 0) for row in rows)
    accepted_oos_candidate_count = sum(int(row.get("accepted_oos_count") or 0) for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "artifact_count": len(rows),
            "classification_counts": dict(sorted(counts.items())),
            "accepted_lineage_artifact_count": sum(
                1 for row in rows if bool(row.get("accepted_for_campaign_lineage"))
            ),
            "accepted_oos_artifact_count": sum(
                1 for row in rows if bool(row.get("accepted_for_oos_evidence"))
            ),
            "accepted_lineage_candidate_count": accepted_lineage_candidate_count,
            "accepted_oos_candidate_count": accepted_oos_candidate_count,
            "operator_summary": (
                "Post-generation acceptance verifier remains read-only and classifies future "
                "bounded artifacts against the explicit acceptance contract."
            ),
            "final_recommendation": "artifact_acceptance_verifier_ready",
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "does_not_generate_evidence": True,
            "does_not_accept_context_only_as_proof": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return "\n".join(
        [
            "# QRE Bounded Generation Artifact Acceptance Verifier",
            "",
            _table(
                ["Field", "Value"],
                [
                    ["artifact_count", str(summary.get("artifact_count") or 0)],
                    ["final_recommendation", str(summary.get("final_recommendation") or "")],
                ],
            ),
            "",
            _table(
                ["Path", "Classification"],
                [
                    [str(row.get("relative_path") or ""), str(row.get("classification") or "")]
                    for row in rows[:20]
                ]
                or [["none", "none"]],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_bounded_generation_artifact_acceptance_verifier: refusing write outside allowlist: {path!r}"
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
        prog="python -m research.qre_bounded_generation_artifact_acceptance_verifier",
        description="Build the bounded generation artifact acceptance verifier report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_bounded_generation_artifact_acceptance_verifier()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
