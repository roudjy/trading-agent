"""Agent Flow Orchestration (v3.15.16.7).

Pure read-only projection that, for every in-flight task in the
task-board (v3.15.16.6), surfaces the agent orchestration view:

* ``current_stage`` — same as the task-board's ``current_state``;
  the eight closed states.
* ``responsible_agent`` — which canonical agent role owns the
  current stage (mirrors task_board).
* ``next_agent`` — which agent receives the handoff at the next
  state.
* ``next_action_proposed`` — the closed-enum action the
  v3.15.16.11 actuator should perform once the v3.15.16.10
  governance is in place.
* ``blocking_reason`` — when the task is blocked or human_needed,
  a short string describing why.
* ``handoff_eligible`` — boolean: True iff the handoff to the
  next agent is mechanically valid (i.e., the next state is not
  a terminal blocker / human-needed state).

This module:

* never starts work
* never opens a branch
* never opens a PR
* never merges
* never invokes ``gh``
* never invokes ``git``
* never calls any external service
* never mutates any input artifact

Hard guarantees (enforced by code AND tests)
--------------------------------------------

* Stdlib-only. No subprocess, no ``gh``, no ``git``, no network.
* Reads ``logs/task_board/latest.json`` only. Never invokes the
  task_board CLI; the recurring maintenance scheduler is the
  canonical refresh path.
* Output limited to ``logs/agent_flow/``.
* Atomic writes (``tmp`` + ``os.replace``); no in-place edits.
* ``safe_to_execute`` is hard-coded ``false`` at the digest level.
* Missing or malformed task_board artifact produces
  ``final_recommendation = "not_available"``; never silently OK.
* Determinism: two runs on the same input produce a byte-identical
  ``handoffs`` list (modulo ``generated_at_utc``).
* Closed action vocabulary; unknown source data lands in ``no_op``
  with a deterministic reason.

Closed next_action_proposed vocabulary
--------------------------------------

::

    select_next_task   — product_owner stage
    generate_plan      — planner stage
    implement          — implementation_agent stage (todo / in_progress)
    validate           — implementation_agent (CI in flight)
    review             — ci_guardian (review state, ready for merge gate)
    merge              — operator (review state, all gates pass)
    escalate_human     — operator (blocked / human_needed / unknown)
    no_op              — terminal done state, or no actionable handoff

CLI
---

::

    python -m reporting.agent_flow
    python -m reporting.agent_flow --no-write
    python -m reporting.agent_flow --status

Stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
MODULE_VERSION: str = "v3.15.16.7"
SCHEMA_VERSION: int = 1

DIGEST_DIR_JSON: Path = REPO_ROOT / "logs" / "agent_flow"
SOURCE_TASK_BOARD: Path = REPO_ROOT / "logs" / "task_board" / "latest.json"


# ---------------------------------------------------------------------------
# Closed taxonomies
# ---------------------------------------------------------------------------


# next_action_proposed — closed enum the v3.15.16.11 actuator
# consumes. Mirror of the task-board state vocabulary, mapped to
# the action that resolves the current stage.
ACTION_SELECT_NEXT_TASK: str = "select_next_task"
ACTION_GENERATE_PLAN: str = "generate_plan"
ACTION_IMPLEMENT: str = "implement"
ACTION_VALIDATE: str = "validate"
ACTION_REVIEW: str = "review"
ACTION_MERGE: str = "merge"
ACTION_ESCALATE_HUMAN: str = "escalate_human"
ACTION_NO_OP: str = "no_op"

ACTIONS: tuple[str, ...] = (
    ACTION_SELECT_NEXT_TASK,
    ACTION_GENERATE_PLAN,
    ACTION_IMPLEMENT,
    ACTION_VALIDATE,
    ACTION_REVIEW,
    ACTION_MERGE,
    ACTION_ESCALATE_HUMAN,
    ACTION_NO_OP,
)


# Owner-agent vocabulary mirrors reporting.task_board.OWNER_AGENTS.
# Kept local so this module can be tested in isolation; sync via
# the task_board MODULE_VERSION reference if the closed set
# changes.
AGENT_PRODUCT_OWNER: str = "product_owner"
AGENT_STRATEGIC_ADVISOR: str = "strategic_advisor"
AGENT_PLANNER: str = "planner"
AGENT_IMPLEMENTATION: str = "implementation_agent"
AGENT_ARCHITECTURE_GUARDIAN: str = "architecture_guardian"
AGENT_CI_GUARDIAN: str = "ci_guardian"
AGENT_SECURITY_GOVERNANCE_GUARDIAN: str = "security_governance_guardian"
AGENT_OPERATOR: str = "operator"

OWNER_AGENTS: tuple[str, ...] = (
    AGENT_PRODUCT_OWNER,
    AGENT_STRATEGIC_ADVISOR,
    AGENT_PLANNER,
    AGENT_IMPLEMENTATION,
    AGENT_ARCHITECTURE_GUARDIAN,
    AGENT_CI_GUARDIAN,
    AGENT_SECURITY_GOVERNANCE_GUARDIAN,
    AGENT_OPERATOR,
)


# Mapping from current_stage to next_agent. Determined by which
# agent receives the handoff when the task progresses to its
# next_state. Mirrors task_board's _STATE_TO_NEXT and _STATE_TO_OWNER.
_STAGE_TO_NEXT_AGENT: dict[str, str] = {
    "backlog": AGENT_PLANNER,
    "refined": AGENT_IMPLEMENTATION,
    "todo": AGENT_IMPLEMENTATION,
    "in_progress": AGENT_CI_GUARDIAN,
    "review": AGENT_OPERATOR,
    "done": AGENT_OPERATOR,  # terminal; no further handoff
    "blocked": AGENT_OPERATOR,  # terminal until unblocked
    "human_needed": AGENT_OPERATOR,  # terminal until cleared
}


# Mapping from current_stage to the next_action_proposed the
# v3.15.16.11 actuator should consume.
_STAGE_TO_ACTION: dict[str, str] = {
    "backlog": ACTION_SELECT_NEXT_TASK,
    "refined": ACTION_GENERATE_PLAN,
    "todo": ACTION_IMPLEMENT,
    "in_progress": ACTION_VALIDATE,
    "review": ACTION_MERGE,
    "done": ACTION_NO_OP,
    "blocked": ACTION_ESCALATE_HUMAN,
    "human_needed": ACTION_ESCALATE_HUMAN,
}


# Stages where the handoff to the next agent is mechanically
# valid. Terminal blockers (blocked, human_needed) and terminal
# successes (done) are NOT handoff_eligible — operator action is
# required.
_HANDOFF_ELIGIBLE_STAGES: frozenset[str] = frozenset(
    {"backlog", "refined", "todo", "in_progress", "review"}
)


REC_OK: str = "ok"
REC_NOT_AVAILABLE: str = "not_available"

FINAL_RECOMMENDATIONS: tuple[str, ...] = (REC_OK, REC_NOT_AVAILABLE)


# ---------------------------------------------------------------------------
# Time / path helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace(
            "\\", "/"
        )
    except ValueError:
        return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Source-artifact read (passive)
# ---------------------------------------------------------------------------


def _read_json_artifact(
    path: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return (None, "missing")
    if not path.is_file():
        return (None, "not_a_file")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return (None, f"unreadable: {type(e).__name__}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return (None, f"malformed: {type(e).__name__}")
    if not isinstance(data, dict):
        return (None, "not_an_object")
    return (data, None)


# ---------------------------------------------------------------------------
# Per-task projection
# ---------------------------------------------------------------------------


def _build_handoff_record(task: Mapping[str, Any]) -> dict[str, Any] | None:
    """Project one task_board row into one agent_flow record.
    Returns ``None`` if the row's shape is invalid (missing
    item_id or unknown current_state)."""
    item_id = task.get("item_id")
    current_stage = task.get("current_state")
    responsible_agent = task.get("owner_agent")
    if not isinstance(item_id, str) or not item_id:
        return None
    if not isinstance(current_stage, str):
        return None
    if current_stage not in _STAGE_TO_NEXT_AGENT:
        # Unknown stage -> no_op + escalate
        next_agent = AGENT_OPERATOR
        next_action = ACTION_ESCALATE_HUMAN
        blocking_reason = f"unknown_current_stage: {current_stage!r}"
    else:
        next_agent = _STAGE_TO_NEXT_AGENT[current_stage]
        next_action = _STAGE_TO_ACTION[current_stage]
        if current_stage == "blocked":
            tr = task.get("transition_reason")
            blocking_reason = (
                str(tr) if isinstance(tr, str) else "blocked"
            )
        elif current_stage == "human_needed":
            tr = task.get("transition_reason")
            blocking_reason = (
                str(tr) if isinstance(tr, str) else "human_needed"
            )
        else:
            blocking_reason = None
    handoff_eligible = current_stage in _HANDOFF_ELIGIBLE_STAGES
    return {
        "item_id": item_id,
        "title": str(task.get("title") or ""),
        "current_stage": current_stage,
        "responsible_agent": (
            responsible_agent
            if isinstance(responsible_agent, str) and responsible_agent in OWNER_AGENTS
            else AGENT_OPERATOR
        ),
        "next_agent": next_agent,
        "next_action_proposed": next_action,
        "blocking_reason": blocking_reason,
        "handoff_eligible": handoff_eligible,
        "evidence": {
            "release_id": task.get("release_id"),
            "transition_reason": task.get("transition_reason"),
            "pr_url": (task.get("evidence") or {}).get("pr_url"),
            "pr_number": (task.get("evidence") or {}).get("pr_number"),
        },
    }


def _counts_by_action(
    handoffs: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    out = {a: 0 for a in ACTIONS}
    for h in handoffs:
        a = str(h.get("next_action_proposed") or "")
        if a in out:
            out[a] += 1
    return out


def _counts_by_responsible_agent(
    handoffs: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    out = {a: 0 for a in OWNER_AGENTS}
    for h in handoffs:
        a = str(h.get("responsible_agent") or "")
        if a in out:
            out[a] += 1
    return out


def collect_snapshot(
    *,
    frozen_utc: str | None = None,
    task_board_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the full agent-flow digest. Pure function."""
    generated = frozen_utc or _utcnow()

    if task_board_override is not None:
        tb: Mapping[str, Any] | None = task_board_override
        tb_error: str | None = None
    else:
        tb, tb_error = _read_json_artifact(SOURCE_TASK_BOARD)

    if tb is None:
        return _build_not_available_digest(
            generated_at_utc=generated,
            reason=tb_error or "unknown",
            source_path=_rel(SOURCE_TASK_BOARD),
        )

    tasks_raw = tb.get("tasks")
    if not isinstance(tasks_raw, list):
        return _build_not_available_digest(
            generated_at_utc=generated,
            reason="tasks_field_not_a_list",
            source_path=_rel(SOURCE_TASK_BOARD),
        )

    handoffs: list[dict[str, Any]] = []
    skipped = 0
    for t in tasks_raw:
        if not isinstance(t, Mapping):
            skipped += 1
            continue
        record = _build_handoff_record(t)
        if record is None:
            skipped += 1
            continue
        handoffs.append(record)

    # Stable ordering: by item_id ascending.
    handoffs.sort(key=lambda h: str(h.get("item_id") or ""))

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "agent_flow_digest",
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated,
        "mode": "dry-run",
        "source_task_board": {
            "path": _rel(SOURCE_TASK_BOARD),
            "status": "ok",
            "module_version": tb.get("module_version"),
            "task_count": len(tasks_raw),
            "skipped_invalid_rows": skipped,
        },
        "policy": {
            "actions": list(ACTIONS),
            "owner_agents": list(OWNER_AGENTS),
        },
        "counts": {
            "handoffs_total": len(handoffs),
            "by_next_action_proposed": _counts_by_action(handoffs),
            "by_responsible_agent": _counts_by_responsible_agent(handoffs),
            "handoff_eligible_total": sum(
                1 for h in handoffs if h.get("handoff_eligible")
            ),
        },
        "handoffs": handoffs,
        "final_recommendation": REC_OK,
        "safe_to_execute": False,
    }


