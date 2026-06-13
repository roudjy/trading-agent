"""QRE runtime update and research continuation.

After a safe merge signal, this module can update main and run bounded
autonomous research again. By default it refuses runtime mutation unless
``QRE_RUNTIME_UPDATE=true`` or tests inject a command runner.
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

from research import qre_autonomous_market_research_loop as research_loop


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_runtime_update_and_continue"
DEFAULT_MERGE_RESULT_PATH: Final[Path] = Path("logs/qre_pr_auto_merge_gate/latest.json")
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_runtime_update_and_continue")
PROTECTED_PUBLIC_OUTPUTS: Final[tuple[Path, ...]] = (
    Path("research/research_latest.json"),
    Path("research/strategy_matrix.csv"),
)


CommandRunner = Callable[[list[str]], tuple[int, str, str]]


class RuntimeUpdateAndContinueError(RuntimeError):
    """Raised when continuation cannot be evaluated safely."""


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


def _file_fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "content": None}
    return {"exists": True, "content": path.read_bytes().hex()}


def _protected_fingerprints() -> dict[str, dict[str, Any]]:
    return {path.as_posix(): _file_fingerprint(path) for path in PROTECTED_PUBLIC_OUTPUTS}


def _assert_protected_unchanged(before: dict[str, dict[str, Any]]) -> None:
    if before != _protected_fingerprints():
        raise RuntimeUpdateAndContinueError("protected public research artifacts changed")


def _assert_inside(root: Path, path: Path) -> None:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise RuntimeUpdateAndContinueError(f"refusing write outside output dir: {path}")


def _default_command_runner(cmd: list[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return (-1, "", repr(exc))
    return (result.returncode, result.stdout or "", result.stderr or "")


def run_continuation(
    *,
    merge_result_path: Path = DEFAULT_MERGE_RESULT_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    max_cycles: int = 3,
    write: bool = False,
    env: dict[str, str] | None = None,
    command_runner: CommandRunner | None = None,
    skip_git_update: bool = False,
) -> dict[str, Any]:
    before = _protected_fingerprints()
    generated = _utcnow()
    merge_result = _read_json(merge_result_path)
    blockers: list[str] = []
    if not merge_result:
        blockers.append("merge_result_missing")
    elif merge_result.get("pr_auto_merged") is not True:
        blockers.append("pr_not_auto_merged")

    source_env = env if env is not None else os.environ
    runtime_update_enabled = str(source_env.get("QRE_RUNTIME_UPDATE") or "").lower() == "true"
    update_results: list[dict[str, Any]] = []
    runtime_updated = False
    if not blockers:
        if not runtime_update_enabled and not skip_git_update and command_runner is None:
            blockers.append("runtime_update_not_enabled")
        elif not skip_git_update:
            runner = command_runner or _default_command_runner
            for cmd in (["git", "checkout", "main"], ["git", "pull", "--ff-only", "origin", "main"]):
                rc, stdout, stderr = runner(cmd)
                update_results.append(
                    {"cmd": cmd, "returncode": rc, "stdout": stdout[:2000], "stderr": stderr[:2000]}
                )
                if rc != 0:
                    blockers.append("runtime_update_command_failed")
                    break
            runtime_updated = not blockers
        else:
            runtime_updated = True

    continuation_packet: dict[str, Any] | None = None
    if not blockers:
        continuation_packet = research_loop.run_autonomous_loop(max_cycles=max_cycles, write=write)

    _assert_protected_unchanged(before)
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated,
        "merge_result_path": merge_result_path.as_posix(),
        "runtime_updated": runtime_updated,
        "research_continuation_started": continuation_packet is not None,
        "research_cycles_started": (
            (continuation_packet.get("summary") or {}).get("cycle_count")
            if continuation_packet
            else 0
        ),
        "blocked_reasons": blockers,
        "update_results": update_results,
        "latest_research_recommendation": (
            (continuation_packet.get("summary") or {}).get("latest_recommendation")
            if continuation_packet
            else None
        ),
        "paper_shadow_live_allowed": False,
        "broker_risk_allowed": False,
        "execution_allowed": False,
        "campaign_launcher_called": False,
        "run_research_called": False,
        "protected_outputs_mutated": False,
        "final_recommendation": (
            "research_continuation_started" if continuation_packet else "research_continuation_blocked"
        ),
    }
    if write:
        snapshot["_artifact_paths"] = write_outputs(snapshot, output_dir=output_dir)
    return snapshot


def render_operator_summary(snapshot: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# QRE Runtime Update And Continue",
            "",
            f"- Runtime updated: {snapshot.get('runtime_updated')}",
            f"- Research continuation started: {snapshot.get('research_continuation_started')}",
            f"- Research cycles started: {snapshot.get('research_cycles_started')}",
            f"- Blocked reasons: {', '.join(snapshot.get('blocked_reasons') or []) or 'none'}",
            "- Trading: disabled.",
            "- Protected public research outputs: not mutated.",
            "",
        ]
    )


def write_outputs(snapshot: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    run_id = "continuation__" + str(snapshot["generated_at_utc"]).replace(":", "").replace("-", "")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update runtime after merge and continue QRE research.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--max-cycles", type=int, default=3)
    parser.add_argument("--merge-result", default=DEFAULT_MERGE_RESULT_PATH.as_posix())
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR.as_posix())
    parser.add_argument("--skip-git-update", action="store_true")
    args = parser.parse_args(argv)
    snapshot = run_continuation(
        merge_result_path=Path(args.merge_result),
        output_dir=Path(args.output_dir),
        max_cycles=args.max_cycles,
        write=args.write,
        skip_git_update=args.skip_git_update,
    )
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

