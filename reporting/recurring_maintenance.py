"""Recurring safe maintenance scheduler (v3.15.15.23).

A typed, whitelisted, deterministic scheduler that runs a closed
set of low-risk maintenance jobs at fixed intervals. Sits ON TOP of
the v3.15.15.22 workloop runtime — it does not replace it. The
runtime supervises one round of read-only reporters; the
maintenance scheduler decides which of those reporters should
actually be re-run on a schedule.

Hard guarantees
---------------

See ``docs/governance/recurring_maintenance.md`` for the full list
and the test suite that enforces each one. The shape is the same as
``reporting.workloop_runtime``: closed registry, in-process
executors only, atomic writes, bounded loop, credential-value
redaction, and a hard-coded false ``safe_to_execute`` flag at the
digest level.

The Dependabot LOW/MEDIUM execute-safe job is the only job that can
mutate GitHub state. It is gated by two independent flags: the
state-file ``enabled`` flag (defaults to false) AND a runtime CLI
opt-in flag. Without both, the job is refused. Even when both are
set, the actual merge logic lives in
``reporting.github_pr_lifecycle`` — the maintenance scheduler is
a thin pass-through.

CLI
---

::

    python -m reporting.recurring_maintenance --list-jobs
    python -m reporting.recurring_maintenance --plan
    python -m reporting.recurring_maintenance --run-once <job_type>
    python -m reporting.recurring_maintenance --run-due-once
    python -m reporting.recurring_maintenance --loop \\
        --interval-seconds 300 --max-iterations 3
    python -m reporting.recurring_maintenance --status

Stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from reporting import approval_policy as _approval_policy

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
MODULE_VERSION: str = "v3.15.15.23"
SCHEMA_VERSION: int = 1

DIGEST_DIR_JSON: Path = REPO_ROOT / "logs" / "recurring_maintenance"

# Hard runtime caps.
MAX_ITERATIONS_LIMIT: int = 24
MIN_INTERVAL_SECONDS: int = 30
MAX_INTERVAL_SECONDS: int = 6 * 3600  # 6 hours

# Per-job wall-clock timeout (seconds). The Dependabot path is the
# only one with a long budget because it can post comments and
# squash-merge PRs.
DEFAULT_JOB_TIMEOUT_SECONDS: int = 90
DEPENDABOT_JOB_TIMEOUT_SECONDS: int = 600


# ---------------------------------------------------------------------------
# Closed job-type list
# ---------------------------------------------------------------------------


JOB_REFRESH_WORKLOOP_RUNTIME: str = "refresh_workloop_runtime_once"
JOB_REFRESH_PROPOSAL_QUEUE: str = "refresh_proposal_queue"
JOB_REFRESH_APPROVAL_INBOX: str = "refresh_approval_inbox"
JOB_REFRESH_PR_LIFECYCLE_DRY_RUN: str = "refresh_github_pr_lifecycle_dry_run"
JOB_DEPENDABOT_EXECUTE_SAFE: str = "dependabot_low_medium_execute_safe"
# v3.15.16.2 — read-only roadmap priority projection. Joins the
# proposal queue with the roadmap execution protocol to emit a
# deterministic chosen_next_up item plus its plan summary. LOW
# risk; no gh; no external network; no mutation.
JOB_REFRESH_ROADMAP_PRIORITY: str = "refresh_roadmap_priority"
# v3.15.16.6 — read-only task board state machine. Projects every
# proposal-queue row into a typed kanban record carrying
# current_state, next_state, transition_reason, owner_agent. LOW
# risk; no gh; no external network; no mutation.
JOB_REFRESH_TASK_BOARD: str = "refresh_task_board"
# v3.15.16.7 — read-only agent flow projection. Per task surfaces
# responsible_agent, next_agent, next_action_proposed (closed enum)
# so the v3.15.16.11 actuator can consume handoffs deterministically.
JOB_REFRESH_AGENT_FLOW: str = "refresh_agent_flow"
# v3.15.16.8 — read-only human_needed event detection. Auto-detects
# wiring gaps and other operator-blockers; emits structured events
# with proposed_patch text. Future push notifications trigger only
# from these events.
JOB_REFRESH_HUMAN_NEEDED: str = "refresh_human_needed"
# v3.15.16.9 — read-only governance-bootstrap PR-template
# synthesizer. Reads logs/human_needed/latest.json and produces
# copy-paste-able bootstrap-PR templates (text only).
JOB_REFRESH_GOVERNANCE_BOOTSTRAP: str = "refresh_governance_bootstrap"
# v3.15.16.10 PR-4 / A6 — read-only autonomous backlog discipline.
# Reads logs/proposal_queue/latest.json and groups every proposal
# into the closed Agent Execution Authority buckets via the
# reporting.execution_authority classifier. LOW risk; no gh; no
# external network; no mutation.
JOB_REFRESH_AUTONOMOUS_BACKLOG: str = "refresh_autonomous_backlog"
# v3.15.16.N5b.phase1 — read-only N5b Phase 1 dry-run merge
# preflight projector. Reads A22
# (logs/development_pr_lifecycle_observer/latest.json) and A23
# (logs/development_merge_recommendation/latest.json) and emits a
# closed-schema dry-run preflight snapshot at
# logs/development_merge_preflight/latest.json. LOW risk; no gh;
# no external network; no mutation; never merges; never deploys;
# never mints or verifies approval tokens. Failure-non-fatal when
# upstream A22/A23 artefacts are absent — the projector
# default-denies with closed-vocab warnings rather than raising.
JOB_REFRESH_MERGE_PREFLIGHT: str = "refresh_merge_preflight"

JOB_TYPES: tuple[str, ...] = (
    JOB_REFRESH_WORKLOOP_RUNTIME,
    JOB_REFRESH_PROPOSAL_QUEUE,
    JOB_REFRESH_APPROVAL_INBOX,
    JOB_REFRESH_PR_LIFECYCLE_DRY_RUN,
    JOB_DEPENDABOT_EXECUTE_SAFE,
    JOB_REFRESH_ROADMAP_PRIORITY,
    JOB_REFRESH_TASK_BOARD,
    JOB_REFRESH_AGENT_FLOW,
    JOB_REFRESH_HUMAN_NEEDED,
    JOB_REFRESH_GOVERNANCE_BOOTSTRAP,
    JOB_REFRESH_AUTONOMOUS_BACKLOG,
    JOB_REFRESH_MERGE_PREFLIGHT,
)


# Result-status enum.
STATUS_NOT_RUN: str = "not_run"
STATUS_SUCCEEDED: str = "succeeded"
STATUS_SKIPPED: str = "skipped"
STATUS_BLOCKED: str = "blocked"
STATUS_FAILED: str = "failed"
STATUS_TIMEOUT: str = "timeout"
STATUS_NOT_AVAILABLE: str = "not_available"

STATUS_VALUES: tuple[str, ...] = (
    STATUS_NOT_RUN,
    STATUS_SUCCEEDED,
    STATUS_SKIPPED,
    STATUS_BLOCKED,
    STATUS_FAILED,
    STATUS_TIMEOUT,
    STATUS_NOT_AVAILABLE,
)

RISK_LOW: str = "LOW"
RISK_MEDIUM: str = "MEDIUM"


# Credential-value patterns — same posture as workloop_runtime: we
# refuse credential VALUES at the snapshot boundary, but allow
# path-shaped strings (no-touch metadata legitimately appears in
# job descriptions).
_OUTER_CREDENTIAL_PATTERNS: tuple[str, ...] = (
    "sk-ant-",
    "ghp_",
    "github_pat_",
    "AKIA",
    "-----BEGIN ",
)


def _assert_no_credential_values(snapshot: dict[str, Any]) -> None:
    import collections.abc as _abc

    def _walk(o: Any):
        if isinstance(o, str):
            yield o
        elif isinstance(o, dict):
            for v in o.values():
                yield from _walk(v)
        elif isinstance(o, _abc.Iterable) and not isinstance(o, (bytes, bytearray)):
            for v in o:
                yield from _walk(v)

    for s in _walk(snapshot):
        for pat in _OUTER_CREDENTIAL_PATTERNS:
            if pat in s:
                raise AssertionError(
                    f"recurring_maintenance leaked credential-like value: "
                    f"pattern={pat!r}"
                )


# ---------------------------------------------------------------------------
# Time / id helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _utcnow_dt() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0)


def _job_id(job_type: str) -> str:
    raw = job_type.encode("utf-8")
    return "j_" + hashlib.sha256(raw).hexdigest()[:8]


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _parse_iso_utc(s: str | None) -> _dt.datetime | None:
    if not s:
        return None
    try:
        # Strip the trailing 'Z' and parse.
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return _dt.datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Job executors (in-process; no subprocess from this module)
# ---------------------------------------------------------------------------


def _exec_refresh_workloop_runtime() -> dict[str, Any]:
    """Run a single iteration of the v3.15.15.22 workloop runtime."""
    from reporting.workloop_runtime import run_once as _run_once

    snap = _run_once(write=True)
    return {
        "summary": (
            f"workloop_runtime "
            f"{snap.get('final_recommendation') or 'no recommendation'}"
        ),
        "evidence": {
            "run_id": snap.get("run_id"),
            "duration_ms": snap.get("duration_ms"),
            "counts": snap.get("counts"),
        },
    }


def _exec_refresh_proposal_queue() -> dict[str, Any]:
    from reporting.proposal_queue import collect_snapshot, write_outputs

    snap = collect_snapshot(mode="dry-run")
    write_outputs(snap)
    return {
        "summary": (
            f"proposal_queue "
            f"{snap.get('final_recommendation') or 'no recommendation'}"
        ),
        "evidence": {
            "counts": snap.get("counts"),
        },
    }


def _exec_refresh_approval_inbox() -> dict[str, Any]:
    from reporting.approval_inbox import collect_snapshot, write_outputs

    snap = collect_snapshot(mode="dry-run")
    write_outputs(snap)
    return {
        "summary": (
            f"approval_inbox "
            f"{snap.get('final_recommendation') or 'no recommendation'}"
        ),
        "evidence": {
            "counts": snap.get("counts"),
        },
    }


def _exec_refresh_pr_lifecycle_dry_run() -> dict[str, Any]:
    from reporting.github_pr_lifecycle import collect_snapshot, write_outputs

    snap = collect_snapshot(mode="dry-run")
    write_outputs(snap)
    return {
        "summary": (
            f"github_pr_lifecycle "
            f"{snap.get('final_recommendation') or 'no recommendation'}"
        ),
        "evidence": {
            "provider_status": snap.get("provider_status"),
        },
    }


def _exec_refresh_roadmap_priority() -> dict[str, Any]:
    """Run the v3.15.16.2 roadmap priority projection (read-only).

    Reads ``logs/proposal_queue/latest.json`` and, for each
    proposal, calls ``roadmap_execution_protocol.plan_item`` to
    obtain the per-item decision. Writes the deterministic
    ``logs/roadmap_priority/latest.json`` digest. Never starts a
    branch, never opens a PR, never invokes ``gh``. The digest's
    ``safe_to_execute`` field is hard-coded ``false``."""
    from reporting.roadmap_priority import collect_snapshot, write_outputs

    snap = collect_snapshot()
    write_outputs(snap)
    chosen = snap.get("chosen_next_up") or {}
    return {
        "summary": (
            f"roadmap_priority "
            f"{snap.get('final_recommendation') or 'no recommendation'}"
        ),
        "evidence": {
            "chosen_proposal_id": chosen.get("proposal_id"),
            "chosen_title": chosen.get("title"),
            "counts": snap.get("counts"),
        },
    }


def _exec_refresh_task_board() -> dict[str, Any]:
    """Run the v3.15.16.6 task-board state-machine projection
    (read-only). Reads logs/proposal_queue/latest.json plus the
    optional sibling artifacts (roadmap_priority, github_pr_lifecycle,
    approval_inbox) and writes logs/task_board/latest.json. Never
    starts a branch, never opens a PR, never invokes ``gh``."""
    from reporting.task_board import collect_snapshot, write_outputs

    snap = collect_snapshot()
    write_outputs(snap)
    counts = snap.get("counts") or {}
    return {
        "summary": (
            f"task_board "
            f"{snap.get('final_recommendation') or 'no recommendation'}"
        ),
        "evidence": {
            "tasks_total": counts.get("tasks_total"),
            "by_state": counts.get("by_state"),
        },
    }


def _exec_refresh_agent_flow() -> dict[str, Any]:
    """Run the v3.15.16.7 agent-flow projection (read-only).
    Reads logs/task_board/latest.json (v3.15.16.6) and writes
    logs/agent_flow/latest.json. Never starts a branch, never opens
    a PR, never invokes ``gh``."""
    from reporting.agent_flow import collect_snapshot, write_outputs

    snap = collect_snapshot()
    write_outputs(snap)
    counts = snap.get("counts") or {}
    return {
        "summary": (
            f"agent_flow "
            f"{snap.get('final_recommendation') or 'no recommendation'}"
        ),
        "evidence": {
            "handoffs_total": counts.get("handoffs_total"),
            "by_next_action_proposed": counts.get("by_next_action_proposed"),
        },
    }


def _exec_refresh_human_needed() -> dict[str, Any]:
    """Run the v3.15.16.8 human_needed event-detection projection
    (read-only). Reads logs/task_board/latest.json (v3.15.16.6) and
    statically analyses dashboard/api_*.py + dashboard/dashboard.py
    for wiring gaps. Writes logs/human_needed/latest.json. Never
    starts a branch, never opens a PR, never invokes ``gh``."""
    from reporting.human_needed import collect_snapshot, write_outputs

    snap = collect_snapshot()
    write_outputs(snap)
    counts = snap.get("counts") or {}
    return {
        "summary": (
            f"human_needed "
            f"{snap.get('final_recommendation') or 'no recommendation'}"
        ),
        "evidence": {
            "events_total": counts.get("events_total"),
            "by_reason": counts.get("by_reason"),
            "by_priority": counts.get("by_priority"),
        },
    }


def _exec_refresh_governance_bootstrap() -> dict[str, Any]:
    """Run the v3.15.16.9 governance-bootstrap PR-template
    synthesizer (read-only). Reads logs/human_needed/latest.json
    (v3.15.16.8) and writes logs/governance_bootstrap/latest.json
    with one copy-paste-able PR template per bootstrappable event.
    Never starts a branch, never opens a PR, never invokes ``gh``."""
    from reporting.governance_bootstrap import collect_snapshot, write_outputs

    snap = collect_snapshot()
    write_outputs(snap)
    counts = snap.get("counts") or {}
    return {
        "summary": (
            f"governance_bootstrap "
            f"{snap.get('final_recommendation') or 'no recommendation'}"
        ),
        "evidence": {
            "templates_total": counts.get("templates_total"),
        },
    }


def _exec_refresh_autonomous_backlog() -> dict[str, Any]:
    """Run the v3.15.16.10 PR-4 autonomous backlog discipline summary
    (read-only). Reads logs/proposal_queue/latest.json and writes
    logs/autonomous_backlog/latest.json with proposals grouped by
    Agent Execution Authority decision. Never starts a branch, never
    opens a PR, never invokes ``gh``."""
    from reporting.autonomous_backlog_summary import run_once as _run_once

    snap = _run_once(write=True)
    counts = snap.get("counts") or {}
    return {
        "summary": (
            "autonomous_backlog "
            f"total={counts.get('total', 0)} "
            f"needs_human={counts.get('needs_human', 0)} "
            f"auto_allowed={counts.get('auto_allowed', 0)} "
            f"permanently_denied={counts.get('permanently_denied', 0)}"
        ),
        "evidence": {
            "total": counts.get("total"),
            "permanently_denied": counts.get("permanently_denied"),
            "needs_human": counts.get("needs_human"),
            "auto_allowed": counts.get("auto_allowed"),
            "stale_or_resolved": counts.get("stale_or_resolved"),
            "unknown_failsafe": counts.get("unknown_failsafe"),
            "source_available": snap.get("source_available"),
        },
    }


def _exec_refresh_merge_preflight() -> dict[str, Any]:
    """Run the v3.15.16.N5b.phase1 dry-run merge-preflight projector
    (read-only). Reads A22 and A23 artefacts and writes
    ``logs/development_merge_preflight/latest.json``. Never starts
    a branch, never opens a PR, never invokes ``gh``, never mints
    or verifies approval tokens, never deploys. Failure-non-fatal
    when upstream artefacts are absent — the projector
    default-denies with closed-vocab warnings.

    Step 5 + Level 6 invariants stay pinned by the projector:
    ``step5_implementation_allowed=false``,
    ``step5_enabled_substage="none"``, ``level6_enabled=false``,
    ``dry_run_only=true``, ``live_merge_implemented=false``,
    ``deploy_coupled=false``.
    """
    from reporting.development_merge_preflight import (
        collect_snapshot,
        write_outputs,
    )

    snap = collect_snapshot()
    write_outputs(snap)
    return {
        "summary": (
            f"development_merge_preflight "
            f"candidate_count={snap.get('candidate_count', 0)} "
            f"note={snap.get('note') or 'no note'}"
        ),
        "evidence": {
            "candidate_count": snap.get("candidate_count"),
            "dry_run_only": snap.get("dry_run_only"),
            "live_merge_implemented": snap.get("live_merge_implemented"),
            "deploy_coupled": snap.get("deploy_coupled"),
            "note": snap.get("note"),
            "validation_warnings": snap.get("validation_warnings"),
        },
    }


def _exec_dependabot_execute_safe() -> dict[str, Any]:
    """Delegate to the existing ``reporting.github_pr_lifecycle``
    execute-safe path. The lifecycle module owns every Dependabot
    precondition (LOW/MEDIUM only, CLEAN mergeability, checks green,
    no protected paths, no live/trading paths, etc.) — we do not
    re-implement them here.
    """
    from reporting.github_pr_lifecycle import (
        collect_snapshot,
        execute_safe_actions,
        write_outputs,
    )

    snap = collect_snapshot(mode="execute-safe")
    snap = execute_safe_actions(snap)
    write_outputs(snap)
    return {
        "summary": (
            f"dependabot_execute_safe "
            f"{snap.get('final_recommendation') or 'no recommendation'}"
        ),
        "evidence": {
            "actions_taken_count": len(snap.get("actions_taken") or []),
        },
    }


# Registry: closed list, addressed by job_type.
_JOB_REGISTRY: dict[str, dict[str, Any]] = {
    JOB_REFRESH_WORKLOOP_RUNTIME: {
        "default_interval_seconds": 15 * 60,
        "default_enabled": True,
        "executor": _exec_refresh_workloop_runtime,
        "description": "Run reporting.workloop_runtime.run_once() (read-only refresh).",
        "risk_class": RISK_LOW,
        "needs_gh": False,
        "timeout_seconds": DEFAULT_JOB_TIMEOUT_SECONDS,
    },
    JOB_REFRESH_PROPOSAL_QUEUE: {
        # Aligned with JOB_REFRESH_APPROVAL_INBOX at 15 min. Previously
        # 60 min; that left a 60-min race where two close-together
        # deploys would let the second post-deploy ``--run-due-once``
        # skip proposal_queue while every downstream (task_board /
        # human_needed / governance_bootstrap / approval_inbox) was
        # already due, refreshed, and re-projected the stale upstream
        # source. The proposal_queue ingester is stdlib-only, parses
        # ~6 markdown files, and runs in <100 ms — running it 4× more
        # often is harmless. Invariant pinned by tests:
        # proposal_queue.interval <= task_board.interval (upstream
        # must never refresh slower than its downstream projection).
        "default_interval_seconds": 15 * 60,
        "default_enabled": True,
        "executor": _exec_refresh_proposal_queue,
        "description": "Refresh proposal-queue dry-run artifact.",
        "risk_class": RISK_LOW,
        "needs_gh": False,
        "timeout_seconds": DEFAULT_JOB_TIMEOUT_SECONDS,
    },
    JOB_REFRESH_APPROVAL_INBOX: {
        "default_interval_seconds": 15 * 60,
        "default_enabled": True,
        "executor": _exec_refresh_approval_inbox,
        "description": "Refresh approval-inbox dry-run artifact.",
        "risk_class": RISK_LOW,
        "needs_gh": False,
        "timeout_seconds": DEFAULT_JOB_TIMEOUT_SECONDS,
    },
    JOB_REFRESH_PR_LIFECYCLE_DRY_RUN: {
        "default_interval_seconds": 30 * 60,
        "default_enabled": True,
        "executor": _exec_refresh_pr_lifecycle_dry_run,
        "description": "Refresh GitHub PR lifecycle dry-run artifact.",
        "risk_class": RISK_LOW,
        "needs_gh": True,
        "timeout_seconds": DEFAULT_JOB_TIMEOUT_SECONDS,
    },
    JOB_DEPENDABOT_EXECUTE_SAFE: {
        "default_interval_seconds": 60 * 60,
        # *** Disabled by default. The CLI also requires
        # --enable-dependabot-execute-safe at runtime, so a stray
        # invocation cannot accidentally merge a PR. ***
        "default_enabled": False,
        "executor": _exec_dependabot_execute_safe,
        "description": (
            "Run reporting.github_pr_lifecycle execute-safe path "
            "(LOW/MEDIUM Dependabot PRs only). Disabled by default; "
            "requires --enable-dependabot-execute-safe at the CLI."
        ),
        "risk_class": RISK_MEDIUM,
        "needs_gh": True,
        "timeout_seconds": DEPENDABOT_JOB_TIMEOUT_SECONDS,
    },
    JOB_REFRESH_ROADMAP_PRIORITY: {
        "default_interval_seconds": 30 * 60,
        "default_enabled": True,
        "executor": _exec_refresh_roadmap_priority,
        "description": (
            "Refresh roadmap priority dry-run digest "
            "(read-only projection over the proposal queue + "
            "roadmap execution protocol)."
        ),
        "risk_class": RISK_LOW,
        "needs_gh": False,
        "timeout_seconds": DEFAULT_JOB_TIMEOUT_SECONDS,
    },
    JOB_REFRESH_TASK_BOARD: {
        "default_interval_seconds": 30 * 60,
        "default_enabled": True,
        "executor": _exec_refresh_task_board,
        "description": (
            "Refresh task-board state-machine digest "
            "(read-only kanban projection over the proposal queue "
            "+ roadmap_priority + github_pr_lifecycle + approval_inbox)."
        ),
        "risk_class": RISK_LOW,
        "needs_gh": False,
        "timeout_seconds": DEFAULT_JOB_TIMEOUT_SECONDS,
    },
    JOB_REFRESH_AGENT_FLOW: {
        "default_interval_seconds": 30 * 60,
        "default_enabled": True,
        "executor": _exec_refresh_agent_flow,
        "description": (
            "Refresh agent-flow handoff digest "
            "(read-only orchestration projection over the task_board)."
        ),
        "risk_class": RISK_LOW,
        "needs_gh": False,
        "timeout_seconds": DEFAULT_JOB_TIMEOUT_SECONDS,
    },
    JOB_REFRESH_HUMAN_NEEDED: {
        "default_interval_seconds": 30 * 60,
        "default_enabled": True,
        "executor": _exec_refresh_human_needed,
        "description": (
            "Refresh human_needed event-detection digest "
            "(read-only blocker detection with proposed_patch synthesis)."
        ),
        "risk_class": RISK_LOW,
        "needs_gh": False,
        "timeout_seconds": DEFAULT_JOB_TIMEOUT_SECONDS,
    },
    JOB_REFRESH_GOVERNANCE_BOOTSTRAP: {
        "default_interval_seconds": 30 * 60,
        "default_enabled": True,
        "executor": _exec_refresh_governance_bootstrap,
        "description": (
            "Refresh governance-bootstrap PR-template digest "
            "(read-only text synthesis over the human_needed events)."
        ),
        "risk_class": RISK_LOW,
        "needs_gh": False,
        "timeout_seconds": DEFAULT_JOB_TIMEOUT_SECONDS,
    },
    JOB_REFRESH_AUTONOMOUS_BACKLOG: {
        "default_interval_seconds": 30 * 60,
        "default_enabled": True,
        "executor": _exec_refresh_autonomous_backlog,
        "description": (
            "Refresh autonomous-backlog discipline digest "
            "(read-only Agent Execution Authority projection over the "
            "proposal queue). Disable by setting --no-job to opt out; "
            "the CLI alone (`python -m reporting.autonomous_backlog_summary`) "
            "remains usable on demand for rollback."
        ),
        "risk_class": RISK_LOW,
        "needs_gh": False,
        "timeout_seconds": DEFAULT_JOB_TIMEOUT_SECONDS,
    },
    JOB_REFRESH_MERGE_PREFLIGHT: {
        "default_interval_seconds": 30 * 60,
        "default_enabled": True,
        "executor": _exec_refresh_merge_preflight,
        "description": (
            "Refresh N5b Phase 1 dry-run merge-preflight digest "
            "(read-only projection over the A22 PR-lifecycle observer "
            "+ A23 merge recommendation artefacts). Never calls gh, "
            "never merges, never deploys, never mints or verifies an "
            "approval token. Failure-non-fatal when upstream A22/A23 "
            "artefacts are absent."
        ),
        "risk_class": RISK_LOW,
        "needs_gh": False,
        "timeout_seconds": DEFAULT_JOB_TIMEOUT_SECONDS,
    },
}


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


def _state_file() -> Path:
    return DIGEST_DIR_JSON / "state.json"


def _read_state() -> dict[str, Any]:
    """Read the per-job state file. Returns ``{}`` on any error."""
    p = _state_file()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_state(state: dict[str, Any]) -> None:
    """Atomic write of ``state.json``."""
    DIGEST_DIR_JSON.mkdir(parents=True, exist_ok=True)
    p = _state_file()
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(state, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _initial_job_state(job_type: str) -> dict[str, Any]:
    spec = _JOB_REGISTRY[job_type]
    return {
        "job_id": _job_id(job_type),
        "job_type": job_type,
        "schedule": {
            "kind": "fixed_interval",
            "interval_seconds": int(spec["default_interval_seconds"]),
        },
        "enabled": bool(spec["default_enabled"]),
        "risk_class": spec["risk_class"],
        "default_enabled": bool(spec["default_enabled"]),
        "needs_gh": bool(spec.get("needs_gh", False)),
        "last_run_at_utc": None,
        "next_run_after_utc": None,
        "last_status": STATUS_NOT_RUN,
        "last_result_summary": None,
        "consecutive_failures": 0,
        "blocked_reason": None,
        "audit_refs": [],
    }


def _hydrate_state() -> dict[str, dict[str, Any]]:
    """Merge persisted state with the canonical defaults so renames
    in the registry never desync the on-disk state."""
    persisted = _read_state()
    out: dict[str, dict[str, Any]] = {}
    for job_type in JOB_TYPES:
        base = _initial_job_state(job_type)
        if isinstance(persisted.get(job_type), dict):
            for key in (
                "enabled",
                "last_run_at_utc",
                "next_run_after_utc",
                "last_status",
                "last_result_summary",
                "consecutive_failures",
                "blocked_reason",
                "audit_refs",
            ):
                if key in persisted[job_type]:
                    base[key] = persisted[job_type][key]
            # Allow operator override of schedule via state file.
            if isinstance(persisted[job_type].get("schedule"), dict):
                base["schedule"] = persisted[job_type]["schedule"]
        out[job_type] = base
    return out


# ---------------------------------------------------------------------------
# Per-job supervisor
# ---------------------------------------------------------------------------


def _is_due(job_state: dict[str, Any], *, now: _dt.datetime | None = None) -> bool:
    if not job_state.get("enabled"):
        return False
    next_run = _parse_iso_utc(job_state.get("next_run_after_utc"))
    if next_run is None:
        return True  # never run before
    now_dt = now or _utcnow_dt()
    return now_dt >= next_run


def _supervise_job(
    job_type: str,
    *,
    state: dict[str, Any],
    enable_dependabot: bool = False,
) -> dict[str, Any]:
    """Run one job under the supervisor. Returns the updated job
    state dict. Never raises."""
    if job_type not in _JOB_REGISTRY:
        new_state = dict(state)
        new_state["last_run_at_utc"] = _utcnow()
        new_state["last_status"] = STATUS_BLOCKED
        new_state["last_result_summary"] = f"unknown_job_type: {job_type!r}"
        new_state["blocked_reason"] = "unknown_job_type"
        return new_state

    spec = _JOB_REGISTRY[job_type]

    # Disabled? -> skipped.
    if not state.get("enabled", False):
        new_state = dict(state)
        new_state["last_run_at_utc"] = _utcnow()
        new_state["last_status"] = STATUS_SKIPPED
        new_state["last_result_summary"] = "job is disabled in state.json"
        new_state["blocked_reason"] = None
        return _bump_next_run_after(new_state)

    # Dependabot opt-in gate.
    if job_type == JOB_DEPENDABOT_EXECUTE_SAFE and not enable_dependabot:
        new_state = dict(state)
        new_state["last_run_at_utc"] = _utcnow()
        new_state["last_status"] = STATUS_BLOCKED
        new_state["last_result_summary"] = (
            "dependabot execute-safe requires --enable-dependabot-execute-safe at the CLI"
        )
        new_state["blocked_reason"] = "missing_dependabot_cli_opt_in"
        return _bump_next_run_after(new_state)

    timeout = int(spec.get("timeout_seconds", DEFAULT_JOB_TIMEOUT_SECONDS))
    holder: dict[str, Any] = {}

    def _runner() -> None:
        try:
            holder["value"] = spec["executor"]()
        except BaseException as e:  # noqa: BLE001 - defensive fence
            holder["error"] = e

    t = threading.Thread(target=_runner, daemon=True)
    start = time.monotonic()
    t.start()
    t.join(timeout)
    duration_ms = int((time.monotonic() - start) * 1000)

    new_state = dict(state)
    new_state["last_run_at_utc"] = _utcnow()
    new_state["audit_refs"] = list(state.get("audit_refs") or [])

    if t.is_alive():
        new_state["last_status"] = STATUS_TIMEOUT
        new_state["last_result_summary"] = (
            f"timeout after {timeout}s (duration_ms={duration_ms})"
        )
        new_state["blocked_reason"] = None
        new_state["consecutive_failures"] = (
            int(state.get("consecutive_failures") or 0) + 1
        )
        return _bump_next_run_after(new_state)

    if "error" in holder:
        e = holder["error"]
        new_state["last_status"] = STATUS_FAILED
        new_state["last_result_summary"] = (
            f"{type(e).__name__}: {str(e)[:200]} (duration_ms={duration_ms})"
        )
        new_state["blocked_reason"] = None
        new_state["consecutive_failures"] = (
            int(state.get("consecutive_failures") or 0) + 1
        )
        return _bump_next_run_after(new_state)

    value = holder.get("value")
    if not isinstance(value, dict):
        new_state["last_status"] = STATUS_NOT_AVAILABLE
        new_state["last_result_summary"] = "executor did not return a dict"
        new_state["blocked_reason"] = None
        new_state["consecutive_failures"] = (
            int(state.get("consecutive_failures") or 0) + 1
        )
        return _bump_next_run_after(new_state)

    summary = str(value.get("summary") or "ok")
    # Sanitise summary against credential-value patterns even though
    # the supervised executor's own per-source guard already catches
    # them — defense in depth.
    for pat in _OUTER_CREDENTIAL_PATTERNS:
        if pat in summary:
            summary = "secret_redaction_failed"
            break

    new_state["last_status"] = STATUS_SUCCEEDED
    new_state["last_result_summary"] = (
        f"{summary} (duration_ms={duration_ms})"
    )[:480]
    new_state["blocked_reason"] = None
    new_state["consecutive_failures"] = 0
    return _bump_next_run_after(new_state)


def _bump_next_run_after(state: dict[str, Any]) -> dict[str, Any]:
    schedule = state.get("schedule") or {}
    interval = int(schedule.get("interval_seconds") or 900)
    interval = max(MIN_INTERVAL_SECONDS, min(interval, MAX_INTERVAL_SECONDS))
    next_run = _utcnow_dt() + _dt.timedelta(seconds=interval)
    out = dict(state)
    out["next_run_after_utc"] = next_run.isoformat().replace("+00:00", "Z")
    return out


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------


def _final_recommendation(jobs: list[dict[str, Any]]) -> str:
    failed = sum(1 for j in jobs if j["last_status"] in (STATUS_FAILED, STATUS_TIMEOUT))
    blocked = sum(1 for j in jobs if j["last_status"] == STATUS_BLOCKED)
    consecutive_max = max(
        (int(j.get("consecutive_failures") or 0) for j in jobs),
        default=0,
    )
    if consecutive_max >= 3:
        return f"runtime_halt_after_{consecutive_max}_consecutive_failures"
    if failed > 0:
        return f"degraded_failed_{failed}"
    if blocked > 0:
        return f"degraded_blocked_{blocked}"
    return "all_jobs_ok"


def collect_snapshot(
    *,
    mode: str = "list",
    iteration: int = 0,
    max_iterations: int = 1,
    interval_seconds: int | None = None,
    jobs_state: dict[str, dict[str, Any]] | None = None,
    actions_taken: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    state = jobs_state if jobs_state is not None else _hydrate_state()
    job_rows = [state[jt] for jt in JOB_TYPES]
    counts: dict[str, int] = {}
    for j in job_rows:
        s = j["last_status"]
        counts[s] = counts.get(s, 0) + 1

    snap = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "recurring_maintenance_digest",
        "module_version": MODULE_VERSION,
        "generated_at_utc": _utcnow(),
        "mode": mode,
        "iteration": iteration,
        "max_iterations": max_iterations,
        "interval_seconds": interval_seconds,
        "next_run_after_utc": (
            (
                (_utcnow_dt() + _dt.timedelta(seconds=interval_seconds))
                .isoformat()
                .replace("+00:00", "Z")
            )
            if (mode == "loop" and interval_seconds is not None)
            else None
        ),
        "safe_to_execute": False,
        "jobs": job_rows,
        "actions_taken": list(actions_taken or []),
        "counts": {"by_status": counts, "total": len(job_rows)},
        "final_recommendation": _final_recommendation(job_rows),
        "policy": {
            "module_version": _approval_policy.MODULE_VERSION,
            "schema_version": _approval_policy.SCHEMA_VERSION,
            "high_or_unknown_is_executable": False,
            "execute_safe_requires_two_layer_opt_in": True,
        },
    }
    _assert_no_credential_values(snap)
    return snap


def write_outputs(snapshot: dict[str, Any]) -> dict[str, str]:
    """Atomic write of latest.json + timestamped copy + history append."""
    DIGEST_DIR_JSON.mkdir(parents=True, exist_ok=True)
    ts = snapshot["generated_at_utc"].replace(":", "-")
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
        "json_now": _rel(json_now),
        "json_latest": _rel(json_latest),
        "history_jsonl": _rel(history),
    }


# ---------------------------------------------------------------------------
# Public driver functions
# ---------------------------------------------------------------------------


def list_jobs() -> dict[str, Any]:
    """Return the current state of all jobs (no execution)."""
    return collect_snapshot(mode="list")


def plan(*, now: _dt.datetime | None = None) -> dict[str, Any]:
    """Return a snapshot annotated with which jobs are due RIGHT
    NOW. Does not mutate state."""
    state = _hydrate_state()
    due = []
    for job_type in JOB_TYPES:
        if _is_due(state[job_type], now=now):
            due.append(job_type)
    snap = collect_snapshot(mode="plan", jobs_state=state)
    snap["due_now"] = due
    return snap


def run_one_job(
    job_type: str,
    *,
    enable_dependabot: bool = False,
    persist: bool = True,
) -> dict[str, Any]:
    """Run a single job by type. Returns the resulting snapshot."""
    state = _hydrate_state()
    if job_type not in _JOB_REGISTRY:
        snap = collect_snapshot(mode="run_once", jobs_state=state)
        snap["actions_taken"].append(
            {
                "kind": "refused",
                "target": job_type,
                "outcome": "blocked",
                "reason": f"unknown_job_type: {job_type!r}",
            }
        )
        if persist:
            write_outputs(snap)
        return snap

    new_job_state = _supervise_job(
        job_type, state=state[job_type], enable_dependabot=enable_dependabot
    )
    state[job_type] = new_job_state
    _write_state(state)
    snap = collect_snapshot(mode="run_once", jobs_state=state)
    snap["actions_taken"].append(
        {
            "kind": "run_job",
            "target": job_type,
            "outcome": new_job_state["last_status"],
            "reason": new_job_state["last_result_summary"],
        }
    )
    if persist:
        write_outputs(snap)
    return snap


def run_due_once(
    *,
    enable_dependabot: bool = False,
    persist: bool = True,
    now: _dt.datetime | None = None,
) -> dict[str, Any]:
    """Run every job whose ``next_run_after_utc <= now`` exactly
    once. Returns the resulting snapshot."""
    state = _hydrate_state()
    actions: list[dict[str, Any]] = []
    for job_type in JOB_TYPES:
        if not _is_due(state[job_type], now=now):
            continue
        new_job_state = _supervise_job(
            job_type, state=state[job_type], enable_dependabot=enable_dependabot
        )
        state[job_type] = new_job_state
        actions.append(
            {
                "kind": "run_job",
                "target": job_type,
                "outcome": new_job_state["last_status"],
                "reason": new_job_state["last_result_summary"],
            }
        )
    _write_state(state)
    snap = collect_snapshot(mode="run_due_once", jobs_state=state, actions_taken=actions)
    if persist:
        write_outputs(snap)
    return snap


def run_loop(
    *,
    interval_seconds: int,
    max_iterations: int,
    enable_dependabot: bool = False,
    persist: bool = True,
    sleeper: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Bounded loop. Runs ``run_due_once`` up to ``max_iterations``
    times with ``interval_seconds`` between iterations. Both bounds
    are clamped."""
    iters = max(1, min(max_iterations, MAX_ITERATIONS_LIMIT))
    interval = max(MIN_INTERVAL_SECONDS, min(interval_seconds, MAX_INTERVAL_SECONDS))
    snaps: list[dict[str, Any]] = []
    try:
        for i in range(iters):
            snap = run_due_once(enable_dependabot=enable_dependabot, persist=persist)
            snap["iteration"] = i
            snap["max_iterations"] = iters
            snap["interval_seconds"] = interval
            snap["mode"] = "loop"
            snaps.append(snap)
            if i < iters - 1:
                sleeper(interval)
    except KeyboardInterrupt:
        pass
    return snaps


