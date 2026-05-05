"""Task Board State Machine (v3.15.16.6).

Pure read-only projection over the roadmap-item lifecycle. For every
known roadmap item or proposal-queue row this module emits a typed
state-machine record carrying ``current_state``, ``next_state``,
``transition_reason``, ``owner_agent``, ``retry_count`` and
``last_update``. The autonomous loop's actuation layer
(v3.15.16.11) consumes the ``next_state`` field directly so it
never has to re-derive transition logic.

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
* Reads ``logs/proposal_queue/latest.json``,
  ``logs/roadmap_priority/latest.json``,
  ``logs/github_pr_lifecycle/latest.json``,
  ``logs/approval_inbox/latest.json``.
* Output limited to ``logs/task_board/``.
* Atomic writes (``tmp`` + ``os.replace``); no in-place edits.
* ``safe_to_execute`` is hard-coded ``false`` at the digest level.
* Missing or malformed source artifacts produce
  ``final_recommendation = "not_available"``; never silently OK.
* Determinism: two runs on the same input produce a byte-identical
  ``tasks`` list (modulo ``generated_at_utc``).
* The transition vocabulary is closed; unknown source data lands
  in ``backlog`` with a deterministic reason string.

State machine
-------------

The closed state vocabulary is::

    backlog       — proposal exists, not yet classified for execution
    refined       — proposal_queue has classified the item with risk_class
                    and acceptance_criteria
    todo          — appears in roadmap_priority's eligible candidates
    in_progress   — a matching open PR exists in github_pr_lifecycle
    review        — open PR with all required CI green and merge state
                    CLEAN
    done          — matching PR is merged
    blocked       — a blocker is recorded (HIGH risk, protected path
                    touched, dependencies unmet, etc.)
    human_needed  — explicit operator review required (proposal status
                    needs_human, approval_inbox row, or
                    requires_human plan flag)

CLI
---

::

    python -m reporting.task_board
    python -m reporting.task_board --no-write
    python -m reporting.task_board --status

Stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
MODULE_VERSION: str = "v3.15.16.6"
SCHEMA_VERSION: int = 1

DIGEST_DIR_JSON: Path = REPO_ROOT / "logs" / "task_board"

SOURCE_PROPOSAL_QUEUE: Path = (
    REPO_ROOT / "logs" / "proposal_queue" / "latest.json"
)
SOURCE_ROADMAP_PRIORITY: Path = (
    REPO_ROOT / "logs" / "roadmap_priority" / "latest.json"
)
SOURCE_PR_LIFECYCLE: Path = (
    REPO_ROOT / "logs" / "github_pr_lifecycle" / "latest.json"
)
SOURCE_APPROVAL_INBOX: Path = (
    REPO_ROOT / "logs" / "approval_inbox" / "latest.json"
)


# ---------------------------------------------------------------------------
# Closed taxonomies
# ---------------------------------------------------------------------------


STATE_BACKLOG: str = "backlog"
STATE_REFINED: str = "refined"
STATE_TODO: str = "todo"
STATE_IN_PROGRESS: str = "in_progress"
STATE_REVIEW: str = "review"
STATE_DONE: str = "done"
STATE_BLOCKED: str = "blocked"
STATE_HUMAN_NEEDED: str = "human_needed"

STATES: tuple[str, ...] = (
    STATE_BACKLOG,
    STATE_REFINED,
    STATE_TODO,
    STATE_IN_PROGRESS,
    STATE_REVIEW,
    STATE_DONE,
    STATE_BLOCKED,
    STATE_HUMAN_NEEDED,
)


REC_OK: str = "ok"
REC_NOT_AVAILABLE: str = "not_available"

FINAL_RECOMMENDATIONS: tuple[str, ...] = (REC_OK, REC_NOT_AVAILABLE)


# Owner-agent vocabulary mirrors the eight canonical roles already
# enumerated in ``reporting.roadmap_execution_protocol._AGENT_ROLES``.
# Kept local so this module can be tested in isolation; sync via
# the protocol module's MODULE_VERSION reference if the closed set
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


# Mapping from current_state to the canonical owner_agent at that
# stage. Deterministic.
_STATE_TO_OWNER: dict[str, str] = {
    STATE_BACKLOG: AGENT_PRODUCT_OWNER,
    STATE_REFINED: AGENT_PLANNER,
    STATE_TODO: AGENT_IMPLEMENTATION,
    STATE_IN_PROGRESS: AGENT_IMPLEMENTATION,
    STATE_REVIEW: AGENT_CI_GUARDIAN,
    STATE_DONE: AGENT_OPERATOR,
    STATE_BLOCKED: AGENT_OPERATOR,
    STATE_HUMAN_NEEDED: AGENT_OPERATOR,
}


# Mapping from current_state to the next_state under nominal
# progression. Used by the v3.15.16.11 actuator to know what to
# wait for / drive next.
_STATE_TO_NEXT: dict[str, str] = {
    STATE_BACKLOG: STATE_REFINED,
    STATE_REFINED: STATE_TODO,
    STATE_TODO: STATE_IN_PROGRESS,
    STATE_IN_PROGRESS: STATE_REVIEW,
    STATE_REVIEW: STATE_DONE,
    STATE_DONE: STATE_DONE,  # terminal
    STATE_BLOCKED: STATE_BLOCKED,  # terminal until unblocked
    STATE_HUMAN_NEEDED: STATE_HUMAN_NEEDED,  # terminal until cleared
}


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
# Source-artifact reads (passive; never invokes the producers)
# ---------------------------------------------------------------------------


def _read_json_artifact(
    path: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    """Read a JSON artifact and return ``(parsed, None)`` on success
    or ``(None, reason)`` on any error. Never raises."""
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
# State derivation
# ---------------------------------------------------------------------------


# A release tag like v3.15.16.5 or v3.15.16.10 in a PR title or
# branch name.
_RELEASE_TAG_RE = re.compile(r"v\d+(?:\.\d+){2,}(?:[.\-][^\s)]+)?")


def _extract_release_tags(text: str) -> tuple[str, ...]:
    if not isinstance(text, str):
        return ()
    return tuple(m.group(0) for m in _RELEASE_TAG_RE.finditer(text))


def _index_pr_lifecycle(
    pr_lifecycle: Mapping[str, Any] | None,
) -> dict[str, list[Mapping[str, Any]]]:
    """Index PRs by every release tag mentioned in their title or
    branch. Returns ``{release_tag: [prs...]}``. A PR mentioning
    multiple tags is indexed under each."""
    out: dict[str, list[Mapping[str, Any]]] = {}
    if not isinstance(pr_lifecycle, Mapping):
        return out
    prs = pr_lifecycle.get("prs")
    if not isinstance(prs, list):
        return out
    for pr in prs:
        if not isinstance(pr, Mapping):
            continue
        tags: set[str] = set()
        tags.update(_extract_release_tags(str(pr.get("title", ""))))
        tags.update(_extract_release_tags(str(pr.get("branch", ""))))
        for tag in tags:
            out.setdefault(tag, []).append(pr)
    return out


def _index_approval_inbox(
    inbox: Mapping[str, Any] | None,
) -> dict[str, list[Mapping[str, Any]]]:
    """Index approval-inbox items by related_item / item_id."""
    out: dict[str, list[Mapping[str, Any]]] = {}
    if not isinstance(inbox, Mapping):
        return out
    data = inbox.get("data")
    if not isinstance(data, Mapping):
        return out
    items = data.get("items")
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, Mapping):
            continue
        related = (
            item.get("related_item")
            or item.get("source_item_id")
            or item.get("item_id")
        )
        if isinstance(related, str) and related:
            out.setdefault(related, []).append(item)
    return out


def _proposal_release_id(p: Mapping[str, Any]) -> str | None:
    """Pick the release id a proposal belongs to. Looks at
    ``suggested_release_id`` first (set by proposal_queue when the
    title carries a release tag), then scans the title."""
    sug = p.get("suggested_release_id")
    if isinstance(sug, str) and sug:
        return sug
    tags = _extract_release_tags(str(p.get("title", "")))
    if tags:
        return tags[0]
    return None


def _derive_state(
    proposal: Mapping[str, Any],
    *,
    in_priority_eligible: bool,
    in_priority_filtered_blocked: bool,
    matching_prs: Sequence[Mapping[str, Any]],
    matching_inbox_items: Sequence[Mapping[str, Any]],
) -> tuple[str, str]:
    """Compute ``(current_state, transition_reason)`` for one
    proposal. First-match wins; the rule order is the canonical
    state-machine precedence:

    1. matching merged PR → done
    2. matching open PR with CI green + merge CLEAN → review
    3. matching open PR (any other state) → in_progress
    4. proposal status == needs_human OR matching needs_human inbox
       row → human_needed
    5. proposal status == blocked OR matching blocked inbox row OR
       priority filtered with blocked-shaped reason → blocked
    6. proposal in roadmap_priority eligible candidates → todo
    7. proposal classified with risk_class != UNKNOWN → refined
    8. anything else → backlog
    """
    # 1. merged
    for pr in matching_prs:
        state_field = (
            pr.get("state")
            or pr.get("status")
            or pr.get("merge_state")
        )
        merged_at = pr.get("mergedAt") or pr.get("merged_at")
        if merged_at or (isinstance(state_field, str) and state_field.lower() == "merged"):
            return (
                STATE_DONE,
                f"merged_pr_detected: {pr.get('url') or pr.get('number')}",
            )

    # 2-3. open PR
    for pr in matching_prs:
        checks_state = str(pr.get("checks_state", "")).lower()
        merge_state = str(pr.get("merge_state", "")).lower()
        if checks_state == "passed" and merge_state == "clean":
            return (
                STATE_REVIEW,
                f"open_pr_ci_green_merge_clean: {pr.get('url') or pr.get('number')}",
            )
        return (
            STATE_IN_PROGRESS,
            f"open_pr_detected: {pr.get('url') or pr.get('number')}",
        )

    # 4. human_needed
    proposal_status = proposal.get("status")
    if proposal_status == "needs_human":
        return (STATE_HUMAN_NEEDED, "proposal_status_is_needs_human")
    for ibx in matching_inbox_items:
        sev = str(ibx.get("severity", "")).lower()
        if sev in ("critical", "high"):
            return (
                STATE_HUMAN_NEEDED,
                f"approval_inbox_severity_{sev}",
            )

    # 5. blocked
    if proposal_status == "blocked":
        blocked_reason = proposal.get("blocked_reason") or "blocked"
        return (STATE_BLOCKED, f"proposal_status_blocked: {blocked_reason}")
    if in_priority_filtered_blocked:
        return (STATE_BLOCKED, "filtered_by_roadmap_priority")
    for ibx in matching_inbox_items:
        if str(ibx.get("status", "")).lower() == "blocked":
            return (STATE_BLOCKED, "approval_inbox_status_blocked")

    # 6. todo
    if in_priority_eligible:
        return (STATE_TODO, "eligible_in_roadmap_priority")

    # 7. refined
    risk = proposal.get("risk_class")
    if isinstance(risk, str) and risk and risk != "UNKNOWN":
        return (STATE_REFINED, f"classified_with_risk_{risk}")

    # 8. backlog
    return (STATE_BACKLOG, "no_classification_yet")


# ---------------------------------------------------------------------------
# Snapshot construction
# ---------------------------------------------------------------------------


def _build_task_record(
    *,
    proposal: Mapping[str, Any],
    current_state: str,
    transition_reason: str,
    matching_prs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    proposal_id = str(proposal.get("proposal_id") or "")
    title = str(proposal.get("title") or "(no title)")
    next_state = _STATE_TO_NEXT[current_state]
    owner = _STATE_TO_OWNER[current_state]
    pr_url = ""
    pr_number: int | None = None
    if matching_prs:
        first = matching_prs[0]
        url = first.get("url")
        if isinstance(url, str):
            pr_url = url
        num = first.get("number")
        if isinstance(num, int):
            pr_number = num
    return {
        "item_id": proposal_id,
        "title": title,
        "release_id": _proposal_release_id(proposal),
        "current_state": current_state,
        "next_state": next_state,
        "transition_reason": transition_reason,
        "owner_agent": owner,
        "retry_count": 0,
        "last_update": None,
        "evidence": {
            "proposal_source": str(proposal.get("source") or ""),
            "proposal_status": str(proposal.get("status") or ""),
            "proposal_type": str(proposal.get("proposal_type") or ""),
            "risk_class": str(proposal.get("risk_class") or ""),
            "pr_url": pr_url,
            "pr_number": pr_number,
            "affected_files": list(proposal.get("affected_files") or []),
        },
    }


def _counts_by_state(tasks: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    out = {s: 0 for s in STATES}
    for t in tasks:
        cs = str(t.get("current_state") or "")
        if cs in out:
            out[cs] += 1
    return out


def collect_snapshot(
    *,
    frozen_utc: str | None = None,
    proposal_queue_override: Mapping[str, Any] | None = None,
    roadmap_priority_override: Mapping[str, Any] | None = None,
    pr_lifecycle_override: Mapping[str, Any] | None = None,
    approval_inbox_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the full task-board digest. Pure function.

    Tests can supply override mappings to skip the file reads.
    """
    generated = frozen_utc or _utcnow()

    # --- Source ingestion ---
    if proposal_queue_override is not None:
        pq: Mapping[str, Any] | None = proposal_queue_override
        pq_error: str | None = None
    else:
        pq, pq_error = _read_json_artifact(SOURCE_PROPOSAL_QUEUE)

    if pq is None:
        return _build_not_available_digest(
            generated_at_utc=generated,
            reason=pq_error or "unknown",
            source_path=_rel(SOURCE_PROPOSAL_QUEUE),
        )
    proposals_raw = pq.get("proposals")
    if not isinstance(proposals_raw, list):
        return _build_not_available_digest(
            generated_at_utc=generated,
            reason="proposals_field_not_a_list",
            source_path=_rel(SOURCE_PROPOSAL_QUEUE),
        )

    proposals: list[Mapping[str, Any]] = [
        p for p in proposals_raw if isinstance(p, Mapping)
    ]

    # --- Optional sources (best-effort; missing => empty index) ---
    if roadmap_priority_override is not None:
        rp: Mapping[str, Any] | None = roadmap_priority_override
    else:
        rp, _ = _read_json_artifact(SOURCE_ROADMAP_PRIORITY)
    eligible_ids: set[str] = set()
    filtered_blocked_ids: set[str] = set()
    if isinstance(rp, Mapping):
        # Eligible candidates: anything in candidates[] (which is the
        # ranked eligible list from roadmap_priority).
        cands = rp.get("candidates")
        if isinstance(cands, list):
            for c in cands:
                if isinstance(c, Mapping):
                    pid = c.get("proposal_id")
                    if isinstance(pid, str):
                        eligible_ids.add(pid)
        # Filtered_out rows: those rejected with a blocked-shaped
        # reason flow into the blocked state.
        filtered = rp.get("filtered_out")
        if isinstance(filtered, list):
            for f in filtered:
                if not isinstance(f, Mapping):
                    continue
                reason = str(f.get("filter_reason") or "")
                pid = f.get("proposal_id")
                if not isinstance(pid, str):
                    continue
                if reason in (
                    "risk_high_excluded",
                    "protocol_decision_not_allowed_read_only",
                    "protocol_implementation_not_allowed",
                ):
                    filtered_blocked_ids.add(pid)

    if pr_lifecycle_override is not None:
        prl: Mapping[str, Any] | None = pr_lifecycle_override
    else:
        prl, _ = _read_json_artifact(SOURCE_PR_LIFECYCLE)
    pr_index = _index_pr_lifecycle(prl)

    if approval_inbox_override is not None:
        inbox: Mapping[str, Any] | None = approval_inbox_override
    else:
        inbox, _ = _read_json_artifact(SOURCE_APPROVAL_INBOX)
    inbox_index = _index_approval_inbox(inbox)

    # --- Per-proposal state derivation ---
    tasks: list[dict[str, Any]] = []
    for p in proposals:
        proposal_id = str(p.get("proposal_id") or "")
        if not proposal_id:
            continue
        release_id = _proposal_release_id(p)
        matching_prs: list[Mapping[str, Any]] = []
        if release_id:
            matching_prs = list(pr_index.get(release_id, ()))
        matching_inbox = list(inbox_index.get(proposal_id, ()))
        current_state, reason = _derive_state(
            p,
            in_priority_eligible=proposal_id in eligible_ids,
            in_priority_filtered_blocked=proposal_id in filtered_blocked_ids,
            matching_prs=matching_prs,
            matching_inbox_items=matching_inbox,
        )
        tasks.append(
            _build_task_record(
                proposal=p,
                current_state=current_state,
                transition_reason=reason,
                matching_prs=matching_prs,
            )
        )

    # Stable ordering: by proposal_id ascending. Same input -> same
    # output across runs.
    tasks.sort(key=lambda t: str(t.get("item_id") or ""))

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "task_board_digest",
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated,
        "mode": "dry-run",
        "source_proposal_queue": {
            "path": _rel(SOURCE_PROPOSAL_QUEUE),
            "status": "ok",
            "module_version": pq.get("module_version"),
            "proposal_count": len(proposals),
        },
        "policy": {
            "states": list(STATES),
            "owner_agents": list(OWNER_AGENTS),
        },
        "counts": {
            "tasks_total": len(tasks),
            "by_state": _counts_by_state(tasks),
        },
        "tasks": tasks,
        "final_recommendation": REC_OK,
        "safe_to_execute": False,
    }


