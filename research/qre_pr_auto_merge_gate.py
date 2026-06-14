"""QRE PR auto-merge gate.

The gate can evaluate PR metadata from a mocked/configured backend and, only
when explicitly enabled, call an injected or real merge command. Default CLI
behavior is observation/fail-closed; unsafe PRs are never merged.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_pr_auto_merge_gate"
DEFAULT_BUILD_REQUEST_PATH: Final[Path] = Path(
    "logs/qre_autonomous_market_research_loop/latest_build_request.json"
)
DEFAULT_CONSUMER_LATEST: Final[Path] = Path("logs/qre_build_request_consumer/latest.json")
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_pr_auto_merge_gate")
FORBIDDEN_PATH_PREFIXES: Final[tuple[str, ...]] = (
    "broker/",
    "execution/",
    "risk/",
    "paper/",
    "shadow/",
    "live/",
    "automation/live",
    ".github/workflows/",
    ".github/CODEOWNERS",
    ".claude/",
)
FORBIDDEN_EXACT_PATHS: Final[tuple[str, ...]] = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)
GH_PR_VIEW_FIELDS: Final[str] = (
    "number,title,state,mergeCommit,headRefName,baseRefName,statusCheckRollup,"
    "changedFiles,url,mergeable"
)
BLOCKING_CHECK_CONCLUSIONS: Final[set[str]] = {
    "ACTION_REQUIRED",
    "CANCELLED",
    "FAILURE",
    "NEUTRAL",
    "STARTUP_FAILURE",
    "STALE",
    "TIMED_OUT",
}
PENDING_CHECK_STATES: Final[set[str]] = {
    "EXPECTED",
    "IN_PROGRESS",
    "PENDING",
    "QUEUED",
    "REQUESTED",
    "WAITING",
}


CommandRunner = Callable[[list[str]], tuple[int, str, str]]


class PrAutoMergeGateError(RuntimeError):
    """Raised when PR gate inputs are malformed."""


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _assert_inside(root: Path, path: Path) -> None:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise PrAutoMergeGateError(f"refusing write outside output dir: {path}")


def _default_command_runner(cmd: list[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return (-1, "", repr(exc))
    return (result.returncode, result.stdout or "", result.stderr or "")


def _path_forbidden(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return normalized in FORBIDDEN_EXACT_PATHS or any(
        normalized.startswith(prefix) for prefix in FORBIDDEN_PATH_PREFIXES
    )


def _protected_output(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return normalized in FORBIDDEN_EXACT_PATHS


def _metadata_from_sources(
    *,
    consumer_latest_path: Path,
    pr_metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if pr_metadata is not None:
        return pr_metadata
    consumer = _read_json(consumer_latest_path)
    if not consumer:
        return None
    metadata = consumer.get("pr_metadata")
    if not isinstance(metadata, dict):
        return None
    metadata = dict(metadata)
    if "safe_for_auto_merge" in consumer:
        metadata["safe_for_auto_merge"] = consumer.get("safe_for_auto_merge")
    return metadata


def _pr_number(metadata: dict[str, Any]) -> str:
    return str(metadata.get("number") or metadata.get("pr_number") or "").strip()


def _query_live_pr_status(
    pr_number: str,
    *,
    command_runner: CommandRunner,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    rc, stdout, stderr = command_runner(
        ["gh", "pr", "view", pr_number, "--json", GH_PR_VIEW_FIELDS]
    )
    diagnostic = {
        "returncode": rc,
        "stderr": stderr[:2000],
    }
    if rc != 0:
        return None, diagnostic
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        diagnostic["parse_error"] = str(exc)
        return None, diagnostic
    if not isinstance(parsed, dict):
        diagnostic["parse_error"] = "gh pr view did not return a JSON object"
        return None, diagnostic
    return parsed, diagnostic


def _check_label(check: dict[str, Any]) -> str:
    for key in ("name", "context", "workflowName"):
        value = check.get(key)
        if value:
            return str(value)
    return "<unnamed>"


def _check_status(check: dict[str, Any]) -> str:
    return str(check.get("status") or check.get("state") or "").upper()


def _check_conclusion(check: dict[str, Any]) -> str:
    return str(check.get("conclusion") or "").upper()


def _live_check_summary(live_pr: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    rollup = live_pr.get("statusCheckRollup")
    checks = rollup if isinstance(rollup, list) else []
    summary: dict[str, Any] = {
        "success": 0,
        "skipped": 0,
        "pending": 0,
        "failed": 0,
        "blocking": [],
    }
    blocking = summary["blocking"]
    if not checks:
        blocking.append({"check": "<none>", "reason": "no_live_checks"})
        return False, summary
    for raw_check in checks:
        if not isinstance(raw_check, dict):
            continue
        label = _check_label(raw_check)
        status = _check_status(raw_check)
        conclusion = _check_conclusion(raw_check)
        state = str(raw_check.get("state") or "").upper()
        if conclusion == "SKIPPED":
            summary["skipped"] += 1
            continue
        if conclusion == "SUCCESS" or state == "SUCCESS":
            summary["success"] += 1
            continue
        if conclusion in BLOCKING_CHECK_CONCLUSIONS or state in {"ERROR", "FAILURE", "FAILED"}:
            summary["failed"] += 1
            blocking.append({"check": label, "reason": conclusion or state or "failed"})
            continue
        if status in PENDING_CHECK_STATES or state in PENDING_CHECK_STATES or not conclusion:
            summary["pending"] += 1
            blocking.append({"check": label, "reason": status or state or "pending"})
            continue
        summary["failed"] += 1
        blocking.append({"check": label, "reason": conclusion or state or status or "unknown"})
    return not blocking, summary


def evaluate_pr_gate(
    *,
    build_request_path: Path = DEFAULT_BUILD_REQUEST_PATH,
    consumer_latest_path: Path = DEFAULT_CONSUMER_LATEST,
    pr_metadata: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    command_runner: CommandRunner | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    build_request = _read_json(build_request_path)
    metadata = _metadata_from_sources(
        consumer_latest_path=consumer_latest_path,
        pr_metadata=pr_metadata,
    )
    source_env = env if env is not None else os.environ
    auto_merge_requested = str(source_env.get("QRE_AUTO_MERGE_GREEN") or "").lower() == "true"
    blockers: list[str] = []
    if not build_request:
        blockers.append("build_request_missing")
        build_request = {}
    if metadata is None:
        blockers.append("pr_metadata_missing")
        metadata = {}
    runner = command_runner or _default_command_runner
    pr_number = _pr_number(metadata)
    live_pr: dict[str, Any] | None = None
    live_query_diagnostic: dict[str, Any] | None = None
    live_pr_status_queried = False
    live_check_summary = {
        "success": 0,
        "skipped": 0,
        "pending": 0,
        "failed": 0,
        "blocking": [],
    }
    ci_source = "artifact_metadata"
    pr_green = metadata.get("ci_status") == "green"
    if pr_number:
        live_pr_status_queried = True
        live_pr, live_query_diagnostic = _query_live_pr_status(
            pr_number,
            command_runner=runner,
        )
        if live_pr is None:
            blockers.append("live_pr_status_unavailable")
            pr_green = False
            ci_source = "live_gh_pr_view_unavailable"
        else:
            pr_green, live_check_summary = _live_check_summary(live_pr)
            ci_source = "live_gh_pr_view"
    changed_files = [str(item) for item in metadata.get("changed_files") or []]
    forbidden_paths = sorted(path for path in changed_files if _path_forbidden(path))
    protected_paths = sorted(path for path in changed_files if _protected_output(path))
    if build_request.get("safe_for_ade_build") is not True:
        blockers.append("build_request_not_safe_for_ade_build")
    if build_request.get("execution_allowed") is True:
        blockers.append("build_request_execution_allowed_true")
    if metadata.get("safe_for_auto_merge") is not True:
        blockers.append("safe_for_auto_merge_not_true")
    if not pr_green:
        blockers.append("ci_not_green")
    live_state = str(live_pr.get("state") or "") if live_pr else None
    live_mergeable = str(live_pr.get("mergeable") or "") if live_pr else None
    if live_pr is not None and live_state != "OPEN":
        blockers.append("pr_not_open")
    if live_pr is not None and live_mergeable != "MERGEABLE":
        blockers.append("pr_not_mergeable")
    if live_pr is None and metadata.get("mergeable") is not True:
        blockers.append("pr_not_mergeable")
    if not str(metadata.get("branch") or "").startswith("feat/qre-"):
        blockers.append("branch_not_automated_qre_pattern")
    if metadata.get("title") != build_request.get("recommended_pr_title"):
        blockers.append("pr_title_mismatch")
    if forbidden_paths:
        blockers.append("forbidden_paths_touched")
    if protected_paths:
        blockers.append("protected_outputs_mutated")
    if not auto_merge_requested:
        blockers.append("auto_merge_not_enabled")

    auto_merge_allowed = not blockers
    merge_performed = False
    merge_result: dict[str, Any] | None = None
    if auto_merge_allowed:
        if not pr_number:
            blockers.append("pr_number_missing")
            auto_merge_allowed = False
        else:
            rc, stdout, stderr = runner(["gh", "pr", "merge", pr_number, "--squash", "--delete-branch"])
            merge_performed = rc == 0
            merge_result = {"returncode": rc, "stdout": stdout[:2000], "stderr": stderr[:2000]}
            if not merge_performed:
                blockers.append("merge_command_failed")
                auto_merge_allowed = False

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated,
        "request_id": build_request.get("request_id"),
        "pr_number": metadata.get("number") or metadata.get("pr_number"),
        "ci_observed": bool(metadata),
        "pr_green": pr_green,
        "ci_source": ci_source,
        "live_pr_status_queried": live_pr_status_queried,
        "live_pr_state": live_state,
        "live_pr_mergeable": live_mergeable,
        "live_check_summary": live_check_summary,
        "live_query_diagnostic": live_query_diagnostic,
        "auto_merge_requested": auto_merge_requested,
        "auto_merge_allowed": auto_merge_allowed,
        "manual_governance_required": bool(blockers),
        "pr_auto_merged": merge_performed,
        "merge_result": merge_result,
        "forbidden_paths_touched": forbidden_paths,
        "blocked_reasons": blockers,
        "paper_shadow_live_allowed": False,
        "broker_risk_allowed": False,
        "execution_allowed": False,
        "campaign_launcher_called": False,
        "run_research_called": False,
        "protected_outputs_mutated": bool(protected_paths),
        "final_recommendation": (
            "pr_auto_merged" if merge_performed else "manual_governance_required_or_not_green"
        ),
    }


def render_operator_summary(snapshot: dict[str, Any]) -> str:
    reasons = ", ".join(snapshot.get("blocked_reasons") or []) or "none"
    return "\n".join(
        [
            "# QRE PR Auto-Merge Gate",
            "",
            f"- PR: {snapshot.get('pr_number')}",
            f"- CI observed: {snapshot.get('ci_observed')}",
            f"- PR green: {snapshot.get('pr_green')}",
            f"- Auto-merge allowed: {snapshot.get('auto_merge_allowed')}",
            f"- PR auto-merged: {snapshot.get('pr_auto_merged')}",
            f"- Manual governance required: {snapshot.get('manual_governance_required')}",
            f"- Blocked reasons: {reasons}",
            "- Trading: disabled.",
            "- Protected public research outputs: not mutated.",
            "",
        ]
    )


def write_outputs(snapshot: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    run_id = f"pr-{snapshot.get('pr_number') or 'none'}__{str(snapshot['generated_at_utc']).replace(':', '').replace('-', '')}"
    latest = output_dir / "latest.json"
    summary = output_dir / "operator_summary.md"
    run_path = output_dir / "runs" / f"{run_id}.json"
    for path in (latest, summary, run_path):
        _assert_inside(output_dir, path)
    run_path.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(_json_dumps(snapshot), encoding="utf-8", newline="\n")
    summary.write_text(render_operator_summary(snapshot), encoding="utf-8", newline="\n")
    run_path.write_text(_json_dumps(snapshot), encoding="utf-8", newline="\n")
    return {"latest": latest.as_posix(), "operator_summary": summary.as_posix(), "run": run_path.as_posix()}


def run_gate(
    *,
    build_request_path: Path = DEFAULT_BUILD_REQUEST_PATH,
    consumer_latest_path: Path = DEFAULT_CONSUMER_LATEST,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    write: bool = False,
    env: dict[str, str] | None = None,
    command_runner: CommandRunner | None = None,
    pr_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = evaluate_pr_gate(
        build_request_path=build_request_path,
        consumer_latest_path=consumer_latest_path,
        pr_metadata=pr_metadata,
        env=env,
        command_runner=command_runner,
    )
    if write:
        snapshot["_artifact_paths"] = write_outputs(snapshot, output_dir=output_dir)
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate QRE PR auto-merge gate.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--build-request", default=DEFAULT_BUILD_REQUEST_PATH.as_posix())
    parser.add_argument("--consumer-latest", default=DEFAULT_CONSUMER_LATEST.as_posix())
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR.as_posix())
    args = parser.parse_args(argv)
    snapshot = run_gate(
        build_request_path=Path(args.build_request),
        consumer_latest_path=Path(args.consumer_latest),
        output_dir=Path(args.output_dir),
        write=args.write,
    )
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

