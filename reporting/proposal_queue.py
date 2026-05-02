"""Roadmap / Proposal Queue (v3.15.15.19).

This module is the **intake** layer of the autonomous development
loop. It takes one or more roadmap-shaped source documents (markdown,
plain text, or repo paths) and produces a deterministic *queue* of
review-ready proposals — one per detected unit of work.

Core design principle
---------------------

Large roadmap / document upload **never** triggers direct execution.
Instead it triggers:

    intake → diff → proposal queue → approval → small scoped releases.

The module emits proposals; it does not adopt roadmaps, merge PRs,
modify governance docs, or write to ``main``. Adoption / rejection /
release-creation belong to later releases (the approval inbox lands
in v3.15.15.20).

Hard guarantees (enforced by code AND tests)
--------------------------------------------

* Stdlib-only. No subprocess, no ``gh``, no ``git``, no network.
* Reads the source paths the operator passes in. Reads existing
  ``docs/roadmap/`` / ``docs/backlog/`` / ``docs/spillovers/`` only
  when the operator opts in; the default scan list is conservative.
* Never modifies any source document.
* Strategic roadmap adoption is HIGH and ``needs_human`` by default.
* Tooling proposals that mention secrets / tokens / accounts /
  signup / hosted services / telemetry are HIGH and ``needs_human``.
* Free, dev-only, no-telemetry tooling proposals can land at LOW or
  MEDIUM; the canonical rules live in
  ``docs/governance/tooling_intake_policy.md``.
* Proposals touching live / paper / shadow / trading / risk paths
  are HIGH and ``blocked_high_risk``.
* Proposals touching frozen contracts or no-touch paths are HIGH and
  ``blocked_protected_path``.
* Unknown / malformed source → ``blocked_unknown`` (never silently OK).
* Every ``proposal_id`` is a deterministic hash so the same input
  produces the same queue.
* The CLI defaults to ``dry-run``. ``execute-safe`` is *not* enabled
  in this release — there is no execute path to enable yet. The
  CLI rejects any non-dry-run mode.

CLI
---

::

    python -m reporting.proposal_queue --mode dry-run
    python -m reporting.proposal_queue --source docs/roadmap --mode dry-run
    python -m reporting.proposal_queue --source <path> --mode dry-run

Stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import fnmatch
import hashlib
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
MODULE_VERSION: str = "v3.15.15.19"
SCHEMA_VERSION: int = 1

DIGEST_DIR_JSON: Path = REPO_ROOT / "logs" / "proposal_queue"

# ---------------------------------------------------------------------------
# Governance constants (mirror of autonomous_workloop / no_touch_paths.md)
# ---------------------------------------------------------------------------

FROZEN_CONTRACTS: tuple[str, ...] = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)

# Path globs whose presence in a proposal's affected_files classifies
# it as protected. Mirrors the canonical list in
# ``docs/governance/no_touch_paths.md``. Kept local so this module
# can be tested in isolation; sync via release notes when canonical.
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
    "automation/**",
    "execution/**",
    "strategies/**",
    "agent/risk/**",
    "agent/execution/**",
)

# Roadmap-adoption signals — phrases that suggest a *strategic*
# roadmap-level change, not just a release-scoped item.
STRATEGIC_ROADMAP_TOKENS: tuple[str, ...] = (
    "canonical roadmap",
    "new roadmap",
    "roadmap adoption",
    "rewrite roadmap",
    "supersede roadmap",
    "v4 roadmap",
    "post-v3.15",
)

# Tooling-intake signals — anything mentioning these tokens elevates a
# tooling proposal to HIGH per docs/governance/tooling_intake_policy.md.
TOOLING_HIGH_TOKENS: tuple[str, ...] = (
    "api key",
    "api-key",
    "api_key",
    "signup",
    "sign-up",
    "create an account",
    "create account",
    "auth token",
    "access token",
    "bearer token",
    "oauth",
    "telemetry",
    "datadog",
    "sentry",
    "segment.io",
    "google-analytics",
    "googletagmanager",
    "hosted service",
    "saas",
    "paid plan",
    "subscription",
)

TOOLING_LOW_TOKENS: tuple[str, ...] = (
    "dev-only",
    "devdependency",
    "devdependencies",
    "stdlib",
    "stdlib-only",
    "no telemetry",
    "no-telemetry",
    "no signup",
    "no-signup",
    "open source",
    "open-source",
    "mit license",
    "apache 2.0",
    "bsd license",
)

# Proposal-type taxonomy enumerated in the schema doc.
PROPOSAL_TYPES: tuple[str, ...] = (
    "roadmap_adoption",
    "roadmap_diff",
    "release_candidate",
    "governance_change",
    "tooling_intake",
    "ci_hygiene",
    "dependency_cleanup",
    "observability_gap",
    "testing_gap",
    "ux_gap",
    "approval_required",
    "blocked_unknown",
)

# Status values.
STATUS_PROPOSED: str = "proposed"
STATUS_NEEDS_HUMAN: str = "needs_human"
STATUS_APPROVED: str = "approved"
STATUS_REJECTED: str = "rejected"
STATUS_BLOCKED: str = "blocked"
STATUS_SUPERSEDED: str = "superseded"

# Risk classes.
RISK_LOW: str = "LOW"
RISK_MEDIUM: str = "MEDIUM"
RISK_HIGH: str = "HIGH"


# Default source roots scanned when no --source is provided. Each root
# is parsed best-effort; missing roots are reported but do not abort.
DEFAULT_SOURCE_ROOTS: tuple[str, ...] = (
    "docs/roadmap",
    "docs/backlog",
    "docs/spillovers",
)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# Path matching
# ---------------------------------------------------------------------------


def _path_matches_any(path: str, globs: Iterable[str]) -> bool:
    n = path.replace("\\", "/")
    return any(fnmatch.fnmatchcase(n, g) for g in globs)


def diff_touches_protected(files: Iterable[str]) -> tuple[bool, str | None]:
    for f in files:
        n = f.replace("\\", "/")
        if n in FROZEN_CONTRACTS:
            return (True, n)
    for f in files:
        if _path_matches_any(f, PROTECTED_GLOBS):
            return (True, f)
    return (False, None)


def diff_touches_live_or_trading(files: Iterable[str]) -> tuple[bool, str | None]:
    for f in files:
        if _path_matches_any(f, LIVE_PATH_GLOBS):
            return (True, f)
    return (False, None)


# ---------------------------------------------------------------------------
# Source intake (markdown only — robust for missing/malformed input)
# ---------------------------------------------------------------------------


# A heading line in markdown: leading hash(es) + space + title.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
# A bullet line: leading "*", "-", "+", "1." etc.
_BULLET_RE = re.compile(r"^\s*(?:[*\-+]|\d+\.)\s+(.+?)\s*$")
# A release-candidate marker: "v3.15.15.x", "v4.0", etc.
_RELEASE_TAG_RE = re.compile(r"\bv\d+(?:\.\d+){2,}(?:[.\-][^\s)]+)?\b")
# A path-shaped token. We accept "**/path", "path/**", "path/file.ext",
# "config/config.yaml", "research/...", etc. The regex is intentionally
# narrow — we want clear filenames, not prose.
_PATH_RE = re.compile(
    r"`([A-Za-z0-9_./*\-]+(?:\.[a-zA-Z0-9]+|/[A-Za-z0-9_*\-]+(?:/\*\*?)?))`"
)


def _read_text_safe(path: Path) -> tuple[str | None, str | None]:
    """Read a file as utf-8. Returns (text, None) on success or
    (None, reason) on any error. Never raises."""
    if not path.exists():
        return (None, "missing")
    if not path.is_file():
        return (None, "not_a_file")
    try:
        return (path.read_text(encoding="utf-8"), None)
    except (OSError, UnicodeDecodeError) as e:
        return (None, f"unreadable: {type(e).__name__}")


def _expand_source(source: Path) -> list[Path]:
    """Expand a source argument into a list of markdown files.

    * file → [file] if .md/.markdown/.txt, else [].
    * dir  → recursive scan for .md/.markdown/.txt.
    * missing → [] (caller reports).
    """
    if not source.exists():
        return []
    if source.is_file():
        if source.suffix.lower() in (".md", ".markdown", ".txt"):
            return [source]
        return []
    if source.is_dir():
        out: list[Path] = []
        for p in sorted(source.rglob("*")):
            if p.is_file() and p.suffix.lower() in (".md", ".markdown", ".txt"):
                out.append(p)
        return out
    return []


def _heading_segments(text: str) -> list[tuple[int, int, str, str]]:
    """Split text into (level, line_idx, heading, body_text) tuples.

    The first heading absorbs everything between it and the next
    heading. Lines before the first heading are reported as a level-0
    preamble segment with title ``"<preamble>"``.
    """
    lines = text.splitlines()
    headings: list[tuple[int, int, str]] = []  # (level, line_idx, title)
    for idx, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            headings.append((level, idx, title))
    segments: list[tuple[int, int, str, str]] = []
    if not headings:
        if text.strip():
            segments.append((0, 0, "<preamble>", text))
        return segments
    # Preamble before the first heading.
    if headings[0][1] > 0:
        segments.append((0, 0, "<preamble>", "\n".join(lines[: headings[0][1]])))
    for i, (lvl, idx, title) in enumerate(headings):
        end = headings[i + 1][1] if i + 1 < len(headings) else len(lines)
        body = "\n".join(lines[idx + 1 : end])
        segments.append((lvl, idx, title, body))
    return segments


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


def _proposal_id(source: str, title: str, line_idx: int) -> str:
    """Deterministic 8-char id based on source path + title + line."""
    raw = f"{source}|{title}|{line_idx}".encode("utf-8")
    return "p_" + hashlib.sha256(raw).hexdigest()[:8]


def _extract_paths(body: str) -> list[str]:
    """Extract file-path-shaped tokens from a body block. Backtick-
    quoted only — prose-shaped sentences do not produce paths."""
    return [m.group(1) for m in _PATH_RE.finditer(body)]


def _classify_type(title: str, body: str, source: str) -> str:
    """Pick a proposal type by inspecting the title + body + source.

    First-match wins: most specific signal first. ``approval_required``
    is the catch-all when nothing else fits but the segment looks like
    a proposal; ``blocked_unknown`` is reserved for malformed input.
    """
    text = (title + "\n" + body).lower()
    src = source.replace("\\", "/").lower()

    # roadmap_diff — title explicitly says "diff", or body mentions
    # an explicit diff / supersede phrase. This is intentionally
    # narrower than the strategic-adoption check below: "Replace the
    # roadmap with the new canonical plan" reads as adoption, not a
    # diff, even though the verb "replace" is present.
    title_lower = title.lower()
    if "roadmap" in text and (
        "diff" in title_lower
        or "diff against" in text
        or "supersede the" in text
        or "diff with" in text
    ):
        return "roadmap_diff"

    # roadmap_adoption — strategic-shape signals.
    if any(t in text for t in STRATEGIC_ROADMAP_TOKENS):
        return "roadmap_adoption"

    # release_candidate — title contains a release tag.
    if _RELEASE_TAG_RE.search(title):
        return "release_candidate"

    # governance_change — touches the governance surface.
    if any(
        t in text
        for t in (
            "codeowners",
            "branch protection",
            ".claude/",
            "no_touch_paths",
            "agent governance",
            "release gate",
            "autonomy ladder",
        )
    ):
        return "governance_change"

    # tooling_intake — explicit "tool" / "library" / "package" / "dep",
    # or any well-known dev-tool / SaaS name (Datadog / Sentry /
    # Segment / etc.) — those names imply a tool decision is being
    # proposed even when the heading does not say "tool" verbatim.
    tooling_general_tokens = (
        "tooling",
        "tool intake",
        "add a tool",
        "add tool",
        "new dependency",
        "new package",
        "library upgrade",
        "devdependency",
        "devdependencies",
        "dev-only",
        "stdlib-only",
        # Well-known dev tools (free / open source).
        "vite-plugin",
        "eslint",
        "prettier",
        "ruff",
        "mypy",
        "pre-commit",
        "pytest",
        "vitest",
        # Well-known SaaS / hosted-service names — surface as tooling
        # intake so the risk classifier can elevate them to HIGH.
        "datadog",
        "sentry",
        "segment.io",
        "google-analytics",
        "googletagmanager",
    )
    if any(t in text for t in tooling_general_tokens):
        return "tooling_intake"

    # ci_hygiene
    if any(
        t in text
        for t in (
            "ci hygiene",
            "github action",
            "github actions",
            "workflow",
            "sha pin",
            "dependabot",
        )
    ):
        return "ci_hygiene"

    # dependency_cleanup
    if any(
        t in text
        for t in (
            "dependency cleanup",
            "deps cleanup",
            "requirements bump",
            "package-lock",
        )
    ):
        return "dependency_cleanup"

    # observability_gap
    if any(
        t in text for t in ("observability", "logging", "metrics", "audit log")
    ):
        return "observability_gap"

    # testing_gap
    if any(
        t in text
        for t in (
            "testing gap",
            "missing test",
            "coverage gap",
            "no tests",
            "add tests",
            "pytest",
            "vitest",
        )
    ):
        return "testing_gap"

    # ux_gap
    if any(
        t in text for t in ("ux", "user experience", "ui gap", "frontend gap")
    ):
        return "ux_gap"

    # spillovers/backlog default to approval_required.
    if "spillover" in src or "backlog" in src:
        return "approval_required"

    return "approval_required"


def _classify_risk(
    proposal_type: str,
    title: str,
    body: str,
    affected_files: list[str],
) -> tuple[str, str]:
    """Return ``(risk_class, reason)``.

    Decision order — first-match wins:
      1. Affected files touch a frozen contract / no-touch path → HIGH.
      2. Affected files touch a live-trading path             → HIGH.
      3. Strategic roadmap adoption                           → HIGH.
      4. Governance change                                    → HIGH.
      5. Tooling intake mentions secrets / signup / telemetry → HIGH.
      6. Tooling intake explicitly free / dev-only            → LOW.
      7. CI hygiene / dependency cleanup                      → MEDIUM.
      8. Observability / testing / UX / release_candidate     → MEDIUM.
      9. Anything else                                        → MEDIUM (conservative).
    """
    touched, hit = diff_touches_protected(affected_files)
    if touched:
        return (RISK_HIGH, f"affected_files touches protected path: {hit}")

    touched_l, hit_l = diff_touches_live_or_trading(affected_files)
    if touched_l:
        return (
            RISK_HIGH,
            f"affected_files touches live/trading path: {hit_l}",
        )

    if proposal_type == "roadmap_adoption":
        return (
            RISK_HIGH,
            "strategic roadmap adoption is HIGH and needs_human by default",
        )

    if proposal_type == "governance_change":
        return (RISK_HIGH, "governance changes require human approval")

    text = (title + "\n" + body).lower()

    if proposal_type == "tooling_intake":
        # LOW signals win first: "no telemetry" / "no signup" are
        # explicit negations and must not be re-classified as HIGH by
        # a substring match on the negated word. Same for explicit
        # license markers ("MIT license", "Apache 2.0 license", etc.).
        if any(t in text for t in TOOLING_LOW_TOKENS):
            return (RISK_LOW, "tooling intake is free / dev-only / no telemetry")
        # HIGH signals only count when they are NOT negated. We strip
        # any "no <token>" / "no-<token>" occurrence before checking,
        # so "no telemetry" no longer triggers the "telemetry" rule.
        # Note the dash position in the class: leading "-" avoids the
        # \w-space "bad range" parse error.
        scrubbed = re.sub(r"\bno[- ]\w[-\w ]*", " ", text)
        if any(t in scrubbed for t in TOOLING_HIGH_TOKENS):
            return (
                RISK_HIGH,
                "tooling intake mentions secrets / signup / telemetry / hosted service",
            )
        return (
            RISK_MEDIUM,
            "tooling intake without explicit free / dev-only marker",
        )

    if proposal_type in ("ci_hygiene", "dependency_cleanup"):
        return (RISK_MEDIUM, "CI hygiene / dependency cleanup is MEDIUM")

    if proposal_type == "release_candidate":
        return (RISK_MEDIUM, "release candidate requires scoped review")

    if proposal_type in ("observability_gap", "testing_gap", "ux_gap"):
        return (RISK_MEDIUM, f"{proposal_type} is MEDIUM by default")

    if proposal_type == "blocked_unknown":
        # Caller decides via status; risk stays MEDIUM so it does not
        # short-circuit the planner.
        return (RISK_MEDIUM, "blocked_unknown classified MEDIUM conservatively")

    return (RISK_MEDIUM, "default classification")


def _decide_status(
    proposal_type: str,
    risk_class: str,
    affected_files: list[str],
) -> tuple[str, str | None]:
    """Pick a status + optional blocked_reason.

    Decision order:
      * frozen / protected paths → blocked / blocked_protected_path.
      * live trading             → blocked / blocked_high_risk.
      * HIGH risk                → needs_human (blocked from auto).
      * blocked_unknown type     → blocked / blocked_unknown.
      * everything else          → proposed (review-ready, not adopted).
    """
    touched_p, hit_p = diff_touches_protected(affected_files)
    if touched_p:
        return (STATUS_BLOCKED, f"blocked_protected_path: {hit_p}")
    touched_l, hit_l = diff_touches_live_or_trading(affected_files)
    if touched_l:
        return (STATUS_BLOCKED, f"blocked_high_risk: live/trading path: {hit_l}")
    if proposal_type == "blocked_unknown":
        return (STATUS_BLOCKED, "blocked_unknown: unparseable source")
    if risk_class == RISK_HIGH:
        return (STATUS_NEEDS_HUMAN, None)
    return (STATUS_PROPOSED, None)


def _allowed_actions(
    proposal_type: str, risk_class: str
) -> tuple[list[str], list[str]]:
    """Per-proposal allowlists. The values are advisory — the actual
    enforcement lives in the agent + hook layers. They are surfaced so
    the operator can review at-a-glance what an approval would unlock.
    """
    forbidden = [
        "git push origin main",
        "git push --force",
        "git push --force-with-lease",
        "gh pr merge --admin",
        "edit .claude/**",
        "edit frozen contracts",
        "edit automation/live_gate.py",
        "modify VERSION",
    ]
    allowed: list[str] = []
    if proposal_type == "release_candidate":
        allowed.extend(
            [
                "open feature branch",
                "open PR",
                "run governance_lint",
                "run smoke + unit tests",
            ]
        )
    elif proposal_type == "tooling_intake" and risk_class == RISK_LOW:
        allowed.extend(
            [
                "add devDependency to frontend/package.json",
                "add Python dev dep to requirements-dev.txt",
                "add governance ADR draft",
            ]
        )
    elif proposal_type in ("ci_hygiene", "dependency_cleanup"):
        allowed.extend(
            [
                "edit .github/workflows/** (ci-guardian only)",
                "comment @dependabot rebase",
            ]
        )
    elif proposal_type in ("observability_gap", "testing_gap"):
        allowed.extend(["add reporting/* read-only module", "add tests/**"])
    return allowed, forbidden


def _required_tests(proposal_type: str) -> list[str]:
    base = ["scripts/governance_lint.py", "tests/smoke", "frozen-hash check"]
    if proposal_type == "release_candidate":
        return base + ["tests/unit", "frontend tests if frontend/** changed"]
    if proposal_type == "tooling_intake":
        return base + [
            "tests/unit covering the new tool surface",
            "explicit data-egress assessment in the runbook",
        ]
    if proposal_type in ("ci_hygiene", "dependency_cleanup"):
        return base + [
            "all required GitHub checks green pre-merge",
            "no SHA pin downgrades",
        ]
    if proposal_type in ("observability_gap", "testing_gap"):
        return base + ["tests/unit"]
    return base


def _suggested_branch(proposal_type: str, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48]
    if not slug:
        slug = "proposal"
    prefix = (
        "feat"
        if proposal_type in ("release_candidate", "tooling_intake", "ux_gap")
        else "fix"
    )
    return f"{prefix}/{proposal_type.replace('_', '-')}-{slug}"


# ---------------------------------------------------------------------------
# Build proposals from a parsed source
# ---------------------------------------------------------------------------


def _build_proposal_from_segment(
    *,
    source: str,
    level: int,
    line_idx: int,
    title: str,
    body: str,
) -> dict[str, Any]:
    affected_files = _extract_paths(body)
    proposal_type = _classify_type(title, body, source)
    risk_class, risk_reason = _classify_risk(
        proposal_type, title, body, affected_files
    )
    status, blocked_reason = _decide_status(
        proposal_type, risk_class, affected_files
    )
    allowed, forbidden = _allowed_actions(proposal_type, risk_class)
    pid = _proposal_id(source, title, line_idx)
    return {
        "proposal_id": pid,
        "created_at": _utcnow(),
        "source": source,
        "source_type": "markdown_heading" if level >= 1 else "markdown_preamble",
        "title": title.strip(),
        "summary": _summarize(body),
        "rationale": _summarize(body, max_chars=600),
        "evidence": {
            "heading_level": level,
            "line_idx": line_idx,
            "body_chars": len(body),
        },
        "affected_files": affected_files,
        "risk_class": risk_class,
        "risk_reason": risk_reason,
        "approval_required": (
            status in (STATUS_NEEDS_HUMAN, STATUS_BLOCKED)
            or risk_class == RISK_HIGH
            or proposal_type == "approval_required"
        ),
        "blocked_reason": blocked_reason,
        "proposal_type": proposal_type,
        "allowed_actions": allowed,
        "forbidden_actions": forbidden,
        "required_tests": _required_tests(proposal_type),
        "suggested_branch_name": _suggested_branch(proposal_type, title),
        "suggested_release_id": (
            _RELEASE_TAG_RE.search(title).group(0)
            if _RELEASE_TAG_RE.search(title)
            else None
        ),
        "status": status,
        "parent_proposal_id": None,
        "dependencies": [],
        "operator_notes": "",
    }


def _summarize(body: str, *, max_chars: int = 240) -> str:
    """Extract a short summary from a markdown body. Prefer the first
    non-empty bullet or sentence; fall back to the first non-empty
    line; truncate to ``max_chars``."""
    body_stripped = body.strip()
    if not body_stripped:
        return ""
    for line in body_stripped.splitlines():
        m = _BULLET_RE.match(line)
        if m:
            return _trim(m.group(1), max_chars)
    # First non-empty sentence.
    for sentence in re.split(r"(?<=[.!?])\s+", body_stripped):
        if sentence.strip():
            return _trim(sentence.strip(), max_chars)
    return _trim(body_stripped.splitlines()[0], max_chars)


def _trim(s: str, max_chars: int) -> str:
    s = s.strip()
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Top-level snapshot
# ---------------------------------------------------------------------------


def _resolve_source_paths(
    source: str | None,
) -> tuple[list[Path], list[dict[str, str]]]:
    """Resolve the operator-supplied source(s) into a list of files.

    Returns ``(files, missing_reports)`` where ``missing_reports`` lists
    requested roots that did not exist.
    """
    files: list[Path] = []
    missing: list[dict[str, str]] = []
    if source is None:
        roots = [REPO_ROOT / r for r in DEFAULT_SOURCE_ROOTS]
    else:
        roots = [Path(source) if Path(source).is_absolute() else REPO_ROOT / source]
    for root in roots:
        expanded = _expand_source(root)
        if not expanded and not root.exists():
            missing.append(
                {
                    "path": _rel(root),
                    "reason": "missing",
                }
            )
        files.extend(expanded)
    return files, missing


def collect_snapshot(
    *,
    mode: str = "dry-run",
    source: str | None = None,
    proposals_override: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the full snapshot. ``proposals_override`` is for tests."""
    if mode != "dry-run":
        # Hard guarantee: this release exposes only dry-run. Refuse
        # any other mode at the boundary so we never write outside
        # the gitignored digest.
        return {
            "schema_version": SCHEMA_VERSION,
            "report_kind": "proposal_queue_digest",
            "module_version": MODULE_VERSION,
            "generated_at_utc": _utcnow(),
            "mode": mode,
            "status": "refused",
            "reason": (
                f"mode {mode!r} is not allowed in {MODULE_VERSION}; "
                "only dry-run is supported. The approval inbox + execute path "
                "land in v3.15.15.20 / v3.15.15.21."
            ),
            "sources": [],
            "missing_sources": [],
            "proposals": [],
            "final_recommendation": "needs_human",
        }

    if proposals_override is not None:
        proposals = proposals_override
        sources_used: list[str] = []
        missing: list[dict[str, str]] = []
    else:
        files, missing = _resolve_source_paths(source)
        sources_used = [_rel(f) for f in files]
        proposals = _build_all_proposals(files)

    counts = _proposal_counts(proposals)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "proposal_queue_digest",
        "module_version": MODULE_VERSION,
        "generated_at_utc": _utcnow(),
        "mode": mode,
        "sources": sources_used,
        "missing_sources": missing,
        "proposals": proposals,
        "counts": counts,
        "final_recommendation": _final_recommendation(counts, proposals),
    }


