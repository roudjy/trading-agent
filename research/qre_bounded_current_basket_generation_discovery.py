from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_bounded_basket_request as basket_request


REPORT_KIND: Final[str] = "qre_bounded_current_basket_generation_discovery"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_bounded_current_basket_generation_discovery")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_bounded_current_basket_generation_discovery/"

SAFE_REPORT_ONLY_COMMANDS: Final[tuple[str, ...]] = (
    "python -m research.qre_bounded_basket_request --write",
    "python -m research.qre_bounded_current_basket_generation_discovery --write",
    "python -m research.qre_bounded_current_basket_generation_runner --request-file logs/qre_bounded_basket_request/latest.json --dry-run --write",
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


def _request_snapshot(
    request_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if request_payload is None:
        return {
            "schema_version": basket_request.SCHEMA_VERSION,
            "report_kind": basket_request.REPORT_KIND,
            "request": {},
            "validation_status": "rejected",
            "rejection_reasons": ["missing_request_payload"],
        }
    return basket_request.build_bounded_basket_request_snapshot(request_payload)


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


def _request_tokens(request_payload: Mapping[str, Any]) -> tuple[str, str, str]:
    request = request_payload.get("request")
    if not isinstance(request, Mapping):
        return "", "", ""
    symbols = ",".join(str(symbol) for symbol in request.get("symbols") or [])
    preset_id = str(request.get("preset_id") or "")
    timeframe = str(request.get("timeframe") or "")
    return symbols, preset_id, timeframe


def _scope_fit(command: str, *, request_payload: Mapping[str, Any]) -> str:
    symbols, preset_id, timeframe = _request_tokens(request_payload)
    lowered = " ".join(command.split()).lower()
    if "research.qre_bounded_current_basket_generation_runner" in lowered:
        return "exact" if symbols and preset_id and timeframe else "mismatch"
    if not symbols or not preset_id or not timeframe:
        return "mismatch"
    if symbols.lower() in lowered and preset_id.lower() in lowered and timeframe.lower() in lowered:
        return "exact"
    if any(token in lowered for token in (symbols.lower(), preset_id.lower(), timeframe.lower())):
        return "partial"
    return "mismatch"


def _classify_candidate(
    command: str,
    *,
    request_payload: Mapping[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    module_name = _command_to_module_name(command)
    module_exists = _module_file_exists(repo_root, module_name) if module_name else False
    module_has_cli = _module_has_cli_entrypoint(repo_root, module_name) if module_name else False
    scope_fit = _scope_fit(command, request_payload=request_payload)
    lowered = " ".join(command.split()).lower()
    missing_prerequisites: list[str] = []
    classification = "unknown_requires_operator_review"
    classification_reason = "command_requires_operator_review"
    next_action = "operator_review_required"

    if command in SAFE_REPORT_ONLY_COMMANDS:
        classification = "report_only"
        classification_reason = "read_only_report_command"
        next_action = "use_for_read_only_review"
    elif any(fragment in lowered for fragment in FORBIDDEN_KEYWORDS):
        for fragment, mapped in FORBIDDEN_KEYWORDS.items():
            if fragment in lowered:
                classification = mapped
                classification_reason = f"contains_forbidden_fragment:{fragment}"
                next_action = "reject_command"
                break
    elif module_name == "research.controlled_discovery_grid" and scope_fit == "exact":
        classification = "bounded_generation_candidate"
        classification_reason = "exact_scope_discovery_candidate"
        next_action = "operator_approval_required"
        if not module_exists:
            missing_prerequisites.append("module_missing")
        if module_exists and not module_has_cli:
            missing_prerequisites.append("module_has_no_cli_entrypoint")
    elif module_name == "research.controlled_validation" and scope_fit == "exact":
        classification = "approval_required_generation"
        classification_reason = "exact_scope_validation_requires_operator_approval"
        next_action = "operator_approval_required"
        if not module_exists:
            missing_prerequisites.append("module_missing")
        if module_exists and not module_has_cli:
            missing_prerequisites.append("module_has_no_cli_entrypoint")
    elif module_name == "research.qre_bounded_current_basket_generation_runner" and scope_fit == "exact":
        classification = "unknown_requires_operator_review"
        classification_reason = "runner_scaffold_not_yet_available"
        next_action = "build_runner_scaffold_or_keep_fail_closed"
        if not module_exists:
            missing_prerequisites.append("module_missing")
    elif scope_fit == "exact":
        classification = "unknown_requires_operator_review"
        classification_reason = "exact_scope_command_requires_operator_review"
        next_action = "operator_review_required"

    return {
        "command": command,
        "module_name": module_name,
        "module_exists": module_exists,
        "module_has_cli_entrypoint": module_has_cli,
        "scope_fit": scope_fit,
        "exact_scope_match": scope_fit == "exact",
        "classification": classification,
        "classification_reason": classification_reason,
        "missing_prerequisites": missing_prerequisites,
        "next_action": next_action,
        "operator_approval_required": classification != "report_only",
        "auto_run_allowed": False,
        "safe_command_available": classification == "report_only",
    }


def _candidate_commands(request_payload: Mapping[str, Any]) -> list[str]:
    symbols, preset_id, timeframe = _request_tokens(request_payload)
    symbols_arg = symbols or ""
    exact_scope = f"--symbols {symbols_arg} --preset {preset_id} --timeframe {timeframe}"
    return [
        *SAFE_REPORT_ONLY_COMMANDS,
        "python -m research.controlled_discovery_grid " + exact_scope,
        "python -m research.controlled_validation " + exact_scope,
        "python -m research.qre_bounded_current_basket_generation_runner --request-file logs/qre_bounded_basket_request/latest.json",
        f"python -m research.run_research --preset {preset_id}",
        f"python -m research.campaign_launcher --preset {preset_id}",
        "python -m research.campaign_queue mutation",
        "python -m research.campaign_registry mutation",
        "python -m research.paper shadow live",
        "python -m research.broker risk execution",
        "python -m research.strategy synthesis",
        "python -m research.strategy registration",
        "python -m research.candidate promotion",
        "python -m research.provider activation",
        "python -m research.external data fetch",
    ]


def build_bounded_current_basket_generation_discovery(
    request_payload: Mapping[str, Any] | None = None,
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    request_report = _request_snapshot(request_payload)
    request = request_report.get("request") if isinstance(request_report.get("request"), Mapping) else {}
    command_rows = []
    if request_report.get("validation_status") == "valid":
        command_rows = [
            _classify_candidate(command, request_payload=request_report, repo_root=repo_root)
            for command in _candidate_commands(request_report)
        ]
    counts = Counter(str(row["classification"]) for row in command_rows)
    exact_scope_candidates = [row for row in command_rows if row["scope_fit"] == "exact"]
    safe_candidates = [
        row
        for row in exact_scope_candidates
        if row["classification"] == "bounded_generation_candidate"
        and row["module_exists"]
        and row["module_has_cli_entrypoint"]
        and not row["missing_prerequisites"]
    ]
    top_blocker = ""
    for row in exact_scope_candidates:
        if row["classification"] != "report_only":
            top_blocker = row["classification_reason"]
            if row["missing_prerequisites"]:
                top_blocker = f"{top_blocker}:{','.join(row['missing_prerequisites'])}"
            break
    final_recommendation = (
        "request_invalid_fails_closed"
        if request_report.get("validation_status") != "valid"
        else "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND"
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
            "scope_hash": str(request.get("scope_hash") or ""),
            "exact_scope_candidate_count": len(exact_scope_candidates),
            "report_only_count": sum(1 for row in command_rows if row["classification"] == "report_only"),
            "bounded_generation_candidate_count": sum(
                1 for row in command_rows if row["classification"] == "bounded_generation_candidate"
            ),
            "approval_required_generation_count": sum(
                1 for row in command_rows if row["classification"] == "approval_required_generation"
            ),
            "forbidden_count": sum(
                1
                for row in command_rows
                if row["classification"] in {"forbidden_mutation", "forbidden_trading", "forbidden_external_fetch"}
            ),
            "unknown_count": sum(1 for row in command_rows if row["classification"] == "unknown_requires_operator_review"),
            "safe_bounded_generation_command_found": bool(safe_candidates),
            "top_blocker": top_blocker,
            "operator_summary": (
                "Generic bounded command discovery is request-driven and remains fail-closed until a safe bounded command exists."
            ),
            "final_recommendation": final_recommendation,
        },
        "command_surface": {
            "rows": command_rows,
            "classification_counts": dict(sorted(counts.items())),
        },
        "safety_invariants": {
            "read_only": True,
            "request_driven": True,
            "symbol_agnostic_core_paths": True,
            "no_trading_authority": True,
            "no_auto_run": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    request = report.get("request") if isinstance(report.get("request"), Mapping) else {}
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    rows = report.get("command_surface", {}).get("rows") if isinstance(report.get("command_surface"), Mapping) else []
    rows = rows if isinstance(rows, list) else []
    return "\n".join(
        [
            "# QRE Bounded Current Basket Generation Discovery",
            "",
            "## Summary",
            _table(
                ["Field", "Value"],
                [
                    ["request_id", str(summary.get("request_id") or "")],
                    ["validation_status", str(report.get("request_validation_status") or "")],
                    ["final_recommendation", str(summary.get("final_recommendation") or "")],
                    ["top_blocker", str(summary.get("top_blocker") or "")],
                ],
            ),
            "",
            "## Request",
            _table(
                ["Field", "Value"],
                [
                    ["symbols", ", ".join(str(v) for v in request.get("symbols") or []) or "none"],
                    ["preset_id", str(request.get("preset_id") or "")],
                    ["timeframe", str(request.get("timeframe") or "")],
                    ["scope_hash", str(request.get("scope_hash") or "")],
                ],
            ),
            "",
            "## Command Surface",
            _table(
                ["Command", "Classification", "Scope fit"],
                [
                    [
                        str(row.get("command") or ""),
                        str(row.get("classification") or ""),
                        str(row.get("scope_fit") or ""),
                    ]
                    for row in rows[:20]
                ]
                or [["none", "none", "none"]],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_bounded_current_basket_generation_discovery: refusing write outside allowlist: {path!r}"
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
        prog="python -m research.qre_bounded_current_basket_generation_discovery",
        description="Build the generic bounded current-basket generation discovery report.",
    )
    parser.add_argument("--request-file", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    payload = json.loads(args.request_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("request file must contain a JSON object")
    report = build_bounded_current_basket_generation_discovery(payload)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
