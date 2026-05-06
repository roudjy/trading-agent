"""v3.15.16.10 PR-4 / A6 — Autonomous Backlog Discipline summary.

Read-only projection that reads ``logs/proposal_queue/latest.json``
and groups every proposal into the closed Agent Execution Authority
buckets:

* ``permanently_denied`` — classifier returned PERMANENTLY_DENIED.
* ``needs_human``        — classifier returned NEEDS_HUMAN (any non-
                           fail-safe reason).
* ``auto_allowed``       — classifier returned AUTO_ALLOWED.
* ``stale_or_resolved``  — proposal_id absent from the current
                           snapshot but present in the prior; or
                           ``affected_files`` is empty after path
                           normalization; or source path lies under
                           ``docs/roadmap/archive/``.
* ``unknown_failsafe``   — classifier returned NEEDS_HUMAN with reason
                           ``unknown_risk_or_target_fail_safe``.

The module never decides, never mutates, never spawns subprocesses,
never opens sockets. It is a deterministic projection of the existing
artifacts.

Artifact: ``logs/autonomous_backlog/latest.json``.

CLI::

    python -m reporting.autonomous_backlog_summary
    python -m reporting.autonomous_backlog_summary --indent 2
    python -m reporting.autonomous_backlog_summary --no-write

Reads-only:
* ``logs/proposal_queue/latest.json`` — current snapshot.
* ``logs/autonomous_backlog/last_seen_proposal_ids.json`` — small
  prior-id ledger maintained by this module itself for stale
  detection. Atomic write; never reads any other ledger.

Hard guarantees (pinned by tests):
* Stdlib + ``reporting.execution_authority`` + ``reporting.proposal_queue``.
* No subprocess, no network, no ``gh``, no ``git``.
* No imports from ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``.
* No mutation behaviour, no approval-inbox decisions.
* Bounded scalars in evidence — no PR text, no diffs, no commit
  messages, no file body content.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import execution_authority as ea

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.10"

PROPOSAL_QUEUE_LATEST: Final[Path] = (
    REPO_ROOT / "logs" / "proposal_queue" / "latest.json"
)
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "autonomous_backlog"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
PRIOR_IDS_LEDGER: Final[Path] = ARTIFACT_DIR / "last_seen_proposal_ids.json"

ARTIFACT_RELATIVE_PATH: Final[str] = "logs/autonomous_backlog/latest.json"

#: Closed bucket vocabulary. Tests assert exhaustiveness.
GROUPS: Final[tuple[str, ...]] = (
    "permanently_denied",
    "needs_human",
    "auto_allowed",
    "stale_or_resolved",
    "unknown_failsafe",
)

#: Marker reason for classifier fail-safe (mirrored from the policy doc).
_REASON_UNKNOWN_FAIL_SAFE: Final[str] = "unknown_risk_or_target_fail_safe"


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


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomic temp-file + ``os.replace`` write under ``logs/`` only."""
    posix = path.as_posix()
    if "/logs/" not in posix and not posix.startswith("logs/"):
        raise ValueError(
            "autonomous_backlog_summary._atomic_write_json refuses "
            f"non-logs/ output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".autonomous_backlog_summary.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _normalize_path(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")


def _is_archive_path(p: str) -> bool:
    n = _normalize_path(p).lower()
    return n.startswith("docs/roadmap/archive/")


def _proposal_target_path(proposal: dict[str, Any]) -> str:
    """Choose the representative target_path for the classifier call.

    Preference order: first non-empty ``affected_files`` entry,
    otherwise the proposal's ``source`` path. Empty string falls
    through to the classifier's ``other`` category, which is the
    correct fail-safe.
    """
    affected = proposal.get("affected_files") or []
    if isinstance(affected, list) and affected:
        first = affected[0]
        if isinstance(first, str) and first.strip():
            return _normalize_path(first)
    src = proposal.get("source")
    if isinstance(src, str) and src.strip():
        return _normalize_path(src)
    return ""


def _proposal_risk(proposal: dict[str, Any]) -> str:
    raw = proposal.get("risk_class")
    if isinstance(raw, str) and raw in ea.RISK_CLASSES:
        return raw
    return ea.RISK_UNKNOWN


def _classify_proposal(proposal: dict[str, Any]) -> ea.ExecutionDecision:
    """Run a proposal through ``ea.classify`` as a ``file_edit`` action."""
    return ea.classify(
        action_type="file_edit",
        target_path=_proposal_target_path(proposal),
        risk_class=_proposal_risk(proposal),
    )


def _bucket_for_proposal(
    proposal: dict[str, Any],
    decision: ea.ExecutionDecision,
    prior_ids: set[str],
    current_ids: set[str],
) -> str:
    """Bucket a single proposal. Stale-detection takes precedence
    only when the proposal is *no longer* in the current snapshot.
    Archive paths and empty affected-files are stale-or-resolved
    even if currently present (they cannot move to AUTO_ALLOWED)."""
    pid = proposal.get("proposal_id", "")
    src = _normalize_path(proposal.get("source") or "")

    if pid not in current_ids and pid in prior_ids:
        return "stale_or_resolved"

    if _is_archive_path(src):
        return "stale_or_resolved"

    affected = proposal.get("affected_files") or []
    if not affected:
        # No concrete file means there's nothing for the classifier
        # to act on. Treat as stale_or_resolved (the proposal needs
        # to name files before it can be classified for execution).
        # Exception: if the classifier already returned a non-default
        # reason (governance/canonical/etc.), respect it.
        if decision.decision == ea.DECISION_AUTO_ALLOWED:
            return "stale_or_resolved"

    if decision.decision == ea.DECISION_PERMANENTLY_DENIED:
        return "permanently_denied"
    if decision.decision == ea.DECISION_AUTO_ALLOWED:
        return "auto_allowed"
    # ea.DECISION_NEEDS_HUMAN — distinguish the fail-safe from real
    # governance gates.
    assert decision.decision == ea.DECISION_NEEDS_HUMAN, decision.decision
    if decision.reason == _REASON_UNKNOWN_FAIL_SAFE:
        return "unknown_failsafe"
    return "needs_human"


def _build_row(proposal: dict[str, Any], decision: ea.ExecutionDecision) -> dict[str, Any]:
    """Bounded per-proposal row. Scalars only — no body content."""
    return {
        "proposal_id": proposal.get("proposal_id"),
        "title": proposal.get("title"),
        "source": _normalize_path(proposal.get("source") or ""),
        "risk_class": _proposal_risk(proposal),
        "proposal_type": proposal.get("proposal_type"),
        "status": proposal.get("status"),
        "affected_files": list(proposal.get("affected_files") or []),
        "execution_authority_decision": decision.decision,
        "execution_authority_reason": decision.reason,
        "execution_authority_target_path_category": decision.target_path_category,
    }


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def _load_prior_ids() -> set[str]:
    payload = _read_json(PRIOR_IDS_LEDGER) or {}
    raw = payload.get("proposal_ids") or []
    if not isinstance(raw, list):
        return set()
    return {x for x in raw if isinstance(x, str)}


def _save_prior_ids(current_ids: set[str]) -> None:
    """Persist the current snapshot's id set as the next 'prior'.
    Skip-on-error: persistence is informational, not an invariant."""
    try:
        _atomic_write_json(
            PRIOR_IDS_LEDGER,
            {
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "saved_at_utc": _utcnow(),
                "proposal_ids": sorted(current_ids),
            },
        )
    except OSError:
        pass


def collect_snapshot(
    *,
    proposal_queue_path: Path | None = None,
    persist_prior_ids: bool = True,
) -> dict[str, Any]:
    """Return the read-only autonomous-backlog snapshot.

    Args:
        proposal_queue_path: override the default
            ``logs/proposal_queue/latest.json`` source. Tests pass a
            synthetic fixture path here.
        persist_prior_ids: when True (the default at runtime), persist
            the current snapshot's id set so the *next* run can detect
            stale items. Tests typically set this to False to keep
            their fixtures hermetic.
    """
    pq_path = proposal_queue_path if proposal_queue_path is not None else PROPOSAL_QUEUE_LATEST
    pq_payload = _read_json(pq_path)
    if pq_payload is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "autonomous_backlog_summary",
            "generated_at_utc": _utcnow(),
            "source_path": str(pq_path),
            "source_available": False,
            "groups": {g: [] for g in GROUPS},
            "counts": {g: 0 for g in GROUPS} | {"total": 0},
            "execution_authority_module_version": ea.MODULE_VERSION,
        }

    proposals = pq_payload.get("proposals") or []
    if not isinstance(proposals, list):
        proposals = []

    current_ids = {
        str(p.get("proposal_id"))
        for p in proposals
        if isinstance(p, dict) and p.get("proposal_id")
    }
    prior_ids = _load_prior_ids()

    grouped: dict[str, list[dict[str, Any]]] = {g: [] for g in GROUPS}
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        decision = _classify_proposal(proposal)
        bucket = _bucket_for_proposal(proposal, decision, prior_ids, current_ids)
        grouped[bucket].append(_build_row(proposal, decision))

    # Stale rows for proposals that disappeared since last run.
    for missing_id in prior_ids - current_ids:
        grouped["stale_or_resolved"].append(
            {
                "proposal_id": missing_id,
                "title": None,
                "source": "",
                "risk_class": ea.RISK_UNKNOWN,
                "proposal_type": None,
                "status": "absent_from_current_snapshot",
                "affected_files": [],
                "execution_authority_decision": None,
                "execution_authority_reason": "stale_proposal_id_disappeared",
                "execution_authority_target_path_category": None,
            }
        )

    counts = {g: len(grouped[g]) for g in GROUPS}
    counts["total"] = sum(counts.values())

    if persist_prior_ids:
        _save_prior_ids(current_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "autonomous_backlog_summary",
        "generated_at_utc": _utcnow(),
        "source_path": str(pq_path),
        "source_available": True,
        "groups": grouped,
        "counts": counts,
        "execution_authority_module_version": ea.MODULE_VERSION,
    }


def write_outputs(snapshot: dict[str, Any]) -> Path:
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# Recurring-maintenance executor (read-only)
# ---------------------------------------------------------------------------


def run_once(*, write: bool = True) -> dict[str, Any]:
    """One-shot refresh: collect snapshot and (optionally) write the
    ``logs/autonomous_backlog/latest.json`` artifact. Used by
    ``reporting.recurring_maintenance`` via its closed job registry."""
    snap = collect_snapshot()
    if write and snap.get("source_available"):
        write_outputs(snap)
    return snap


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.autonomous_backlog_summary",
        description=(
            "Read-only autonomous-backlog summary. Groups every proposal "
            "from logs/proposal_queue/latest.json by Agent Execution "
            "Authority decision (permanently_denied / needs_human / "
            "auto_allowed / stale_or_resolved / unknown_failsafe). "
            "Decides nothing; mutates nothing. Use --no-write to print "
            "the snapshot to stdout without persisting it."
        ),
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent (0 for compact).",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Do not persist logs/autonomous_backlog/latest.json (stdout only).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    indent = args.indent if args.indent and args.indent > 0 else None
    snap = collect_snapshot()
    if not args.no_write and snap.get("source_available"):
        write_outputs(snap)
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