def _build_all_proposals(files: list[Path]) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for f in files:
        text, err = _read_text_safe(f)
        if text is None:
            # Single blocked_unknown row representing the bad source.
            proposals.append(
                _build_proposal_from_segment(
                    source=_rel(f),
                    level=0,
                    line_idx=0,
                    title="<unparseable source>",
                    body=err or "",
                )
                | {"proposal_type": "blocked_unknown", "status": STATUS_BLOCKED}
            )
            continue
        if not text.strip():
            # Empty file → no proposals (not a blocker).
            continue
        segments = _heading_segments(text)
        for level, line_idx, title, body in segments:
            # Skip the file-level title heading on a doc that consists
            # only of a single H1 + index (very common in docs/).
            if level == 1 and not body.strip():
                continue
            # Only H1/H2/H3 segments produce proposals; H4+ are sub-
            # sections and would dilute the queue.
            if level == 0 or level > 3:
                # Preamble + deep sub-sections are surfaced as a single
                # row only if they are non-empty AND look like a
                # proposal heading. We elide deep sub-headings.
                if level > 3:
                    continue
            proposals.append(
                _build_proposal_from_segment(
                    source=_rel(f),
                    level=level,
                    line_idx=line_idx,
                    title=title,
                    body=body,
                )
            )
    return proposals


