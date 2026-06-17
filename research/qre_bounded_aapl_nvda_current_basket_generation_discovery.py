from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_bounded_first_batch_generation_decision as decision


REPORT_KIND: Final[str] = "qre_bounded_aapl_nvda_current_basket_generation_discovery"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path(
    "logs/qre_bounded_aapl_nvda_current_basket_generation_discovery"
)
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_bounded_aapl_nvda_current_basket_generation_discovery/"

APPROVAL_SCOPE_ID: Final[str] = (
    "aapl_nvda_current_basket_trend_pullback_continuation_daily_v1_daily_v1"
)
APPROVED_SYMBOLS: Final[tuple[str, ...]] = ("AAPL", "NVDA")
APPROVED_PRESET: Final[str] = "trend_pullback_continuation_daily_v1"
APPROVED_TIMEFRAME: Final[str] = "daily_v1"
APPROVED_PURPOSE: Final[str] = (
    "generate_or_restore_and_accept_structured_current_basket_evidence_within_exact_scope"
)
SOURCE_PR: Final[str] = "#556"
SOURCE_MAIN_COMMIT: Final[str] = "8a23507"

SAFE_REPORT_ONLY_COMMANDS: Final[tuple[str, ...]] = (
    "python -m research.qre_guarded_alias_bounded_generation_cascade --write",
    "python -m research.qre_bounded_first_batch_generation_decision --write",
    "python -m research.qre_bounded_generation_artifact_acceptance_verifier --write",
    "python -m research.qre_bounded_aapl_nvda_current_basket_generation_discovery --write",
)

EXACT_SCOPE_GENERATION_CANDIDATES: Final[tuple[str, ...]] = (
    "python -m research.controlled_discovery_grid --symbols AAPL,NVDA --preset trend_pullback_continuation_daily_v1 --timeframe daily_v1",
    "python -m research.controlled_validation --symbols AAPL,NVDA --preset trend_pullback_continuation_daily_v1 --timeframe daily_v1",
)

BROADER_OR_UNSAFE_CANDIDATES: Final[tuple[str, ...]] = (
    "python -m research.run_research --preset trend_pullback_continuation_daily_v1",
    "python -m research.campaign_launcher --preset trend_pullback_continuation_daily_v1",
    "python -m research.qre_controlled_research_run --write",
    "python -m reporting.qre_controlled_validation_execution --write",
)

FORBIDDEN_KEYWORDS: Final[dict[str, str]] = {
    "campaign_launcher": "forbidden_mutation",
    "run_campaign": "forbidden_mutation",
    "campaign_queue": "forbidden_mutation",
    "campaign_registry": "forbidden_mutation",
    "paper": "forbidden_trading",
    "shadow": "forbidden_trading",
    "live": "forbidden_trading",
    "broker": "forbidden_trading",
    "risk": "forbidden_trading",
    "execution": "forbidden_trading",
    "strategy synthesis": "forbidden_mutation",
    "strategy registration": "forbidden_mutation",
    "candidate promotion": "forbidden_mutation",
    "provider activation": "forbidden_external_fetch",
    "provider fetch": "forbidden_external_fetch",
    "external data fetch": "forbidden_external_fetch",
}


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


def _decision_snapshot(repo_root: Path) -> dict[str, Any]:
    payload = _read_json(
        repo_root / "logs" / "qre_bounded_first_batch_generation_decision" / "latest.json"
    )
    if isinstance(payload, dict) and str(payload.get("report_kind") or "") == "qre_bounded_first_batch_generation_decision":
        return payload
    return decision.build_bounded_first_batch_generation_decision(repo_root=repo_root)


def _git_commit_iso(repo_root: Path, rev: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "show", "-s", "--format=%cI", rev],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    return text or None


def _module_file_exists(repo_root: Path, module_name: str) -> bool:
    module_path = repo_root / Path(*module_name.split("."))
    return module_path.with_suffix(".py").is_file()


def _module_has_cli_entrypoint(repo_root: Path, module_name: str) -> bool:
    module_path = repo_root / Path(*module_name.split("."))
    path = module_path.with_suffix(".py")
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "if __name__ == \"__main__\"" in text or "argparse.ArgumentParser" in text


def _command_to_module_name(command: str) -> str | None:
    parts = command.split()
    if len(parts) < 3 or parts[0] != "python" or parts[1] != "-m":
        return None
    return parts[2]


