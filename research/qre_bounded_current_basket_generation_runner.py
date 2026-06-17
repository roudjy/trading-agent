from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_bounded_basket_request as basket_request
from research import qre_bounded_current_basket_generation_discovery as discovery


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
    return {
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
            "request_valid": valid_request,
            "approval_ref_present": bool(request.get("approval_ref")),
            "output_paths_allowlisted": output_allowlisted,
            "forbidden_capabilities_present": forbidden_capabilities,
        },
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
        },
    }


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
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_bounded_current_basket_generation_runner",
        description="Build the provisional bounded current-basket generation runner report.",
    )
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    request_payload = _request_from_file(Path(args.request_file))
    report = build_bounded_current_basket_generation_runner(request_payload)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
