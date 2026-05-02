"""Execute-safe controls catalog + planner + (small) executor.

This module is the **typed, whitelisted, auditable** action layer for
the autonomous development loop. v3.15.15.21 introduces it with four
allow-listed action types — and **only** four. The executor refuses
any unknown action type, refuses any free-form command string,
refuses HIGH-risk approvals, and refuses to run when the working
tree is dirty (excluding known runtime artifacts).

Hard guarantees (enforced by code AND tests)
--------------------------------------------

* Stdlib-only.
* The action catalog is a closed enum — unknown action types are
  refused at the boundary.
* No action accepts a free-form command string.
* No action mutates ``.claude/**``, frozen contracts, live / paper /
  shadow / risk paths, or any governance-protected file.
* No action wires additional routes beyond the three explicitly
  approved GET-only modules (which were wired in
  ``dashboard/dashboard.py`` separately by the operator).
* Eligibility checks are pure / deterministic — same input always
  produces the same eligibility verdict.
* HIGH-risk action are NEVER eligible in this release.
* Frozen-contract sha256 is captured before AND after every
  executable action; a mismatch is a critical failure.
* The executor never invokes ``git push``, ``--force``, ``--admin``,
  or any destructive shell command.
* When subprocess is needed, the argv list is constructed entirely
  from constants in this module — no operator-supplied tokens.
* Every subprocess invocation has a bounded timeout.

Allowed action classes (closed list)
------------------------------------

1. ``refresh_github_pr_lifecycle_dry_run`` — calls
   ``python -m reporting.github_pr_lifecycle --mode dry-run``.
2. ``refresh_proposal_queue_dry_run`` — calls
   ``python -m reporting.proposal_queue --mode dry-run``.
3. ``refresh_approval_inbox_dry_run`` — calls
   ``python -m reporting.approval_inbox --mode dry-run``.
4. ``run_dependabot_execute_safe_low_medium`` — calls
   ``python -m reporting.github_pr_lifecycle --mode execute-safe``.
   The PR-lifecycle module already encodes the LOW/MEDIUM-only
   merge policy and the HIGH-blocked guard; this action is just a
   pass-through wrapper.

CLI
---

::

    python -m reporting.execute_safe_controls --mode dry-run

Stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
MODULE_VERSION: str = "v3.15.15.21"
SCHEMA_VERSION: int = 1

DIGEST_DIR_JSON: Path = REPO_ROOT / "logs" / "execute_safe_controls"


# ---------------------------------------------------------------------------
# Action catalog (closed list)
# ---------------------------------------------------------------------------


ACTION_REFRESH_PR_LIFECYCLE: str = "refresh_github_pr_lifecycle_dry_run"
ACTION_REFRESH_PROPOSAL_QUEUE: str = "refresh_proposal_queue_dry_run"
ACTION_REFRESH_APPROVAL_INBOX: str = "refresh_approval_inbox_dry_run"
ACTION_RUN_DEPENDABOT_EXECUTE_SAFE: str = "run_dependabot_execute_safe_low_medium"

ACTION_TYPES: tuple[str, ...] = (
    ACTION_REFRESH_PR_LIFECYCLE,
    ACTION_REFRESH_PROPOSAL_QUEUE,
    ACTION_REFRESH_APPROVAL_INBOX,
    ACTION_RUN_DEPENDABOT_EXECUTE_SAFE,
)

# Risk taxonomy — kept narrow on purpose. Anything HIGH is never
# eligible in this release.
RISK_LOW: str = "LOW"
RISK_MEDIUM: str = "MEDIUM"
RISK_HIGH: str = "HIGH"

# Eligibility verdicts.
ELIG_ELIGIBLE: str = "eligible"
ELIG_INELIGIBLE: str = "ineligible"
ELIG_BLOCKED: str = "blocked"
ELIG_UNKNOWN: str = "unknown"

# Result statuses.
RESULT_NOT_RUN: str = "not_run"
RESULT_RUNNING: str = "running"
RESULT_SUCCEEDED: str = "succeeded"
RESULT_FAILED: str = "failed"
RESULT_BLOCKED: str = "blocked"

# Per-action argv recipes. Each tuple is the COMPLETE argv (no
# operator tokens). The executor refuses to run anything not in
# this map.
_ACTION_ARGV: dict[str, tuple[str, ...]] = {
    ACTION_REFRESH_PR_LIFECYCLE: (
        sys.executable,
        "-m",
        "reporting.github_pr_lifecycle",
        "--mode",
        "dry-run",
    ),
    ACTION_REFRESH_PROPOSAL_QUEUE: (
        sys.executable,
        "-m",
        "reporting.proposal_queue",
        "--mode",
        "dry-run",
    ),
    ACTION_REFRESH_APPROVAL_INBOX: (
        sys.executable,
        "-m",
        "reporting.approval_inbox",
        "--mode",
        "dry-run",
    ),
    ACTION_RUN_DEPENDABOT_EXECUTE_SAFE: (
        sys.executable,
        "-m",
        "reporting.github_pr_lifecycle",
        "--mode",
        "execute-safe",
    ),
}

# Per-action output artifact paths (best-effort; the underlying
# module is the source of truth).
_ACTION_OUTPUT: dict[str, str] = {
    ACTION_REFRESH_PR_LIFECYCLE: "logs/github_pr_lifecycle/latest.json",
    ACTION_REFRESH_PROPOSAL_QUEUE: "logs/proposal_queue/latest.json",
    ACTION_REFRESH_APPROVAL_INBOX: "logs/approval_inbox/latest.json",
    ACTION_RUN_DEPENDABOT_EXECUTE_SAFE: "logs/github_pr_lifecycle/latest.json",
}

# Per-action timeouts (seconds).
_ACTION_TIMEOUTS: dict[str, int] = {
    ACTION_REFRESH_PR_LIFECYCLE: 60,
    ACTION_REFRESH_PROPOSAL_QUEUE: 60,
    ACTION_REFRESH_APPROVAL_INBOX: 60,
    ACTION_RUN_DEPENDABOT_EXECUTE_SAFE: 600,
}

# Risk class per action.
_ACTION_RISK: dict[str, str] = {
    ACTION_REFRESH_PR_LIFECYCLE: RISK_LOW,
    ACTION_REFRESH_PROPOSAL_QUEUE: RISK_LOW,
    ACTION_REFRESH_APPROVAL_INBOX: RISK_LOW,
    # Dependabot execute-safe runs gh pr merge for LOW/MEDIUM PRs;
    # the action itself is MEDIUM (the PR-lifecycle module enforces
    # the HIGH-blocked guard internally).
    ACTION_RUN_DEPENDABOT_EXECUTE_SAFE: RISK_MEDIUM,
}

# Whether the action depends on a working ``gh`` provider. Used by
# the eligibility planner to mark gh-dependent actions blocked when
# ``gh`` is missing or unauthenticated.
_ACTION_NEEDS_GH: dict[str, bool] = {
    ACTION_REFRESH_PR_LIFECYCLE: True,
    ACTION_REFRESH_PROPOSAL_QUEUE: False,
    ACTION_REFRESH_APPROVAL_INBOX: False,
    ACTION_RUN_DEPENDABOT_EXECUTE_SAFE: True,
}


# Frozen contracts — must be byte-identical before and after every
# executable action.
FROZEN_CONTRACTS: tuple[str, ...] = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)


# Universal forbidden side-effect list, surfaced on every action so
# the operator can rely on it.
_FORBIDDEN_SIDE_EFFECTS: tuple[str, ...] = (
    "git push origin main",
    "git push --force",
    "git push --force-with-lease",
    "gh pr merge --admin",
    "edit .claude/**",
    "edit frozen contracts",
    "edit automation/live_gate.py",
    "modify VERSION",
    "execute live broker",
    "place real-money order",
    "arbitrary shell command",
    "free-form operator command string",
)

# Per-action allowed side effects (positive list).
_ACTION_ALLOWED_SIDE_EFFECTS: dict[str, tuple[str, ...]] = {
    ACTION_REFRESH_PR_LIFECYCLE: (
        "read GitHub PR list via gh (read-only)",
        "write logs/github_pr_lifecycle/latest.json",
    ),
    ACTION_REFRESH_PROPOSAL_QUEUE: (
        "read docs/roadmap, docs/backlog, docs/spillovers (read-only)",
        "write logs/proposal_queue/latest.json",
    ),
    ACTION_REFRESH_APPROVAL_INBOX: (
        "read upstream JSON artifacts (read-only)",
        "write logs/approval_inbox/latest.json",
    ),
    ACTION_RUN_DEPENDABOT_EXECUTE_SAFE: (
        "post `@dependabot rebase` comment on BEHIND Dependabot PRs",
        "squash-merge LOW/MEDIUM Dependabot PRs that pass every gate",
        "write logs/github_pr_lifecycle/latest.json",
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _action_id(action_type: str, generated_at: str) -> str:
    raw = f"{action_type}|{generated_at}".encode("utf-8")
    return "a_" + hashlib.sha256(raw).hexdigest()[:8]


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return "missing"
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except OSError:
        return "missing"
    return h.hexdigest()


def _frozen_hashes() -> dict[str, str]:
    return {rel: _file_sha256(REPO_ROOT / rel) for rel in FROZEN_CONTRACTS}


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Working-tree cleanliness
# ---------------------------------------------------------------------------


# Tracked files that are allowed to be dirty without blocking the
# planner (none currently). Untracked paths are matched against
# ``KNOWN_RUNTIME_UNTRACKED`` below.
KNOWN_RUNTIME_UNTRACKED: tuple[str, ...] = (
    "research/discovery_sprints/",
    # Stale tsc-emit artifacts are gitignored under frontend/.gitignore
    # since v3.15.15.20, but pre-existing checkouts may still surface
    # them. They are read-only artifacts.
    "frontend/src/",
)


def _git_status_safe() -> tuple[bool, list[str], str | None]:
    """Return ``(is_clean_for_planner, dirty_lines, error)``.

    ``is_clean_for_planner`` is True iff every dirty entry either
    represents a TRACKED change (which always blocks) or matches a
    known-runtime untracked prefix.
    """
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return (False, [], f"git_status_error: {type(e).__name__}")
    if r.returncode != 0:
        return (False, [], f"git_status_rc={r.returncode}")
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    blocking: list[str] = []
    for ln in lines:
        # First two chars are status; chars 3..end are the path.
        flag = ln[:2]
        path = ln[3:].strip().replace("\\", "/")
        if flag == "??":
            # Untracked: only block if NOT in known-runtime list.
            if not any(path.startswith(p) for p in KNOWN_RUNTIME_UNTRACKED):
                blocking.append(ln)
        else:
            # Anything tracked-and-modified is blocking.
            blocking.append(ln)
    return (not blocking, lines, None)


# ---------------------------------------------------------------------------
# gh provider probe (delegated to github_pr_lifecycle when available)
# ---------------------------------------------------------------------------


def _gh_provider_status() -> dict[str, Any]:
    """Best-effort gh probe. Returns the same shape as
    ``github_pr_lifecycle.gh_provider_status``."""
    try:
        from reporting.github_pr_lifecycle import gh_provider_status

        return gh_provider_status()
    except Exception as e:  # noqa: BLE001
        return {
            "status": "not_available",
            "reason": f"gh_provider_status_error: {type(e).__name__}",
            "gh_path": None,
            "version": None,
            "account": None,
            "repo": None,
        }


# ---------------------------------------------------------------------------
# Eligibility planner
# ---------------------------------------------------------------------------


def plan_action(
    action_type: str,
    *,
    git_clean: bool,
    git_dirty_lines: list[str],
    gh_status: dict[str, Any],
) -> dict[str, Any]:
    """Pure function: return an Action record with eligibility.

    Caller supplies the environmental signals (git cleanliness, gh
    provider). The planner does no I/O so unit tests can drive it
    deterministically.
    """
    if action_type not in ACTION_TYPES:
        return _action_record(
            action_type=action_type,
            risk=RISK_HIGH,
            eligibility=ELIG_INELIGIBLE,
            blocked_reason=f"unknown_action_type: {action_type!r}",
            allowed=("none — unknown action type",),
        )

    risk = _ACTION_RISK[action_type]

    # Hard rule: HIGH actions are never eligible in v3.15.15.21.
    if risk == RISK_HIGH:
        return _action_record(
            action_type=action_type,
            risk=risk,
            eligibility=ELIG_BLOCKED,
            blocked_reason="HIGH-risk actions are never executable in v3.15.15.21",
            allowed=_ACTION_ALLOWED_SIDE_EFFECTS.get(action_type, ()),
        )

    if not git_clean:
        return _action_record(
            action_type=action_type,
            risk=risk,
            eligibility=ELIG_BLOCKED,
            blocked_reason=(
                "working tree has tracked or unknown-untracked changes; "
                f"{len(git_dirty_lines)} dirty lines"
            ),
            allowed=_ACTION_ALLOWED_SIDE_EFFECTS.get(action_type, ()),
        )

    if _ACTION_NEEDS_GH.get(action_type, False):
        gh_state = gh_status.get("status")
        if gh_state == "not_available":
            return _action_record(
                action_type=action_type,
                risk=risk,
                eligibility=ELIG_BLOCKED,
                blocked_reason="gh CLI is not available; install gh first",
                allowed=_ACTION_ALLOWED_SIDE_EFFECTS.get(action_type, ()),
            )
        if gh_state == "not_authenticated":
            return _action_record(
                action_type=action_type,
                risk=risk,
                eligibility=ELIG_BLOCKED,
                blocked_reason="gh CLI is not authenticated; run gh auth login",
                allowed=_ACTION_ALLOWED_SIDE_EFFECTS.get(action_type, ()),
            )
        if gh_state in (None, "", "unknown"):
            return _action_record(
                action_type=action_type,
                risk=risk,
                eligibility=ELIG_UNKNOWN,
                blocked_reason="gh provider status is unknown; refusing to act",
                allowed=_ACTION_ALLOWED_SIDE_EFFECTS.get(action_type, ()),
            )
        if gh_state != "available":
            return _action_record(
                action_type=action_type,
                risk=risk,
                eligibility=ELIG_BLOCKED,
                blocked_reason=f"gh provider status={gh_state!r}; only 'available' is acceptable",
                allowed=_ACTION_ALLOWED_SIDE_EFFECTS.get(action_type, ()),
            )

    return _action_record(
        action_type=action_type,
        risk=risk,
        eligibility=ELIG_ELIGIBLE,
        blocked_reason=None,
        allowed=_ACTION_ALLOWED_SIDE_EFFECTS.get(action_type, ()),
    )


def _action_record(
    *,
    action_type: str,
    risk: str,
    eligibility: str,
    blocked_reason: str | None,
    allowed: Iterable[str],
) -> dict[str, Any]:
    generated_at = _utcnow()
    return {
        "action_id": _action_id(action_type, generated_at),
        "action_type": action_type,
        "title": _title_for(action_type),
        "summary": _summary_for(action_type),
        "risk_class": risk,
        "eligibility": eligibility,
        "blocked_reason": blocked_reason,
        "required_confirmations": _required_confirmations(action_type),
        "forbidden_side_effects": list(_FORBIDDEN_SIDE_EFFECTS),
        "allowed_side_effects": list(allowed),
        "source_refs": _source_refs(action_type),
        "created_at": generated_at,
        "stale_after": None,
        "audit_event_id": None,
        "result_status": RESULT_NOT_RUN,
        "result_summary": None,
        "output_artifact_path": _ACTION_OUTPUT.get(action_type),
    }


def _title_for(action_type: str) -> str:
    return {
        ACTION_REFRESH_PR_LIFECYCLE: "Refresh GitHub PR lifecycle digest (dry-run)",
        ACTION_REFRESH_PROPOSAL_QUEUE: "Refresh proposal queue digest (dry-run)",
        ACTION_REFRESH_APPROVAL_INBOX: "Refresh approval inbox digest (dry-run)",
        ACTION_RUN_DEPENDABOT_EXECUTE_SAFE: "Run Dependabot execute-safe (LOW / MEDIUM only)",
    }.get(action_type, action_type)


def _summary_for(action_type: str) -> str:
    return {
        ACTION_REFRESH_PR_LIFECYCLE: (
            "Calls reporting.github_pr_lifecycle in dry-run mode and "
            "writes logs/github_pr_lifecycle/latest.json."
        ),
        ACTION_REFRESH_PROPOSAL_QUEUE: (
            "Calls reporting.proposal_queue in dry-run mode and writes "
            "logs/proposal_queue/latest.json."
        ),
        ACTION_REFRESH_APPROVAL_INBOX: (
            "Calls reporting.approval_inbox in dry-run mode and writes "
            "logs/approval_inbox/latest.json."
        ),
        ACTION_RUN_DEPENDABOT_EXECUTE_SAFE: (
            "Calls reporting.github_pr_lifecycle --mode execute-safe. The "
            "lifecycle module's internal policy posts @dependabot rebase "
            "on BEHIND PRs and squash-merges LOW/MEDIUM Dependabot PRs "
            "that pass every gate. HIGH PRs remain blocked_high_risk."
        ),
    }.get(action_type, "")


def _required_confirmations(action_type: str) -> list[str]:
    if action_type == ACTION_RUN_DEPENDABOT_EXECUTE_SAFE:
        return [
            "operator types --confirm dependabot-execute-safe at the CLI",
            "operator confirms the local baseline (governance_lint + smoke + frozen hashes) is green",
        ]
    return ["none — refresh actions only read upstream state"]


def _source_refs(action_type: str) -> list[str]:
    base = ["docs/governance/execute_safe_controls.md"]
    if action_type == ACTION_REFRESH_PR_LIFECYCLE or action_type == ACTION_RUN_DEPENDABOT_EXECUTE_SAFE:
        base.append("docs/governance/dependabot_cleanup_playbook.md")
        base.append("docs/governance/github_pr_lifecycle_integration.md")
    if action_type == ACTION_REFRESH_PROPOSAL_QUEUE:
        base.append("docs/governance/roadmap_proposal_queue.md")
    if action_type == ACTION_REFRESH_APPROVAL_INBOX:
        base.append("docs/governance/approval_exception_inbox.md")
    return base


# ---------------------------------------------------------------------------
# Catalog snapshot
# ---------------------------------------------------------------------------


def collect_catalog(
    *,
    git_status: tuple[bool, list[str], str | None] | None = None,
    gh_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the full catalog snapshot. Each action is planned with
    the same environmental signals so the operator sees a consistent
    eligibility verdict across the page."""
    if git_status is None:
        git_clean, dirty_lines, _ = _git_status_safe()
    else:
        git_clean, dirty_lines, _ = git_status
    gh = gh_status if gh_status is not None else _gh_provider_status()

    actions: list[dict[str, Any]] = []
    for at in ACTION_TYPES:
        actions.append(
            plan_action(
                at,
                git_clean=git_clean,
                git_dirty_lines=dirty_lines,
                gh_status=gh,
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "execute_safe_controls_catalog",
        "module_version": MODULE_VERSION,
        "generated_at_utc": _utcnow(),
        "git_clean": git_clean,
        "git_dirty_count": len(dirty_lines),
        "gh_provider": gh,
        "frozen_hashes": _frozen_hashes(),
        "actions": actions,
        "counts": _counts(actions),
    }


def _counts(actions: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "total": len(actions),
        "by_eligibility": {},
        "by_risk_class": {},
    }
    for a in actions:
        e = a.get("eligibility", "unknown")
        r = a.get("risk_class", "UNKNOWN")
        out["by_eligibility"][e] = out["by_eligibility"].get(e, 0) + 1
        out["by_risk_class"][r] = out["by_risk_class"].get(r, 0) + 1
    return out


# ---------------------------------------------------------------------------
# Executor (small, fixed-command-only)
# ---------------------------------------------------------------------------


def execute_action(
    action_type: str,
    *,
    confirm_token: str | None = None,
    git_status: tuple[bool, list[str], str | None] | None = None,
    gh_status: dict[str, Any] | None = None,
    runner: Any = None,
) -> dict[str, Any]:
    """Run one whitelisted action.

    Hard guarantees:
      * Refuses any action_type not in :data:`ACTION_TYPES`.
      * Refuses HIGH-risk actions outright.
      * Refuses if the working tree is not clean (excluding known
        runtime artifacts).
      * Refuses gh-dependent actions when gh is unavailable /
        unauthenticated / unknown.
      * Captures frozen-contract sha256 BEFORE and AFTER the
        subprocess; mismatch is a critical failure.
      * Builds argv entirely from the constants in
        :data:`_ACTION_ARGV` — no operator-supplied tokens.
      * Subprocess has a per-action timeout.
      * For ``run_dependabot_execute_safe_low_medium``, requires the
        operator to pass the literal confirm token
        ``"dependabot-execute-safe"`` so a stray invocation cannot
        accidentally execute.
    """
    plan = plan_action(
        action_type,
        git_clean=(git_status[0] if git_status is not None else _git_status_safe()[0]),
        git_dirty_lines=(git_status[1] if git_status is not None else _git_status_safe()[1]),
        gh_status=(gh_status if gh_status is not None else _gh_provider_status()),
    )
    if plan["eligibility"] != ELIG_ELIGIBLE:
        return _executed_record(plan, RESULT_BLOCKED, plan["blocked_reason"] or "ineligible")

    # Action-specific confirmation.
    if action_type == ACTION_RUN_DEPENDABOT_EXECUTE_SAFE:
        if confirm_token != "dependabot-execute-safe":
            return _executed_record(
                plan,
                RESULT_BLOCKED,
                "missing or wrong --confirm token for dependabot execute-safe",
            )

    # Snapshot frozen hashes before.
    frozen_before = _frozen_hashes()

    argv = _ACTION_ARGV.get(action_type)
    timeout = _ACTION_TIMEOUTS.get(action_type, 60)
    if argv is None:  # defense in depth — should be impossible
        return _executed_record(plan, RESULT_BLOCKED, "no argv recipe for action")

    if runner is None:
        runner = _default_runner

    try:
        rc, stdout, stderr = runner(argv, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return _executed_record(plan, RESULT_FAILED, f"runner_error: {type(e).__name__}")

    # Snapshot frozen hashes after.
    frozen_after = _frozen_hashes()
    if frozen_after != frozen_before:
        return _executed_record(
            plan,
            RESULT_FAILED,
            "FROZEN-CONTRACT DRIFT: sha256 changed during action execution; investigate before any further action",
            extra={
                "frozen_before": frozen_before,
                "frozen_after": frozen_after,
                "rc": rc,
            },
        )

    if rc != 0:
        return _executed_record(
            plan,
            RESULT_FAILED,
            f"subprocess exit code {rc}; stderr (truncated): {(stderr or '').strip()[:300]}",
            extra={"rc": rc, "stdout_chars": len(stdout or ""), "stderr_chars": len(stderr or "")},
        )

    return _executed_record(
        plan,
        RESULT_SUCCEEDED,
        f"action {action_type!r} completed successfully",
        extra={"rc": rc, "stdout_chars": len(stdout or ""), "stderr_chars": len(stderr or "")},
    )


def _executed_record(
    plan: dict[str, Any],
    status: str,
    summary: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(plan)
    out["result_status"] = status
    out["result_summary"] = summary
    if extra:
        out.setdefault("evidence", {}).update(extra)
    return out


def _default_runner(argv: tuple[str, ...], *, timeout: int) -> tuple[int, str, str]:
    """Run ``argv`` with a wall-clock timeout. Returns
    ``(rc, stdout, stderr)``. Pure subprocess wrapper — caller has
    already validated the argv recipe."""
    try:
        r = subprocess.run(
            list(argv),
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return (-1, "", f"timeout: {timeout}s")
    return (r.returncode, r.stdout or "", r.stderr or "")


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def write_outputs(snapshot: dict[str, Any]) -> dict[str, str]:
    DIGEST_DIR_JSON.mkdir(parents=True, exist_ok=True)
    ts = snapshot["generated_at_utc"].replace(":", "-")
    json_now = DIGEST_DIR_JSON / f"{ts}.json"
    json_latest = DIGEST_DIR_JSON / "latest.json"
    payload = json.dumps(snapshot, sort_keys=True, indent=2)
    json_now.write_text(payload, encoding="utf-8")
    json_latest.write_text(payload, encoding="utf-8")
    return {
        "json_now": _rel(json_now),
        "json_latest": _rel(json_latest),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.execute_safe_controls",
        description=(
            "Execute-safe controls: typed, whitelisted, auditable "
            "actions only. Default mode dry-run emits the catalog. "
            "--action runs one whitelisted action with safety gates."
        ),
    )
    p.add_argument(
        "--mode",
        choices=["dry-run"],
        default="dry-run",
        help="Catalog-emit mode (default).",
    )
    p.add_argument(
        "--action",
        type=str,
        default=None,
        choices=list(ACTION_TYPES),
        help="Whitelisted action to run. If omitted, only the catalog is emitted.",
    )
    p.add_argument(
        "--confirm",
        type=str,
        default=None,
        help=(
            "Confirmation token for actions that require one "
            "(currently: run_dependabot_execute_safe_low_medium)."
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
    snap = collect_catalog()
    if args.action is not None:
        result = execute_action(args.action, confirm_token=args.confirm)
        snap["executed"] = result
    if not args.no_write:
        write_outputs(snap)
    indent = args.indent if args.indent and args.indent > 0 else None
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
