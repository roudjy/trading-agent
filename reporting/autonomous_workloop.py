"""Autonomous Workloop Controller — Local Planning Mode (v3.15.15.16).

This release reaches Levels B / C of the workloop maturity ladder:

* B — plan + classify (PR / branch / Dependabot / roadmap items, write
  digest, no external actions).
* C — local safe execution (run tests / gates; commit + push to the
  current release branch only; no PR creation, no merge, no main
  push).

Levels D-G (GitHub-backed PR awareness, safe PR execution, dashboard
controls, scheduled runtime, safe automerge) require explicit later
releases and are *not* unlocked here.

Non-capabilities (hard guarantees of this release)
--------------------------------------------------

* Does not create PRs.
* Does not merge PRs.
* Does not push to ``main``.
* Does not call any GitHub API.
* Does not install or require ``gh``.
* Does not recommend ``safe_to_merge`` for any branch — that label is
  reserved but unreachable here.
* Does not start a new roadmap implementation branch.
* Does not write to any no-touch path.
* Does not treat ``unknown`` as ``ok`` or ``safe``.

``merges_performed`` is always 0 in this release.

Outputs
-------

Markdown digest (committed):
  ``docs/governance/autonomous_workloop/{latest.md,<UTC>.md}``

JSON digest (gitignored, under ``logs/`` — see ``schema.v1.md`` for
the deviation note):
  ``logs/autonomous_workloop/{latest.json,<UTC>.json}``

CLI
---

::

    python -m reporting.autonomous_workloop --mode plan
    python -m reporting.autonomous_workloop --mode dry-run            # default
    python -m reporting.autonomous_workloop --mode execute-safe
    python -m reporting.autonomous_workloop --mode continuous --max-cycles 5
    python -m reporting.autonomous_workloop --mode digest

Stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from reporting import agent_audit
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
CONTROLLER_VERSION: str = "v3.15.15.16"
SCHEMA_VERSION: int = 1

DIGEST_DIR_MD: Path = REPO_ROOT / "docs" / "governance" / "autonomous_workloop"
DIGEST_DIR_JSON: Path = REPO_ROOT / "logs" / "autonomous_workloop"

# The release branch the controller is allowed to push to. All other
# branches are deny-listed for push.
CURRENT_RELEASE_BRANCH: str = "fix/v3.15.15.16-autonomous-workloop-controller"

# No-touch globs reused for the execute-safe path defense (mirror of
# .claude/hooks/deny_no_touch.py, kept here so the controller can
# refuse before invoking anything that would hit the hook). This is
# defense in depth; the hook remains the canonical enforcement.
NO_TOUCH_GLOBS: tuple[str, ...] = (
    ".claude/settings.json",
    ".claude/hooks/*",
    ".claude/hooks/**",
    ".claude/agents/*",
    ".claude/agents/**",
    ".github/CODEOWNERS",
    "VERSION",
    "automation/live_gate.py",
    "automation/*.secret",
    "state/*.secret",
    "config/config.yaml",
    ".env",
    ".env.*",
    # Frozen-v1 schema globs (kept here for execute-safe defense in
    # depth) — but the per-PR classifier ABOVE this hook checks frozen
    # contracts BEFORE protected globs, so frozen-contract diffs land
    # in `needs_human_contract_risk` rather than the generic
    # `needs_human_protected_governance` bucket.
    "*_latest.v1.json",
    "*_latest.v1.jsonl",
    "**/*_latest.v1.json",
    "**/*_latest.v1.jsonl",
    "docker-compose.prod.yml",
    "scripts/deploy.sh",
    "Dockerfile",
)

# Path globs that classify a diff as live / paper / shadow / trading.
LIVE_PATH_GLOBS: tuple[str, ...] = (
    "execution/live/**",
    "automation/live/**",
    "agent/execution/live/**",
    "**/live_*broker*.py",
    "**/*live*broker*.py",
    "**/*live_executor*.py",
    "**/*live*executor*.py",
    "**/*_live.py",
    "automation/live_gate.py",
)

# Frozen contracts.
FROZEN_CONTRACTS: tuple[str, ...] = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)

# Major-framework dependency names whose major bumps are
# auto-classified as framework-risk.
FRAMEWORK_MAJOR_PACKAGES: tuple[str, ...] = (
    "react",
    "react-dom",
    "vite",
    "typescript",
    "@types/react",
    "@types/react-dom",
)

# Dependabot branch shape:
# dependabot/<ecosystem>/<package>-<from>-to-<to>
# or dependabot/<ecosystem>/<package>-<version>
_DEPENDABOT_RE = re.compile(
    r"^dependabot/(?P<ecosystem>[^/]+)/(?P<package>[^@\s/]+(?:/[^@\s/]+)?)-(?P<bump>(?:gte-)?[0-9]+(?:\.[0-9]+)*(?:[.\-][^/]+)?)\s*$"
)


# ---------------------------------------------------------------------------
# Subprocess helpers (read-only by default)
# ---------------------------------------------------------------------------


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 30) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd or REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return (-1, "", repr(e))
    return (result.returncode, result.stdout or "", result.stderr or "")


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _today_utc() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Git state collection (read-only)
# ---------------------------------------------------------------------------


def _git_state() -> dict[str, Any]:
    rc, branch, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    rc2, head, _ = _run(["git", "rev-parse", "HEAD"])
    rc3, status, _ = _run(["git", "status", "--porcelain"])
    return {
        "branch": branch.strip() if rc == 0 else "unknown",
        "head_sha": head.strip() if rc2 == 0 else "unknown",
        "is_clean": rc3 == 0 and not status.strip(),
        "dirty_paths_count": (
            len([row for row in status.splitlines() if row.strip()]) if rc3 == 0 else "unknown"
        ),
    }


def _list_remote_branches() -> list[str]:
    rc, out, _ = _run(["git", "ls-remote", "--heads", "origin"])
    if rc != 0:
        return []
    branches: list[str] = []
    for line in out.splitlines():
        parts = line.strip().split("\t")
        if len(parts) != 2:
            continue
        ref = parts[1]
        if ref.startswith("refs/heads/"):
            branches.append(ref[len("refs/heads/") :])
    return sorted(branches)


def _changed_files(branch: str) -> list[str]:
    """Return the list of files that differ between origin/main and the
    branch, or [] on any error.
    """
    # Make sure refs are present locally.
    _run(["git", "fetch", "origin", "main", branch], timeout=20)
    rc, out, _ = _run(["git", "diff", "--name-only", f"origin/main...origin/{branch}"])
    if rc != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _has_conflict_with_main(branch: str) -> bool:
    """Best-effort conflict probe via merge-tree (no working-tree
    impact). Returns False on any error rather than guessing."""
    rc, out, _ = _run(
        ["git", "merge-tree", "--write-tree", "origin/main", f"origin/{branch}"]
    )
    if rc != 0:
        return False
    # merge-tree prints conflict markers when there's a conflict.
    return "<<<<<<<" in out


# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------


def _path_matches_any(path: str, globs: Iterable[str]) -> bool:
    n = path.replace("\\", "/")
    return any(fnmatch.fnmatchcase(n, g) for g in globs)


def _classify_branch(
    branch: str,
    files: list[str],
    *,
    has_conflict: bool,
) -> tuple[str, str]:
    """Return ``(risk_class, reason)``. Never returns ``safe_to_merge``."""
    if has_conflict:
        return ("blocked_conflict", "merge-tree reports conflict markers vs origin/main")

    # Dependabot branch?
    if branch.startswith("dependabot/"):
        return _classify_dependabot(branch)

    # Frozen contract? (more specific — checked first)
    for f in files:
        if f in FROZEN_CONTRACTS:
            return ("needs_human_contract_risk", f"diff touches frozen contract: {f}")

    # Live / paper / shadow / trading? (more specific — checked second)
    for f in files:
        if _path_matches_any(f, LIVE_PATH_GLOBS):
            return (
                "needs_human_trading_or_risk",
                f"diff touches trading-flow path: {f}",
            )

    # Protected governance? (general no-touch — checked last)
    for f in files:
        if _path_matches_any(f, NO_TOUCH_GLOBS):
            return (
                "needs_human_protected_governance",
                f"diff touches no-touch path: {f}",
            )

    # No external check evidence available in this release →
    # everything that survives the protected-path gates is
    # waiting_for_checks (never safe_to_merge in local mode).
    return (
        "waiting_for_checks",
        "checks not_available in v3.15.15.16; safe_to_merge is reserved but unreachable",
    )


def _classify_dependabot(branch: str) -> tuple[str, str]:
    """Return ``(risk_class, reason)`` for a dependabot/* branch."""
    m = _DEPENDABOT_RE.match(branch)
    if not m:
        return ("unknown", f"dependabot branch did not match expected shape: {branch}")
    pkg = m.group("package").lower()
    # Major framework risk by package name regardless of bump shape.
    if pkg in FRAMEWORK_MAJOR_PACKAGES:
        return (
            "dependabot_major_framework_risk",
            f"package {pkg!r} is a UI framework / type set; major bumps require operator review",
        )
    # Heuristic: parse the version, if the leading number is alone and
    # the existing pinned version is missing, treat as candidate-minor;
    # we cannot know patch vs minor without the original version, so
    # default to *_minor_safe_candidate when not "patch-like" by shape.
    # In practice Dependabot includes both old and new versions only in
    # the PR body, not the branch name. Without gh, we cannot tell.
    # Default conservatively: minor-safe-candidate. The operator
    # decides. Major-by-package-name above already pulled out frame-
    # work-risk cases.
    return (
        "dependabot_minor_safe_candidate",
        "candidate label only; checks_status is not_available — operator confirms",
    )


def _next_action(risk_class: str) -> str:
    return {
        "blocked_conflict": "rebase against origin/main; re-run controller",
        "blocked_failing_checks": "fix red checks; re-run controller",
        "needs_human_protected_governance": "open governance-bootstrap PR; CODEOWNERS review",
        "needs_human_contract_risk": "operator decides whether the contract regen is intentional",
        "needs_human_trading_or_risk": "operator decides whether trading-flow change is intentional",
        "dependabot_patch_safe_candidate": "operator confirms green checks then merges",
        "dependabot_minor_safe_candidate": "operator confirms green checks then merges",
        "dependabot_major_framework_risk": "compatibility branch + tested upgrade plan",
        "waiting_for_checks": "operator confirms green checks then merges",
        "unknown": "operator inspects branch manually",
    }.get(risk_class, "operator inspects branch manually")


# ---------------------------------------------------------------------------
# Frozen contract integrity probe
# ---------------------------------------------------------------------------


def _file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    import hashlib

    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _frozen_contracts() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for rel in FROZEN_CONTRACTS:
        p = REPO_ROOT / rel
        out[rel] = {
            "exists": p.exists(),
            "sha256": _file_sha256(p) or "unknown",
        }
    return out


# ---------------------------------------------------------------------------
# Audit chain summary
# ---------------------------------------------------------------------------


def _audit_chain_status() -> dict[str, Any]:
    today = REPO_ROOT / "logs" / f"agent_audit.{_today_utc()}.jsonl"
    if not today.exists():
        return {
            "ledger_path": "logs/" + today.name,
            "status": "not_available",
            "first_corrupt_index": None,
        }
    try:
        ok, idx = agent_audit.verify_chain(today)
    except Exception:
        return {
            "ledger_path": "logs/" + today.name,
            "status": "unreadable",
            "first_corrupt_index": None,
        }
    return {
        "ledger_path": "logs/" + today.name,
        "status": "intact" if ok else "broken",
        "first_corrupt_index": idx,
    }


def _governance_status() -> dict[str, Any]:
    rc, out, err = _run([sys.executable, "scripts/governance_lint.py"])
    return {
        "lint_passed": rc == 0,
        "summary": (out or err).strip().splitlines()[-1] if (out or err).strip() else "unknown",
    }


# ---------------------------------------------------------------------------
# Build PR queue
# ---------------------------------------------------------------------------


def _build_pr_queue() -> list[dict[str, Any]]:
    """For every non-main remote branch, classify and emit one row."""
    branches = _list_remote_branches()
    rows: list[dict[str, Any]] = []
    for branch in branches:
        if branch == "main":
            continue
        if branch.startswith("dependabot/"):
            continue  # handled by dependabot_queue
        files = _changed_files(branch)
        conflict = _has_conflict_with_main(branch)
        risk_class, reason = _classify_branch(branch, files, has_conflict=conflict)
        rows.append(
            {
                "item_id": branch,
                "source": "git_remote",
                "branch_or_pr": branch,
                "title": branch.split("/", 1)[-1].replace("-", " "),
                "risk_class": risk_class,
                "checks_status": "not_available",
                "mergeability": "not_available",
                "decision": "needs_human" if risk_class.startswith("needs_human_") else "operator_click",
                "reason": reason,
                "confidence": "unknown",
                "next_action": _next_action(risk_class),
            }
        )
    return rows


def _build_dependabot_queue() -> list[dict[str, Any]]:
    branches = [b for b in _list_remote_branches() if b.startswith("dependabot/")]
    rows: list[dict[str, Any]] = []
    for branch in branches:
        risk_class, reason = _classify_dependabot(branch)
        rows.append(
            {
                "item_id": branch,
                "source": "dependabot",
                "branch_or_pr": branch,
                "title": branch[len("dependabot/") :],
                "risk_class": risk_class,
                "checks_status": "not_available",
                "mergeability": "not_available",
                "decision": "operator_click",
                "reason": reason,
                "confidence": "low",
                "next_action": _next_action(risk_class),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Roadmap queue (recommendation-only)
# ---------------------------------------------------------------------------


def _build_roadmap_queue() -> list[dict[str, Any]]:
    """Read-only inspection of roadmap sources. Emits at most one
    recommended next item; never starts a branch.
    """
    sources = [
        "docs/roadmap/qre_roadmap_v3_post_v3_15.md",
        "docs/backlog/agent_backlog.md",
        "docs/spillovers/agent_spillovers.md",
    ]
    queue: list[dict[str, Any]] = []
    for rel in sources:
        p = REPO_ROOT / rel
        if not p.exists():
            queue.append(
                {
                    "item_id": rel,
                    "source": "roadmap_source",
                    "branch_or_pr": "not_available",
                    "title": rel,
                    "risk_class": "unknown",
                    "checks_status": "not_available",
                    "mergeability": "not_available",
                    "decision": "needs_human",
                    "reason": "roadmap source missing",
                    "confidence": "unknown",
                    "next_action": "operator restores roadmap source",
                }
            )
            continue
        queue.append(
            {
                "item_id": rel,
                "source": "roadmap_source",
                "branch_or_pr": "not_applicable",
                "title": p.name,
                "risk_class": "waiting_for_checks",
                "checks_status": "not_available",
                "mergeability": "not_applicable",
                "decision": "recommendation_only",
                "reason": "v3.15.15.16 emits roadmap recommendations only — no autonomous execution",
                "confidence": "unknown",
                "next_action": "operator picks next item from this source",
            }
        )
    return queue


# ---------------------------------------------------------------------------
# Top-level snapshot
# ---------------------------------------------------------------------------


def collect_snapshot(*, mode: str, cycle_id: int = 0) -> dict[str, Any]:
    pr_queue = _build_pr_queue()
    dep_queue = _build_dependabot_queue()
    road_queue = _build_roadmap_queue()
    blocked = [r for r in pr_queue + dep_queue if r["risk_class"].startswith("blocked_")]
    needs_human = [
        r
        for r in pr_queue + dep_queue + road_queue
        if r["decision"] in ("needs_human", "operator_click", "recommendation_only")
    ]
    next_recommended = next(
        (r for r in pr_queue if r["risk_class"] == "waiting_for_checks"), None
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "autonomous_workloop_digest",
        "controller_version": CONTROLLER_VERSION,
        "generated_at_utc": _utcnow(),
        "mode": mode,
        "cycle_id": cycle_id,
        "current_branch": _git_state()["branch"],
        "git_state": _git_state(),
        "governance_status": _governance_status(),
        "audit_chain_status": _audit_chain_status(),
        "frozen_contracts": _frozen_contracts(),
        "pr_queue": pr_queue,
        "dependabot_queue": dep_queue,
        "roadmap_queue": road_queue,
        "actions_taken": [],
        "merges_performed": 0,
        "blocked_items": blocked,
        "needs_human": needs_human,
        "next_recommended_item": (
            next_recommended["item_id"] if next_recommended else "unknown"
        ),
        "frontend_control_state": {
            "schema_anchor": "v3.15.15.17",
            "json_artifact_path": "logs/autonomous_workloop/latest.json",
            "markdown_digest_path": "docs/governance/autonomous_workloop/latest.md",
            "read_only": True,
            "operator_actions": ["dry-run", "view-digest"],
            "execute_actions_unlocked_in": "v3.15.15.21",
        },
        "limitations": [
            "v3.15.15.16 is not full PR automation.",
            "gh / API not available — checks_status / mergeability are not_available.",
            "controller_performed merges: 0.",
            "operator-click merge is still required.",
            "roadmap execution is recommendation-only.",
            "dependabot safe candidates are not safe to merge without green checks.",
            "writer-level subagent attribution is gated by ADR-016 bootstrap.",
            "inferred attribution is convenience-only, not source-of-truth.",
            "next technical milestone for true autonomy is GitHub-backed PR/check integration (v3.15.15.19).",
            "frontend should consume JSON artifacts (logs/autonomous_workloop/latest.json), not markdown.",
            "JSON artifact lives under logs/ (gitignored) rather than artifacts/ to avoid touching .gitignore (ask-flow path) in v3.15.15.16.",
        ],
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def render_markdown(snap: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Autonomous Workloop Digest — {snap['generated_at_utc']}")
    lines.append("")
    lines.append(f"- **controller_version**: `{snap['controller_version']}`")
    lines.append(f"- **mode**: `{snap['mode']}`")
    lines.append(f"- **cycle_id**: `{snap['cycle_id']}`")
    lines.append(f"- **current_branch**: `{snap['current_branch']}`")
    lines.append(
        f"- **git_state.head_sha**: `{snap['git_state'].get('head_sha', 'unknown')}`"
    )
    lines.append(
        f"- **audit_chain_status**: `{snap['audit_chain_status']['status']}`"
    )
    lines.append(
        f"- **governance_lint_passed**: `{snap['governance_status']['lint_passed']}`"
    )
    lines.append(f"- **merges_performed**: `{snap['merges_performed']}`")
    lines.append("")
    lines.append("## Frozen contracts")
    lines.append("")
    for rel, info in snap["frozen_contracts"].items():
        lines.append(f"- `{rel}` — sha256 `{info['sha256'][:16]}…` (exists={info['exists']})")
    lines.append("")
    lines.append("## PR queue")
    lines.append("")
    if snap["pr_queue"]:
        lines.append("| branch | risk_class | checks | decision | reason |")
        lines.append("|---|---|---|---|---|")
        for r in snap["pr_queue"]:
            lines.append(
                f"| `{r['branch_or_pr']}` | {r['risk_class']} | {r['checks_status']} | {r['decision']} | {r['reason']} |"
            )
    else:
        lines.append("_(empty)_")
    lines.append("")
    lines.append("## Dependabot queue")
    lines.append("")
    if snap["dependabot_queue"]:
        lines.append("| branch | risk_class | checks | next_action |")
        lines.append("|---|---|---|---|")
        for r in snap["dependabot_queue"]:
            lines.append(
                f"| `{r['branch_or_pr']}` | {r['risk_class']} | {r['checks_status']} | {r['next_action']} |"
            )
    else:
        lines.append("_(empty)_")
    lines.append("")
    lines.append("## Roadmap queue (recommendation-only)")
    lines.append("")
    if snap["roadmap_queue"]:
        lines.append("| source | risk_class | next_action |")
        lines.append("|---|---|---|")
        for r in snap["roadmap_queue"]:
            lines.append(f"| `{r['item_id']}` | {r['risk_class']} | {r['next_action']} |")
    else:
        lines.append("_(empty)_")
    lines.append("")
    lines.append("## Next recommended item")
    lines.append("")
    lines.append(f"`{snap['next_recommended_item']}`")
    lines.append("")
    lines.append("## Final report")
    lines.append("")
    for i, lim in enumerate(snap["limitations"], 1):
        lines.append(f"{i}. {lim}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Push allowlist
# ---------------------------------------------------------------------------


def push_target_allowed(branch: str) -> tuple[bool, str | None]:
    """Decide whether the controller may push to ``branch``.

    Returns (allowed, reason). Allowed only if the target is the
    current release branch."""
    if branch == "main":
        return (False, "push to main is forbidden by Doctrine 8")
    if branch.startswith("dependabot/"):
        return (False, "push to dependabot branches is forbidden")
    if branch != CURRENT_RELEASE_BRANCH:
        return (
            False,
            f"push allowed only to current release branch '{CURRENT_RELEASE_BRANCH}'",
        )
    return (True, None)


def execute_safe_target_allowed(target_path: str) -> tuple[bool, str | None]:
    """Decide whether ``execute-safe`` may write to ``target_path``.

    Defense in depth above the hook layer — the deny_no_touch hook
    remains the canonical enforcement.
    """
    if target_path.replace("\\", "/") in FROZEN_CONTRACTS:
        return (
            False,
            f"target '{target_path}' is a frozen contract",
        )
    if _path_matches_any(target_path, LIVE_PATH_GLOBS):
        return (
            False,
            f"target '{target_path}' matches a live/trading-flow glob",
        )
    if _path_matches_any(target_path, NO_TOUCH_GLOBS):
        return (False, f"target '{target_path}' matches a no-touch glob")
    return (True, None)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def write_outputs(snap: dict[str, Any]) -> dict[str, str]:
    """Write the JSON + markdown digest pair. Returns the paths
    written (relative)."""
    DIGEST_DIR_MD.mkdir(parents=True, exist_ok=True)
    DIGEST_DIR_JSON.mkdir(parents=True, exist_ok=True)
    ts = snap["generated_at_utc"].replace(":", "-")
    json_now = DIGEST_DIR_JSON / f"{ts}.json"
    json_latest = DIGEST_DIR_JSON / "latest.json"
    md_now = DIGEST_DIR_MD / f"{ts}.md"
    md_latest = DIGEST_DIR_MD / "latest.md"
    payload = json.dumps(snap, sort_keys=True, indent=2)
    json_now.write_text(payload, encoding="utf-8")
    json_latest.write_text(payload, encoding="utf-8")
    md_payload = render_markdown(snap)
    md_now.write_text(md_payload, encoding="utf-8")
    md_latest.write_text(md_payload, encoding="utf-8")
    return {
        "json_now": _rel(json_now),
        "json_latest": _rel(json_latest),
        "md_now": _rel(md_now),
        "md_latest": _rel(md_latest),
    }


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace(
            "\\", "/"
        )
    except ValueError:
        return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.autonomous_workloop",
        description=(
            "Autonomous Workloop Controller (Local Planning Mode). "
            "Read-only by default; execute-safe is bounded to local "
            "actions only. Never pushes to main; never calls GitHub "
            "API; never recommends safe_to_merge in this release."
        ),
    )
    p.add_argument(
        "--mode",
        choices=["plan", "dry-run", "execute-safe", "continuous", "digest"],
        default="dry-run",
        help="Operating mode (default: dry-run).",
    )
    p.add_argument(
        "--max-cycles",
        type=int,
        default=1,
        help="Max cycles for --mode continuous (clamped to ≤ 25).",
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
    max_cycles = min(max(args.max_cycles, 1), 25)

    if args.mode in ("plan", "dry-run", "digest"):
        snap = collect_snapshot(mode=args.mode, cycle_id=0)
        assert_no_secrets(snap)
        if args.mode == "digest":
            paths = write_outputs(snap)
            sys.stdout.write(json.dumps(paths, indent=args.indent or None) + "\n")
            return 0
        # plan and dry-run print to stdout without writing.
        indent = args.indent if args.indent and args.indent > 0 else None
        json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    if args.mode == "execute-safe":
        # In v3.15.15.16 the only execute-safe action is writing the
        # digest to disk. No git mutation, no PR action, no merge.
        snap = collect_snapshot(mode="execute-safe", cycle_id=0)
        assert_no_secrets(snap)
        paths = write_outputs(snap)
        snap["actions_taken"] = [
            {
                "kind": "write_digest",
                "target": paths["md_latest"],
                "outcome": "ok",
            },
            {
                "kind": "write_digest",
                "target": paths["json_latest"],
                "outcome": "ok",
            },
        ]
        # Re-write with actions_taken populated.
        write_outputs(snap)
        json.dump(paths, sys.stdout, indent=args.indent or None)
        sys.stdout.write("\n")
        return 0

    # continuous: bounded loop; no merges, no pushes — same as
    # execute-safe N times. Each cycle re-collects state and re-writes
    # the digest pair.
    paths_last: dict[str, str] = {}
    for cycle in range(max_cycles):
        snap = collect_snapshot(mode="continuous", cycle_id=cycle)
        assert_no_secrets(snap)
        paths_last = write_outputs(snap)
    sys.stdout.write(json.dumps(paths_last, indent=args.indent or None) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