def read_latest_snapshot() -> dict[str, Any] | None:
    p = DIGEST_DIR_JSON / "latest.json"
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.recurring_maintenance",
        description=(
            "Recurring safe-maintenance scheduler. Runs a closed set "
            "of low-risk maintenance jobs at fixed intervals. The "
            "Dependabot execute-safe job is disabled by default and "
            "requires --enable-dependabot-execute-safe at the CLI."
        ),
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--list-jobs", action="store_true", help="List jobs and exit.")
    mode.add_argument("--plan", action="store_true", help="Print which jobs are due now (no execution).")
    mode.add_argument("--run-once", type=str, default=None, help="Run a single job by type.")
    mode.add_argument("--run-due-once", action="store_true", help="Run every job whose next_run_after_utc <= now, once.")
    mode.add_argument("--loop", action="store_true", help="Bounded loop over run-due-once.")
    mode.add_argument("--status", action="store_true", help="Print latest.json contents and exit.")
    p.add_argument(
        "--interval-seconds",
        type=int,
        default=300,
        help=f"Loop interval (clamped to [{MIN_INTERVAL_SECONDS}, {MAX_INTERVAL_SECONDS}]).",
    )
    p.add_argument(
        "--max-iterations",
        type=int,
        default=1,
        help=f"Max iterations in --loop mode (clamped to {MAX_ITERATIONS_LIMIT}).",
    )
    p.add_argument(
        "--enable-dependabot-execute-safe",
        action="store_true",
        help=(
            "Explicit opt-in to running the Dependabot LOW/MEDIUM "
            "execute-safe job. Without this flag the job is always "
            "skipped, regardless of its enabled flag in state.json."
        ),
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Do not persist the JSON digest (stdout only).",
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent (0 for compact).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    indent = args.indent if args.indent and args.indent > 0 else None

    if args.status:
        snap = read_latest_snapshot()
        if snap is None:
            sys.stdout.write(
                json.dumps(
                    {"status": "not_available", "reason": "no latest.json"},
                    indent=indent,
                )
                + "\n"
            )
            return 0
        sys.stdout.write(json.dumps(snap, indent=indent, sort_keys=True) + "\n")
        return 0

    if args.list_jobs:
        snap = list_jobs()
        sys.stdout.write(json.dumps(snap, indent=indent, sort_keys=True) + "\n")
        return 0

    if args.plan:
        snap = plan()
        sys.stdout.write(json.dumps(snap, indent=indent, sort_keys=True) + "\n")
        return 0

    if args.run_once is not None:
        snap = run_one_job(
            args.run_once,
            enable_dependabot=args.enable_dependabot_execute_safe,
            persist=not args.no_write,
        )
        sys.stdout.write(json.dumps(snap, indent=indent, sort_keys=True) + "\n")
        return 0

    if args.run_due_once:
        snap = run_due_once(
            enable_dependabot=args.enable_dependabot_execute_safe,
            persist=not args.no_write,
        )
        sys.stdout.write(json.dumps(snap, indent=indent, sort_keys=True) + "\n")
        return 0

    if args.loop:
        snaps = run_loop(
            interval_seconds=args.interval_seconds,
            max_iterations=args.max_iterations,
            enable_dependabot=args.enable_dependabot_execute_safe,
            persist=not args.no_write,
        )
        last = snaps[-1] if snaps else {}
        sys.stdout.write(json.dumps(last, indent=indent, sort_keys=True) + "\n")
        return 0

    # Default: --list-jobs.
    snap = list_jobs()
    sys.stdout.write(json.dumps(snap, indent=indent, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
