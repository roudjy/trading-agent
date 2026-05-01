"""Read-only operator view over the agent audit ledger.

The canonical writer for ``logs/agent_audit.<UTC date>.jsonl`` is
:mod:`reporting.agent_audit`. The existing CLI exposes
``verify`` (chain integrity) and ``tail`` (last single event verbatim).
Neither answers the operator's first-pass question:

    "Which agent did what, when, on this branch?"

This module fills that gap. It is read-only, stdlib-only, and never
mutates the ledger. It does not change the writers — the per-event
schema is whatever ``agent_audit.append_event`` produces.

Two views
---------

1. ``timeline`` — last N events, one row per event, sorted by
   ``sequence_id`` ascending. Each row is a *redacted* projection:

       sequence_id, timestamp_utc, actor, event, tool, outcome,
       block_reason, branch, head_sha, session_id, target_dir,
       redaction_status

   ``target_path`` is **never** surfaced verbatim — only its parent
   directory ("``target_dir``") is shown, so the surface cannot leak
   working-tree filenames the operator did not already know about.

2. ``groups`` — per-actor / per-outcome counts plus per-session and
   per-branch breakdowns. Pure aggregates; no payloads.

Both views report fields that are missing in the source as ``"unknown"``
or ``"not_available"``. Nothing is ever ``"ok"`` by default — ``ok``
must come from the source.

Usage
-----

::

    python -m reporting.agent_audit_summary
        # today's ledger, last 50 events, both views, JSON

    python -m reporting.agent_audit_summary --limit 100 --view timeline

    python -m reporting.agent_audit_summary --date 2026-04-30 \\
        --view groups

    python -m reporting.agent_audit_summary --path \\
        logs/agent_audit.2026-04-30.jsonl --view timeline --format table

The CLI exits 0 even when the chain is broken or the file is unreadable
— this is a diagnostic, not a gate. Chain integrity is reported as a
field; ``verify`` is the actual check.

Stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from reporting import agent_audit

REPO_ROOT: Path = Path(__file__).resolve().parent.parent

# Fields we copy out of an event into the redacted timeline row. Anything
# not in this list is dropped at projection time. command_summary,
# diff_summary, and target_path are intentionally absent (they may carry
# user-controlled strings even after writer-side redaction).
_TIMELINE_KEEP_KEYS: tuple[str, ...] = (
    "sequence_id",
    "timestamp_utc",
    "actor",
    "event",
    "tool",
    "outcome",
    "block_reason",
    "branch",
    "head_sha",
    "session_id",
    "redacted",
    "autonomy_level_claimed",
)

# Patterns we treat as "do not surface even in redacted form". A match in
# any string field of a projection causes the field to be replaced with
# ``"[REDACTED]"`` in the row. This is defense in depth; the writer
# already strips most of these.
_FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"ghp_[A-Za-z0-9]{8,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def _utc_today() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d")


def _ledger_path_for(date_utc: str | None, explicit: str | None) -> Path:
    if explicit is not None:
        return Path(explicit)
    if date_utc is None:
        date_utc = _utc_today()
    return REPO_ROOT / "logs" / f"agent_audit.{date_utc}.jsonl"


def _is_valid_event(obj: Any) -> bool:
    """A defensive structural check — anything that does not look like a
    sealed event is treated as ``invalid``. We do **not** reject events
    by chain validity here; chain breaks are a separate report."""
    if not isinstance(obj, dict):
        return False
    if obj.get("schema_version") != 1:
        return False
    return isinstance(obj.get("sequence_id"), int)


def _read_events(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Return ``(events, malformed_line_count)``.

    Malformed lines (non-JSON, or JSON that does not look like a v1
    event) are counted but never raised. The CLI must keep working on a
    half-written or truncated file — the operator's job is to look at
    the count, not to crash.
    """
    if not path.exists():
        return ([], 0)
    events: list[dict[str, Any]] = []
    malformed = 0
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ([], 0)
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not _is_valid_event(obj):
            malformed += 1
            continue
        events.append(obj)
    events.sort(key=lambda e: e.get("sequence_id", -1))
    return (events, malformed)


