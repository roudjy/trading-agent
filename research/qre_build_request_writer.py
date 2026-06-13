"""QRE build-request artifact writer.

Build requests are machine-readable and human-readable handoff artifacts for
ADE/Codex. They do not execute code, create branches, open PRs, merge PRs, or
mutate development queues.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_build_request"
DEFAULT_POST_MERGE_RESEARCH_COMMAND: Final[str] = (
    "python -m research.qre_autonomous_market_research_loop --write --max-cycles 3"
)


class BuildRequestWriterError(RuntimeError):
    """Raised when build-request writing would violate its output boundary."""


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _request_id(*, next_action: str, blocker: str, source_run_group_id: str) -> str:
    seed = "|".join(["qre_build_request", next_action, blocker, source_run_group_id])
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"build-request-{digest}"


def _assert_inside(root: Path, path: Path) -> None:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise BuildRequestWriterError(f"refusing write outside output dir: {path}")


def build_request_packet(
    *,
    source_cycle: dict[str, Any],
    classification: dict[str, Any],
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    next_action = str(classification.get("next_action") or "")
    result_analysis = source_cycle.get("result_analysis")
    if not isinstance(result_analysis, dict):
        result_analysis = {}
    blockers = result_analysis.get("content_blockers")
    blocker = str(blockers[0]) if isinstance(blockers, list) and blockers else ""
    source_market_seed = source_cycle.get("next_market_intake_seed")
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "request_id": _request_id(
            next_action=next_action,
            blocker=blocker,
            source_run_group_id=str(source_cycle.get("source_research_run_group_id") or ""),
        ),
        "created_at_utc": created_at_utc or _utcnow(),
        "source_cycle_id": source_cycle.get("cycle_id"),
        "source_research_run_id": source_cycle.get("source_research_run_id"),
        "source_research_run_group_id": source_cycle.get("source_research_run_group_id"),
        "source_market_intake_seed": source_market_seed,
        "next_action": next_action,
        "action_class": classification.get("action_class"),
        "safety_class": classification.get("safety_class"),
        "safe_for_ade_build": classification.get("ade_build_allowed") is True,
        "execution_allowed": False,
        "build_executed_by_this_controller": False,
        "recommended_branch": classification.get("recommended_branch"),
        "recommended_pr_title": classification.get("recommended_pr_title"),
        "implementation_scope": classification.get("implementation_scope") or [],
        "forbidden_actions": classification.get("forbidden_actions") or [],
        "acceptance_commands": classification.get("acceptance_commands") or [],
        "post_merge_research_command": DEFAULT_POST_MERGE_RESEARCH_COMMAND,
        "future_build_result_contract": {
            "artifact_dir": "logs/qre_autonomous_market_research_loop/build_results",
            "required_statuses": ["pending", "merged", "blocked", "superseded"],
            "post_merge_research_required": True,
            "blocker_to_check": blocker,
        },
    }


def render_build_request_markdown(packet: dict[str, Any]) -> str:
    scope = "\n".join(f"- {item}" for item in packet.get("implementation_scope") or [])
    forbidden = "\n".join(f"- {item}" for item in packet.get("forbidden_actions") or [])
    commands = "\n".join(f"- `{item}`" for item in packet.get("acceptance_commands") or [])
    return "\n".join(
        [
            "# QRE Build Request",
            "",
            f"- Request ID: `{packet['request_id']}`",
            f"- Next action: `{packet['next_action']}`",
            f"- Action class: `{packet['action_class']}`",
            f"- Safe for ADE build: `{packet['safe_for_ade_build']}`",
            "- Execution allowed: `False`",
            "- Build executed by this controller: `False`",
            f"- Recommended branch: `{packet['recommended_branch']}`",
            f"- Recommended PR title: `{packet['recommended_pr_title']}`",
            "",
            "## Implementation Scope",
            scope or "- Operator review required before scope is defined.",
            "",
            "## Forbidden Actions",
            forbidden,
            "",
            "## Acceptance Commands",
            commands,
            "",
            "## Post-Merge Research",
            f"- `{packet['post_merge_research_command']}`",
            "",
            "## Stop Condition",
            "- Stop if protected public research artifacts change, any paper/shadow/live authority appears, or the build needs broker/risk/execution access.",
            "",
        ]
    )


def write_build_request(
    packet: dict[str, Any],
    *,
    output_dir: Path,
    overwrite: bool = True,
) -> dict[str, str | bool]:
    build_dir = output_dir / "build_requests"
    request_id = str(packet["request_id"])
    json_path = build_dir / f"{request_id}.json"
    md_path = build_dir / f"{request_id}.md"
    latest_path = output_dir / "latest_build_request.json"
    for path in (json_path, md_path, latest_path):
        _assert_inside(output_dir, path)

    existed = json_path.exists()
    if existed and not overwrite:
        return {
            "request_id": request_id,
            "json": json_path.as_posix(),
            "markdown": md_path.as_posix(),
            "latest": latest_path.as_posix(),
            "created": False,
        }

    build_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(_json_dumps(packet), encoding="utf-8", newline="\n")
    md_path.write_text(render_build_request_markdown(packet), encoding="utf-8", newline="\n")
    latest_path.write_text(_json_dumps(packet), encoding="utf-8", newline="\n")
    return {
        "request_id": request_id,
        "json": json_path.as_posix(),
        "markdown": md_path.as_posix(),
        "latest": latest_path.as_posix(),
        "created": not existed,
    }


__all__ = [
    "BuildRequestWriterError",
    "DEFAULT_POST_MERGE_RESEARCH_COMMAND",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "build_request_packet",
    "render_build_request_markdown",
    "write_build_request",
]
