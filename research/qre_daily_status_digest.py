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
DEFAULT_BUILD_REQUEST_LATEST: Final[Path] = Path("logs/qre_autonomous_market_research_loop/latest_build_request.json")
DEFAULT_BUILD_CONSUMER_LATEST: Final[Path] = Path("logs/qre_build_request_consumer/latest.json")
DEFAULT_BUILD_BACKEND_RESULTS_DIR: Final[Path] = Path("logs/qre_build_request_consumer/backend_results")
DEFAULT_PR_AUTO_MERGE_LATEST: Final[Path] = Path("logs/qre_pr_auto_merge_gate/latest.json")
DEFAULT_RUNTIME_CONTINUATION_LATEST: Final[Path] = Path("logs/qre_runtime_update_and_continue/latest.json")
DEFAULT_FLYWHEEL_LATEST: Final[Path] = Path("logs/qre_research_development_flywheel/latest.json")
DEFAULT_TRUSTED_LOOP_REVIEW_LATEST: Final[Path] = Path("logs/qre_trusted_loop_review/latest.json")
DEFAULT_RESEARCH_MEMORY_CURRENT_ARTIFACTS_LATEST: Final[Path] = Path(
    "logs/qre_research_memory_current_artifacts/latest.json"
)
DEFAULT_SHADOW_READINESS_LATEST: Final[Path] = Path("logs/qre_shadow_readiness_gates/latest.json")
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


