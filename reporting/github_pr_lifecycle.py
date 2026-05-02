"""GitHub PR Lifecycle Provider + Dependabot Cleanup Playbook (v3.15.15.17).

This release codifies the proven Dependabot cleanup pilot (10/10 PRs
processed cleanly to final SHA ``bd206ba9ea0eeb4c696a30d5778d97cdc7107926``)
into a reproducible module:

* **Provider abstraction** over the ``gh`` CLI — authentication,
  repo detection, PR listing/inspection/checks, and the two
  mutating actions actually used by the pilot:
  ``@dependabot rebase`` comment and ``--squash`` merge.
* **Risk classifier** matching the LOW / MEDIUM / HIGH policy from
  the pilot brief, including the explicit HIGH list
  (numpy / pandas / pyarrow / scipy / sklearn / pydantic /
  FastAPI / SQLAlchemy / Docker / build / runtime / majors /
  conflicts / failing checks / protected paths / lockfile churn).
* **Decision planner** that maps each PR into one of the documented
  decisions: ``merge_allowed``, ``wait_for_rebase``,
  ``wait_for_checks``, ``blocked_failing_checks``, ``blocked_conflict``,
  ``blocked_high_risk``, ``blocked_protected_path``,
  ``blocked_unknown``, ``needs_human``.
* **Two modes**: ``dry-run`` (read-only, no mutation) and
  ``execute-safe`` (may comment ``@dependabot rebase`` and squash-merge
  LOW/MEDIUM PRs only — never HIGH, never main, never force-push).

Hard guarantees (enforced by code AND tests)
--------------------------------------------

* Never pushes to ``main``.
* Never force-pushes any branch.
* Never merges a HIGH-risk PR — even with all checks green.
* Never merges a PR whose diff touches a protected path.
* Never merges a PR with unknown mergeability.
* Never merges a PR with pending or failing required checks.
* Treats ``unknown`` as never-safe.

The frozen-contract hashes are checked at the start of every cycle.
A drift aborts the cycle before any mutation.

CLI
---

::

    python -m reporting.github_pr_lifecycle --mode dry-run
    python -m reporting.github_pr_lifecycle --mode execute-safe

Stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
MODULE_VERSION: str = "v3.15.15.17"
SCHEMA_VERSION: int = 1

DIGEST_DIR_JSON: Path = REPO_ROOT / "logs" / "github_pr_lifecycle"


# ---------------------------------------------------------------------------
# Governance constants (mirror of autonomous_workloop / no_touch_paths.md)
# ---------------------------------------------------------------------------

# Frozen contracts — any diff that touches one of these is
# blocked_protected_path regardless of risk class.
FROZEN_CONTRACTS: tuple[str, ...] = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)

# Path globs whose presence in a PR diff classifies it as
# protected. Mirrors ``autonomous_workloop.NO_TOUCH_GLOBS`` and the
# canonical list in ``docs/governance/no_touch_paths.md``. Kept local
# so this module can be tested in isolation; sync via release notes
# when the canonical list changes.
PROTECTED_GLOBS: tuple[str, ...] = (
    ".claude/settings.json",
    ".claude/hooks/*",
    ".claude/hooks/**",
    ".claude/agents/*",
    ".claude/agents/**",
    ".claude/commands/*",
    ".claude/commands/**",
    ".github/CODEOWNERS",
    "VERSION",
    "automation/live_gate.py",
    "automation/*.secret",
    "state/*.secret",
    "config/config.yaml",
    ".env",
    ".env.*",
    "*_latest.v1.json",
    "*_latest.v1.jsonl",
    "**/*_latest.v1.json",
    "**/*_latest.v1.jsonl",
    "docker-compose.prod.yml",
    "scripts/deploy.sh",
    "Dockerfile",
    "Dockerfile.*",
)

# Live / paper / shadow / trading-flow globs.
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

# Python packages whose updates are HIGH regardless of bump shape.
HIGH_RISK_PYTHON_PACKAGES: frozenset[str] = frozenset({
    "numpy",
    "pandas",
    "pyarrow",
    "scipy",
    "sklearn",
    "scikit-learn",
    "pydantic",
    "fastapi",
    "sqlalchemy",
})

# Tokens that, when present in a Dependabot title or branch slug,
# elevate the PR to HIGH (Docker / build / runtime base changes).
HIGH_RISK_DOCKER_TOKENS: tuple[str, ...] = (
    "docker",
    "dockerfile",
    "buildx",
    "build-push-action",
    "node:",
    "python:",
    "alpine:",
)


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 30) -> tuple[int, str, str]:
    """Read-only subprocess helper. Returns ``(rc, stdout, stderr)``.

    ``rc == -1`` indicates a launch error (timeout / OSError /
    SubprocessError). Callers must distinguish that from a non-zero
    process exit.
    """
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


# ---------------------------------------------------------------------------
# Provider — gh CLI wrapper
# ---------------------------------------------------------------------------


# Status surface enumerated in the schema doc.
PROVIDER_STATUSES: tuple[str, ...] = (
    "available",
    "not_available",
    "not_authenticated",
    "repo_not_detected",
    "permission_denied",
)


def _gh_path() -> str | None:
    """Locate ``gh`` on PATH. Returns None if not found.

    This is a hot path — keep it stdlib-only and side-effect free.
    """
    # ``shutil.which`` honours PATHEXT on Windows.
    return shutil.which("gh")


def gh_provider_status() -> dict[str, Any]:
    """Probe the ``gh`` CLI for availability, authentication, and a
    detectable repo. Returns a status dict with one of the values in
    :data:`PROVIDER_STATUSES`."""
    gh = _gh_path()
    if gh is None:
        return {
            "status": "not_available",
            "gh_path": None,
            "version": None,
            "account": None,
            "repo": None,
        }
    rc, out, err = _run([gh, "--version"], timeout=10)
    if rc != 0:
        return {
            "status": "not_available",
            "gh_path": gh,
            "version": None,
            "account": None,
            "repo": None,
            "stderr": err.strip()[:200],
        }
    version_line = (out.strip().splitlines() or [""])[0]
    rc2, out2, err2 = _run([gh, "auth", "status"], timeout=10)
    if rc2 != 0:
        return {
            "status": "not_authenticated",
            "gh_path": gh,
            "version": version_line,
            "account": None,
            "repo": None,
            "stderr": (out2 + err2).strip()[:200],
        }
    # ``gh auth status`` prints to stderr in older releases, stdout in
    # newer ones — accept either.
    account: str | None = None
    for line in (out2 + "\n" + err2).splitlines():
        m = re.search(r"Logged in to \S+ account (\S+)", line)
        if m:
            account = m.group(1)
            break
    rc3, out3, err3 = _run(
        [gh, "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        timeout=10,
    )
    if rc3 != 0:
        return {
            "status": "repo_not_detected",
            "gh_path": gh,
            "version": version_line,
            "account": account,
            "repo": None,
            "stderr": (out3 + err3).strip()[:200],
        }
    return {
        "status": "available",
        "gh_path": gh,
        "version": version_line,
        "account": account,
        "repo": out3.strip() or None,
    }


def _gh(args: list[str], *, timeout: int = 30) -> tuple[int, str, str]:
    """Invoke ``gh`` with the located binary. Returns ``(-1, "", err)``
    if ``gh`` is missing — caller should treat that as ``not_available``.
    """
    gh = _gh_path()
    if gh is None:
        return (-1, "", "gh not on PATH")
    return _run([gh, *args], timeout=timeout)


def list_open_prs(*, base: str = "main") -> tuple[list[dict[str, Any]], str | None]:
    """List open PRs targeting ``base``. Returns ``(prs, error)``.

    On any gh error returns ``([], error_string)`` rather than raising
    so the caller can map it into ``provider_status``. Each PR carries
    the fields requested in the schema (number, title, author,
    headRefName, baseRefName, mergeStateStatus, isDraft, reviewDecision,
    updatedAt).
    """
    rc, out, err = _gh(
        [
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            "100",
            "--base",
            base,
            "--json",
            "number,title,author,headRefName,baseRefName,mergeStateStatus,"
            "isDraft,reviewDecision,updatedAt,url",
        ],
        timeout=30,
    )
    if rc != 0:
        return ([], (out + err).strip()[:300])
    try:
        data = json.loads(out or "[]")
    except json.JSONDecodeError as e:
        return ([], f"malformed gh output: {e}")
    if not isinstance(data, list):
        return ([], "malformed gh output: expected list")
    return (data, None)


def pr_inspect(number: int) -> tuple[dict[str, Any], str | None]:
    """Inspect a single PR with the fields needed for risk + decision."""
    rc, out, err = _gh(
        [
            "pr",
            "view",
            str(int(number)),
            "--json",
            "number,title,author,headRefName,baseRefName,mergeStateStatus,"
            "isDraft,reviewDecision,additions,deletions,files,url",
        ],
        timeout=30,
    )
    if rc != 0:
        return ({}, (out + err).strip()[:300])
    try:
        data = json.loads(out or "{}")
    except json.JSONDecodeError as e:
        return ({}, f"malformed gh output: {e}")
    if not isinstance(data, dict):
        return ({}, "malformed gh output: expected object")
    return (data, None)


def pr_changed_files(pr: dict[str, Any]) -> list[str]:
    """Extract the changed-file paths from an inspected PR. Returns
    ``[]`` if the field is missing or malformed."""
    files = pr.get("files")
    if not isinstance(files, list):
        return []
    out: list[str] = []
    for f in files:
        if isinstance(f, dict):
            p = f.get("path")
            if isinstance(p, str) and p.strip():
                out.append(p.strip())
        elif isinstance(f, str) and f.strip():
            out.append(f.strip())
    return out


def pr_checks(number: int) -> tuple[list[dict[str, Any]], str | None]:
    """Return the list of GitHub checks for the PR.

    Each entry has keys ``name``, ``status``, ``conclusion`` (where
    available). ``status`` is one of ``COMPLETED`` / ``IN_PROGRESS`` /
    ``QUEUED``; ``conclusion`` is ``SUCCESS`` / ``FAILURE`` / ``""``.
    """
    rc, out, err = _gh(
        [
            "pr",
            "view",
            str(int(number)),
            "--json",
            "statusCheckRollup",
            "-q",
            "[.statusCheckRollup[] | {name: .name, status: .status, "
            "conclusion: .conclusion}]",
        ],
        timeout=30,
    )
    if rc != 0:
        return ([], (out + err).strip()[:300])
    try:
        data = json.loads(out or "[]")
    except json.JSONDecodeError as e:
        return ([], f"malformed gh output: {e}")
    if not isinstance(data, list):
        return ([], "malformed gh output: expected list")
    return (data, None)


def comment_dependabot_rebase(number: int) -> tuple[bool, str | None]:
    """Post the ``@dependabot rebase`` comment. Mutating — only call
    from ``execute-safe`` after passing every gate."""
    rc, out, err = _gh(
        ["pr", "comment", str(int(number)), "--body", "@dependabot rebase"],
        timeout=30,
    )
    if rc != 0:
        return (False, (out + err).strip()[:300])
    return (True, None)


def merge_squash(number: int) -> tuple[bool, str | None]:
    """Squash-merge the PR and delete its branch. Mutating — only
    callable from ``execute-safe`` after every gate is green."""
    rc, out, err = _gh(
        ["pr", "merge", str(int(number)), "--squash", "--delete-branch"],
        timeout=60,
    )
    if rc != 0:
        return (False, (out + err).strip()[:300])
    return (True, None)


# ---------------------------------------------------------------------------
# Path matching
# ---------------------------------------------------------------------------


def _path_matches_any(path: str, globs: Iterable[str]) -> bool:
    n = path.replace("\\", "/")
    return any(fnmatch.fnmatchcase(n, g) for g in globs)


def diff_touches_protected(files: list[str]) -> tuple[bool, str | None]:
    """Return ``(touched, first_match)``. A frozen contract or any
    NO_TOUCH glob match counts as protected."""
    for f in files:
        n = f.replace("\\", "/")
        if n in FROZEN_CONTRACTS:
            return (True, n)
    for f in files:
        if _path_matches_any(f, PROTECTED_GLOBS):
            return (True, f)
    return (False, None)


def diff_touches_live_or_trading(files: list[str]) -> tuple[bool, str | None]:
    """Return ``(touched, first_match)`` for live / paper / shadow /
    trading-flow paths."""
    for f in files:
        if _path_matches_any(f, LIVE_PATH_GLOBS):
            return (True, f)
    return (False, None)


# ---------------------------------------------------------------------------
# Risk classifier
# ---------------------------------------------------------------------------


# Risk classes (string constants for clarity in tests).
RISK_LOW: str = "LOW"
RISK_MEDIUM: str = "MEDIUM"
RISK_HIGH: str = "HIGH"


# Dependabot branch shapes:
#   dependabot/<ecosystem>/<package>-<version>           (pip pkgs use gte-)
#   dependabot/<ecosystem>/<vendor>/<package>-<version>  (some GHA pkgs)
_DEPENDABOT_BRANCH_RE = re.compile(
    r"^dependabot/(?P<ecosystem>[^/]+)/(?P<rest>.+)$"
)

# Title pattern used by Dependabot to surface the bump:
#   "Bump <pkg> from <old> to <new>"
#   "Update <pkg> requirement from >=<old> to >=<new>"
_BUMP_RE = re.compile(
    r"(?:Bump|Update)\s+(?P<pkg>[^\s]+(?:/[^\s]+)?)\s+(?:requirement\s+)?"
    r"from\s+(?P<from>\S+)\s+to\s+(?P<to>\S+)",
    re.IGNORECASE,
)


def _is_major_bump(from_v: str, to_v: str) -> bool:
    """Best-effort major-version detection. Returns True if the leading
    integer in ``to_v`` is strictly greater than the leading integer in
    ``from_v``. Strips a leading ``>=`` if present."""

    def _major(s: str) -> int | None:
        s2 = s.lstrip(">=").strip()
        m = re.match(r"^(\d+)", s2)
        return int(m.group(1)) if m else None

    a = _major(from_v)
    b = _major(to_v)
    if a is None or b is None:
        return False
    return b > a


def _is_zero_x_minor_bump(from_v: str, to_v: str) -> bool:
    """0.x packages have a convention where the minor number behaves
    like a major. ``>=0.17.0`` → ``>=0.24.0`` is not a major-version
    semver bump (0 == 0) but the public API can still break."""

    def _parts(s: str) -> tuple[int, int] | None:
        s2 = s.lstrip(">=").strip()
        m = re.match(r"^(\d+)\.(\d+)", s2)
        return (int(m.group(1)), int(m.group(2))) if m else None

    a = _parts(from_v)
    b = _parts(to_v)
    if a is None or b is None:
        return False
    return a[0] == 0 and b[0] == 0 and b[1] > a[1]


def _package_from_branch(branch: str) -> str | None:
    m = _DEPENDABOT_BRANCH_RE.match(branch)
    if not m:
        return None
    rest = m.group("rest")
    # Strip trailing ``-<version>`` (with optional ``gte-`` prefix).
    rest2 = re.sub(r"-(?:gte-)?\d+(?:\.\d+)*(?:[.\-][^/]+)?$", "", rest)
    return rest2.lower() if rest2 else None


def classify_pr(pr: dict[str, Any], files: list[str]) -> tuple[str, str, str | None]:
    """Return ``(risk_class, reason, package_or_None)``.

    Decision order — first-match wins:
      1. Diff touches a frozen contract or any protected path → HIGH.
      2. Diff touches a live / paper / shadow / trading path  → HIGH.
      3. Dependabot package is on the HIGH list (numpy etc.)  → HIGH.
      4. Bump shape suggests a major-version jump            → HIGH.
      5. Title / branch contains a Docker/build/runtime token → HIGH.
      6. CI tooling (GHA / pre-commit) patch+minor           → LOW.
      7. Production-Python patch/minor                       → MEDIUM.
      8. Unparseable bump shape but Dependabot                → MEDIUM (conservative).
    """
    title = (pr.get("title") or "")
    branch = (pr.get("headRefName") or "")
    pkg = _package_from_branch(branch)
    bump = _BUMP_RE.search(title)
    from_v = bump.group("from") if bump else ""
    to_v = bump.group("to") if bump else ""

    # (1) Protected path
    touched, hit = diff_touches_protected(files)
    if touched:
        return (RISK_HIGH, f"diff touches protected path: {hit}", pkg)

    # (2) Live / trading path
    touched_l, hit_l = diff_touches_live_or_trading(files)
    if touched_l:
        return (RISK_HIGH, f"diff touches live/trading path: {hit_l}", pkg)

    # (3) HIGH-risk Python package by name
    if pkg and pkg in HIGH_RISK_PYTHON_PACKAGES:
        return (
            RISK_HIGH,
            f"package {pkg!r} is on the HIGH-risk list (numerical/data infra)",
            pkg,
        )

    # (4) Major-version bump
    if from_v and to_v and _is_major_bump(from_v, to_v):
        return (
            RISK_HIGH,
            f"major-version bump {from_v} -> {to_v}",
            pkg,
        )

    # (5) Docker / build / runtime tokens — be careful not to misclassify
    # ``docker/login-action`` as Docker-base. Docker-base risk applies
    # to the runtime image (Dockerfile / docker-compose / image tags),
    # not to action wrappers used in workflows. Action-wrapper bumps
    # touch only ``.github/workflows/**`` and were proven safe in the
    # pilot; we let them flow through to the GHA-tooling rules below.
    if any(t in title.lower() for t in ("dockerfile", "docker-compose", "alpine:", "node:", "python:")):
        return (
            RISK_HIGH,
            "title mentions Docker base / runtime image",
            pkg,
        )
    for f in files:
        n = f.replace("\\", "/")
        if n == "Dockerfile" or n.startswith("Dockerfile.") or n.startswith("docker-compose"):
            return (
                RISK_HIGH,
                f"diff modifies Docker runtime artifact: {n}",
                pkg,
            )

    # 0.x minor bumps for CI tooling are MEDIUM (0.x APIs break easily;
    # downgrading from HIGH because the action is alert-only / wrapper).
    is_workflow_only = bool(files) and all(
        f.replace("\\", "/").startswith(".github/workflows/") for f in files
    )
    if is_workflow_only:
        if from_v and to_v and _is_zero_x_minor_bump(from_v, to_v):
            return (
                RISK_MEDIUM,
                f"GHA 0.x minor bump {from_v} -> {to_v} (semver-unstable)",
                pkg,
            )
        # Patch / minor (1.x+) on .github/workflows/** is LOW.
        return (
            RISK_LOW,
            "GitHub Actions patch/minor update (workflow-only diff)",
            pkg,
        )

    # Pure pip dependency floor bump.
    is_requirements_only = bool(files) and all(
        f.replace("\\", "/") == "requirements.txt" for f in files
    )
    if is_requirements_only:
        return (
            RISK_MEDIUM,
            "Python production dependency patch/minor floor bump",
            pkg,
        )

    # Frontend / npm dev-only patch — LOW. (pilot did not surface
    # frontend PRs but the policy keeps a place for them.)
    is_frontend_only = bool(files) and all(
        f.replace("\\", "/").startswith("frontend/") for f in files
    )
    if is_frontend_only:
        return (RISK_LOW, "frontend dev dependency update", pkg)

    # Mixed / unknown → MEDIUM, conservatively.
    return (
        RISK_MEDIUM,
        "mixed-or-unknown diff scope; classified MEDIUM conservatively",
        pkg,
    )


# ---------------------------------------------------------------------------
# Decision planner
# ---------------------------------------------------------------------------


# Decisions enumerated in the schema doc.
DECISIONS: tuple[str, ...] = (
    "merge_allowed",
    "wait_for_rebase",
    "wait_for_checks",
    "blocked_failing_checks",
    "blocked_conflict",
    "blocked_high_risk",
    "blocked_protected_path",
    "blocked_unknown",
    "needs_human",
)


def _author_login(pr: dict[str, Any]) -> str:
    a = pr.get("author")
    if isinstance(a, dict):
        return (a.get("login") or "").lower()
    if isinstance(a, str):
        return a.lower()
    return ""


def _is_dependabot(pr: dict[str, Any]) -> bool:
    login = _author_login(pr)
    return login in ("app/dependabot", "dependabot[bot]", "dependabot")


def aggregate_checks(checks: list[dict[str, Any]]) -> str:
    """Reduce the per-check rollup into one of:
       ``passed`` / ``pending`` / ``failed`` / ``unknown``.

    Empty list → ``unknown`` (deliberate; never assume green when no
    evidence is available).
    """
    if not checks:
        return "unknown"
    seen_pending = False
    for c in checks:
        status = (c.get("status") or "").upper()
        conclusion = (c.get("conclusion") or "").upper()
        if status != "COMPLETED":
            seen_pending = True
            continue
        if conclusion in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            continue
        if conclusion in ("FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"):
            return "failed"
        if conclusion == "":
            seen_pending = True
            continue
        # Unknown conclusion → never assume green.
        return "unknown"
    if seen_pending:
        return "pending"
    return "passed"


def decide_for_pr(
    pr: dict[str, Any],
    files: list[str],
    checks: list[dict[str, Any]],
    *,
    risk_class: str,
    risk_reason: str,
    baseline_ok: bool,
) -> dict[str, Any]:
    """Return a decision record for one PR.

    Pure function — no I/O, no mutation. The caller decides whether
    to act on the proposed actions based on the run mode.
    """
    actions: list[str] = []
    merge_state = (pr.get("mergeStateStatus") or "").upper()
    is_draft = bool(pr.get("isDraft"))
    base = (pr.get("baseRefName") or "")
    author = _author_login(pr)
    checks_state = aggregate_checks(checks)

    # Hard refusal layer — order matters.
    if not _is_dependabot(pr):
        return {
            "decision": "needs_human",
            "reason": f"author {author!r} is not Dependabot; out of scope for autoplaybook",
            "actions_proposed": [],
            "merge_state": merge_state.lower() or "unknown",
            "checks_state": checks_state,
        }
    if base != "main":
        return {
            "decision": "needs_human",
            "reason": f"PR base {base!r} is not main",
            "actions_proposed": [],
            "merge_state": merge_state.lower() or "unknown",
            "checks_state": checks_state,
        }
    if is_draft:
        return {
            "decision": "needs_human",
            "reason": "PR is a draft",
            "actions_proposed": [],
            "merge_state": merge_state.lower() or "unknown",
            "checks_state": checks_state,
        }

    # Path / risk gates — protected wins over everything else.
    touched, hit = diff_touches_protected(files)
    if touched:
        return {
            "decision": "blocked_protected_path",
            "reason": f"diff touches protected path: {hit}",
            "actions_proposed": [],
            "merge_state": merge_state.lower() or "unknown",
            "checks_state": checks_state,
        }
    touched_l, hit_l = diff_touches_live_or_trading(files)
    if touched_l:
        return {
            "decision": "blocked_protected_path",
            "reason": f"diff touches live/trading path: {hit_l}",
            "actions_proposed": [],
            "merge_state": merge_state.lower() or "unknown",
            "checks_state": checks_state,
        }
    if not baseline_ok:
        return {
            "decision": "needs_human",
            "reason": "local baseline gates (governance_lint / smoke / frozen hashes) are not green; aborting before any mutation",
            "actions_proposed": [],
            "merge_state": merge_state.lower() or "unknown",
            "checks_state": checks_state,
        }

    # Mergeability gates.
    if merge_state == "DIRTY":
        return {
            "decision": "blocked_conflict",
            "reason": "merge conflict against main; manual rebase required",
            "actions_proposed": [],
            "merge_state": merge_state.lower(),
            "checks_state": checks_state,
        }
    if merge_state == "BEHIND":
        return {
            "decision": "wait_for_rebase",
            "reason": "PR branch behind main; will request Dependabot rebase",
            "actions_proposed": ["comment_dependabot_rebase"],
            "merge_state": "behind",
            "checks_state": checks_state,
        }
    if merge_state in ("UNKNOWN", ""):
        return {
            "decision": "blocked_unknown",
            "reason": f"mergeStateStatus={merge_state!r} is not safe to act on",
            "actions_proposed": [],
            "merge_state": merge_state.lower() or "unknown",
            "checks_state": checks_state,
        }

    # CLEAN / BLOCKED / UNSTABLE / etc. We accept only CLEAN below.
    if merge_state != "CLEAN":
        return {
            "decision": "blocked_unknown",
            "reason": f"mergeStateStatus={merge_state!r}; only CLEAN is acceptable",
            "actions_proposed": [],
            "merge_state": merge_state.lower(),
            "checks_state": checks_state,
        }

    # Checks gate (post-CLEAN).
    if checks_state == "failed":
        return {
            "decision": "blocked_failing_checks",
            "reason": "one or more required checks failed",
            "actions_proposed": [],
            "merge_state": "clean",
            "checks_state": checks_state,
        }
    if checks_state == "pending":
        return {
            "decision": "wait_for_checks",
            "reason": "one or more required checks are still running",
            "actions_proposed": [],
            "merge_state": "clean",
            "checks_state": checks_state,
        }
    if checks_state != "passed":
        return {
            "decision": "blocked_unknown",
            "reason": f"checks_state={checks_state!r}; never assume green",
            "actions_proposed": [],
            "merge_state": "clean",
            "checks_state": checks_state,
        }

    # Risk gate — HIGH never auto-merges in this release.
    if risk_class == RISK_HIGH:
        return {
            "decision": "blocked_high_risk",
            "reason": f"HIGH risk: {risk_reason} (HIGH is inspect-only in {MODULE_VERSION})",
            "actions_proposed": [],
            "merge_state": "clean",
            "checks_state": checks_state,
        }

    # All gates green for a LOW or MEDIUM Dependabot PR with CLEAN
    # mergeability and passed checks → merge_allowed.
    return {
        "decision": "merge_allowed",
        "reason": f"{risk_class}: {risk_reason}; all gates green",
        "actions_proposed": ["squash_merge"],
        "merge_state": "clean",
        "checks_state": checks_state,
    }


# ---------------------------------------------------------------------------
# Local baseline (frozen contracts + governance_lint + smoke)
# ---------------------------------------------------------------------------


def _file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def frozen_hashes() -> dict[str, str]:
    """Compute sha256 for every frozen contract path. Missing files
    map to ``"missing"`` rather than crashing — the caller decides
    what to do."""
    out: dict[str, str] = {}
    for rel in FROZEN_CONTRACTS:
        p = REPO_ROOT / rel
        out[rel] = _file_sha256(p) or "missing"
    return out


def governance_lint_ok() -> tuple[bool, str]:
    rc, out, err = _run([sys.executable, "scripts/governance_lint.py"], timeout=60)
    summary_lines = (out + err).strip().splitlines()
    last = summary_lines[-1] if summary_lines else ""
    return (rc == 0, last[:200])


def smoke_tests_ok() -> tuple[bool, str]:
    rc, out, err = _run(
        [sys.executable, "-m", "pytest", "tests/smoke", "-q", "--no-header"],
        timeout=300,
    )
    summary_lines = (out + err).strip().splitlines()
    last = summary_lines[-1] if summary_lines else ""
    return (rc == 0, last[:200])


def collect_baseline(*, run_smoke: bool = True) -> dict[str, Any]:
    """Read-only baseline collection. ``run_smoke=False`` lets tests
    skip the slow path."""
    gov_ok, gov_summary = governance_lint_ok()
    if run_smoke:
        smoke_ok, smoke_summary = smoke_tests_ok()
    else:
        smoke_ok, smoke_summary = (True, "skipped")
    hashes = frozen_hashes()
    all_ok = gov_ok and smoke_ok and all(v != "missing" for v in hashes.values())
    return {
        "governance_lint": {"ok": gov_ok, "summary": gov_summary},
        "smoke_tests": {"ok": smoke_ok, "summary": smoke_summary},
        "frozen_hashes": hashes,
        "all_ok": all_ok,
    }


# ---------------------------------------------------------------------------
# Top-level snapshot
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    mode: str,
    provider: dict[str, Any] | None = None,
    prs_override: list[dict[str, Any]] | None = None,
    baseline_override: dict[str, Any] | None = None,
    fetch_inspect: Any = None,
    fetch_checks: Any = None,
) -> dict[str, Any]:
    """Build the full snapshot dict.

    All gh interactions are dependency-injected so the snapshot can be
    tested without a real ``gh`` binary. In production the defaults
    call the live provider.
    """
    if provider is None:
        provider = gh_provider_status()

    if baseline_override is not None:
        baseline = baseline_override
    else:
        # In dry-run we still run the baseline so the snapshot can
        # report whether the local environment is currently safe.
        baseline = collect_baseline(run_smoke=True)

    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "github_pr_lifecycle_digest",
        "module_version": MODULE_VERSION,
        "generated_at_utc": _utcnow(),
        "repo": provider.get("repo") or "unknown",
        "provider_status": provider.get("status", "not_available"),
        "provider": provider,
        "mode": mode,
        "baseline_status": "ok" if baseline.get("all_ok") else "blocked",
        "baseline": baseline,
        "frozen_hashes": baseline.get("frozen_hashes", {}),
        "prs": [],
        "actions_taken": [],
        "final_recommendation": "needs_human",
    }

    if provider.get("status") != "available":
        snapshot["final_recommendation"] = "provider_not_available"
        return snapshot

    if not baseline.get("all_ok"):
        snapshot["final_recommendation"] = "baseline_not_green"
        return snapshot

    if prs_override is not None:
        prs = prs_override
        list_err: str | None = None
    else:
        prs, list_err = list_open_prs(base="main")
    if list_err:
        snapshot["provider_status"] = "permission_denied"
        snapshot["provider"]["list_error"] = list_err
        snapshot["final_recommendation"] = "provider_error"
        return snapshot

    rows: list[dict[str, Any]] = []
    for pr in prs:
        number = int(pr.get("number") or 0)
        # Use the inspect call when files are not embedded in the list view.
        if fetch_inspect is not None:
            inspected, err_i = fetch_inspect(number)
        else:
            inspected, err_i = pr_inspect(number)
        if err_i:
            rows.append(_row_for_inspect_error(pr, err_i))
            continue
        files = pr_changed_files(inspected)
        if fetch_checks is not None:
            checks, err_c = fetch_checks(number)
        else:
            checks, err_c = pr_checks(number)
        if err_c:
            rows.append(_row_for_checks_error(pr, inspected, files, err_c))
            continue
        risk_class, risk_reason, package = classify_pr(inspected, files)
        decision = decide_for_pr(
            inspected,
            files,
            checks,
            risk_class=risk_class,
            risk_reason=risk_reason,
            baseline_ok=baseline.get("all_ok", False),
        )
        protected, _hit = diff_touches_protected(files)
        if not protected:
            protected, _hit = diff_touches_live_or_trading(files)
        rows.append(
            {
                "number": number,
                "title": inspected.get("title") or pr.get("title") or "",
                "author": _author_login(inspected),
                "base": inspected.get("baseRefName") or pr.get("baseRefName") or "",
                "branch": inspected.get("headRefName") or pr.get("headRefName") or "",
                "url": inspected.get("url") or pr.get("url") or "",
                "package": package,
                "risk_class": risk_class,
                "risk_reason": risk_reason,
                "merge_state": decision["merge_state"],
                "checks_state": decision["checks_state"],
                "protected_paths_touched": protected,
                "files_count": len(files),
                "additions": inspected.get("additions", 0),
                "deletions": inspected.get("deletions", 0),
                "decision": decision["decision"],
                "reason": decision["reason"],
                "actions_taken": [],
            }
        )

    snapshot["prs"] = rows

    # Final recommendation: how many can be safely acted on?
    mergeable = [r for r in rows if r["decision"] == "merge_allowed"]
    rebase = [r for r in rows if r["decision"] == "wait_for_rebase"]
    if mergeable:
        snapshot["final_recommendation"] = (
            f"merge_{len(mergeable)}_low_or_medium_prs"
        )
    elif rebase:
        snapshot["final_recommendation"] = (
            f"request_rebase_on_{len(rebase)}_behind_prs"
        )
    elif rows:
        snapshot["final_recommendation"] = "all_open_prs_blocked_or_waiting"
    else:
        snapshot["final_recommendation"] = "no_open_prs"

    return snapshot


def _row_for_inspect_error(pr: dict[str, Any], err: str) -> dict[str, Any]:
    return {
        "number": int(pr.get("number") or 0),
        "title": pr.get("title") or "",
        "author": _author_login(pr),
        "base": pr.get("baseRefName") or "",
        "branch": pr.get("headRefName") or "",
        "url": pr.get("url") or "",
        "package": None,
        "risk_class": "UNKNOWN",
        "risk_reason": f"inspect failed: {err}",
        "merge_state": "unknown",
        "checks_state": "unknown",
        "protected_paths_touched": False,
        "files_count": 0,
        "additions": 0,
        "deletions": 0,
        "decision": "blocked_unknown",
        "reason": f"PR inspect failed: {err}",
        "actions_taken": [],
    }


def _row_for_checks_error(
    pr: dict[str, Any],
    inspected: dict[str, Any],
    files: list[str],
    err: str,
) -> dict[str, Any]:
    return {
        "number": int(pr.get("number") or 0),
        "title": inspected.get("title") or pr.get("title") or "",
        "author": _author_login(inspected),
        "base": inspected.get("baseRefName") or "",
        "branch": inspected.get("headRefName") or "",
        "url": inspected.get("url") or "",
        "package": None,
        "risk_class": "UNKNOWN",
        "risk_reason": f"checks fetch failed: {err}",
        "merge_state": (inspected.get("mergeStateStatus") or "").lower() or "unknown",
        "checks_state": "unknown",
        "protected_paths_touched": diff_touches_protected(files)[0],
        "files_count": len(files),
        "additions": inspected.get("additions", 0),
        "deletions": inspected.get("deletions", 0),
        "decision": "blocked_unknown",
        "reason": f"PR checks fetch failed: {err}",
        "actions_taken": [],
    }


# ---------------------------------------------------------------------------
# Execute-safe runner
# ---------------------------------------------------------------------------


def execute_safe_actions(
    snapshot: dict[str, Any],
    *,
    do_comment: Any = None,
    do_merge: Any = None,
) -> dict[str, Any]:
    """Apply the proposed actions in execute-safe mode and return an
    updated snapshot.

    Hard guarantees:
      * Only acts on rows whose ``decision`` is ``merge_allowed`` or
        ``wait_for_rebase``.
      * Never merges a row whose ``risk_class`` is ``HIGH`` (defensive
        re-check; the planner already excluded these).
      * Never merges if ``protected_paths_touched`` is True.
      * Never merges if ``baseline_status`` is not ``ok``.
      * Never invokes ``git push`` directly.

    Both ``do_comment`` and ``do_merge`` are dependency-injected so
    the runner can be tested without making real GitHub calls.
    """
    if do_comment is None:
        do_comment = comment_dependabot_rebase
    if do_merge is None:
        do_merge = merge_squash

    if snapshot.get("baseline_status") != "ok":
        # Refuse to act on anything if the baseline is not green.
        snapshot["actions_taken"].append(
            {
                "kind": "abort",
                "target": "baseline",
                "outcome": "refused",
                "reason": "baseline_status != ok; refusing all mutations",
            }
        )
        return snapshot

    for row in snapshot.get("prs", []):
        if row["decision"] == "wait_for_rebase":
            ok, err = do_comment(row["number"])
            row["actions_taken"].append(
                {
                    "kind": "comment_dependabot_rebase",
                    "target": f"PR#{row['number']}",
                    "outcome": "ok" if ok else "error",
                    "reason": err or "comment posted",
                }
            )
            snapshot["actions_taken"].append(row["actions_taken"][-1])
            continue

        if row["decision"] != "merge_allowed":
            continue

        # Defense in depth — re-check every kill switch.
        if row["risk_class"] == RISK_HIGH:
            row["actions_taken"].append(
                {
                    "kind": "merge_squash",
                    "target": f"PR#{row['number']}",
                    "outcome": "refused",
                    "reason": "execute-safe never merges HIGH (defensive re-check)",
                }
            )
            snapshot["actions_taken"].append(row["actions_taken"][-1])
            continue
        if row["protected_paths_touched"]:
            row["actions_taken"].append(
                {
                    "kind": "merge_squash",
                    "target": f"PR#{row['number']}",
                    "outcome": "refused",
                    "reason": "execute-safe never merges a diff touching protected paths (defensive re-check)",
                }
            )
            snapshot["actions_taken"].append(row["actions_taken"][-1])
            continue
        if row["merge_state"] != "clean" or row["checks_state"] != "passed":
            row["actions_taken"].append(
                {
                    "kind": "merge_squash",
                    "target": f"PR#{row['number']}",
                    "outcome": "refused",
                    "reason": (
                        f"merge_state={row['merge_state']!r} "
                        f"checks_state={row['checks_state']!r}; "
                        "only CLEAN+passed are mergeable"
                    ),
                }
            )
            snapshot["actions_taken"].append(row["actions_taken"][-1])
            continue

        ok, err = do_merge(row["number"])
        row["actions_taken"].append(
            {
                "kind": "merge_squash",
                "target": f"PR#{row['number']}",
                "outcome": "ok" if ok else "error",
                "reason": err or "squash-merge succeeded",
            }
        )
        snapshot["actions_taken"].append(row["actions_taken"][-1])

    return snapshot


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def write_outputs(snapshot: dict[str, Any]) -> dict[str, str]:
    """Persist the JSON digest under ``logs/github_pr_lifecycle/``.
    Stable layout: ``latest.json`` + a timestamped copy."""
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


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.github_pr_lifecycle",
        description=(
            "GitHub PR Lifecycle + Dependabot cleanup playbook "
            "(read-only by default; execute-safe is bounded to "
            "@dependabot rebase comments and squash-merges of "
            "LOW/MEDIUM PRs only — never HIGH, never main, never "
            "force-push)."
        ),
    )
    p.add_argument(
        "--mode",
        choices=["dry-run", "execute-safe"],
        default="dry-run",
        help="Operating mode (default: dry-run).",
    )
    p.add_argument(
        "--no-smoke",
        action="store_true",
        help=(
            "Skip the local smoke-test gate. Only valid in dry-run; "
            "execute-safe always runs the full baseline."
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

    # In execute-safe we always run the full baseline regardless of
    # ``--no-smoke``; the operator cannot opt out of safety gates here.
    if args.mode == "execute-safe":
        snapshot = collect_snapshot(mode="execute-safe")
    else:
        if args.no_smoke:
            baseline = {
                "governance_lint": governance_lint_ok(),
                "smoke_tests": {"ok": True, "summary": "skipped (--no-smoke)"},
                "frozen_hashes": frozen_hashes(),
                "all_ok": True,
            }
            # Recompute all_ok properly (governance_lint returns tuple here).
            gov_ok, gov_sum = baseline["governance_lint"]
            baseline["governance_lint"] = {"ok": gov_ok, "summary": gov_sum}
            baseline["all_ok"] = gov_ok and all(
                v != "missing" for v in baseline["frozen_hashes"].values()
            )
            snapshot = collect_snapshot(mode="dry-run", baseline_override=baseline)
        else:
            snapshot = collect_snapshot(mode="dry-run")

    if args.mode == "execute-safe":
        snapshot = execute_safe_actions(snapshot)

    if not args.no_write:
        write_outputs(snapshot)

    indent = args.indent if args.indent and args.indent > 0 else None
    json.dump(snapshot, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
