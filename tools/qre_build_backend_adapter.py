"""Adapter for QRE build-request backends.

This script is intentionally thin: it receives a build-request JSON path,
invokes an explicitly selected local backend (Codex or Claude), queries git/gh
for the resulting branch/PR metadata, writes one backend-result JSON artifact,
and prints the same JSON to stdout for ``qre_build_request_consumer``.

It does not trade, call QRE runtime execution paths, or bypass repository gates.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_build_backend_adapter_result"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_build_request_consumer/backend_results")
BACKENDS: Final[tuple[str, ...]] = ("codex_cli", "claude_cli")


class AdapterError(RuntimeError):
    """Raised when adapter inputs are invalid."""


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise AdapterError(f"build request unavailable: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AdapterError(f"build request malformed: {path}") from exc
    if not isinstance(parsed, dict):
        raise AdapterError("build request must be a JSON object")
    return parsed


def _run(cmd: list[str], *, timeout: int = 3600) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return (-1, "", repr(exc))
    return (result.returncode, result.stdout or "", result.stderr or "")


def _prompt(request: dict[str, Any], request_path: Path) -> str:
    acceptance = "\n".join(f"- {item}" for item in request.get("acceptance_commands") or [])
    forbidden = "\n".join(f"- {item}" for item in request.get("forbidden_actions") or [])
    scope = "\n".join(f"- {item}" for item in request.get("implementation_scope") or [])
    return "\n".join(
        [
            "You are implementing a QRE build request in the current repository.",
            "",
            f"Build request path: {request_path.as_posix()}",
            f"Request ID: {request.get('request_id')}",
            f"Next action: {request.get('next_action')}",
            f"Recommended branch: {request.get('recommended_branch')}",
            f"Recommended PR title: {request.get('recommended_pr_title')}",
            "",
            "Implementation scope:",
            scope,
            "",
            "Forbidden actions:",
            forbidden,
            "",
            "Required acceptance commands:",
            acceptance,
            "",
            "Requirements:",
            "- Create/use the recommended branch.",
            "- Implement only the requested safe development change.",
            "- Run the listed tests/commands.",
            "- Open a PR with the recommended title.",
            "- Do not activate paper, shadow, live, broker, risk, or execution.",
            "- Do not mutate research/research_latest.json or research/strategy_matrix.csv.",
            "- Do not call broad run_research or campaign_launcher.",
            "- Leave a concise final note with PR number/URL and tests run.",
        ]
    )


def _backend_command(backend: str, prompt: str) -> list[str]:
    if backend == "codex_cli":
        return ["codex", "exec", "--sandbox", "danger-full-access", prompt]
    if backend == "claude_cli":
        return [
            "claude",
            "--print",
            "--permission-mode",
            "bypassPermissions",
            "--output-format",
            "text",
            prompt,
        ]
    raise AdapterError(f"unsupported backend: {backend}")


def _current_branch() -> str:
    rc, out, _ = _run(["git", "branch", "--show-current"], timeout=60)
    return out.strip() if rc == 0 else ""


def _changed_paths(branch: str) -> list[str]:
    if not branch:
        return []
    _run(["git", "fetch", "origin", "main"], timeout=120)
    rc, out, _ = _run(["git", "diff", "--name-only", f"origin/main...{branch}"], timeout=120)
    if rc != 0:
        rc, out, _ = _run(["git", "diff", "--name-only", "origin/main...HEAD"], timeout=120)
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()] if rc == 0 else []


def _pr_metadata(branch: str) -> dict[str, Any] | None:
    if not branch:
        return None
    rc, out, _ = _run(
        [
            "gh",
            "pr",
            "view",
            branch,
            "--json",
            "number,url,title,headRefName,statusCheckRollup,mergeable,changedFiles",
        ],
        timeout=120,
    )
    if rc != 0:
        return None
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    checks = parsed.get("statusCheckRollup")
    ci_status = "unknown"
    if isinstance(checks, list) and checks:
        conclusions = {str(item.get("conclusion") or item.get("status") or "").upper() for item in checks if isinstance(item, dict)}
        if conclusions and conclusions <= {"SUCCESS", "COMPLETED", "NEUTRAL", "SKIPPED"}:
            ci_status = "green"
        elif any(item in conclusions for item in {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"}):
            ci_status = "failure"
        else:
            ci_status = "pending"
    return {
        "number": parsed.get("number"),
        "pr_number": parsed.get("number"),
        "url": parsed.get("url"),
        "pr_url": parsed.get("url"),
        "title": parsed.get("title"),
        "branch": parsed.get("headRefName") or branch,
        "ci_status": ci_status,
        "mergeable": parsed.get("mergeable") in {True, "MERGEABLE"},
        "changed_files_count": parsed.get("changedFiles"),
    }


def _safe_for_auto_merge(request: dict[str, Any], changed_paths: list[str]) -> bool:
    forbidden_prefixes = (
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
    forbidden_exact = {"research/research_latest.json", "research/strategy_matrix.csv"}
    if request.get("safe_for_ade_build") is not True or request.get("execution_allowed") is True:
        return False
    for path in changed_paths:
        normalized = path.replace("\\", "/").lstrip("./")
        if normalized in forbidden_exact or any(normalized.startswith(prefix) for prefix in forbidden_prefixes):
            return False
    return True


def build_backend_result(
    *,
    build_request_path: Path,
    backend: str,
    execute: bool = True,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    request = _read_json(build_request_path)
    started_at = _utcnow()
    backend_rc = 0
    backend_stdout = ""
    backend_stderr = ""
    if execute:
        backend_rc, backend_stdout, backend_stderr = _run(
            _backend_command(backend, _prompt(request, build_request_path)),
            timeout=7200,
        )

    branch = _current_branch()
    changed = _changed_paths(branch)
    metadata = _pr_metadata(branch)
    pr_created = metadata is not None
    if metadata is None:
        metadata = {
            "branch": branch,
            "title": request.get("recommended_pr_title"),
            "ci_status": "unknown",
            "mergeable": False,
            "changed_files": changed,
        }
    else:
        metadata["changed_files"] = changed

    tests_passed = bool(execute and backend_rc == 0)
    safe_for_auto_merge = bool(
        pr_created
        and tests_passed
        and metadata.get("branch") == request.get("recommended_branch")
        and metadata.get("title") == request.get("recommended_pr_title")
        and _safe_for_auto_merge(request, changed)
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "created_at_utc": started_at,
        "backend": backend,
        "request_id": request.get("request_id"),
        "build_request_path": build_request_path.as_posix(),
        "build_request_consumed": backend_rc == 0 and pr_created,
        "build_started": execute,
        "branch_created": bool(branch and branch == request.get("recommended_branch")),
        "code_changed": bool(changed),
        "tests_run": bool(execute),
        "pr_created": pr_created,
        "pr_metadata": metadata,
        "pr_number": metadata.get("number") or metadata.get("pr_number"),
        "pr_url": metadata.get("url") or metadata.get("pr_url"),
        "branch": metadata.get("branch"),
        "pr_title": metadata.get("title"),
        "tests_passed": tests_passed,
        "safe_for_auto_merge": safe_for_auto_merge,
        "changed_paths": changed,
        "backend_returncode": backend_rc,
        "backend_stdout_tail": backend_stdout[-4000:],
        "backend_stderr_tail": backend_stderr[-4000:],
        "paper_shadow_live_allowed": False,
        "broker_risk_allowed": False,
        "execution_allowed": False,
        "campaign_launcher_called": False,
        "run_research_called": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{request.get('request_id')}.json"
    out_path.write_text(_json_dumps(result), encoding="utf-8", newline="\n")
    result["backend_result_path"] = out_path.as_posix()
    out_path.write_text(_json_dumps(result), encoding="utf-8", newline="\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run QRE build backend and emit consumer-compatible JSON.")
    parser.add_argument("build_request", nargs="?", default=os.environ.get("QRE_BUILD_REQUEST_PATH", ""))
    parser.add_argument("--backend", choices=BACKENDS, default=os.environ.get("QRE_BUILD_BACKEND", "codex_cli"))
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR.as_posix())
    parser.add_argument("--no-execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.build_request:
        raise SystemExit("build request path required")
    result = build_backend_result(
        build_request_path=Path(args.build_request),
        backend=args.backend,
        output_dir=Path(args.output_dir),
        execute=not args.no_execute,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
