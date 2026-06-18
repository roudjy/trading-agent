from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_bounded_basket_request as basket_request
from research import qre_bounded_current_basket_generation_discovery as discovery
from research import qre_controlled_validation_adapter as validation_adapter
from research import qre_controlled_validation_adapter_result_materialization as adapter_materialization


REPORT_KIND: Final[str] = "qre_bounded_current_basket_generation_runner"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_bounded_current_basket_generation_runner")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_bounded_current_basket_generation_runner/"

RUNNER_COMMAND: Final[str] = (
    "python -m research.qre_bounded_current_basket_generation_runner "
    "--request-file logs/qre_bounded_basket_request/latest.json --dry-run --write"
)
NON_AUTHORITATIVE_FLAG: Final[bool] = True
EVIDENCE_AUTHORITY: Final[str] = "runner_context_until_verifier_acceptance"


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


def _request_snapshot(request_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if request_payload is None:
        return {
            "schema_version": basket_request.SCHEMA_VERSION,
            "report_kind": basket_request.REPORT_KIND,
            "request": {},
            "validation_status": "rejected",
            "rejection_reasons": ["missing_request_payload"],
        }
    return basket_request.build_bounded_basket_request_snapshot(request_payload)


def _request_from_file(request_file: Path | None) -> dict[str, Any] | None:
    if request_file is None:
        return None
    return _read_json(request_file)


def _source_from_file(source_file: Path | None) -> dict[str, Any] | None:
    if source_file is None:
        return None
    return _read_json(source_file)


def _unique_in_order(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))


def _canonical_runner_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report.get("schema_version", SCHEMA_VERSION),
        "report_kind": report.get("report_kind", REPORT_KIND),
        "runner_status": report.get("runner_status"),
        "request_ref": report.get("request_ref"),
        "controlled_validation_source_ref": report.get("controlled_validation_source_ref"),
        "lineage_candidate_refs": list(report.get("lineage_candidate_refs", [])),
        "oos_candidate_refs": list(report.get("oos_candidate_refs", [])),
        "accepted_lineage_count": int(report.get("accepted_lineage_count", 0) or 0),
        "accepted_oos_count": int(report.get("accepted_oos_count", 0) or 0),
        "rejected_reasons": list(report.get("rejected_reasons", [])),
        "can_clear_blockers": bool(report.get("can_clear_blockers", False)),
        "can_authorize_execution": bool(report.get("can_authorize_execution", False)),
        "can_synthesize_strategy": bool(report.get("can_synthesize_strategy", False)),
        "can_promote_candidate": bool(report.get("can_promote_candidate", False)),
        "can_activate_deployment": bool(report.get("can_activate_deployment", False)),
        "non_authoritative": bool(report.get("non_authoritative", NON_AUTHORITATIVE_FLAG)),
        "evidence_authority": report.get("evidence_authority", EVIDENCE_AUTHORITY),
    }


def compute_runner_hash(report: Mapping[str, Any]) -> str:
    payload = _canonical_runner_payload(report)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _reason_record(
    *,
    record_id: str,
    subject_id: str,
    reason_code: str,
    reason_text: str,
    evidence_refs: Sequence[str],
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "record_kind": "reason_record",
        "record_family": "bounded_generation_runner",
        "subject_id": subject_id,
        "reason_codes": [reason_code],
        "reason_text": reason_text,
        "evidence_refs": list(evidence_refs),
        "inputs_digest": f"{subject_id}:{reason_code}",
        "validation_status": "provisional",
        "authority_kind": "reason_record",
    }