def _scrub(value: Any) -> Any:
    """Replace credential-like strings with ``[REDACTED]``. Non-strings
    pass through untouched. The writer already redacts these; this is
    defense in depth at presentation time."""
    if not isinstance(value, str):
        return value
    out = value
    for pat in _FORBIDDEN_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def _project_target_dir(event: dict[str, Any]) -> str:
    """Surface only the parent directory of ``target_path``. The full
    filename can carry information that should not appear in operator
    output (working-copy paths the operator did not explicitly ask
    about). ``"unknown"`` if absent."""
    raw = event.get("target_path")
    if not isinstance(raw, str) or not raw.strip():
        return "unknown"
    p = raw.replace("\\", "/")
    parent = p.rsplit("/", 1)[0] if "/" in p else "."
    if not parent:
        parent = "."
    return parent


def _redaction_status(event: dict[str, Any]) -> str:
    """One of ``redacted_by_writer`` / ``not_redacted`` / ``unknown``."""
    val = event.get("redacted")
    if val is True:
        return "redacted_by_writer"
    if val is False:
        return "not_redacted"
    return "unknown"


def _projection(event: dict[str, Any]) -> dict[str, Any]:
    """Build the operator-facing redacted row for a single event."""
    row: dict[str, Any] = {}
    for k in _TIMELINE_KEEP_KEYS:
        v = event.get(k)
        if v is None:
            # Distinguish "field absent in writer" from "field present and
            # null". For booleans, None ⇒ unknown. For strings, None ⇒
            # unknown. For ints, None ⇒ unknown.
            row[k] = "unknown"
        else:
            row[k] = _scrub(v)
    row["target_dir"] = _project_target_dir(event)
    row["redaction_status"] = _redaction_status(event)
    return row


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def collect_timeline(
    path: Path,
    *,
    limit: int = 50,
    actor: str | None = None,
    outcome: str | None = None,
) -> dict[str, Any]:
    """Return a redacted timeline of the last ``limit`` events.

    Filters apply at the source level (full event), then the projection
    is applied. The output shape is intentionally JSON-stable.
    """
    events, malformed = _read_events(path)
    chain_status, first_corrupt = _chain_status(path)
    if actor is not None:
        events = [e for e in events if e.get("actor") == actor]
    if outcome is not None:
        events = [e for e in events if e.get("outcome") == outcome]
    rows = [_projection(e) for e in events[-max(0, limit):]]
    return {
        "schema_version": 1,
        "report_kind": "agent_audit_timeline",
        "ledger_path": _rel(path),
        "ledger_present": path.exists(),
        "ledger_event_count": len(events),
        "malformed_line_count": malformed,
        "chain_status": chain_status,
        "first_corrupt_index": first_corrupt,
        "filters": {"actor": actor, "outcome": outcome, "limit": limit},
        "rows": rows,
    }


def collect_groups(path: Path) -> dict[str, Any]:
    """Aggregates: counts by actor, outcome, tool, branch, session.

    Pure aggregates — no payloads, no command summaries, no diffs.
    """
    events, malformed = _read_events(path)
    chain_status, first_corrupt = _chain_status(path)
    by_actor: dict[str, int] = {}
    by_outcome: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    by_branch: dict[str, int] = {}
    by_session: dict[str, int] = {}
    earliest: str | None = None
    latest: str | None = None
    for e in events:
        actor = e.get("actor") or "unknown"
        outcome = e.get("outcome") or "unknown"
        tool = e.get("tool") or "unknown"
        branch = e.get("branch") or "unknown"
        session = e.get("session_id") or "unknown"
        by_actor[actor] = by_actor.get(actor, 0) + 1
        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
        by_tool[tool] = by_tool.get(tool, 0) + 1
        by_branch[branch] = by_branch.get(branch, 0) + 1
        by_session[session] = by_session.get(session, 0) + 1
        ts = e.get("timestamp_utc")
        if isinstance(ts, str):
            if earliest is None or ts < earliest:
                earliest = ts
            if latest is None or ts > latest:
                latest = ts
    return {
        "schema_version": 1,
        "report_kind": "agent_audit_groups",
        "ledger_path": _rel(path),
        "ledger_present": path.exists(),
        "ledger_event_count": len(events),
        "malformed_line_count": malformed,
        "chain_status": chain_status,
        "first_corrupt_index": first_corrupt,
        "earliest_timestamp_utc": earliest or "not_available",
        "latest_timestamp_utc": latest or "not_available",
        "by_actor": dict(sorted(by_actor.items())),
        "by_outcome": dict(sorted(by_outcome.items())),
        "by_tool": dict(sorted(by_tool.items())),
        "by_branch": dict(sorted(by_branch.items())),
        "by_session": dict(sorted(by_session.items())),
    }


