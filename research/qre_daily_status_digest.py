"""Daily QRE autonomous market-research status digest."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_daily_status"
DEFAULT_LOOP_LATEST: Final[Path] = Path("logs/qre_autonomous_market_research_loop/latest.json")
DEFAULT_FLYWHEEL_LATEST: Final[Path] = Path("logs/qre_research_development_flywheel/latest.json")
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_daily_status")


class DailyStatusDigestError(RuntimeError):
    """Raised when daily status cannot be built."""


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise DailyStatusDigestError(f"loop artifact unavailable: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DailyStatusDigestError(f"loop artifact malformed: {path}") from exc
    if not isinstance(parsed, dict):
        raise DailyStatusDigestError("loop artifact must be a JSON object")
    return parsed


def _assert_inside(root: Path, path: Path) -> None:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise DailyStatusDigestError(f"refusing write outside output dir: {path}")


def _discover_build_requests(loop_output_dir: Path) -> list[dict[str, Any]]:
    build_dir = loop_output_dir / "build_requests"
    if not build_dir.exists():
        return []
    requests: list[dict[str, Any]] = []
    for path in sorted(build_dir.glob("build-request-*.json")):
        try:
            parsed = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            requests.append(parsed)
    return requests


def _discover_build_results(loop_output_dir: Path) -> list[dict[str, Any]]:
    results_dir = loop_output_dir / "build_results"
    if not results_dir.exists():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*.json")):
        try:
            parsed = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            results.append(parsed)
    return results


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def build_daily_status_packet(
    *,
    loop_latest_path: Path = DEFAULT_LOOP_LATEST,
    flywheel_latest_path: Path = DEFAULT_FLYWHEEL_LATEST,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    loop_packet = _read_json(loop_latest_path)
    cycles = loop_packet.get("cycles")
    if not isinstance(cycles, list) or not cycles:
        raise DailyStatusDigestError("loop artifact has no cycles")
    latest_cycle = cycles[-1]
    if not isinstance(latest_cycle, dict):
        raise DailyStatusDigestError("latest cycle malformed")

    loop_output_dir = loop_latest_path.parent
    build_requests = _discover_build_requests(loop_output_dir)
    build_results = _discover_build_results(loop_output_dir)
    flywheel = _read_optional_json(flywheel_latest_path)
    flywheel_summary = flywheel.get("summary") if isinstance(flywheel, dict) and isinstance(flywheel.get("summary"), dict) else {}
    completed_ids = {
        str(item.get("request_id"))
        for item in build_results
        if item.get("status") in {"merged", "completed"}
    }
    pending = [
        item for item in build_requests if str(item.get("request_id")) not in completed_ids
    ]
    result_analysis = latest_cycle.get("result_analysis") if isinstance(latest_cycle.get("result_analysis"), dict) else {}
    blockers = result_analysis.get("content_blockers")
    if not isinstance(blockers, list):
        blockers = []
    summary = loop_packet.get("summary") if isinstance(loop_packet.get("summary"), dict) else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc or _utcnow(),
        "period_covered": "latest_autonomous_loop_artifact",
        "source_loop_latest": loop_latest_path.as_posix(),
        "summary": {
            "autonomous_cycles": len(cycles),
            "controlled_research_inner_loops": summary.get("controlled_research_inner_loop_count"),
            "market_intake_cycles": summary.get("market_intake_cycle_count"),
            "build_requests_created": len(build_requests),
            "build_requests_consumed": flywheel_summary.get("build_requests_consumed", 0),
            "build_requests_pending": len(pending),
            "build_requests_completed_or_merged": len(completed_ids),
            "prs_opened": flywheel_summary.get("prs_opened", 0),
            "prs_green": flywheel_summary.get("prs_green", 0),
            "prs_merged": flywheel_summary.get("prs_merged", 0),
            "runtime_updates_completed": flywheel_summary.get("runtime_updates_completed", 0),
            "research_continuations_started": flywheel_summary.get("research_continuations_started", 0),
            "manual_governance_blockers": flywheel_summary.get("manual_governance_blockers", []),
            "unsafe_actions_blocked": summary.get("unsafe_actions_blocked", 0),
            "trading_status": "disabled",
            "protected_artifact_mutation": "none"
            if summary.get("protected_outputs_mutated") is False
            else "unknown_or_detected",
            "latest_universe": latest_cycle.get("market_intake", {}).get("universe"),
            "latest_hypothesis": latest_cycle.get("hypothesis_generation", {}).get("statement"),
            "latest_preset": latest_cycle.get("preset_selection", {}).get("preset_id"),
            "latest_metric_mode": latest_cycle.get("metric_evidence", {}).get("metric_mode"),
            "latest_blocker": blockers[0] if blockers else "none",
            "latest_recommendation": latest_cycle.get("next_action", {}).get("recommended_action"),
        },
        "build_requests": build_requests,
        "build_results": build_results,
        "flywheel": flywheel,
        "latest_cycle": {
            "cycle_id": latest_cycle.get("cycle_id"),
            "learning_feedback": latest_cycle.get("learning_feedback"),
            "next_market_intake_seed": latest_cycle.get("next_market_intake_seed"),
            "next_action": latest_cycle.get("next_action"),
        },
        "next_system_action": (
            "Await build result for pending ADE/Codex request, then rerun market-intake "
            "-> analysis -> controlled research loop."
            if pending
            else "Continue bounded autonomous market-research cycles."
        ),
        "safety": {
            "paper_shadow_live_allowed": False,
            "broker_risk_allowed": False,
            "execution_allowed": False,
            "campaign_launcher_called": False,
            "run_research_called": False,
            "validation_executed": False,
            "protected_outputs_mutated": False,
        },
    }


def render_daily_status(packet: dict[str, Any]) -> str:
    summary = packet["summary"]
    build_lines = [
        f"- {item.get('request_id')}: {item.get('next_action')}, safe_for_ade_build={item.get('safe_for_ade_build')}, pending"
        for item in packet.get("build_requests", [])
    ]
    if not build_lines:
        build_lines = ["- No build requests currently present."]
    return "\n".join(
        [
            "# QRE Daily Status",
            "",
            f"Period covered: {packet['period_covered']}",
            f"Autonomous cycles: {summary['autonomous_cycles']}",
            f"Controlled research inner loops: {summary['controlled_research_inner_loops']}",
            f"Market-intake cycles: {summary['market_intake_cycles']}",
            f"Build requests created: {summary['build_requests_created']}",
            f"Build requests consumed: {summary['build_requests_consumed']}",
            f"Build requests pending: {summary['build_requests_pending']}",
            f"Build requests completed/merged if known: {summary['build_requests_completed_or_merged']}",
            f"PRs opened: {summary['prs_opened']}",
            f"PRs green: {summary['prs_green']}",
            f"PRs merged: {summary['prs_merged']}",
            f"Runtime updates completed: {summary['runtime_updates_completed']}",
            f"Research continuations started: {summary['research_continuations_started']}",
            f"Unsafe actions blocked: {summary['unsafe_actions_blocked']}",
            f"Manual governance blockers: {', '.join(summary['manual_governance_blockers']) if summary['manual_governance_blockers'] else 'none'}",
            f"Trading status: {summary['trading_status']}",
            f"Protected artifact mutation: {summary['protected_artifact_mutation']}",
            f"Latest universe: {', '.join(summary['latest_universe'] or [])}",
            f"Latest hypothesis: {summary['latest_hypothesis']}",
            f"Latest preset: {summary['latest_preset']}",
            f"Latest metric mode: {summary['latest_metric_mode']}",
            f"Latest blocker: {summary['latest_blocker']}",
            f"Latest recommendation: {summary['latest_recommendation']}",
            "",
            "Research intelligence progress:",
            "- Learning is feeding back into the next market-intake seed.",
            "- The system does not rotate assets when the blocker is infrastructure rather than asset quality.",
            "",
            "ADE/build progress:",
            *build_lines,
            "",
            "Next system action:",
            f"- {packet['next_system_action']}",
            "",
        ]
    )


def render_scheduler_setup() -> str:
    return "\n".join(
        [
            "# QRE Scheduler Setup Examples",
            "",
            "No scheduler is installed by this module. Use these commands from an operator-controlled scheduler.",
            "",
            "## VPS",
            "```bash",
            "cd /root/trading-agent",
            "python3 -m research.qre_autonomous_market_research_loop --write --max-cycles 40",
            "python3 -m research.qre_daily_status_digest --write",
            "```",
            "",
            "## Local PowerShell",
            "```powershell",
            "cd C:\\Users\\joery.van.rooij\\trading-agent",
            "python -m research.qre_autonomous_market_research_loop --write --max-cycles 40",
            "python -m research.qre_daily_status_digest --write",
            "```",
            "",
        ]
    )


def write_outputs(packet: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    latest_path = output_dir / "latest.json"
    daily_path = output_dir / "daily_status.md"
    summary_path = output_dir / "operator_summary.md"
    scheduler_path = output_dir / "scheduler_setup.md"
    for path in (latest_path, daily_path, summary_path, scheduler_path):
        _assert_inside(output_dir, path)
    output_dir.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(_json_dumps(packet), encoding="utf-8", newline="\n")
    rendered = render_daily_status(packet)
    daily_path.write_text(rendered, encoding="utf-8", newline="\n")
    summary_path.write_text(rendered, encoding="utf-8", newline="\n")
    scheduler_path.write_text(render_scheduler_setup(), encoding="utf-8", newline="\n")
    return {
        "latest": latest_path.as_posix(),
        "daily_status": daily_path.as_posix(),
        "operator_summary": summary_path.as_posix(),
        "scheduler_setup": scheduler_path.as_posix(),
    }


def run_daily_status_digest(
    *,
    loop_latest_path: Path = DEFAULT_LOOP_LATEST,
    flywheel_latest_path: Path = DEFAULT_FLYWHEEL_LATEST,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    write: bool = False,
) -> dict[str, Any]:
    packet = build_daily_status_packet(
        loop_latest_path=loop_latest_path,
        flywheel_latest_path=flywheel_latest_path,
    )
    if write:
        packet["_artifact_paths"] = write_outputs(packet, output_dir=output_dir)
    return packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write QRE daily status digest.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--loop-latest", default=DEFAULT_LOOP_LATEST.as_posix())
    parser.add_argument("--flywheel-latest", default=DEFAULT_FLYWHEEL_LATEST.as_posix())
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR.as_posix())
    args = parser.parse_args(argv)
    packet = run_daily_status_digest(
        loop_latest_path=Path(args.loop_latest),
        flywheel_latest_path=Path(args.flywheel_latest),
        output_dir=Path(args.output_dir),
        write=args.write,
    )
    print(json.dumps(packet["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DailyStatusDigestError",
    "DEFAULT_LOOP_LATEST",
    "DEFAULT_OUTPUT_DIR",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "build_daily_status_packet",
    "render_daily_status",
    "run_daily_status_digest",
    "write_outputs",
]
