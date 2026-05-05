"""Human Needed Event Detection (v3.15.16.8).

Pure read-only blocker detector. Scans the read-only signal stack
(task_board, agent_flow, approval_inbox) plus the dashboard route
modules for wiring gaps, and emits a structured event per blocker
with:

* ``event_id`` — deterministic hash of (reason, blocking_component,
  related_item).
* ``reason`` — closed enum.
* ``blocking_component`` — the file / module / capability that is
  blocked.
* ``required_action`` — short imperative for the operator.
* ``proposed_patch`` — literal text patch when derivable; ``None``
  otherwise. The patch is **never** auto-applied.
* ``impact`` — closed enum: LOW / MEDIUM / HIGH / CRITICAL.
* ``priority`` — closed enum: LOW / MEDIUM / HIGH / CRITICAL.
* ``related_item`` — task_board ``item_id`` when applicable.
* ``generated_at_utc``.

This module:

* never starts work
* never opens a branch
* never opens a PR
* never merges
* never invokes ``gh``
* never invokes ``git``
* never auto-applies any patch (pinned by source-text test)

Hard guarantees (enforced by code AND tests)
--------------------------------------------

* Stdlib-only. No subprocess, no ``gh``, no ``git``, no network.
* Reads ``logs/task_board/latest.json``,
  ``logs/agent_flow/latest.json``,
  ``logs/approval_inbox/latest.json``, and the source text of
  ``dashboard/api_*.py`` + ``dashboard/dashboard.py`` for static
  wiring-gap analysis.
* Output limited to ``logs/human_needed/``.
* Atomic writes (``tmp`` + ``os.replace``).
* ``safe_to_execute`` is hard-coded ``false`` at the digest level.
* ``proposed_patch`` field is text only; the module has no
  file-write or subprocess path that could apply it (pinned).
* Closed reason vocabulary; closed impact / priority vocabulary.
* Determinism: two runs on the same input produce a byte-identical
  ``events`` list (modulo ``generated_at_utc``).

Closed reason vocabulary
------------------------

::

    governance_bootstrap_required
    no_touch_path_blocks_wiring
    allowlist_blocks_completion
    release_gate_blocks_progression
    system_cannot_proceed_safely
    decision_cannot_be_inferred

CLI
---

::

    python -m reporting.human_needed
    python -m reporting.human_needed --no-write
    python -m reporting.human_needed --status

Stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
MODULE_VERSION: str = "v3.15.16.8"
SCHEMA_VERSION: int = 1

DIGEST_DIR_JSON: Path = REPO_ROOT / "logs" / "human_needed"

SOURCE_TASK_BOARD: Path = REPO_ROOT / "logs" / "task_board" / "latest.json"
SOURCE_AGENT_FLOW: Path = REPO_ROOT / "logs" / "agent_flow" / "latest.json"
SOURCE_APPROVAL_INBOX: Path = (
    REPO_ROOT / "logs" / "approval_inbox" / "latest.json"
)

DASHBOARD_PY: Path = REPO_ROOT / "dashboard" / "dashboard.py"
DASHBOARD_API_DIR: Path = REPO_ROOT / "dashboard"


# ---------------------------------------------------------------------------
# Closed taxonomies
# ---------------------------------------------------------------------------


REASON_GOVERNANCE_BOOTSTRAP: str = "governance_bootstrap_required"
REASON_NO_TOUCH_PATH: str = "no_touch_path_blocks_wiring"
REASON_ALLOWLIST: str = "allowlist_blocks_completion"
REASON_RELEASE_GATE: str = "release_gate_blocks_progression"
REASON_SYSTEM_UNSAFE: str = "system_cannot_proceed_safely"
REASON_DECISION_UNCLEAR: str = "decision_cannot_be_inferred"

REASONS: tuple[str, ...] = (
    REASON_GOVERNANCE_BOOTSTRAP,
    REASON_NO_TOUCH_PATH,
    REASON_ALLOWLIST,
    REASON_RELEASE_GATE,
    REASON_SYSTEM_UNSAFE,
    REASON_DECISION_UNCLEAR,
)

IMPACT_LOW: str = "LOW"
IMPACT_MEDIUM: str = "MEDIUM"
IMPACT_HIGH: str = "HIGH"
IMPACT_CRITICAL: str = "CRITICAL"

IMPACTS: tuple[str, ...] = (IMPACT_LOW, IMPACT_MEDIUM, IMPACT_HIGH, IMPACT_CRITICAL)
PRIORITIES: tuple[str, ...] = IMPACTS  # same closed scale


REC_OK: str = "ok"
REC_NOT_AVAILABLE: str = "not_available"

FINAL_RECOMMENDATIONS: tuple[str, ...] = (REC_OK, REC_NOT_AVAILABLE)


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


def _event_id(reason: str, blocking_component: str, related_item: str | None) -> str:
    raw = f"{reason}|{blocking_component}|{related_item or ''}".encode("utf-8")
    return "h_" + hashlib.sha256(raw).hexdigest()[:10]


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace(
            "\\", "/"
        )
    except ValueError:
        return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Source readers (passive)
# ---------------------------------------------------------------------------


def _read_json_artifact(path: Path) -> tuple[dict[str, Any] | None, str | None]:
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


def _read_text_safe(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------------------
# Wiring-gap detection
# ---------------------------------------------------------------------------


# Matches a top-level ``def register_<thing>_routes(`` definition.
_REGISTER_DEF_RE = re.compile(
    r"^def\s+(register_[A-Za-z0-9_]+_routes)\s*\(", re.MULTILINE
)


def _scan_register_definitions(
    api_dir: Path = DASHBOARD_API_DIR,
) -> list[tuple[str, str]]:
    """Scan ``dashboard/api_*.py`` files for ``register_*_routes``
    function definitions. Returns ``[(module_path, function_name),
    ...]`` sorted by module path ascending for determinism.

    Skips ``dashboard/dashboard.py`` and ``dashboard/api_execute_safe_controls.py``
    (the latter is intentionally never wired per the v3.15.15.27
    hardening invariant)."""
    out: list[tuple[str, str]] = []
    if not api_dir.is_dir():
        return out
    skip = {
        "dashboard.py",
        "api_execute_safe_controls.py",  # intentionally unwired
    }
    for p in sorted(api_dir.glob("api_*.py")):
        if p.name in skip:
            continue
        text = _read_text_safe(p)
        if text is None:
            continue
        for m in _REGISTER_DEF_RE.finditer(text):
            fn_name = m.group(1)
            module_dot = "dashboard." + p.stem
            out.append((module_dot, fn_name))
    out.sort()
    return out


def _is_module_imported(dash_text: str, module_dot: str, fn_name: str) -> bool:
    """Return True iff ``dashboard/dashboard.py`` imports ``fn_name``
    from ``module_dot``. Handles both single-line and multi-line
    ``from <module> import (...)`` forms.

    Matched shapes:

      from <module_dot> import <fn_name>
      from <module_dot> import <fn_name>, other
      from <module_dot> import (
          <fn_name>,
          other,
      )
    """
    # Pattern: ``from <module> import`` followed by either the bare
    # name or a parenthesised list that contains the name. We allow
    # arbitrary whitespace and newlines inside the parens.
    pattern = (
        r"from\s+"
        + re.escape(module_dot)
        + r"\s+import\s+(?:"
        + re.escape(fn_name)
        + r"\b|\([^)]*\b"
        + re.escape(fn_name)
        + r"\b[^)]*\))"
    )
    return re.search(pattern, dash_text) is not None


def _detect_wiring_gaps(
    api_dir: Path = DASHBOARD_API_DIR, dashboard_py: Path = DASHBOARD_PY
) -> list[dict[str, Any]]:
    """Detect `register_*_routes` definitions that do NOT have a
    matching import-and-call pair in dashboard/dashboard.py. For
    each gap emit a governance_bootstrap_required event with a
    literal proposed_patch.

    A module is considered wired iff ``dashboard/dashboard.py``
    contains BOTH:

      * ``from <module> import <fn>`` in some form (single-line or
        multi-line parenthesised) — see ``_is_module_imported``;
      * ``<fn>(app)`` substring.

    Same shape as the existing
    ``reporting.approval_inbox._build_manual_route_wiring_items``
    detector — kept independent here so this module can produce
    richer events with literal proposed_patch text and so it can
    handle multi-line imports correctly."""
    dash_text = _read_text_safe(dashboard_py)
    if dash_text is None:
        return []
    events: list[dict[str, Any]] = []
    for module_dot, fn_name in _scan_register_definitions(api_dir):
        wired = (
            _is_module_imported(dash_text, module_dot, fn_name)
            and f"{fn_name}(app)" in dash_text
        )
        if wired:
            continue
        # Compose the literal two-line patch the operator can paste.
        patch = (
            f"# Add to dashboard/dashboard.py imports section:\n"
            f"from {module_dot} import {fn_name}\n"
            f"\n"
            f"# Add to the route-registration block:\n"
            f"{fn_name}(app)\n"
        )
        events.append(
            _build_event(
                reason=REASON_GOVERNANCE_BOOTSTRAP,
                blocking_component=f"dashboard/dashboard.py:{fn_name}",
                required_action=(
                    f"Open a one-shot governance-bootstrap PR adding "
                    f"`from {module_dot} import {fn_name}` and "
                    f"`{fn_name}(app)` to dashboard/dashboard.py."
                ),
                proposed_patch=patch,
                impact=IMPACT_MEDIUM,
                priority=IMPACT_HIGH,
                related_item=None,
                evidence={
                    "module": module_dot,
                    "register_function": fn_name,
                    "deny_no_touch_blocked": True,
                },
            )
        )
    return events


# ---------------------------------------------------------------------------
# Task-board derived events
# ---------------------------------------------------------------------------


def _detect_blocked_tasks(
    task_board: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """For each task_board row in the ``blocked`` or ``human_needed``
    state, emit one event. Reason is derived from the
    transition_reason string."""
    if not isinstance(task_board, Mapping):
        return []
    tasks = task_board.get("tasks")
    if not isinstance(tasks, list):
        return []
    events: list[dict[str, Any]] = []
    for t in tasks:
        if not isinstance(t, Mapping):
            continue
        state = t.get("current_state")
        if state not in ("blocked", "human_needed"):
            continue
        item_id = str(t.get("item_id") or "")
        title = str(t.get("title") or "")
        reason_str = str(t.get("transition_reason") or "")
        affected_files = (t.get("evidence") or {}).get("affected_files") or []
        # Map transition_reason fragments to closed reason vocab.
        if "blocked_protected_path" in reason_str or any(
            f.startswith(".claude/")
            or f == "VERSION"
            or f == "config/config.yaml"
            or "live_gate" in f
            for f in affected_files
            if isinstance(f, str)
        ):
            r = REASON_NO_TOUCH_PATH
            impact = IMPACT_MEDIUM
            priority = IMPACT_MEDIUM
        elif "blocked_high_risk" in reason_str or "live" in reason_str:
            r = REASON_NO_TOUCH_PATH
            impact = IMPACT_HIGH
            priority = IMPACT_HIGH
        elif state == "human_needed":
            r = REASON_DECISION_UNCLEAR
            impact = IMPACT_MEDIUM
            priority = IMPACT_HIGH
        else:
            r = REASON_ALLOWLIST
            impact = IMPACT_LOW
            priority = IMPACT_MEDIUM
        events.append(
            _build_event(
                reason=r,
                blocking_component=f"task_board:{item_id}",
                required_action=(
                    f"Inspect task {item_id!r} ({title[:60]}) — "
                    f"current_state={state!r}, "
                    f"transition_reason={reason_str!r}"
                ),
                proposed_patch=None,  # task-board blockers rarely have a derivable patch
                impact=impact,
                priority=priority,
                related_item=item_id,
                evidence={
                    "title": title[:200],
                    "current_state": state,
                    "transition_reason": reason_str,
                    "affected_files": list(affected_files)[:8],
                },
            )
        )
    return events


# ---------------------------------------------------------------------------
# Event construction
# ---------------------------------------------------------------------------


def _build_event(
    *,
    reason: str,
    blocking_component: str,
    required_action: str,
    proposed_patch: str | None,
    impact: str,
    priority: str,
    related_item: str | None,
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if reason not in REASONS:
        reason = REASON_DECISION_UNCLEAR
    if impact not in IMPACTS:
        impact = IMPACT_MEDIUM
    if priority not in PRIORITIES:
        priority = IMPACT_MEDIUM
    return {
        "event_id": _event_id(reason, blocking_component, related_item),
        "reason": reason,
        "blocking_component": blocking_component,
        "required_action": required_action,
        "proposed_patch": proposed_patch,
        "impact": impact,
        "priority": priority,
        "related_item": related_item,
        "evidence": dict(evidence) if isinstance(evidence, Mapping) else {},
    }


def _counts_by_reason(events: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    out = {r: 0 for r in REASONS}
    for e in events:
        r = str(e.get("reason") or "")
        if r in out:
            out[r] += 1
    return out


def _counts_by_priority(events: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    out = {p: 0 for p in PRIORITIES}
    for e in events:
        p = str(e.get("priority") or "")
        if p in out:
            out[p] += 1
    return out


def collect_snapshot(
    *,
    frozen_utc: str | None = None,
    task_board_override: Mapping[str, Any] | None = None,
    api_dir_override: Path | None = None,
    dashboard_py_override: Path | None = None,
) -> dict[str, Any]:
    """Build the full human_needed digest. Pure function."""
    generated = frozen_utc or _utcnow()

    # --- Task-board source ---
    if task_board_override is not None:
        tb: Mapping[str, Any] | None = task_board_override
        tb_status = "ok"
        tb_error: str | None = None
    else:
        tb, tb_error = _read_json_artifact(SOURCE_TASK_BOARD)
        tb_status = "ok" if tb is not None else "not_available"

    events: list[dict[str, Any]] = []

    # --- Wiring-gap detection (v3.15.16.5 case lands here) ---
    api_dir = api_dir_override or DASHBOARD_API_DIR
    dash_py = dashboard_py_override or DASHBOARD_PY
    events.extend(_detect_wiring_gaps(api_dir=api_dir, dashboard_py=dash_py))

    # --- Task-board derived events ---
    events.extend(_detect_blocked_tasks(tb))

    # Stable ordering: sort by (priority, reason, event_id) so two
    # runs on the same input produce a byte-identical events list.
    _PRIO_RANK = {
        IMPACT_CRITICAL: 0,
        IMPACT_HIGH: 1,
        IMPACT_MEDIUM: 2,
        IMPACT_LOW: 3,
    }
    events.sort(
        key=lambda e: (
            _PRIO_RANK.get(str(e.get("priority") or ""), 9),
            str(e.get("reason") or ""),
            str(e.get("event_id") or ""),
        )
    )

    # If task_board source was missing AND no wiring gaps and no
    # blocked tasks, surface as not_available so the operator
    # knows the digest could not see the upstream signals.
    if tb_status == "not_available" and not events:
        return _build_not_available_digest(
            generated_at_utc=generated,
            reason=tb_error or "unknown",
            source_path=_rel(SOURCE_TASK_BOARD),
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "human_needed_digest",
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated,
        "mode": "dry-run",
        "source_task_board": {
            "path": _rel(SOURCE_TASK_BOARD),
            "status": tb_status,
            "error": tb_error,
        },
        "policy": {
            "reasons": list(REASONS),
            "impacts": list(IMPACTS),
            "priorities": list(PRIORITIES),
        },
        "counts": {
            "events_total": len(events),
            "by_reason": _counts_by_reason(events),
            "by_priority": _counts_by_priority(events),
        },
        "events": events,
        "final_recommendation": REC_OK,
        "safe_to_execute": False,
    }


def _build_not_available_digest(
    *, generated_at_utc: str, reason: str, source_path: str
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "human_needed_digest",
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated_at_utc,
        "mode": "dry-run",
        "source_task_board": {
            "path": source_path,
            "status": "not_available",
            "error": reason,
        },
        "policy": {
            "reasons": list(REASONS),
            "impacts": list(IMPACTS),
            "priorities": list(PRIORITIES),
        },
        "counts": {
            "events_total": 0,
            "by_reason": {r: 0 for r in REASONS},
            "by_priority": {p: 0 for p in PRIORITIES},
        },
        "events": [],
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
        prog="reporting.human_needed",
        description=(
            f"human_needed event detection ({MODULE_VERSION}). "
            "Stdlib-only. Read-only blocker detection over the "
            "task_board + dashboard route surface."
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