def _chain_status(path: Path) -> tuple[str, int | None]:
    """Run :func:`agent_audit.verify_chain` defensively. Failures on
    any axis collapse to ``"unreadable"`` so the diagnostic stays
    informative even if the writer module changes shape."""
    if not path.exists():
        return ("not_available", None)
    if path.stat().st_size == 0:
        return ("not_available", None)
    try:
        ok, idx = agent_audit.verify_chain(path)
    except Exception:
        return ("unreadable", None)
    return ("intact" if ok else "broken", idx)


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace(
            "\\", "/"
        )
    except ValueError:
        return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Self-check (used by the CLI and the tests)
# ---------------------------------------------------------------------------


def _walk_strings(obj: Any) -> Iterator[str]:
    if isinstance(obj, str):
        yield obj
        return
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
        return
    if isinstance(obj, list | tuple):
        for v in obj:
            yield from _walk_strings(v)


_SENSITIVE_FRAGMENTS: tuple[str, ...] = (
    "config/config.yaml",
    "live_gate.secret",
    "fred.secret",
    "operator_token.secret",
    "dashboard_session.secret",
)


def assert_no_secrets(snapshot: dict[str, Any]) -> None:
    """Raise ``AssertionError`` if any string in the snapshot matches a
    forbidden credential pattern or sensitive-path fragment."""
    for s in _walk_strings(snapshot):
        for pat in _FORBIDDEN_PATTERNS:
            if pat.search(s):
                raise AssertionError(
                    f"agent_audit_summary leaked credential-like string: pattern={pat.pattern!r}"
                )
        lowered = s.lower()
        for frag in _SENSITIVE_FRAGMENTS:
            if frag in lowered:
                raise AssertionError(
                    f"agent_audit_summary leaked sensitive path fragment: {frag!r}"
                )


# ---------------------------------------------------------------------------
# Table rendering (operator-friendly text output)
# ---------------------------------------------------------------------------


_TIMELINE_COLUMNS: tuple[tuple[str, int], ...] = (
    ("sequence_id", 6),
    ("timestamp_utc", 22),
    ("actor", 26),
    ("outcome", 16),
    ("tool", 12),
    ("branch", 28),
    ("session_id", 12),
)


def _trim(value: Any, width: int) -> str:
    s = str(value) if value is not None else ""
    if len(s) <= width:
        return s.ljust(width)
    return s[: max(0, width - 1)] + "…"


def render_timeline_table(snapshot: dict[str, Any]) -> str:
    """Render a timeline snapshot as a fixed-width text table.

    Operator-friendly. Each row is one event. Columns are deliberately
    narrow so the output fits a terminal."""
    header_cells = [c for c, _ in _TIMELINE_COLUMNS]
    widths = [w for _, w in _TIMELINE_COLUMNS]
    sep = "  "
    lines: list[str] = []
    lines.append(
        sep.join(name.ljust(w) for name, w in zip(header_cells, widths, strict=False))
    )
    lines.append(sep.join("-" * w for w in widths))
    rows: Iterable[dict[str, Any]] = snapshot.get("rows", []) or []
    for row in rows:
        cells = [_trim(row.get(name), w) for name, w in zip(header_cells, widths, strict=False)]
        lines.append(sep.join(cells))
    lines.append("")
    lines.append(
        f"-- {snapshot.get('ledger_event_count', 0)} events total, "
        f"chain={snapshot.get('chain_status')}, "
        f"malformed={snapshot.get('malformed_line_count', 0)} --"
    )
    return "\n".join(lines) + "\n"


