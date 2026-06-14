"""QRE build-request consumer.

The consumer reads QRE build-request artifacts and optionally invokes an
explicit operator-configured build backend. Default behavior is fail-closed:
no backend, no branch, no PR, no code execution.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_build_request_consumer"
DEFAULT_BUILD_REQUEST_PATH: Final[Path] = Path(
    "logs/qre_autonomous_market_research_loop/latest_build_request.json"
)
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_build_request_consumer")
SUPPORTED_BACKENDS: Final[tuple[str, ...]] = (
    "codex_cli",
    "claude_cli",
    "gh_workflow_dispatch",
    "repo_native_ade",
    "dry_run_only",
)


CommandRunner = Callable[[list[str], dict[str, str]], tuple[int, str, str]]


class BuildRequestConsumerError(RuntimeError):
    """Raised when build-request consumption cannot be evaluated safely."""


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise BuildRequestConsumerError(f"build request unavailable: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BuildRequestConsumerError(f"build request malformed: {path}") from exc
    if not isinstance(parsed, dict):
        raise BuildRequestConsumerError("build request must be a JSON object")
    return parsed


def _assert_inside(root: Path, path: Path) -> None:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise BuildRequestConsumerError(f"refusing write outside output dir: {path}")


def _default_command_runner(cmd: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            cmd,
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return (-1, "", repr(exc))
    return (result.returncode, result.stdout or "", result.stderr or "")


def _backend_config(env: dict[str, str] | None = None) -> dict[str, Any]:
    source = env if env is not None else os.environ
    backend = str(source.get("QRE_BUILD_BACKEND") or "dry_run_only").strip()
    command = str(source.get("QRE_BUILD_COMMAND") or "").strip()
    auto_pr = str(source.get("QRE_AUTO_PR") or "").lower() == "true"
    return {
        "backend": backend,
        "command": command,
        "auto_pr": auto_pr,
        "configured": bool(command) and backend in SUPPORTED_BACKENDS and backend != "dry_run_only",
    }


def _parse_backend_stdout(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"raw_stdout": text[:2000]}
    return parsed if isinstance(parsed, dict) else {"raw_stdout": text[:2000]}


def build_consumption_snapshot(
    *,
    build_request_path: Path = DEFAULT_BUILD_REQUEST_PATH,
    env: dict[str, str] | None = None,
    command_runner: CommandRunner | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    request = _read_json(build_request_path)
    config = _backend_config(env)
    base = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated,
        "build_request_path": build_request_path.as_posix(),
        "request_id": request.get("request_id"),
        "next_action": request.get("next_action"),
        "backend": config["backend"],
        "build_request_consumed": False,
        "build_started": False,
        "branch_created": False,
        "code_changed": False,
        "tests_run": False,
        "pr_created": False,
        "execution_allowed": False,
        "paper_shadow_live_allowed": False,
        "broker_risk_allowed": False,
        "campaign_launcher_called": False,
        "run_research_called": False,
        "protected_outputs_mutated": False,
        "build_backend_available": False,
        "build_executed_by_this_controller": False,
        "auto_pr_requested": config["auto_pr"],
        "safe_for_auto_merge": False,
        "pr_metadata": None,
        "missing_capability": None,
        "blocked_reason": None,
    }
    if request.get("safe_for_ade_build") is not True or request.get("execution_allowed") is True:
        return {
            **base,
            "blocked_reason": "build_request_not_safe_for_ade_build",
            "missing_capability": "safe_build_request",
            "final_recommendation": "build_request_blocked",
        }
    if not config["configured"]:
        return {
            **base,
            "missing_capability": "safe_build_backend",
            "blocked_reason": "no_safe_build_backend_configured",
            "final_recommendation": "build_request_ready_but_not_consumed",
        }

    runner = command_runner or _default_command_runner
    command = str(config["command"]).replace("%QRE_BUILD_REQUEST_PATH%", build_request_path.as_posix())
    cmd = shlex.split(command)
    if not cmd:
        return {
            **base,
            "missing_capability": "safe_build_backend",
            "blocked_reason": "empty_build_command",
            "final_recommendation": "build_request_ready_but_not_consumed",
        }
    rc, stdout, stderr = runner(
        cmd,
        {
            "QRE_BUILD_REQUEST_PATH": build_request_path.as_posix(),
            "QRE_BUILD_REQUEST_ID": str(request.get("request_id") or ""),
        },
    )
    backend_result = _parse_backend_stdout(stdout)
    pr_metadata = backend_result.get("pr_metadata")
    if not isinstance(pr_metadata, dict):
        pr_metadata = None
    success = rc == 0 and backend_result.get("build_request_consumed") is True
    return {
        **base,
        "build_backend_available": True,
        "build_backend": config["backend"],
        "build_command_configured": True,
        "build_executed_by_this_controller": True,
        "build_request_consumed": success,
        "build_started": success or bool(backend_result.get("build_started")),
        "branch_created": bool(backend_result.get("branch_created")),
        "code_changed": bool(backend_result.get("code_changed")),
        "tests_run": bool(backend_result.get("tests_run")),
        "pr_created": bool(backend_result.get("pr_created")),
        "safe_for_auto_merge": backend_result.get("safe_for_auto_merge") is True,
        "pr_metadata": pr_metadata,
        "backend_returncode": rc,
        "backend_stderr": stderr[:2000],
        "blocked_reason": None if success else "build_backend_failed",
        "final_recommendation": (
            "build_request_consumed_pr_ready" if success else "build_backend_failed"
        ),
    }


def render_operator_summary(snapshot: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# QRE Build Request Consumer",
            "",
            f"- Request ID: {snapshot.get('request_id')}",
            f"- Backend: {snapshot.get('backend')}",
            f"- Build backend available: {snapshot.get('build_backend_available')}",
            f"- Build request consumed: {snapshot.get('build_request_consumed')}",
            f"- Build started: {snapshot.get('build_started')}",
            f"- Branch created: {snapshot.get('branch_created')}",
            f"- Code changed: {snapshot.get('code_changed')}",
            f"- Tests run: {snapshot.get('tests_run')}",
            f"- PR created: {snapshot.get('pr_created')}",
            f"- Missing capability: {snapshot.get('missing_capability')}",
            f"- Blocked reason: {snapshot.get('blocked_reason')}",
            "- Trading: disabled.",
            "- No broker/risk/execution authority.",
            "",
        ]
    )


def write_outputs(snapshot: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    run_id = str(snapshot.get("request_id") or "no-request") + "__" + str(snapshot["generated_at_utc"]).replace(":", "").replace("-", "")
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


def run_consumer(
    *,
    build_request_path: Path = DEFAULT_BUILD_REQUEST_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    write: bool = False,
    env: dict[str, str] | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    snapshot = build_consumption_snapshot(
        build_request_path=build_request_path,
        env=env,
        command_runner=command_runner,
    )
    if write:
        snapshot["_artifact_paths"] = write_outputs(snapshot, output_dir=output_dir)
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consume QRE build request with an explicit backend.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--build-request", default=DEFAULT_BUILD_REQUEST_PATH.as_posix())
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR.as_posix())
    args = parser.parse_args(argv)
    snapshot = run_consumer(
        build_request_path=Path(args.build_request),
        output_dir=Path(args.output_dir),
        write=args.write,
    )
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