def _read_optional_artifact(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    parsed = _read_optional_json(path)
    if parsed is None:
        return None, None
    return parsed, path.as_posix()


def _discover_backend_results(results_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    if not results_dir.exists():
        return []
    results: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(results_dir.glob("*.json")):
        parsed = _read_optional_json(path)
        if parsed is not None:
            results.append((path, parsed))
    return results


def _artifact_sort_key(item: tuple[Path, dict[str, Any]]) -> tuple[str, str]:
    path, payload = item
    timestamp = payload.get("generated_at_utc") or payload.get("created_at_utc") or ""
    return str(timestamp), path.as_posix()


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _append_blocker(blockers: list[str], value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            _append_blocker(blockers, item)
        return
    if _has_value(value):
        text = str(value)
        if text not in blockers:
            blockers.append(text)


def _yes_no_unknown(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _extract_pr_number(*artifacts: dict[str, Any] | None) -> int | None:
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        for key in ("pr_number", "number"):
            value = artifact.get(key)
            if isinstance(value, int):
                return value
        metadata = artifact.get("pr_metadata")
        if isinstance(metadata, dict):
            for key in ("pr_number", "number"):
                value = metadata.get(key)
                if isinstance(value, int):
                    return value
    return None


def _qre_operator_authority(
    *,
    trusted_loop_review: dict[str, Any] | None,
    research_memory_current_artifacts: dict[str, Any] | None,
    shadow_readiness: dict[str, Any] | None,
) -> str:
    trusted_summary = (
        trusted_loop_review.get("summary") if isinstance(trusted_loop_review, dict) else {}
    )
    memory_summary = (
        research_memory_current_artifacts.get("summary")
        if isinstance(research_memory_current_artifacts, dict)
        else {}
    )
    shadow_summary = shadow_readiness.get("summary") if isinstance(shadow_readiness, dict) else {}
    if trusted_summary.get("trusted_loop_review_ready") is True:
        return "operator_trusted_read_only"
    if _has_value(trusted_summary.get("trust_verdict")):
        return "working_read_only_fail_closed"
    if _has_value(memory_summary.get("final_recommendation")) or _has_value(
        shadow_summary.get("readiness_status")
    ):
        return "context_visible_fail_closed"
    return "loop_only"


def _count_true(*values: Any) -> int:
    return 1 if any(value is True for value in values) else 0


def build_daily_status_packet(
    *,
    loop_latest_path: Path = DEFAULT_LOOP_LATEST,
    build_request_latest_path: Path = DEFAULT_BUILD_REQUEST_LATEST,
    build_consumer_latest_path: Path = DEFAULT_BUILD_CONSUMER_LATEST,
    backend_results_dir: Path = DEFAULT_BUILD_BACKEND_RESULTS_DIR,
    pr_auto_merge_latest_path: Path = DEFAULT_PR_AUTO_MERGE_LATEST,
    runtime_continuation_latest_path: Path = DEFAULT_RUNTIME_CONTINUATION_LATEST,
    flywheel_latest_path: Path = DEFAULT_FLYWHEEL_LATEST,
    trusted_loop_review_latest_path: Path = DEFAULT_TRUSTED_LOOP_REVIEW_LATEST,
    research_memory_current_artifacts_latest_path: Path = DEFAULT_RESEARCH_MEMORY_CURRENT_ARTIFACTS_LATEST,
    shadow_readiness_latest_path: Path = DEFAULT_SHADOW_READINESS_LATEST,
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
    build_request_latest, build_request_latest_used = _read_optional_artifact(build_request_latest_path)
    if build_request_latest is not None:
        latest_request_id = build_request_latest.get("request_id")
        known_request_ids = {item.get("request_id") for item in build_requests}
        if latest_request_id not in known_request_ids:
            build_requests.append(build_request_latest)

    build_consumer_latest, build_consumer_latest_used = _read_optional_artifact(build_consumer_latest_path)
    backend_results = _discover_backend_results(backend_results_dir)
    latest_backend_result = max(backend_results, key=_artifact_sort_key)[1] if backend_results else None
    backend_result_paths = [path.as_posix() for path, _payload in backend_results]
    pr_auto_merge, pr_auto_merge_used = _read_optional_artifact(pr_auto_merge_latest_path)
    runtime_continuation, runtime_continuation_used = _read_optional_artifact(runtime_continuation_latest_path)
    flywheel = _read_optional_json(flywheel_latest_path)
    flywheel_summary = flywheel.get("summary") if isinstance(flywheel, dict) and isinstance(flywheel.get("summary"), dict) else {}
    trusted_loop_review, trusted_loop_review_used = _read_optional_artifact(trusted_loop_review_latest_path)
    research_memory_current_artifacts, research_memory_current_artifacts_used = _read_optional_artifact(
        research_memory_current_artifacts_latest_path
    )
    shadow_readiness, shadow_readiness_used = _read_optional_artifact(shadow_readiness_latest_path)

    build_consumed = _count_true(
        build_consumer_latest.get("build_request_consumed") if isinstance(build_consumer_latest, dict) else None,
        latest_backend_result.get("build_request_consumed") if isinstance(latest_backend_result, dict) else None,
    )
    pr_opened = _count_true(
        build_consumer_latest.get("pr_created") if isinstance(build_consumer_latest, dict) else None,
        latest_backend_result.get("pr_created") if isinstance(latest_backend_result, dict) else None,
    )
    pr_green = _count_true(pr_auto_merge.get("pr_green") if isinstance(pr_auto_merge, dict) else None)
    pr_merged = _count_true(pr_auto_merge.get("pr_auto_merged") if isinstance(pr_auto_merge, dict) else None)
    runtime_updated = _count_true(
        runtime_continuation.get("runtime_updated") if isinstance(runtime_continuation, dict) else None
    )
    research_continuation_started = _count_true(
        runtime_continuation.get("research_continuation_started")
        if isinstance(runtime_continuation, dict)
        else None
    )

    completed_ids = {
        str(item.get("request_id"))
        for item in build_results
        if item.get("status") in {"merged", "completed"}
    }
    if pr_merged:
        for artifact in (pr_auto_merge, latest_backend_result, build_consumer_latest):
            if isinstance(artifact, dict) and _has_value(artifact.get("request_id")):
                completed_ids.add(str(artifact["request_id"]))
    pending = [
        item for item in build_requests if str(item.get("request_id")) not in completed_ids
    ]
    result_analysis = latest_cycle.get("result_analysis") if isinstance(latest_cycle.get("result_analysis"), dict) else {}
    blockers = result_analysis.get("content_blockers")
    if not isinstance(blockers, list):
        blockers = []
    summary = loop_packet.get("summary") if isinstance(loop_packet.get("summary"), dict) else {}
    active_manual_blockers: list[str] = []
    backend_success_supersedes_consumer = (
        isinstance(latest_backend_result, dict)
        and latest_backend_result.get("build_request_consumed") is True
        and latest_backend_result.get("pr_created") is True
        and not _has_value(latest_backend_result.get("blocked_reason"))
        and not _has_value(latest_backend_result.get("missing_capability"))
    )
    if isinstance(build_consumer_latest, dict) and not backend_success_supersedes_consumer:
        _append_blocker(active_manual_blockers, build_consumer_latest.get("blocked_reason"))
        _append_blocker(active_manual_blockers, build_consumer_latest.get("missing_capability"))
    if isinstance(latest_backend_result, dict):
        _append_blocker(active_manual_blockers, latest_backend_result.get("blocked_reason"))
        _append_blocker(active_manual_blockers, latest_backend_result.get("missing_capability"))
    if isinstance(pr_auto_merge, dict) and pr_auto_merge.get("pr_auto_merged") is not True:
        _append_blocker(active_manual_blockers, pr_auto_merge.get("blocked_reasons"))
        if pr_auto_merge.get("manual_governance_required") is True and not active_manual_blockers:
            _append_blocker(active_manual_blockers, "manual_governance_required")
    if isinstance(runtime_continuation, dict):
        _append_blocker(active_manual_blockers, runtime_continuation.get("blocked_reasons"))
        if runtime_continuation.get("runtime_updated") is False:
            _append_blocker(active_manual_blockers, "runtime_update_failed")
        if (
            runtime_continuation.get("research_continuation_started") is False
            and runtime_continuation.get("blocked_reasons")
        ):
            _append_blocker(active_manual_blockers, "continuation_blocked")

    protected_outputs_mutated = any(
        artifact.get("protected_outputs_mutated") is True
        for artifact in (
            summary,
            build_consumer_latest or {},
            latest_backend_result or {},
            pr_auto_merge or {},
            runtime_continuation or {},
        )
        if isinstance(artifact, dict)
    )
    artifact_paths_used = [
        path
        for path in [
            loop_latest_path.as_posix(),
            build_request_latest_used,
            build_consumer_latest_used,
            *backend_result_paths,
            pr_auto_merge_used,
            runtime_continuation_used,
            flywheel_latest_path.as_posix() if flywheel is not None else None,
            trusted_loop_review_used,
            research_memory_current_artifacts_used,
            shadow_readiness_used,
        ]
        if path is not None
    ]
    latest_pr_number = _extract_pr_number(latest_backend_result, build_consumer_latest, pr_auto_merge)
    build_requests_consumed = max(build_consumed, flywheel_summary.get("build_requests_consumed", 0) or 0)
    prs_opened = max(pr_opened, flywheel_summary.get("prs_opened", 0) or 0)
    prs_green = max(pr_green, flywheel_summary.get("prs_green", 0) or 0)
    prs_merged = max(pr_merged, flywheel_summary.get("prs_merged", 0) or 0)
    runtime_updates_completed = max(runtime_updated, flywheel_summary.get("runtime_updates_completed", 0) or 0)
    research_continuations_started = max(
        research_continuation_started,
        flywheel_summary.get("research_continuations_started", 0) or 0,
    )
    build_request_statuses = {
        str(item.get("request_id")): "completed_or_merged"
        if str(item.get("request_id")) in completed_ids
        else "pending"
        for item in build_requests
    }
    build_consumer_observation = dict(build_consumer_latest) if isinstance(build_consumer_latest, dict) else None
    if build_consumer_observation is not None and backend_success_supersedes_consumer:
        build_consumer_observation["blocked_reason"] = None
        build_consumer_observation["missing_capability"] = None
        build_consumer_observation["superseded_by_backend_result"] = True
    trusted_loop_summary = (
        trusted_loop_review.get("summary") if isinstance(trusted_loop_review, dict) else {}
    )
    research_memory_summary = (
        research_memory_current_artifacts.get("summary")
        if isinstance(research_memory_current_artifacts, dict)
        else {}
    )
    shadow_summary = shadow_readiness.get("summary") if isinstance(shadow_readiness, dict) else {}
    qre_exact_next_action = (
        shadow_summary.get("exact_next_action")
        or trusted_loop_summary.get("exact_next_action")
        or (
            runtime_continuation.get("final_recommendation")
            if isinstance(runtime_continuation, dict)
            else latest_cycle.get("next_action", {}).get("recommended_action")
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc or _utcnow(),
        "period_covered": "latest_autonomous_loop_artifact",
        "source_loop_latest": loop_latest_path.as_posix(),
        "artifact_paths_used": artifact_paths_used,
        "summary": {
            "autonomous_cycles": len(cycles),
            "controlled_research_inner_loops": summary.get("controlled_research_inner_loop_count"),
            "market_intake_cycles": summary.get("market_intake_cycle_count"),
            "build_requests_created": len(build_requests),
            "build_requests_consumed": build_requests_consumed,
            "build_requests_pending": len(pending),
            "build_requests_completed_or_merged": len(completed_ids),
            "prs_opened": prs_opened,
            "prs_green": prs_green,
            "prs_merged": prs_merged,
            "runtime_updates_completed": runtime_updates_completed,
            "research_continuations_started": research_continuations_started,
            "manual_governance_blockers": active_manual_blockers,
            "unsafe_actions_blocked": summary.get("unsafe_actions_blocked", 0),
            "trading_status": "disabled",
            "protected_artifact_mutation": "detected" if protected_outputs_mutated else "none",
            "latest_universe": latest_cycle.get("market_intake", {}).get("universe"),
            "latest_hypothesis": latest_cycle.get("hypothesis_generation", {}).get("statement"),
            "latest_preset": latest_cycle.get("preset_selection", {}).get("preset_id"),
            "latest_metric_mode": latest_cycle.get("metric_evidence", {}).get("metric_mode"),
            "latest_blocker": active_manual_blockers[0]
            if active_manual_blockers
            else (blockers[0] if blockers else "none"),
            "latest_recommendation": (
                runtime_continuation.get("final_recommendation")
                if isinstance(runtime_continuation, dict)
                else latest_cycle.get("next_action", {}).get("recommended_action")
            ),
            "trusted_loop_review_ready": bool(trusted_loop_summary.get("trusted_loop_review_ready")),
            "trusted_loop_trust_verdict": trusted_loop_summary.get("trust_verdict"),
            "trusted_loop_trust_blocker_count": trusted_loop_summary.get("trust_blocker_count"),
            "trusted_loop_exact_next_action": trusted_loop_summary.get("exact_next_action"),
            "research_memory_current_artifacts_ready": (
                research_memory_summary.get("final_recommendation")
                == "research_memory_current_artifacts_ready"
            ),
            "research_memory_current_artifacts_status": research_memory_summary.get(
                "final_recommendation"
            ),
            "shadow_readiness_status": shadow_summary.get("readiness_status"),
            "shadow_readiness_blocker_count": shadow_summary.get("blocker_count"),
            "shadow_readiness_exact_next_action": shadow_summary.get("exact_next_action"),
            "qre_operator_authority": _qre_operator_authority(
                trusted_loop_review=trusted_loop_review,
                research_memory_current_artifacts=research_memory_current_artifacts,
                shadow_readiness=shadow_readiness,
            ),
            "qre_exact_next_action": qre_exact_next_action,
            "flywheel_progress": {
                "build_request_consumed": _yes_no_unknown(
                    build_requests_consumed > 0 if build_requests_consumed else None
                ),
                "pr_opened": f"#{latest_pr_number}"
                if prs_opened and latest_pr_number is not None
                else _yes_no_unknown(prs_opened > 0 if prs_opened else None),
                "pr_green": _yes_no_unknown(pr_auto_merge.get("pr_green") if isinstance(pr_auto_merge, dict) else None),
                "pr_merged": _yes_no_unknown(pr_auto_merge.get("pr_auto_merged") if isinstance(pr_auto_merge, dict) else None),
                "runtime_updated": _yes_no_unknown(
                    runtime_continuation.get("runtime_updated") if isinstance(runtime_continuation, dict) else None
                ),
                "research_continuation_started": _yes_no_unknown(
                    runtime_continuation.get("research_continuation_started")
                    if isinstance(runtime_continuation, dict)
                    else None
                ),
            },
        },
        "build_requests": build_requests,
        "build_request_statuses": build_request_statuses,
        "build_results": build_results,
        "build_consumer_latest": build_consumer_observation,
        "build_backend_results": [payload for _path, payload in backend_results],
        "pr_auto_merge": pr_auto_merge,
        "runtime_continuation": runtime_continuation,
        "trusted_loop_review": trusted_loop_review,
        "research_memory_current_artifacts": research_memory_current_artifacts,
        "shadow_readiness": shadow_readiness,
        "flywheel_summary_fallback": {
            key: value
            for key, value in flywheel_summary.items()
            if key != "manual_governance_blockers"
        },
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
            else str(qre_exact_next_action or "Continue bounded autonomous market-research cycles.")
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
    flywheel_progress = summary.get("flywheel_progress") if isinstance(summary.get("flywheel_progress"), dict) else {}
    build_request_statuses = packet.get("build_request_statuses")
    if not isinstance(build_request_statuses, dict):
        build_request_statuses = {}
    build_lines = [
        (
            f"- {item.get('request_id')}: {item.get('next_action')}, "
            f"safe_for_ade_build={item.get('safe_for_ade_build')}, "
            f"{build_request_statuses.get(str(item.get('request_id')), 'pending')}"
        )
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
            "QRE operator trust:",
            f"- Trusted-loop review ready: {summary['trusted_loop_review_ready']}",
            f"- Trusted-loop trust verdict: {summary['trusted_loop_trust_verdict']}",
            f"- Trusted-loop blocker count: {summary['trusted_loop_trust_blocker_count']}",
            f"- Trusted-loop exact next action: {summary['trusted_loop_exact_next_action']}",
            f"- Research-memory current artifacts ready: {summary['research_memory_current_artifacts_ready']}",
            f"- Research-memory current artifacts status: {summary['research_memory_current_artifacts_status']}",
            f"- Shadow readiness status: {summary['shadow_readiness_status']}",
            f"- Shadow readiness blocker count: {summary['shadow_readiness_blocker_count']}",
            f"- Shadow readiness exact next action: {summary['shadow_readiness_exact_next_action']}",
            f"- QRE operator authority: {summary['qre_operator_authority']}",
            f"- QRE exact next action: {summary['qre_exact_next_action']}",
            "",
            "Research intelligence progress:",
            "- Learning is feeding back into the next market-intake seed.",
            "- The system does not rotate assets when the blocker is infrastructure rather than asset quality.",
            "",
            "Flywheel progress:",
            f"- Build request consumed: {flywheel_progress.get('build_request_consumed', 'unknown')}",
            f"- PR opened: {flywheel_progress.get('pr_opened', 'unknown')}",
            f"- PR green: {flywheel_progress.get('pr_green', 'unknown')}",
            f"- PR merged: {flywheel_progress.get('pr_merged', 'unknown')}",
            f"- Runtime updated: {flywheel_progress.get('runtime_updated', 'unknown')}",
            f"- Research continuation started: {flywheel_progress.get('research_continuation_started', 'unknown')}",
            "",
            "Artifact sources used:",
            *[f"- {path}" for path in packet.get("artifact_paths_used", [])],
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
    build_request_latest_path: Path = DEFAULT_BUILD_REQUEST_LATEST,
    build_consumer_latest_path: Path = DEFAULT_BUILD_CONSUMER_LATEST,
    backend_results_dir: Path = DEFAULT_BUILD_BACKEND_RESULTS_DIR,
    pr_auto_merge_latest_path: Path = DEFAULT_PR_AUTO_MERGE_LATEST,
    runtime_continuation_latest_path: Path = DEFAULT_RUNTIME_CONTINUATION_LATEST,
    flywheel_latest_path: Path = DEFAULT_FLYWHEEL_LATEST,
    trusted_loop_review_latest_path: Path = DEFAULT_TRUSTED_LOOP_REVIEW_LATEST,
    research_memory_current_artifacts_latest_path: Path = DEFAULT_RESEARCH_MEMORY_CURRENT_ARTIFACTS_LATEST,
    shadow_readiness_latest_path: Path = DEFAULT_SHADOW_READINESS_LATEST,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    write: bool = False,
) -> dict[str, Any]:
    packet = build_daily_status_packet(
        loop_latest_path=loop_latest_path,
        build_request_latest_path=build_request_latest_path,
        build_consumer_latest_path=build_consumer_latest_path,
        backend_results_dir=backend_results_dir,
        pr_auto_merge_latest_path=pr_auto_merge_latest_path,
        runtime_continuation_latest_path=runtime_continuation_latest_path,
        flywheel_latest_path=flywheel_latest_path,
        trusted_loop_review_latest_path=trusted_loop_review_latest_path,
        research_memory_current_artifacts_latest_path=research_memory_current_artifacts_latest_path,
        shadow_readiness_latest_path=shadow_readiness_latest_path,
    )
    if write:
        packet["_artifact_paths"] = write_outputs(packet, output_dir=output_dir)
    return packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write QRE daily status digest.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--loop-latest", default=DEFAULT_LOOP_LATEST.as_posix())
    parser.add_argument("--build-request-latest", default=DEFAULT_BUILD_REQUEST_LATEST.as_posix())
    parser.add_argument("--build-consumer-latest", default=DEFAULT_BUILD_CONSUMER_LATEST.as_posix())
    parser.add_argument("--backend-results-dir", default=DEFAULT_BUILD_BACKEND_RESULTS_DIR.as_posix())
    parser.add_argument("--pr-auto-merge-latest", default=DEFAULT_PR_AUTO_MERGE_LATEST.as_posix())
    parser.add_argument("--runtime-continuation-latest", default=DEFAULT_RUNTIME_CONTINUATION_LATEST.as_posix())
    parser.add_argument("--flywheel-latest", default=DEFAULT_FLYWHEEL_LATEST.as_posix())
    parser.add_argument("--trusted-loop-review-latest", default=DEFAULT_TRUSTED_LOOP_REVIEW_LATEST.as_posix())
    parser.add_argument(
        "--research-memory-current-artifacts-latest",
        default=DEFAULT_RESEARCH_MEMORY_CURRENT_ARTIFACTS_LATEST.as_posix(),
    )
    parser.add_argument("--shadow-readiness-latest", default=DEFAULT_SHADOW_READINESS_LATEST.as_posix())
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR.as_posix())
    args = parser.parse_args(argv)
    packet = run_daily_status_digest(
        loop_latest_path=Path(args.loop_latest),
        build_request_latest_path=Path(args.build_request_latest),
        build_consumer_latest_path=Path(args.build_consumer_latest),
        backend_results_dir=Path(args.backend_results_dir),
        pr_auto_merge_latest_path=Path(args.pr_auto_merge_latest),
        runtime_continuation_latest_path=Path(args.runtime_continuation_latest),
        flywheel_latest_path=Path(args.flywheel_latest),
        trusted_loop_review_latest_path=Path(args.trusted_loop_review_latest),
        research_memory_current_artifacts_latest_path=Path(
            args.research_memory_current_artifacts_latest
        ),
        shadow_readiness_latest_path=Path(args.shadow_readiness_latest),
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
