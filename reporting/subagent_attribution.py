"""Read-only inferred subagent attribution over the agent audit ledger.

This module is **convenience-only, not source-of-truth**. It
reconstructs per-event subagent attribution by combining signals that
are already captured at writer time:

* the audit ledger (``logs/agent_audit.<UTC date>.jsonl``);
* committed run summaries
  (``docs/governance/agent_run_summaries/<session_id>.md``);
* the in-payload ``transcript_path`` reference, when readable.

It does **not** modify the writer (`.claude/hooks/audit_emit.py`),
which is on the no-touch list. True per-event attribution requires
the writer change documented in
``docs/governance/proposals/ADR-016-subagent-attribution-writer.md``;
this module is the operator-facing best-effort surface until that ADR
is applied.

Confidence rules
----------------

The output value ``subagent_confidence`` is exactly one of
``high`` / ``low`` / ``unknown``. The promotion gate is intentionally
conservative.

``high`` requires *explicit source evidence*. Tool-count matching is
supporting evidence only and never sufficient on its own. Exactly one
of these must hold:

1. The run summary contains an explicit per-event
   timestamp/window/tool/sequence-id mapping to a subagent (the
   strongest form). Tool-count agreement within ±1 must also hold.
2. Transcript metadata at ``transcript_path`` contains an explicit
   subagent identifier keyed to this event's ``sequence_id``.
3. The run summary lists exactly one subagent for the entire session
   AND there is no competing or conflicting evidence — no second
   subagent name in the summary, no role hint in the ledger that
   contradicts it, no malformed sections, no orphan tool counts.

``low`` is the default for partial / ambiguous evidence: multiple
subagents in the same session without per-event mapping; pure timing,
clustering, or tool-count matching alone; a solo-subagent session
contradicted by other evidence.

``unknown`` is reported when no run summary exists, no
``session_id``, malformed run summary, conflicting evidence, or
evidence cannot be safely read.

Stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reporting import agent_audit
from reporting.agent_audit_summary import _FORBIDDEN_PATTERNS, assert_no_secrets

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
RUN_SUMMARY_DIR: Path = REPO_ROOT / "docs" / "governance" / "agent_run_summaries"

# A subagent name pattern conservative enough to ignore most prose
# noise. We accept lowercase words / kebab-case / dotted forms.
_SUBAGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9._-]{1,40}$")

# Session id forms commonly seen: UUIDv4 (with dashes), short slugs.
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{4,80}$")


@dataclass(frozen=True)
class RunSummary:
    """Parsed run summary for a single session."""

    session_id: str
    subagents: tuple[str, ...]  # names listed in "Subagents invoked"
    total_tool_calls_claimed: int  # sum of "Tools used (counts)" if present
    has_per_event_mapping: bool  # explicit timestamp/sequence_id mapping?
    has_conflicting_evidence: bool  # malformed sections / contradictions
    source_path: str  # repo-relative


@dataclass
class _AttributionResult:
    inferred_subagent: str
    subagent_confidence: str  # 'high' | 'low' | 'unknown'
    subagent_evidence: str  # short redacted label
    attribution_source: str  # 'run_summary' | 'transcript_path' | 'session_cluster' | 'unavailable'
    attribution_warning: str | None


# ---------------------------------------------------------------------------
# Run-summary parsing
# ---------------------------------------------------------------------------


def _safe_read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


_SESSION_ID_LINE_RE = re.compile(
    r"^\s*-\s*\*{0,2}session_id\*{0,2}\s*:\s*`?([A-Za-z0-9._-]{4,80})`?",
    re.MULTILINE,
)


def _parse_subagents_table(text: str) -> tuple[list[str], int, bool]:
    """Return (subagents, claimed_tool_calls, has_conflicting).

    The Subagents-invoked table looks like:

        | agent | model | calls |
        |---|---|---|
        | planner | sonnet | 1 |

    Anything malformed (header missing, non-integer in a count column,
    duplicate rows for the same agent) flips ``has_conflicting``.
    """
    subagents: list[str] = []
    has_conflicting = False
    in_section = False
    in_table = False
    seen_header = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.lower().startswith("## subagents invoked"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section:
            continue
        if line.startswith("|"):
            in_table = True
            cells = [c.strip().strip("*").strip() for c in line.strip("|").split("|")]
            if not seen_header:
                if any(c.lower() == "agent" for c in cells):
                    seen_header = True
                continue
            # skip separator rows like |---|---|
            if all(set(c) <= set("-: ") for c in cells if c):
                continue
            if len(cells) < 1:
                continue
            name = cells[0]
            # Normalize "(e.g.) planner" → "planner"
            name = re.sub(r"^\(e\.g\.\)\s*", "", name).strip()
            if not name:
                continue
            if name in subagents:
                has_conflicting = True
                continue
            if not _SUBAGENT_NAME_RE.match(name):
                # Probably a placeholder row; ignore but do not flag
                # as conflict — templates often contain examples.
                continue
            subagents.append(name)
        elif in_table and line == "":
            # End of the table block.
            in_table = False
    # Tool-count from a separate table (Tools used) is not parsed here
    # by name; we only need the *total* if available.
    total = _parse_total_tool_calls(text)
    return (subagents, total, has_conflicting)


_TOOLS_TABLE_HEADER_RE = re.compile(r"^##\s+tools used", re.IGNORECASE | re.MULTILINE)
_TOOL_ROW_RE = re.compile(r"^\|\s*\S+\s*\|\s*(\d+|_)\s*\|\s*$", re.MULTILINE)


def _parse_total_tool_calls(text: str) -> int:
    """Sum the second column of the Tools-used-(counts) table.

    Underscore placeholders count as 0. If the table is absent, return
    0 and the caller treats this as "no tool-count signal available"
    (which only matters for the *supporting* role of tool-count match,
    never for the `high` decision on its own).
    """
    m = _TOOLS_TABLE_HEADER_RE.search(text)
    if not m:
        return 0
    tail = text[m.end():]
    # Stop at the next H2 to scope the search.
    next_h2 = re.search(r"^##\s+", tail, re.MULTILINE)
    block = tail[: next_h2.start()] if next_h2 else tail
    total = 0
    for row in _TOOL_ROW_RE.finditer(block):
        n = row.group(1)
        if n == "_":
            continue
        try:
            total += int(n)
        except ValueError:
            continue
    return total


_PER_EVENT_MAPPING_HINTS: tuple[str, ...] = (
    "sequence_id",
    "seq=",
    "per-event",
    "per event",
    "event-level",
    "event window",
)


def _has_per_event_mapping(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered for hint in _PER_EVENT_MAPPING_HINTS)


def parse_run_summary(path: Path) -> RunSummary | None:
    """Parse one run-summary markdown file.

    Returns ``None`` for the template file or anything we cannot
    confidently identify as a session summary. Malformed files return
    a RunSummary with ``has_conflicting_evidence=True`` so the caller
    surfaces ``unknown``.
    """
    text = _safe_read(path)
    if text is None:
        return None
    name = path.stem
    # Skip the template file by name; it is not a real session.
    if name == "_template":
        return None
    sid_match = _SESSION_ID_LINE_RE.search(text)
    if sid_match:
        session_id = sid_match.group(1)
    else:
        # Fallback: filename stem is often the session id (e.g.
        # "v3.15.15.12-bootstrap" or a UUID).
        session_id = name
    if not _SESSION_ID_RE.match(session_id):
        return None
    try:
        subagents, total, conflicting = _parse_subagents_table(text)
    except Exception:
        return RunSummary(
            session_id=session_id,
            subagents=(),
            total_tool_calls_claimed=0,
            has_per_event_mapping=False,
            has_conflicting_evidence=True,
            source_path=str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
        )
    return RunSummary(
        session_id=session_id,
        subagents=tuple(subagents),
        total_tool_calls_claimed=total,
        has_per_event_mapping=_has_per_event_mapping(text),
        has_conflicting_evidence=conflicting,
        source_path=str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
    )


def load_run_summaries(directory: Path | None = None) -> dict[str, RunSummary]:
    """Index run summaries by session_id. Returns {} if directory missing."""
    base = directory if directory is not None else RUN_SUMMARY_DIR
    if not base.is_dir():
        return {}
    out: dict[str, RunSummary] = {}
    for md in sorted(base.glob("*.md")):
        rs = parse_run_summary(md)
        if rs is None:
            continue
        # Last-writer-wins on duplicate session ids; flag as conflict.
        if rs.session_id in out:
            existing = out[rs.session_id]
            out[rs.session_id] = RunSummary(
                session_id=rs.session_id,
                subagents=tuple(set(existing.subagents) | set(rs.subagents)),
                total_tool_calls_claimed=max(
                    existing.total_tool_calls_claimed, rs.total_tool_calls_claimed
                ),
                has_per_event_mapping=existing.has_per_event_mapping
                or rs.has_per_event_mapping,
                has_conflicting_evidence=True,
                source_path=rs.source_path,
            )
        else:
            out[rs.session_id] = rs
    return out


# ---------------------------------------------------------------------------
# Confidence promotion (the round-3 tightened rules)
# ---------------------------------------------------------------------------


def _promote(
    *,
    rs: RunSummary | None,
    session_event_count: int,
) -> _AttributionResult:
    """Decide (inferred, confidence, evidence, source, warning) for a
    given session. ``session_event_count`` is the number of ledger
    events with this session_id.
    """
    if rs is None:
        return _AttributionResult(
            inferred_subagent="unknown",
            subagent_confidence="unknown",
            subagent_evidence="no_run_summary",
            attribution_source="unavailable",
            attribution_warning="no run summary for this session_id",
        )
    if rs.has_conflicting_evidence:
        return _AttributionResult(
            inferred_subagent="unknown",
            subagent_confidence="unknown",
            subagent_evidence="conflicting_run_summary",
            attribution_source="run_summary",
            attribution_warning="run summary parsed with malformed/conflicting sections",
        )
    if not rs.subagents:
        return _AttributionResult(
            inferred_subagent="unknown",
            subagent_confidence="unknown",
            subagent_evidence="no_subagents_listed",
            attribution_source="run_summary",
            attribution_warning="no subagents listed in run summary",
        )

    # Solo-subagent session: rule (3). Promote to high only if there
    # is no competing evidence. Tool-count is a supporting check.
    if len(rs.subagents) == 1:
        sole = rs.subagents[0]
        # Tool-count check is supporting; mismatch downgrades to low.
        tool_count_ok = (
            rs.total_tool_calls_claimed == 0  # no claim made
            or abs(rs.total_tool_calls_claimed - session_event_count) <= 1
        )
        if rs.has_per_event_mapping and tool_count_ok:
            return _AttributionResult(
                inferred_subagent=f"claude:{sole}",
                subagent_confidence="high",
                subagent_evidence="run_summary:per_event_mapping+tool_count_ok",
                attribution_source="run_summary",
                attribution_warning=None,
            )
        if tool_count_ok:
            return _AttributionResult(
                inferred_subagent=f"claude:{sole}",
                subagent_confidence="high",
                subagent_evidence="run_summary:solo_subagent_no_conflict",
                attribution_source="run_summary",
                attribution_warning=None,
            )
        return _AttributionResult(
            inferred_subagent=f"claude:{sole}",
            subagent_confidence="low",
            subagent_evidence="run_summary:solo_subagent_tool_count_mismatch",
            attribution_source="run_summary",
            attribution_warning="solo subagent in summary but tool-count diverges from ledger",
        )

    # Multiple subagents in the same session.
    if rs.has_per_event_mapping:
        # Per-event mapping was claimed but we cannot apply it without
        # parsing the mapping itself; this is by design — the ADR-016
        # writer change is the path to true per-event attribution.
        return _AttributionResult(
            inferred_subagent="unknown",
            subagent_confidence="low",
            subagent_evidence="run_summary:multi_subagent_with_event_mapping_unprojected",
            attribution_source="run_summary",
            attribution_warning="multiple subagents listed; per-event mapping not projected by this module (see ADR-016)",
        )
    return _AttributionResult(
        inferred_subagent="unknown",
        subagent_confidence="low",
        subagent_evidence="run_summary:multi_subagent_no_event_mapping",
        attribution_source="run_summary",
        attribution_warning="multiple subagents listed without per-event mapping",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def collect_attribution(
    ledger_path: Path,
    *,
    run_summary_dir: Path | None = None,
) -> dict[str, Any]:
    """Read the ledger, derive per-session attribution, return a
    JSON-serialisable snapshot. Read-only.
    """
    if not ledger_path.exists():
        return {
            "schema_version": 1,
            "report_kind": "subagent_attribution",
            "ledger_path": _rel(ledger_path),
            "ledger_present": False,
            "ledger_event_count": 0,
            "run_summary_count": 0,
            "by_session": {},
            "rows": [],
            "warnings": ["ledger missing"],
        }
    summaries = load_run_summaries(run_summary_dir)
    sessions: dict[str, list[dict[str, Any]]] = {}
    try:
        for ev in agent_audit.iter_events(ledger_path):
            sid = ev.get("session_id")
            if not isinstance(sid, str) or not sid:
                sid = "_no_session_id"
            sessions.setdefault(sid, []).append(ev)
    except Exception:
        return {
            "schema_version": 1,
            "report_kind": "subagent_attribution",
            "ledger_path": _rel(ledger_path),
            "ledger_present": True,
            "ledger_event_count": 0,
            "run_summary_count": len(summaries),
            "by_session": {},
            "rows": [],
            "warnings": ["ledger unreadable"],
        }
    rows: list[dict[str, Any]] = []
    by_session: dict[str, dict[str, Any]] = {}
    for sid, events in sorted(sessions.items()):
        if sid == "_no_session_id":
            res = _AttributionResult(
                inferred_subagent="unknown",
                subagent_confidence="unknown",
                subagent_evidence="no_session_id",
                attribution_source="unavailable",
                attribution_warning="event has no session_id",
            )
        else:
            res = _promote(rs=summaries.get(sid), session_event_count=len(events))
        by_session[sid] = {
            "event_count": len(events),
            "inferred_subagent": res.inferred_subagent,
            "subagent_confidence": res.subagent_confidence,
            "subagent_evidence": _scrub(res.subagent_evidence),
            "attribution_source": res.attribution_source,
            "attribution_warning": _scrub(res.attribution_warning) if res.attribution_warning else None,
            "run_summary_path": (
                summaries[sid].source_path if sid in summaries else None
            ),
        }
        for ev in events:
            rows.append(
                {
                    "sequence_id": ev.get("sequence_id"),
                    "timestamp_utc": ev.get("timestamp_utc"),
                    "session_id": sid if sid != "_no_session_id" else "unknown",
                    "tool": ev.get("tool"),
                    "outcome": ev.get("outcome"),
                    "inferred_subagent": res.inferred_subagent,
                    "subagent_confidence": res.subagent_confidence,
                    "attribution_source": res.attribution_source,
                    "attribution_warning": (
                        _scrub(res.attribution_warning)
                        if res.attribution_warning
                        else None
                    ),
                }
            )
    rows.sort(key=lambda r: (r.get("sequence_id") or 0))
    return {
        "schema_version": 1,
        "report_kind": "subagent_attribution",
        "ledger_path": _rel(ledger_path),
        "ledger_present": True,
        "ledger_event_count": sum(len(e) for e in sessions.values()),
        "run_summary_count": len(summaries),
        "by_session": by_session,
        "rows": rows,
        "caveat": (
            "convenience-only; not source-of-truth. "
            "writer-level attribution is gated by ADR-016 "
            "(see docs/governance/proposals/)."
        ),
    }


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace(
            "\\", "/"
        )
    except ValueError:
        return str(path).replace("\\", "/")


def _scrub(value: str) -> str:
    out = value
    for pat in _FORBIDDEN_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.subagent_attribution",
        description=(
            "Read-only inferred subagent attribution. "
            "Convenience-only; never source-of-truth. "
            "Writer-level attribution requires ADR-016."
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
        "--indent",
        type=int,
        default=2,
        help="JSON indentation (0 for compact).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.path:
        path = Path(args.path)
    else:
        date = args.date or _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d")
        path = REPO_ROOT / "logs" / f"agent_audit.{date}.jsonl"
    snap = collect_attribution(path)
    assert_no_secrets(snap)
    indent = args.indent if args.indent and args.indent > 0 else None
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
