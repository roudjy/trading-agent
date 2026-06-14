"""Top-level QRE research-development flywheel."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research import qre_autonomous_market_research_loop as research_loop
from research import qre_build_request_consumer as consumer
from research import qre_pr_auto_merge_gate as merge_gate
from research import qre_runtime_update_and_continue as continuation


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_research_development_flywheel"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_research_development_flywheel")
PROTECTED_PUBLIC_OUTPUTS: Final[tuple[Path, ...]] = (
    Path("research/research_latest.json"),
    Path("research/strategy_matrix.csv"),
)


class ResearchDevelopmentFlywheelError(RuntimeError):
    """Raised when the flywheel cannot write safely."""


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _file_fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "content": None}
    return {"exists": True, "content": path.read_bytes().hex()}


def _protected_fingerprints() -> dict[str, dict[str, Any]]:
    return {path.as_posix(): _file_fingerprint(path) for path in PROTECTED_PUBLIC_OUTPUTS}


def _assert_protected_unchanged(before: dict[str, dict[str, Any]]) -> None:
    if before != _protected_fingerprints():
        raise ResearchDevelopmentFlywheelError("protected public research artifacts changed")


def _assert_inside(root: Path, path: Path) -> None:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ResearchDevelopmentFlywheelError(f"refusing write outside output dir: {path}")


def _copy_snapshot(snapshot: dict[str, Any], *, output_dir: Path, subdir: str) -> str:
    target = output_dir / subdir / "latest.json"
    _assert_inside(output_dir, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_json_dumps(snapshot), encoding="utf-8", newline="\n")
    return target.as_posix()


def run_flywheel(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    max_cycles: int = 40,
    max_builds: int = 5,
    write: bool = False,
    env: dict[str, str] | None = None,
    build_command_runner: consumer.CommandRunner | None = None,
    merge_command_runner: merge_gate.CommandRunner | None = None,
    runtime_command_runner: continuation.CommandRunner | None = None,
    skip_runtime_git_update: bool = False,
    controlled_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if max_cycles < 1:
        raise ResearchDevelopmentFlywheelError("--max-cycles must be positive")
    if max_builds < 0:
        raise ResearchDevelopmentFlywheelError("--max-builds must be non-negative")
    before = _protected_fingerprints()
    generated = _utcnow()

    research_packet = research_loop.run_autonomous_loop(
        controlled_packet=controlled_packet,
        max_cycles=max_cycles,
        until_build_request=max_builds > 0,
        write=write,
    )
    build_request = research_packet.get("_artifact_paths", {}).get("build_request", {})
    build_request_path = Path(build_request.get("latest") or "logs/qre_autonomous_market_research_loop/latest_build_request.json")

    build_snapshot: dict[str, Any] | None = None
    pr_snapshot: dict[str, Any] | None = None
    continuation_snapshot: dict[str, Any] | None = None
    if max_builds > 0 and build_request_path.exists():
        build_snapshot = consumer.run_consumer(
            build_request_path=build_request_path,
            write=write,
            env=env,
            command_runner=build_command_runner,
        )
        if build_snapshot.get("pr_created") is True:
            pr_metadata = (
                dict(build_snapshot["pr_metadata"])
                if isinstance(build_snapshot.get("pr_metadata"), dict)
                else None
            )
            if pr_metadata is not None:
                pr_metadata["safe_for_auto_merge"] = build_snapshot.get("safe_for_auto_merge")
            pr_snapshot = merge_gate.run_gate(
                build_request_path=build_request_path,
                write=write,
                env=env,
                command_runner=merge_command_runner,
                pr_metadata=pr_metadata,
            )
            if pr_snapshot.get("pr_auto_merged") is True:
                continuation_snapshot = continuation.run_continuation(
                    max_cycles=min(3, max_cycles),
                    write=write,
                    env=env,
                    command_runner=runtime_command_runner,
                    skip_git_update=skip_runtime_git_update,
                    controlled_packet=controlled_packet,
                )

    states = {
        "build_request_created": bool(build_request),
        "build_request_consumed": bool(build_snapshot and build_snapshot.get("build_request_consumed")),
        "build_started": bool(build_snapshot and build_snapshot.get("build_started")),
        "branch_created": bool(build_snapshot and build_snapshot.get("branch_created")),
        "code_changed": bool(build_snapshot and build_snapshot.get("code_changed")),
        "tests_run": bool(build_snapshot and build_snapshot.get("tests_run")),
        "pr_created": bool(build_snapshot and build_snapshot.get("pr_created")),
        "ci_observed": bool(pr_snapshot and pr_snapshot.get("ci_observed")),
        "pr_green": bool(pr_snapshot and pr_snapshot.get("pr_green")),
        "pr_auto_merged": bool(pr_snapshot and pr_snapshot.get("pr_auto_merged")),
        "runtime_updated": bool(continuation_snapshot and continuation_snapshot.get("runtime_updated")),
        "research_continuation_started": bool(
            continuation_snapshot and continuation_snapshot.get("research_continuation_started")
        ),
        "research_blocked": not bool(research_packet.get("summary", {}).get("autonomous_loop_ready")),
        "unsafe_action_blocked": bool(research_packet.get("summary", {}).get("unsafe_actions_blocked")),
    }
    blocked_reasons: list[str] = []
    for snapshot in (build_snapshot, pr_snapshot, continuation_snapshot):
        if not snapshot:
            continue
        if snapshot.get("blocked_reason"):
            blocked_reasons.append(str(snapshot["blocked_reason"]))
        for reason in snapshot.get("blocked_reasons") or []:
            blocked_reasons.append(str(reason))
    summary = {
        "flywheel_ready": True,
        "max_cycles": max_cycles,
        "max_builds": max_builds,
        "research_cycles_completed": research_packet.get("summary", {}).get("cycle_count"),
        "market_intake_cycles_completed": research_packet.get("summary", {}).get("market_intake_cycle_count"),
        "build_requests_created": 1 if build_request else 0,
        "build_requests_consumed": 1 if states["build_request_consumed"] else 0,
        "prs_opened": 1 if states["pr_created"] else 0,
        "prs_green": 1 if states["pr_green"] else 0,
        "prs_merged": 1 if states["pr_auto_merged"] else 0,
        "runtime_updates_completed": 1 if states["runtime_updated"] else 0,
        "research_continuations_started": 1 if states["research_continuation_started"] else 0,
        "manual_governance_blockers": blocked_reasons,
        "paper_shadow_live_allowed": False,
        "broker_risk_allowed": False,
        "execution_allowed": False,
        "campaign_launcher_called": False,
        "run_research_called": False,
        "protected_outputs_mutated": False,
        "auto_trade_allowed": False,
        "final_recommendation": (
            "flywheel_continuation_started"
            if states["research_continuation_started"]
            else "flywheel_waiting_or_blocked"
        ),
    }
    packet = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated,
        "summary": summary,
        "states": states,
        "research_loop": research_packet,
        "build_consumption": build_snapshot,
        "pr_status": pr_snapshot,
        "runtime_continuation": continuation_snapshot,
    }
    if write:
        packet["_artifact_paths"] = write_outputs(packet, output_dir=output_dir)
    _assert_protected_unchanged(before)
    return packet


def render_operator_summary(packet: dict[str, Any]) -> str:
    summary = packet["summary"]
    states = packet["states"]
    blockers = ", ".join(summary.get("manual_governance_blockers") or []) or "none"
    return "\n".join(
        [
            "# QRE Research-Development Flywheel",
            "",
            f"- Research cycles completed: {summary.get('research_cycles_completed')}",
            f"- Market-intake cycles completed: {summary.get('market_intake_cycles_completed')}",
            f"- Build requests created: {summary.get('build_requests_created')}",
            f"- Build requests consumed: {summary.get('build_requests_consumed')}",
            f"- PRs opened: {summary.get('prs_opened')}",
            f"- PRs green: {summary.get('prs_green')}",
            f"- PRs merged: {summary.get('prs_merged')}",
            f"- Runtime updates completed: {summary.get('runtime_updates_completed')}",
            f"- Research continuations started: {summary.get('research_continuations_started')}",
            f"- Current states: {json.dumps(states, sort_keys=True)}",
            f"- Manual governance blockers: {blockers}",
            "- Trading: disabled.",
            "- Protected public research outputs: not mutated.",
            "",
        ]
    )


def write_outputs(packet: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    latest = output_dir / "latest.json"
    summary = output_dir / "operator_summary.md"
    ledger = output_dir / "ledger.jsonl"
    for path in (latest, summary, ledger):
        _assert_inside(output_dir, path)
    output_dir.mkdir(parents=True, exist_ok=True)
    latest.write_text(_json_dumps(packet), encoding="utf-8", newline="\n")
    summary.write_text(render_operator_summary(packet), encoding="utf-8", newline="\n")
    with ledger.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "report_kind": REPORT_KIND,
                    "generated_at_utc": packet["generated_at_utc"],
                    "states": packet["states"],
                    "final_recommendation": packet["summary"]["final_recommendation"],
                },
                sort_keys=True,
            )
            + "\n"
        )
    paths: dict[str, Any] = {
        "latest": latest.as_posix(),
        "operator_summary": summary.as_posix(),
        "ledger": ledger.as_posix(),
    }
    if packet.get("build_consumption"):
        paths["build_consumption"] = _copy_snapshot(
            packet["build_consumption"], output_dir=output_dir, subdir="build_consumption"
        )
    if packet.get("pr_status"):
        paths["pr_status"] = _copy_snapshot(packet["pr_status"], output_dir=output_dir, subdir="pr_status")
    if packet.get("runtime_continuation"):
        paths["continuation"] = _copy_snapshot(
            packet["runtime_continuation"], output_dir=output_dir, subdir="continuations"
        )
    merge_dir = output_dir / "merge_results"
    _assert_inside(output_dir, merge_dir)
    merge_dir.mkdir(parents=True, exist_ok=True)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run QRE research-development flywheel.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--max-cycles", type=int, default=40)
    parser.add_argument("--max-builds", type=int, default=5)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR.as_posix())
    parser.add_argument("--skip-runtime-git-update", action="store_true")
    args = parser.parse_args(argv)
    packet = run_flywheel(
        output_dir=Path(args.output_dir),
        max_cycles=args.max_cycles,
        max_builds=args.max_builds,
        write=args.write,
        skip_runtime_git_update=args.skip_runtime_git_update,
    )
    print(json.dumps(packet["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