def _has_exact_scope_tokens(command: str) -> bool:
    lowered = " ".join(command.split()).lower()
    return (
        "aapl,nvda" in lowered
        and APPROVED_PRESET in lowered
        and APPROVED_TIMEFRAME in lowered
    )


def _approval_manifest(repo_root: Path) -> dict[str, Any]:
    created_at_utc = _git_commit_iso(repo_root, SOURCE_MAIN_COMMIT) or "1970-01-01T00:00:00+00:00"
    return {
        "approval_scope_id": APPROVAL_SCOPE_ID,
        "approved_by_operator": True,
        "approval_text_summary": (
            "Operator approval is granted for bounded current-basket evidence generation only "
            "within the exact AAPL/NVDA trend_pullback_continuation_daily_v1 daily_v1 scope."
        ),
        "approved_symbols": list(APPROVED_SYMBOLS),
        "approved_preset": APPROVED_PRESET,
        "approved_timeframe": APPROVED_TIMEFRAME,
        "approved_purpose": APPROVED_PURPOSE,
        "allowed_output_paths": [
            "logs/",
            "artifacts/",
            "archived/",
            "backup/",
            "local_quarantine/",
        ],
        "forbidden_paths": [
            "research/research_latest.json",
            "research/strategy_matrix.csv",
            "paper/",
            "shadow/",
            "live/",
            "broker/",
            "risk/",
            "execution/",
        ],
        "forbidden_capabilities": [
            "campaign_launch",
            "campaign_queue_mutation",
            "campaign_registry_mutation",
            "run_campaign_mutation",
            "strategy_synthesis",
            "strategy_registration",
            "candidate_promotion",
            "paper_shadow_live",
            "broker_risk_execution",
            "provider_activation",
            "external_data_fetch",
            "frozen_contract_mutation",
        ],
        "created_at_utc": created_at_utc,
        "source_pr": SOURCE_PR,
        "source_main_commit": SOURCE_MAIN_COMMIT,
    }


def _classify_candidate(command: str, repo_root: Path) -> dict[str, Any]:
    envelope = decision.classify_command_envelope(command)
    module_name = _command_to_module_name(command)
    module_exists = _module_file_exists(repo_root, module_name) if module_name else False
    module_has_cli = _module_has_cli_entrypoint(repo_root, module_name) if module_name else False
    exact_scope = _has_exact_scope_tokens(command)
    lowered = command.lower()
    disposition = "unknown_requires_operator_review"
    reason = "exact_scope_bounded_generation_command_not_found"
    if envelope["classification"] == "safe_report_only":
        disposition = "report_only"
        reason = "report_only_command_does_not_generate_evidence"
    elif envelope["classification"] == "approval_required_generation" and exact_scope:
        if module_exists and module_has_cli:
            disposition = "bounded_generation_approved_for_this_pr"
            reason = "exact_scope_cli_entrypoint_present_but_operator_approval_required"
        else:
            disposition = "unknown_requires_operator_review"
            reason = "exact_scope_candidate_missing_cli_entrypoint_or_module"
    elif envelope["classification"] in {"forbidden_mutation", "forbidden_trading", "forbidden_external_fetch"}:
        disposition = envelope["classification"]
        reason = "command_exceeds_read_only_governance_boundary"
    elif any(fragment in lowered for fragment in FORBIDDEN_KEYWORDS):
        disposition = "unknown_requires_operator_review"
        reason = "command_contains_forbidden_fragment"

    return {
        "command": command,
        "module_name": module_name,
        "module_exists": module_exists,
        "module_has_cli_entrypoint": module_has_cli,
        "exact_scope_match": exact_scope,
        "classification": envelope["classification"],
        "disposition": disposition,
        "reason": reason,
        "operator_approval_required": bool(envelope.get("operator_approval_required")) or disposition != "report_only",
        "auto_run_allowed": False,
        "safe_command_available": disposition == "bounded_generation_approved_for_this_pr",
    }