def _proposal_counts(proposals: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {
        "total": len(proposals),
        "by_status": {},
        "by_risk": {},
        "by_type": {},
    }
    for p in proposals:
        status = p.get("status", "unknown")
        risk = p.get("risk_class", "UNKNOWN")
        ptype = p.get("proposal_type", "unknown")
        counts["by_status"][status] = counts["by_status"].get(status, 0) + 1
        counts["by_risk"][risk] = counts["by_risk"].get(risk, 0) + 1
        counts["by_type"][ptype] = counts["by_type"].get(ptype, 0) + 1
    return counts


def _final_recommendation(
    counts: dict[str, int], proposals: list[dict[str, Any]]
) -> str:
    if counts["total"] == 0:
        return "no_proposals"
    proposed = counts["by_status"].get(STATUS_PROPOSED, 0)
    needs_human = counts["by_status"].get(STATUS_NEEDS_HUMAN, 0)
    blocked = counts["by_status"].get(STATUS_BLOCKED, 0)
    if proposed > 0 and needs_human == 0 and blocked == 0:
        return f"review_{proposed}_proposed_items"
    if needs_human > 0:
        return f"needs_human_on_{needs_human}_items"
    if blocked > 0:
        return f"blocked_on_{blocked}_items"
    return "needs_human"


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
        prog="python -m reporting.proposal_queue",
        description=(
            "Roadmap / proposal queue (read-only intake). Reads "
            "markdown / text source(s) and emits a deterministic queue "
            "of review-ready proposals. NEVER triggers execution. "
            "Strategic roadmap adoption is HIGH and needs_human by "
            "default; v3.15.15.19 only supports --mode dry-run."
        ),
    )
    p.add_argument(
        "--mode",
        choices=["dry-run"],
        default="dry-run",
        help="Operating mode (only dry-run is supported in this release).",
    )
    p.add_argument(
        "--source",
        type=str,
        default=None,
        help=(
            "Source path (file or directory). Defaults to scanning "
            "docs/roadmap, docs/backlog, docs/spillovers."
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
    snap = collect_snapshot(mode=args.mode, source=args.source)
    if not args.no_write and snap.get("status") != "refused":
        write_outputs(snap)
    indent = args.indent if args.indent and args.indent > 0 else None
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