def _build_not_available_digest(
    *, generated_at_utc: str, reason: str, source_path: str
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "task_board_digest",
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated_at_utc,
        "mode": "dry-run",
        "source_proposal_queue": {
            "path": source_path,
            "status": "not_available",
            "error": reason,
            "module_version": None,
            "proposal_count": 0,
        },
        "policy": {
            "states": list(STATES),
            "owner_agents": list(OWNER_AGENTS),
        },
        "counts": {
            "tasks_total": 0,
            "by_state": {s: 0 for s in STATES},
        },
        "tasks": [],
        "final_recommendation": REC_NOT_AVAILABLE,
        "safe_to_execute": False,
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def write_outputs(snapshot: Mapping[str, Any]) -> dict[str, str]:
    """Atomic write of latest.json + timestamped copy + history
    append. Mirrors the atomic-write pattern used by the rest of
    the reporting modules."""
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
        prog="reporting.task_board",
        description=(
            f"Task board state machine ({MODULE_VERSION}). "
            "Stdlib-only. Read-only projection over the roadmap "
            "lifecycle artifacts."
        ),
    )
    g = parser.add_mutually_exclusive_group(required=False)
    g.add_argument(
        "--mode",
        type=str,
        default="dry-run",
        choices=["dry-run"],
        help=(
            "Operating mode. Only dry-run is supported; the task "
            "board never executes anything."
        ),
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