def render_groups_table(snapshot: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"ledger: {snapshot.get('ledger_path')}")
    lines.append(
        f"events: {snapshot.get('ledger_event_count', 0)}  "
        f"malformed: {snapshot.get('malformed_line_count', 0)}  "
        f"chain: {snapshot.get('chain_status')}  "
        f"earliest: {snapshot.get('earliest_timestamp_utc')}  "
        f"latest: {snapshot.get('latest_timestamp_utc')}"
    )
    for header, key in (
        ("by_actor", "by_actor"),
        ("by_outcome", "by_outcome"),
        ("by_tool", "by_tool"),
        ("by_branch", "by_branch"),
        ("by_session", "by_session"),
    ):
        lines.append("")
        lines.append(f"[{header}]")
        for k, v in (snapshot.get(key) or {}).items():
            lines.append(f"  {k:<40} {v:>6}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.agent_audit_summary",
        description=(
            "Read-only operator view of the agent audit ledger. "
            "Decides nothing; never mutates the ledger; never prints "
            "secrets or full command/diff payloads."
        ),
    )
    p.add_argument(
        "--date",
        default=None,
        help="UTC date for the ledger file (default: today). Ignored when --path is given.",
    )
    p.add_argument(
        "--path",
        default=None,
        help="Explicit ledger path (overrides --date).",
    )
    p.add_argument(
        "--view",
<<<<<<< fix/v3.15.15.15-agent-audit-subagent-attribution
        choices=["timeline", "groups", "attribution", "both"],
        default="both",
        help=(
            "Which view to render. 'attribution' is the inferred "
            "subagent view from reporting.subagent_attribution; "
            "convenience-only, never source-of-truth (see ADR-016 "
            "proposal). Default: both (timeline + groups)."
        ),
=======
        choices=["timeline", "groups", "both"],
        default="both",
        help="Which view to render (default: both).",
>>>>>>> main
    )
    p.add_argument(
        "--format",
        choices=["json", "table"],
        default="json",
        help="Output format (default: json).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Number of events to include in timeline (default: 50).",
    )
    p.add_argument(
        "--actor",
        default=None,
        help="Filter timeline by actor (e.g. claude:hook).",
    )
    p.add_argument(
        "--outcome",
        default=None,
        help="Filter timeline by outcome (e.g. blocked_by_hook).",
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation (0 for compact). Ignored when --format=table.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    path = _ledger_path_for(args.date, args.path)

    out: dict[str, Any] = {}
    if args.view in ("timeline", "both"):
        out["timeline"] = collect_timeline(
            path,
            limit=args.limit,
            actor=args.actor,
            outcome=args.outcome,
        )
    if args.view in ("groups", "both"):
        out["groups"] = collect_groups(path)
<<<<<<< fix/v3.15.15.15-agent-audit-subagent-attribution
    if args.view == "attribution":
        # Lazy import to keep the no-attribution code paths free of the
        # extra dependency on subagent_attribution module state.
        from reporting import subagent_attribution

        out["attribution"] = subagent_attribution.collect_attribution(path)
=======
>>>>>>> main

    assert_no_secrets(out)

    if args.format == "json":
        indent = args.indent if args.indent and args.indent > 0 else None
        json.dump(out, sys.stdout, indent=indent, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    # table
    if "timeline" in out:
        sys.stdout.write(render_timeline_table(out["timeline"]))
    if "groups" in out:
        sys.stdout.write(render_groups_table(out["groups"]))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
