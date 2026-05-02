"""Approval / exception inbox (v3.15.15.20).

This module is the read-only **inbox surface** of the autonomous
development loop. It does not approve, reject, or mutate anything —
it merely collects every needs_human / blocked / high-risk / unknown
item from the upstream JSON artifacts (proposal queue, GitHub PR
lifecycle, autonomous workloop, governance status) and projects them
into a single deterministic queue tagged with one of the canonical
inbox categories.

Core design principle
---------------------

* The system may **prepare** decisions, evidence, and recommended
  next actions.
* Only the operator can **approve** strategic / canonical / HIGH /
  protected actions.
* Unknown state is **never safe** — a missing or malformed source
  produces an ``unknown_state`` item, never silently OK.

Hard guarantees (enforced by code AND tests)
--------------------------------------------

* Stdlib-only. No subprocess, no ``gh``, no ``git``, no network.
* Reads JSON artifacts produced by sibling reporters; calls
  ``governance_status.collect_status`` and
  ``agent_audit_summary.collect_timeline`` in-process for fresh
  signals. Never invokes any CLI.
* Every payload goes through ``assert_no_secrets`` before it
  becomes an inbox item.
* This release exposes only ``--mode dry-run`` — any other mode is
  refused at the CLI boundary.
* Status changes (``acknowledged`` / ``resolved`` / ``superseded``)
  are part of the schema for v3.15.15.21+, but this release only
  emits ``open`` and ``blocked``.
* Emits a deterministic ``item_id`` (sha256 over source +
  item_key) so the same inputs always produce the same queue.

CLI
---

::

    python -m reporting.approval_inbox --mode dry-run
    python -m reporting.approval_inbox --no-write --indent 2

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

from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
MODULE_VERSION: str = "v3.15.15.20"
SCHEMA_VERSION: int = 1

DIGEST_DIR_JSON: Path = REPO_ROOT / "logs" / "approval_inbox"

# Source artifact locations (gitignored). Each is best-effort: a
# missing artifact emits an ``unknown_state`` item and the run keeps
# going.
SOURCE_PROPOSAL_QUEUE: Path = REPO_ROOT / "logs" / "proposal_queue" / "latest.json"
SOURCE_PR_LIFECYCLE: Path = (
    REPO_ROOT / "logs" / "github_pr_lifecycle" / "latest.json"
)
SOURCE_WORKLOOP: Path = REPO_ROOT / "logs" / "autonomous_workloop" / "latest.json"
SOURCE_WORKLOOP_RUNTIME: Path = (
    REPO_ROOT / "logs" / "workloop_runtime" / "latest.json"
)

# Canonical inbox categories (18 per the v3.15.15.20 brief).
CATEGORIES: tuple[str, ...] = (
    "roadmap_adoption_required",
    "high_risk_pr",
    "protected_path_change",
    "governance_change",
    "tooling_requires_approval",
    "external_account_or_secret_required",
    "telemetry_or_data_egress_required",
    "paid_tool_required",
    "frozen_contract_risk",
    "live_paper_shadow_risk_change",
    "ci_or_test_weakening_risk",
    "unknown_state",
    "failed_automation",
    "blocked_rebase",
    "blocked_checks",
    "runtime_halt",
    "security_alert",
    "manual_route_wiring_required",
)

# Severity scale.
SEVERITIES: tuple[str, ...] = ("info", "low", "medium", "high", "critical")

# Status values (read-only emitter in this release).
STATUS_OPEN: str = "open"
STATUS_ACK: str = "acknowledged"
STATUS_BLOCKED: str = "blocked"
STATUS_RESOLVED: str = "resolved"
STATUS_SUPERSEDED: str = "superseded"

# Frozen / no-touch / live-trading globs (mirror of the canonical
# governance lists). Kept local so the module is self-contained.
FROZEN_CONTRACTS: tuple[str, ...] = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)
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


# Default forbidden agent actions surfaced on every inbox item — the
# universal hard-no list that the operator can rely on regardless of
# what an item is asking.
_FORBIDDEN_AGENT_ACTIONS: tuple[str, ...] = (
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
)


# ---------------------------------------------------------------------------
# Time / hash helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _item_id(source: str, item_key: str) -> str:
    raw = f"{source}|{item_key}".encode("utf-8")
    return "i_" + hashlib.sha256(raw).hexdigest()[:8]


def _path_matches_any(path: str, globs: Iterable[str]) -> bool:
    n = path.replace("\\", "/")
    return any(fnmatch.fnmatchcase(n, g) for g in globs)


# ---------------------------------------------------------------------------
# Source readers
# ---------------------------------------------------------------------------


def _read_json_artifact(path: Path) -> dict[str, Any]:
    """Return ``{status: ok|not_available, ...}``. Never raises."""
    if not path.exists():
        return {
            "status": "not_available",
            "path": _rel(path),
            "reason": "missing",
            "data": None,
        }
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return {
            "status": "not_available",
            "path": _rel(path),
            "reason": f"unreadable: {type(e).__name__}",
            "data": None,
        }
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return {
            "status": "not_available",
            "path": _rel(path),
            "reason": f"malformed: {type(e).__name__}",
            "data": None,
        }
    if not isinstance(data, dict):
        return {
            "status": "not_available",
            "path": _rel(path),
            "reason": "malformed: not_an_object",
            "data": None,
        }
    return {"status": "ok", "path": _rel(path), "reason": None, "data": data}


def _governance_status_safe() -> dict[str, Any]:
    """Best-effort governance status without raising. Returns the same
    envelope shape as ``_read_json_artifact``."""
    try:
        from reporting.governance_status import (
            collect_status,
            assert_no_secrets as _gov_assert_no_secrets,
        )

        snap = collect_status()
        _gov_assert_no_secrets(snap)
        return {
            "status": "ok",
            "path": "governance_status:in_process",
            "reason": None,
            "data": snap,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "status": "not_available",
            "path": "governance_status:in_process",
            "reason": f"governance_status_error: {type(e).__name__}",
            "data": None,
        }


# ---------------------------------------------------------------------------
# Categorization helpers
# ---------------------------------------------------------------------------


def _diff_touches_protected(files: Iterable[str]) -> tuple[bool, str | None]:
    for f in files:
        n = f.replace("\\", "/")
        if n in FROZEN_CONTRACTS:
            return (True, n)
    for f in files:
        if _path_matches_any(f, PROTECTED_GLOBS):
            return (True, f)
    return (False, None)


def _diff_touches_live_or_trading(files: Iterable[str]) -> tuple[bool, str | None]:
    for f in files:
        if _path_matches_any(f, LIVE_PATH_GLOBS):
            return (True, f)
    return (False, None)


def _diff_touches_frozen(files: Iterable[str]) -> tuple[bool, str | None]:
    for f in files:
        n = f.replace("\\", "/")
        if n in FROZEN_CONTRACTS:
            return (True, n)
    return (False, None)


# Tooling-intake category disambiguation: given a proposal that
# classifies as a HIGH tooling intake, decide which of the four
# canonical "external dependency" categories it belongs to.
_TOOLING_TOKENS = {
    "external_account_or_secret_required": (
        "api key",
        "api-key",
        "api_key",
        "auth token",
        "access token",
        "bearer token",
        "oauth",
        "signup",
        "sign-up",
        "create an account",
        "create account",
    ),
    "telemetry_or_data_egress_required": (
        "telemetry",
        "datadog",
        "sentry",
        "segment.io",
        "google-analytics",
        "googletagmanager",
        "data egress",
    ),
    "paid_tool_required": (
        "paid plan",
        "subscription",
        "saas",
        "hosted service",
    ),
}


def _tooling_subcategory(title: str, body: str) -> str:
    text = (title + "\n" + body).lower()
    # Negation-aware: strip "no <token>" / "no-<token>" before checks.
    scrubbed = re.sub(r"\bno[- ]\w[-\w ]*", " ", text)
    for cat, tokens in _TOOLING_TOKENS.items():
        if any(t in scrubbed for t in tokens):
            return cat
    return "tooling_requires_approval"


def _severity_for_category(category: str) -> str:
    """Map an inbox category to a default severity."""
    if category in (
        "live_paper_shadow_risk_change",
        "frozen_contract_risk",
        "runtime_halt",
        "security_alert",
    ):
        return "critical"
    if category in (
        "roadmap_adoption_required",
        "high_risk_pr",
        "protected_path_change",
        "governance_change",
        "external_account_or_secret_required",
        "telemetry_or_data_egress_required",
        "paid_tool_required",
        "ci_or_test_weakening_risk",
        "failed_automation",
    ):
        return "high"
    if category in (
        "tooling_requires_approval",
        "blocked_checks",
        "blocked_rebase",
    ):
        return "medium"
    if category in ("manual_route_wiring_required",):
        return "low"
    if category == "unknown_state":
        return "medium"
    return "info"


def _recommended_action(category: str) -> str:
    return {
        "roadmap_adoption_required": "review the strategic roadmap proposal; only adopt via a human-authored PR",
        "high_risk_pr": "review the PR; HIGH-risk PRs are inspect-only in the lifecycle module",
        "protected_path_change": "open a governance-bootstrap PR; CODEOWNERS review required",
        "governance_change": "review the governance change; needs CODEOWNERS sign-off",
        "tooling_requires_approval": "review the tooling proposal against docs/governance/tooling_intake_policy.md",
        "external_account_or_secret_required": "operator decides whether to create the account / handle the secret manually",
        "telemetry_or_data_egress_required": "operator decides whether telemetry / data egress is acceptable; review privacy posture",
        "paid_tool_required": "operator decides on the paid plan; do not subscribe automatically",
        "frozen_contract_risk": "operator decides whether the contract regen is intentional; signed-off via release notes",
        "live_paper_shadow_risk_change": "operator decides; live trading flow changes never auto-merge",
        "ci_or_test_weakening_risk": "block; do not weaken CI / tests",
        "unknown_state": "operator inspects the source; rerun the upstream reporter",
        "failed_automation": "operator inspects the failure; rerun the upstream reporter",
        "blocked_rebase": "operator confirms rebase is appropriate (Dependabot canonical comment is the safe path)",
        "blocked_checks": "operator inspects failing checks before any further action",
        "runtime_halt": "operator inspects the halt; do not auto-restart trading flow",
        "security_alert": "operator inspects the alert; defense in depth before remediation",
        "manual_route_wiring_required": "add the documented one-line register_*_routes call to dashboard/dashboard.py via a human-authored PR",
    }.get(category, "operator inspects manually")


# ---------------------------------------------------------------------------
# Builders — one function per upstream source
# ---------------------------------------------------------------------------


def _build_from_proposal_queue(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    """Project proposal_queue items into inbox items. Returns []
    when the source is not_available; the caller emits the
    not_available row separately."""
    if envelope["status"] != "ok" or not envelope.get("data"):
        return []
    proposals = envelope["data"].get("proposals") or []
    items: list[dict[str, Any]] = []
    for p in proposals:
        if not isinstance(p, dict):
            continue
        ptype = p.get("proposal_type") or "approval_required"
        risk = p.get("risk_class") or "MEDIUM"
        status = p.get("status") or "proposed"
        files = list(p.get("affected_files") or [])
        title = p.get("title") or "(no title)"
        summary = p.get("summary") or ""
        proposal_id = p.get("proposal_id")

        # Category resolution — first-match wins, matching the
        # proposal_queue precedence.
        if _diff_touches_frozen(files)[0]:
            category = "frozen_contract_risk"
        elif _diff_touches_protected(files)[0]:
            category = "protected_path_change"
        elif _diff_touches_live_or_trading(files)[0]:
            category = "live_paper_shadow_risk_change"
        elif ptype == "roadmap_adoption":
            category = "roadmap_adoption_required"
        elif ptype == "governance_change":
            category = "governance_change"
        elif ptype == "tooling_intake" and risk == "HIGH":
            category = _tooling_subcategory(title, summary)
        elif ptype == "tooling_intake":
            # Non-HIGH tooling intake doesn't require approval per
            # docs/governance/tooling_intake_policy.md (LOW path).
            # We do NOT emit an inbox item for these — they flow as
            # normal proposed work.
            continue
        elif ptype == "blocked_unknown" or status == "blocked":
            # blocked status with non-protected/non-live cause →
            # unknown_state. (Protected/live causes were handled
            # above via affected_files.)
            category = "unknown_state"
        elif risk == "HIGH" or status == "needs_human":
            # Generic HIGH / needs_human catch-all.
            category = "tooling_requires_approval"
        else:
            # Plain proposed items don't go to the inbox.
            continue

        item_status = STATUS_BLOCKED if status == "blocked" else STATUS_OPEN
        items.append(
            _build_item(
                source=f"proposal_queue:{proposal_id}",
                source_type="proposal",
                title=title,
                summary=summary,
                category=category,
                risk_class=risk,
                status=item_status,
                affected_files=files,
                evidence={"proposal_type": ptype, "proposal_status": status},
                related_proposal_id=proposal_id,
            )
        )
    return items


def _build_from_pr_lifecycle(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    if envelope["status"] != "ok" or not envelope.get("data"):
        return []
    prs = envelope["data"].get("prs") or []
    items: list[dict[str, Any]] = []
    for pr in prs:
        if not isinstance(pr, dict):
            continue
        decision = pr.get("decision") or "unknown"
        risk = pr.get("risk_class") or "UNKNOWN"
        number = pr.get("number")
        title = pr.get("title") or f"PR #{number}"
        url = pr.get("url") or ""
        protected = bool(pr.get("protected_paths_touched"))
        if decision == "merge_allowed":
            # No inbox row needed — merge is allowed by policy.
            continue
        if decision == "blocked_protected_path" or protected:
            category = "protected_path_change"
        elif decision == "blocked_high_risk" or risk == "HIGH":
            category = "high_risk_pr"
        elif decision == "blocked_failing_checks":
            category = "blocked_checks"
        elif decision == "blocked_conflict":
            category = "failed_automation"
        elif decision == "wait_for_rebase":
            category = "blocked_rebase"
        elif decision == "wait_for_checks":
            # Pending checks are not approval items.
            continue
        elif decision == "blocked_unknown":
            category = "unknown_state"
        elif decision == "needs_human":
            category = "tooling_requires_approval"
        else:
            continue
        items.append(
            _build_item(
                source=f"pr_lifecycle:#{number}",
                source_type="pr",
                title=title,
                summary=pr.get("reason") or pr.get("risk_reason") or "",
                category=category,
                risk_class=risk,
                status=STATUS_BLOCKED if decision.startswith("blocked_") else STATUS_OPEN,
                affected_files=[],
                evidence={"decision": decision, "url": url},
                related_pr_number=number,
            )
        )
    return items


def _build_from_workloop(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    if envelope["status"] != "ok" or not envelope.get("data"):
        return []
    items: list[dict[str, Any]] = []
    queue_keys = ("pr_queue", "dependabot_queue")
    for qk in queue_keys:
        for row in envelope["data"].get(qk) or []:
            if not isinstance(row, dict):
                continue
            risk = row.get("risk_class") or ""
            decision = row.get("decision") or ""
            item_id = row.get("item_id") or row.get("branch_or_pr") or "unknown"
            if risk == "blocked_conflict":
                category = "failed_automation"
            elif risk == "needs_human_protected_governance":
                category = "protected_path_change"
            elif risk == "needs_human_contract_risk":
                category = "frozen_contract_risk"
            elif risk == "needs_human_trading_or_risk":
                category = "live_paper_shadow_risk_change"
            elif risk == "unknown" or decision == "needs_human":
                category = "unknown_state"
            else:
                continue
            items.append(
                _build_item(
                    source=f"workloop:{item_id}",
                    source_type="workloop",
                    title=row.get("title") or item_id,
                    summary=row.get("reason") or "",
                    category=category,
                    risk_class="HIGH",
                    status=STATUS_BLOCKED if category == "failed_automation" else STATUS_OPEN,
                    affected_files=[],
                    evidence={"workloop_risk_class": risk, "workloop_decision": decision},
                )
            )
    return items


def _build_from_governance_status(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    if envelope["status"] != "ok" or not envelope.get("data"):
        return []
    snap = envelope["data"]
    items: list[dict[str, Any]] = []
    audit = snap.get("audit_chain_status") or {}
    if isinstance(audit, dict) and audit.get("status") == "broken":
        items.append(
            _build_item(
                source="governance_status:audit_chain",
                source_type="governance",
                title="Audit chain broken",
                summary=f"first_corrupt_index={audit.get('first_corrupt_index')}",
                category="security_alert",
                risk_class="HIGH",
                status=STATUS_OPEN,
                affected_files=[],
                evidence={"audit_chain": audit},
            )
        )
    return items


def _dashboard_py_text() -> str:
    """Read ``dashboard/dashboard.py`` once to detect which
    ``register_*_routes(app)`` lines are already wired. Returns ""
    on any error (so wiring detection fails closed → items stay
    open until proven wired)."""
    p = REPO_ROOT / "dashboard" / "dashboard.py"
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def _build_from_workloop_runtime(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    """Project a v3.15.15.22 workloop runtime artifact into inbox items.

    Mapping:
      * ``loop_health.consecutive_failures >= 3`` → ``runtime_halt``
        (severity: critical) — the loop has degraded enough to warrant
        human attention.
      * Each source with ``state in {failed, timeout}`` →
        ``failed_automation`` (severity: high) so the operator sees
        which exact source died.
      * Each source with ``state == unknown`` → ``unknown_state``.

    A clean runtime artifact (every source ok or only ``not_available``)
    produces zero inbox items.
    """
    if envelope["status"] != "ok" or not envelope.get("data"):
        return []
    data = envelope["data"]
    items: list[dict[str, Any]] = []

    health = data.get("loop_health") or {}
    consecutive = (
        int(health.get("consecutive_failures") or 0)
        if isinstance(health, dict)
        else 0
    )
    if consecutive >= 3:
        items.append(
            _build_item(
                source="workloop_runtime:loop_health",
                source_type="manual",
                title=(
                    f"Workloop runtime: {consecutive} consecutive failed "
                    "iterations — runtime_halt"
                ),
                summary=str(data.get("final_recommendation") or "runtime_halt"),
                category="runtime_halt",
                risk_class="HIGH",
                status=STATUS_BLOCKED,
                affected_files=[],
                evidence={"loop_health": health},
            )
        )

    for src in data.get("sources") or []:
        if not isinstance(src, dict):
            continue
        state = src.get("state")
        name = src.get("source") or "unknown_source"
        module = src.get("module") or ""
        summary = src.get("summary") or ""
        if state in ("failed", "timeout"):
            items.append(
                _build_item(
                    source=f"workloop_runtime:{name}",
                    source_type="manual",
                    title=f"Workloop runtime: {name} {state}",
                    summary=summary,
                    category="failed_automation",
                    risk_class="HIGH",
                    status=STATUS_BLOCKED,
                    affected_files=[],
                    evidence={
                        "module": module,
                        "duration_ms": src.get("duration_ms"),
                        "error_class": src.get("error_class"),
                    },
                )
            )
        elif state == "unknown":
            items.append(
                _build_item(
                    source=f"workloop_runtime:{name}",
                    source_type="manual",
                    title=f"Workloop runtime: {name} unknown state",
                    summary=summary,
                    category="unknown_state",
                    risk_class="MEDIUM",
                    status=STATUS_BLOCKED,
                    affected_files=[],
                    evidence={"module": module},
                )
            )

    return items


def _build_manual_route_wiring_items() -> list[dict[str, Any]]:
    """Per the v3.15.15.18 / .19 / .20 release notes,
    ``dashboard/dashboard.py`` is no-touch except via an
    operator-led, CODEOWNERS-reviewed PR. This emits one
    ``manual_route_wiring_required`` item per pending route module —
    and **clears items automatically** once the corresponding
    ``register_*_routes(app)`` call appears in the file.

    Detection is a pure substring check. False negatives (a
    commented-out line still passes) are intentionally accepted —
    the Inbox surface is informational and the upstream route tests
    are the canonical "is it wired?" gate.
    """
    pending = (
        ("dashboard.api_agent_control", "register_agent_control_routes", "v3.15.15.18"),
        ("dashboard.api_proposal_queue", "register_proposal_queue_routes", "v3.15.15.19"),
        ("dashboard.api_approval_inbox", "register_approval_inbox_routes", "v3.15.15.20"),
    )
    dashboard_text = _dashboard_py_text()
    items: list[dict[str, Any]] = []
    for module, fn, release in pending:
        # Already wired? The detection is intentionally narrow: the
        # file must contain BOTH the import line AND the call.
        wired = (
            f"from {module} import {fn}" in dashboard_text
            and f"{fn}(app)" in dashboard_text
        )
        if wired:
            continue
        items.append(
            _build_item(
                source=f"manual:{module}",
                source_type="manual",
                title=f"Wire {module}.{fn} into dashboard.py",
                summary=(
                    f"{release} ships {module} with {fn}; one operator-led "
                    "line in dashboard/dashboard.py activates the route."
                ),
                category="manual_route_wiring_required",
                risk_class="LOW",
                status=STATUS_OPEN,
                affected_files=["dashboard/dashboard.py"],
                evidence={"release": release, "register_function": fn},
                related_release_id=release,
            )
        )
    return items


# ---------------------------------------------------------------------------
# Item builder
# ---------------------------------------------------------------------------


def _build_item(
    *,
    source: str,
    source_type: str,
    title: str,
    summary: str,
    category: str,
    risk_class: str,
    status: str,
    affected_files: list[str],
    evidence: dict[str, Any],
    related_proposal_id: str | None = None,
    related_pr_number: int | None = None,
    related_release_id: str | None = None,
    audit_refs: list[str] | None = None,
) -> dict[str, Any]:
    item_key = f"{source_type}|{category}|{title}"
    return {
        "item_id": _item_id(source, item_key),
        "created_at": _utcnow(),
        "source": source,
        "source_type": source_type,
        "title": title.strip(),
        "summary": (summary or "").strip()[:480],
        "category": category,
        "severity": _severity_for_category(category),
        "status": status,
        "risk_class": risk_class,
        "approval_required": True,
        "recommended_operator_action": _recommended_action(category),
        "forbidden_agent_actions": list(_FORBIDDEN_AGENT_ACTIONS),
        "evidence": evidence,
        "affected_files": affected_files,
        "related_proposal_id": related_proposal_id,
        "related_pr_number": related_pr_number,
        "related_release_id": related_release_id,
        "dependencies": [],
        "stale_after": None,
        "audit_refs": audit_refs or [],
    }


# ---------------------------------------------------------------------------
# Top-level snapshot
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    mode: str = "dry-run",
    sources_override: dict[str, dict[str, Any]] | None = None,
    skip_manual_route_items: bool = False,
) -> dict[str, Any]:
    """Build the full snapshot. ``sources_override`` is for tests."""
    if mode != "dry-run":
        return {
            "schema_version": SCHEMA_VERSION,
            "report_kind": "approval_inbox_digest",
            "module_version": MODULE_VERSION,
            "generated_at_utc": _utcnow(),
            "mode": mode,
            "status": "refused",
            "reason": (
                f"mode {mode!r} is not allowed in {MODULE_VERSION}; "
                "only dry-run is supported. Approval execution lands "
                "in v3.15.15.21+."
            ),
            "sources": {},
            "items": [],
            "counts": _empty_counts(),
            "final_recommendation": "needs_human",
        }

    if sources_override is not None:
        sources = sources_override
    else:
        sources = {
            "proposal_queue": _read_json_artifact(SOURCE_PROPOSAL_QUEUE),
            "pr_lifecycle": _read_json_artifact(SOURCE_PR_LIFECYCLE),
            "workloop": _read_json_artifact(SOURCE_WORKLOOP),
            "workloop_runtime": _read_json_artifact(SOURCE_WORKLOOP_RUNTIME),
            "governance_status": _governance_status_safe(),
        }

    items: list[dict[str, Any]] = []
    items.extend(_build_from_proposal_queue(sources.get("proposal_queue", {"status": "not_available"})))
    items.extend(_build_from_pr_lifecycle(sources.get("pr_lifecycle", {"status": "not_available"})))
    items.extend(_build_from_workloop(sources.get("workloop", {"status": "not_available"})))
    items.extend(
        _build_from_workloop_runtime(
            sources.get("workloop_runtime", {"status": "not_available"})
        )
    )
    items.extend(
        _build_from_governance_status(
            sources.get("governance_status", {"status": "not_available"})
        )
    )

    # not_available source(s) → unknown_state items (one per
    # missing source). The operator sees the gap explicitly.
    for src_name, env in sources.items():
        if env.get("status") != "ok":
            items.append(
                _build_item(
                    source=f"missing:{src_name}",
                    source_type="manual",
                    title=f"Source {src_name!r} is not available",
                    summary=str(env.get("reason") or "missing"),
                    category="unknown_state",
                    risk_class="MEDIUM",
                    status=STATUS_BLOCKED,
                    affected_files=[],
                    evidence={"source_envelope": env},
                )
            )

    if not skip_manual_route_items:
        items.extend(_build_manual_route_wiring_items())

    counts = _counts(items)
    snap: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "approval_inbox_digest",
        "module_version": MODULE_VERSION,
        "generated_at_utc": _utcnow(),
        "mode": mode,
        "sources": {k: {"status": v.get("status"), "path": v.get("path"), "reason": v.get("reason")} for k, v in sources.items()},
        "items": items,
        "counts": counts,
        "final_recommendation": _final_recommendation(counts),
    }
    assert_no_secrets(snap)
    return snap


def _empty_counts() -> dict[str, Any]:
    return {"total": 0, "by_category": {}, "by_severity": {}, "by_status": {}}


def _counts(items: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "total": len(items),
        "by_category": {},
        "by_severity": {},
        "by_status": {},
    }
    for it in items:
        c = it.get("category", "unknown")
        s = it.get("severity", "unknown")
        st = it.get("status", "unknown")
        out["by_category"][c] = out["by_category"].get(c, 0) + 1
        out["by_severity"][s] = out["by_severity"].get(s, 0) + 1
        out["by_status"][st] = out["by_status"].get(st, 0) + 1
    return out


def _final_recommendation(counts: dict[str, Any]) -> str:
    if counts["total"] == 0:
        return "no_items"
    crit = counts["by_severity"].get("critical", 0)
    high = counts["by_severity"].get("high", 0)
    if crit > 0:
        return f"critical_on_{crit}_items"
    if high > 0:
        return f"high_severity_on_{high}_items"
    return f"review_{counts['total']}_open_items"


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
        prog="python -m reporting.approval_inbox",
        description=(
            "Approval / exception inbox (read-only). Aggregates "
            "needs_human / blocked / high-risk / unknown items from "
            "the proposal queue, GitHub PR lifecycle, autonomous "
            "workloop, and governance status into a single "
            "deterministic queue. Never approves, rejects, or mutates."
        ),
    )
    p.add_argument(
        "--mode",
        choices=["dry-run"],
        default="dry-run",
        help="Operating mode (only dry-run is supported in this release).",
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
    snap = collect_snapshot(mode=args.mode)
    if not args.no_write and snap.get("status") != "refused":
        write_outputs(snap)
    indent = args.indent if args.indent and args.indent > 0 else None
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