def build_bounded_current_basket_generation_runner(
    request_payload: Mapping[str, Any] | None = None,
    *,
    repo_root: Path = Path("."),
    controlled_validation_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    raw_request_payload = request_payload if isinstance(request_payload, Mapping) else None
    request_report = _request_snapshot(raw_request_payload)
    discovery_report = discovery.build_bounded_current_basket_generation_discovery(
        raw_request_payload if request_report.get("validation_status") == "valid" else None,
        repo_root=repo_root,
    )
    request = request_report.get("request") if isinstance(request_report.get("request"), Mapping) else {}
    safe_generation_command_found = bool((discovery_report.get("summary") or {}).get("safe_bounded_generation_command_found"))
    valid_request = request_report.get("validation_status") == "valid"
    output_allowlisted = all(
        str(path).replace("\\", "/").startswith(("logs/", "artifacts/", "archived/", "backup/", "local_quarantine/"))
        for path in request.get("allowed_output_paths") or []
    )
    forbidden_capabilities = list(request.get("forbidden_capabilities") or [])
    blocking_reasons: list[str] = []
    if not valid_request:
        blocking_reasons.extend(list(request_report.get("rejection_reasons") or []))
    if not bool(request.get("approval_ref")):
        blocking_reasons.append("missing_approval_ref")
    if not output_allowlisted:
        blocking_reasons.append("output_paths_not_allowlisted")
    if forbidden_capabilities:
        blocking_reasons.append("forbidden_capabilities_present")
    if not safe_generation_command_found:
        blocking_reasons.append("safe_bounded_generation_command_not_found")
    source_ref = (
        str(controlled_validation_source.get("source_ref") or "")
        if isinstance(controlled_validation_source, Mapping)
        else ""
    )
    adapter_called = valid_request and bool(request.get("approval_ref")) and output_allowlisted and not forbidden_capabilities
    if adapter_called:
        adapter_result = validation_adapter.build_controlled_validation_adapter_result(
            request,
            controlled_validation_source=controlled_validation_source,
        )
    else:
        adapter_result = {
            "adapter_status": "blocked_invalid_bounded_request",
            "request_ref": str(request.get("request_id") or ""),
            "controlled_validation_source_ref": source_ref,
            "lineage_candidate_refs": [],
            "oos_candidate_refs": [],
            "accepted_lineage_count": 0,
            "accepted_oos_count": 0,
            "rejected_reasons": list(blocking_reasons),
            "can_clear_blockers": False,
            "non_authoritative": True,
            "evidence_authority": "adapter_not_called_preflight_failed",
        }
    adapter_status = str(adapter_result.get("adapter_status") or "")
    accepted_lineage_count = int(adapter_result.get("accepted_lineage_count") or 0)
    accepted_oos_count = int(adapter_result.get("accepted_oos_count") or 0)
    adapter_rejected_reasons = list(adapter_result.get("rejected_reasons") or [])
    adapter_has_required_counts = (
        bool(adapter_result.get("can_clear_blockers"))
        and accepted_lineage_count > 0
        and accepted_oos_count > 0
    )
    can_clear_blockers = False
    if adapter_has_required_counts:
        adapter_rejected_reasons.append("verifier_acceptance_required_to_clear_blockers")
    if not adapter_called:
        runner_status = (
            "blocked_missing_approval_ref"
            if "missing_approval_ref" in blocking_reasons
            else "blocked_output_path_not_allowlisted"
            if "output_paths_not_allowlisted" in blocking_reasons
            else "blocked_forbidden_capability"
            if "forbidden_capabilities_present" in blocking_reasons
            else "blocked_invalid_bounded_request"
        )
    elif adapter_status == "no_safe_controlled_validation_source":
        runner_status = "no_safe_controlled_validation_source"
    elif adapter_status == "accepted_structured_evidence":
        runner_status = "adapter_accepted_structured_evidence"
    elif adapter_status in {
        "blocked_missing_candidate_id",
        "blocked_missing_campaign_or_generation_id",
        "blocked_missing_oos_window",
        "blocked_missing_oos_metrics",
        "blocked_missing_cost_slippage_refs",
    }:
        runner_status = "adapter_provisional_only"
    elif adapter_status.startswith("rejected_") or adapter_status == "blocked_source_not_structured":
        runner_status = "adapter_rejected_source"
    else:
        runner_status = "dry_run_only" if blocking_reasons else "runner_ready"
    if adapter_rejected_reasons:
        blocking_reasons.extend(adapter_rejected_reasons)
    generation_status = "not_executed"
    reason_records = [
        _reason_record(
            record_id="rr_runner_missing_safe_command",
            subject_id=str(request.get("request_id") or ""),
            reason_code="safe_bounded_generation_command_not_found",
            reason_text="No safe bounded generation command is proven, so the runner stays dry-run only.",
            evidence_refs=["logs/qre_bounded_current_basket_generation_discovery/latest.json"],
        ),
        _reason_record(
            record_id="rr_runner_no_execution",
            subject_id=str(request.get("request_id") or ""),
            reason_code="no_execution_performed",
            reason_text="The runner did not execute generation, campaign, or trading behavior.",
            evidence_refs=[RUNNER_COMMAND],
        ),
    ]
    if blocking_reasons:
        reason_records.append(
            _reason_record(
                record_id="rr_runner_blocked_preflight",
                subject_id=str(request.get("request_id") or ""),
                reason_code="blocked_preflight",
                reason_text="Runner preflight failed closed because the request or command surface is not safely executable.",
                evidence_refs=["logs/qre_bounded_basket_request/latest.json", "logs/qre_bounded_current_basket_generation_discovery/latest.json"],
            )
        )
    preflight_status = "blocked_no_safe_generation_command" if safe_generation_command_found is False else "provisional_dry_run_ready"
    final_recommendation = (
        "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND"
        if request_report.get("validation_status") == "valid"
        else "request_invalid_fails_closed"
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "request": request,
        "request_validation_status": request_report.get("validation_status"),
        "request_rejection_reasons": list(request_report.get("rejection_reasons") or []),
        "summary": {
            "request_id": str(request.get("request_id") or ""),
            "symbols": list(request.get("symbols") or []),
            "preset_id": str(request.get("preset_id") or ""),
            "timeframe": str(request.get("timeframe") or ""),
            "safe_generation_command_found": safe_generation_command_found,
            "generation_status": generation_status,
            "reason_record_count": len(reason_records),
            "final_recommendation": final_recommendation,
            "operator_summary": (
                "Provisional bounded current-basket runner stays dry-run only until a safe bounded generation command is proven."
            ),
        },
        "preflight": {
            "preflight_status": preflight_status,
            "blocking_preflight_reasons": blocking_reasons,
            "approval_packet_ready": request_report.get("validation_status") == "valid" and not safe_generation_command_found,
            "auto_run_allowed": False,
            "operator_decision_required": True,
            "safe_existing_generation_command_available": safe_generation_command_found,
            "controlled_validation_adapter_called": adapter_called,
            "request_valid": valid_request,
            "approval_ref_present": bool(request.get("approval_ref")),
            "output_paths_allowlisted": output_allowlisted,
            "forbidden_capabilities_present": forbidden_capabilities,
        },
        "runner_status": runner_status,
        "request_ref": str(request.get("request_id") or ""),
        "adapter_result_ref": "embedded:adapter_result",
        "adapter_result": adapter_result,
        "controlled_validation_source_ref": str(adapter_result.get("controlled_validation_source_ref") or source_ref),
        "lineage_candidate_refs": list(adapter_result.get("lineage_candidate_refs") or []),
        "oos_candidate_refs": list(adapter_result.get("oos_candidate_refs") or []),
        "accepted_lineage_count": accepted_lineage_count,
        "accepted_oos_count": accepted_oos_count,
        "rejected_reasons": _unique_in_order([str(reason) for reason in blocking_reasons]),
        "can_clear_blockers": can_clear_blockers,
        "can_authorize_execution": False,
        "can_synthesize_strategy": False,
        "can_promote_candidate": False,
        "can_activate_deployment": False,
        "non_authoritative": NON_AUTHORITATIVE_FLAG,
        "evidence_authority": EVIDENCE_AUTHORITY,
        "generation_manifest": {
            "generation_run_id": None,
            "generation_mode": "provisional_dry_run_only",
            "execution_status": generation_status,
            "scope_hash": str(request.get("scope_hash") or ""),
            "symbols": list(request.get("symbols") or []),
            "preset_id": str(request.get("preset_id") or ""),
            "timeframe": str(request.get("timeframe") or ""),
            "safe_existing_generation_command_available": safe_generation_command_found,
            "approval_required": True,
            "auto_run_allowed": False,
            "final_recommendation": final_recommendation,
            "controlled_validation_source_ref": str(adapter_result.get("controlled_validation_source_ref") or source_ref),
            "adapter_status": adapter_status,
            "accepted_lineage_count": accepted_lineage_count,
            "accepted_oos_count": accepted_oos_count,
            "can_clear_blockers": can_clear_blockers,
        },
        "command_manifest": {
            "runner_command": RUNNER_COMMAND,
            "discovery_report_ref": "logs/qre_bounded_current_basket_generation_discovery/latest.json",
            "safe_report_only_commands": list(discovery.SAFE_REPORT_ONLY_COMMANDS),
            "command_classification_counts": dict((discovery_report.get("command_surface") or {}).get("classification_counts") or {}),
            "final_recommendation": final_recommendation,
        },
        "reason_records": reason_records,
        "downstream_rerun_manifest": {
        "commands": [
            "python -m research.qre_bounded_current_basket_generation_discovery --write",
            "python -m research.qre_bounded_first_batch_generation_decision --write",
            "python -m research.qre_artifact_authority --write",
            "python -m research.qre_reason_record_contract --write",
            "python -m research.qre_structured_lineage_artifacts --write",
            "python -m research.qre_structured_oos_artifacts --write",
            "python -m research.qre_first_batch_evidence_recovery_cascade --write",
            "python -m research.qre_guarded_alias_bounded_generation_cascade --write",
            "python -m research.qre_first_batch_evidence_recovery_readiness --write",
                "python -m research.qre_basket_operator_action_plan --write",
                "python -m research.qre_basket_next_action_queue --write",
                "python -m research.qre_evidence_complete_basket_closure --write",
                "python -m research.qre_trusted_loop_review_packet --write",
            ],
            "generation_mutation_attempted": False,
            "trading_authority_granted": False,
        },
        "safety_invariants": {
            "read_only": True,
            "dry_run_only": True,
            "no_campaign_mutation": True,
            "no_trading_authority": True,
            "no_external_fetch": True,
            "no_runner_execution": True,
            "provisional_until_safe_command_exists": True,
            "adapter_output_not_proof_by_itself": True,
            "verifier_acceptance_required_to_clear_blockers": True,
        },
    }
    report["controlled_validation_adapter_result_materialization"] = adapter_materialization.build_controlled_validation_adapter_result_materialization(
        report
    )
    report["controlled_validation_adapter_result_materialization_ref"] = "embedded:controlled_validation_adapter_result_materialization"
    report["controlled_validation_adapter_result_materialization_status"] = str(
        (report.get("controlled_validation_adapter_result_materialization") or {}).get("materialization_status") or ""
    )
    report["hash"] = compute_runner_hash(report)
    return report


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    preflight = report.get("preflight") if isinstance(report.get("preflight"), Mapping) else {}
    return "\n".join(
        [
            "# QRE Bounded Current Basket Generation Runner",
            "",
            _table(
                ["Field", "Value"],
                [
                    ["request_id", str(summary.get("request_id") or "")],
                    ["generation_status", str(summary.get("generation_status") or "")],
                    ["final_recommendation", str(summary.get("final_recommendation") or "")],
                    ["preflight_status", str(preflight.get("preflight_status") or "")],
                ],
            ),
            "",
            _table(
                ["Field", "Value"],
                [
                    ["symbols", ", ".join(str(v) for v in summary.get("symbols") or []) or "none"],
                    ["preset_id", str(summary.get("preset_id") or "")],
                    ["timeframe", str(summary.get("timeframe") or "")],
                    ["safe_generation_command_found", str(bool(summary.get("safe_generation_command_found"))).lower()],
                ],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_bounded_current_basket_generation_runner: refusing write outside allowlist: {path!r}"
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
    materialization = report.get("controlled_validation_adapter_result_materialization")
    if isinstance(materialization, Mapping):
        materialization_paths = adapter_materialization.write_outputs(materialization, repo_root=repo_root)
    else:
        materialization_paths = {}
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
        **({"controlled_validation_adapter_result_materialization": materialization_paths.get("latest")} if materialization_paths else {}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_bounded_current_basket_generation_runner",
        description="Build the provisional bounded current-basket generation runner report.",
    )
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--controlled-validation-source-file")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    request_payload = _request_from_file(Path(args.request_file))
    source_payload = _source_from_file(
        Path(args.controlled_validation_source_file)
        if args.controlled_validation_source_file
        else None
    )
    report = build_bounded_current_basket_generation_runner(
        request_payload,
        controlled_validation_source=source_payload,
    )
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