def build_bounded_aapl_nvda_current_basket_generation_discovery(
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    approval_manifest = _approval_manifest(repo_root)
    preflight = _decision_snapshot(repo_root)
    candidate_commands = (
        *SAFE_REPORT_ONLY_COMMANDS,
        *EXACT_SCOPE_GENERATION_CANDIDATES,
        *BROADER_OR_UNSAFE_CANDIDATES,
    )
    command_rows = [_classify_candidate(command, repo_root) for command in candidate_commands]
    safe_candidates = [row for row in command_rows if bool(row.get("safe_command_available"))]
    exact_scope_candidates = [row for row in command_rows if bool(row.get("exact_scope_match"))]
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "approval_scope_id": approval_manifest["approval_scope_id"],
            "approval_packet_ready": bool((preflight.get("preflight") or {}).get("approval_packet_ready")),
            "blocking_preflight_reasons": list((preflight.get("preflight") or {}).get("blocking_preflight_reasons") or []),
            "safe_bounded_generation_command_found": bool(safe_candidates),
            "safe_bounded_generation_command_count": len(safe_candidates),
            "exact_scope_candidate_count": len(exact_scope_candidates),
            "final_recommendation": (
                "bounded_generation_command_found"
                if safe_candidates
                else "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND"
            ),
            "operator_summary": (
                "No repo-local exact-scope bounded generation command can be proven safe and executable "
                "from the current command surface; report-only surfaces remain available."
                if not safe_candidates
                else "A repo-local exact-scope bounded generation command is available but remains operator-approved only."
            ),
        },
        "approval_manifest": approval_manifest,
        "preflight": preflight.get("preflight") or {},
        "command_surface": {
            "safe_report_only": list(SAFE_REPORT_ONLY_COMMANDS),
            "exact_scope_generation_candidates": list(EXACT_SCOPE_GENERATION_CANDIDATES),
            "broader_or_unsafe_candidates": list(BROADER_OR_UNSAFE_CANDIDATES),
            "rows": command_rows,
        },
        "decision_packet_ref": "logs/qre_bounded_first_batch_generation_decision/latest.json",
        "safety_invariants": {
            "read_only": True,
            "no_actual_generation_run": True,
            "no_campaign_mutation": True,
            "no_queue_mutation": True,
            "no_registry_mutation": True,
            "no_trading_authority": True,
            "no_external_provider_activation": True,
            "no_frozen_contract_mutation": True,
            "no_context_only_evidence_promoted_to_proof": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    approval = report.get("approval_manifest") if isinstance(report.get("approval_manifest"), Mapping) else {}
    rows = report.get("command_surface", {}).get("rows") if isinstance(report.get("command_surface"), Mapping) else []
    return "\n".join(
        [
            "# QRE Bounded AAPL/NVDA Current-Basket Generation Discovery",
            "",
            _table(
                ["Field", "Value"],
                [
                    ["approval_scope_id", str(summary.get("approval_scope_id") or "")],
                    ["approval_packet_ready", str(bool(summary.get("approval_packet_ready"))).lower()],
                    ["safe_bounded_generation_command_found", str(bool(summary.get("safe_bounded_generation_command_found"))).lower()],
                    ["final_recommendation", str(summary.get("final_recommendation") or "")],
                ],
            ),
            "",
            _table(
                ["Approval", "Value"],
                [
                    ["approved_symbols", ",".join(str(v) for v in approval.get("approved_symbols") or []) or "none"],
                    ["approved_preset", str(approval.get("approved_preset") or "")],
                    ["approved_timeframe", str(approval.get("approved_timeframe") or "")],
                    ["source_pr", str(approval.get("source_pr") or "")],
                    ["source_main_commit", str(approval.get("source_main_commit") or "")],
                ],
            ),
            "",
            _table(
                ["Command", "Disposition", "Module", "Exact Scope", "Safe bounded"],
                [
                    [
                        str(row.get("command") or ""),
                        str(row.get("disposition") or ""),
                        str(row.get("module_name") or ""),
                        str(bool(row.get("exact_scope_match"))).lower(),
                        str(bool(row.get("safe_command_available"))).lower(),
                    ]
                    for row in rows
                ] or [["none", "none", "none", "false", "false"]],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_bounded_aapl_nvda_current_basket_generation_discovery: refusing write outside allowlist: {path!r}"
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
        prog="python -m research.qre_bounded_aapl_nvda_current_basket_generation_discovery",
        description="Build the bounded AAPL/NVDA current-basket generation discovery report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_bounded_aapl_nvda_current_basket_generation_discovery()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