def _build_not_available_digest(
    *, generated_at_utc: str, reason: str, source_path: str
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "agent_flow_digest",
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated_at_utc,
        "mode": "dry-run",
        "source_task_board": {
            "path": source_path,
            "status": "not_available",
            "error": reason,
            "module_version": None,
            "task_count": 0,
            "skipped_invalid_rows": 0,
        },
        "policy": {
            "actions": list(ACTIONS),
            "owner_agents": list(OWNER_AGENTS),
        },
        "counts": {
            "handoffs_total": 0,
            "by_next_action_proposed": {a: 0 for a in ACTIONS},
            "by_responsible_agent": {a: 0 for a in OWNER_AGENTS},
            "handoff_eligible_total": 0,
        },
        "handoffs": [],
        "final_recommendation": REC_NOT_AVAILABLE,
        "safe_to_execute": False,
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def write_outputs(snapshot: Mapping[str, Any]) -> dict[str, str]:
    DIGEST_DIR_JSON.mkdir(parents=True, exist_ok=True)
    ts = str(snapshot["generated_at_utc"]).replace(":", "-")
    json_now = DIGEST_DIR_JSON / f"{ts}.json"
    json_latest = DIGEST_DIR_JSON / "latest.json"
    history = DIGEST_DIR_JSON / "history.jsonl"
    payload = json.dumps(snapshot, sort_keys=True, indent=2)

    tmp_now = json_now.with_suffix(json_now.suffix + ".tmp")
    tmp_now.write_text(payload, encoding="utf-8")
    os.replace(tmp_now, json_now)

    tmp_latest = json_latest.with_suffix(json_latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, json_latest)

    compact = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as f:
        f.write(compact + "\n")

    return {
        "latest": _rel(json_latest),
        "timestamped": _rel(json_now),
        "history": _rel(history),
    }


def read_latest_snapshot() -> dict[str, Any] | None:
    p = DIGEST_DIR_JSON / "latest.json"
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reporting.agent_flow",
        description=(
            f"Agent flow orchestration ({MODULE_VERSION}). "
            "Stdlib-only. Read-only projection over the task_board "
            "kanban projection."
        ),
    )
    g = parser.add_mutually_exclusive_group(required=False)
    g.add_argument(
        "--mode",
        type=str,
        default="dry-run",
        choices=["dry-run"],
        help="Operating mode. Only dry-run is supported.",
    )
    g.add_argument(
        "--status",
        action="store_true",
        help="Read and print the latest digest from logs/.",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not persist the JSON digest (stdout only).",
    )
    parser.add_argument(
        "--frozen-utc",
        type=str,
        default=None,
        help="Pin generated_at_utc for deterministic tests.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent for stdout (0 for compact).",
    )
    args = parser.parse_args(argv)

    if args.status:
        snap = read_latest_snapshot()
        if snap is None:
            print(
                json.dumps(
                    {"status": "not_available", "reason": "missing"},
                    indent=args.indent or None,
                )
            )
            return 1
        print(json.dumps(snap, sort_keys=True, indent=args.indent or None))
        return 0

    snap = collect_snapshot(frozen_utc=args.frozen_utc)
    if not args.no_write:
        write_outputs(snap)
    print(json.dumps(snap, sort_keys=True, indent=args.indent or None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
