"""Roadmap Priority Projection (v3.15.16.2).

Pure read-only projection over the proposal queue + roadmap
execution protocol. Selects exactly one ``chosen_next_up`` item
under a deterministic eligibility + ranking policy, and writes the
result to ``logs/roadmap_priority/latest.json``.

This module:

* never starts work
* never opens a branch
* never opens a PR
* never merges
* never calls ``gh``
* never calls any external service
* never mutates the proposal queue, the protocol module, or any
  other artifact

Hard guarantees (enforced by code AND tests)
--------------------------------------------

* Stdlib-only. No subprocess, no ``gh``, no ``git``, no network.
* Reads ``logs/proposal_queue/latest.json`` only. Never invokes
  the proposal queue's CLI; the recurring maintenance scheduler is
  the canonical refresh path for that artifact.
* Output limited to ``logs/roadmap_priority/``.
* Atomic writes (``tmp`` + ``os.replace``); no in-place edits.
* ``safe_to_execute`` is hard-coded ``false`` at the digest level —
  the prioritizer surfaces; the operator decides.
* Missing or malformed proposal_queue artifact produces
  ``final_recommendation = "not_available"``; never silently OK.
* Risk classification delegates to
  ``reporting.roadmap_execution_protocol.plan_item`` — there is no
  second source of truth.
* Determinism: two runs on the same input produce a byte-identical
  ``chosen_next_up`` and ``candidates`` list (modulo the
  ``generated_at_utc`` timestamp).

CLI
---

::

    python -m reporting.roadmap_priority --mode dry-run
    python -m reporting.roadmap_priority --mode dry-run --no-write
    python -m reporting.roadmap_priority --status

Stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from reporting import roadmap_execution_protocol as _rep

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
MODULE_VERSION: str = "v3.15.16.2"
SCHEMA_VERSION: int = 1

DIGEST_DIR_JSON: Path = REPO_ROOT / "logs" / "roadmap_priority"
SOURCE_PROPOSAL_QUEUE: Path = (
    REPO_ROOT / "logs" / "proposal_queue" / "latest.json"
)


# ---------------------------------------------------------------------------
# Closed taxonomies
# ---------------------------------------------------------------------------


REC_READY: str = "ready_for_implementation"
REC_NOTHING_READY: str = "nothing_ready"
REC_NOT_AVAILABLE: str = "not_available"

FINAL_RECOMMENDATIONS: tuple[str, ...] = (
    REC_READY,
    REC_NOTHING_READY,
    REC_NOT_AVAILABLE,
)


# Eligibility filter labels — surfaced verbatim in ``filtered_out``
# so the operator can audit why each candidate was rejected.
FILTER_STATUS_NOT_PROPOSED: str = "status_not_proposed"
FILTER_RISK_HIGH: str = "risk_high_excluded"
FILTER_PROTOCOL_DECISION: str = "protocol_decision_not_allowed_read_only"
FILTER_PROTOCOL_IMPL_NOT_ALLOWED: str = "protocol_implementation_not_allowed"
FILTER_PROTOCOL_REQUIRES_HUMAN: str = "protocol_requires_human"
FILTER_PROTOCOL_SAFE_TO_EXECUTE_TRUE: str = "protocol_safe_to_execute_true"
FILTER_PROTOCOL_ERROR: str = "protocol_classification_error"
FILTER_INVALID_PROPOSAL_SHAPE: str = "invalid_proposal_shape"

FILTER_REASONS: tuple[str, ...] = (
    FILTER_STATUS_NOT_PROPOSED,
    FILTER_RISK_HIGH,
    FILTER_PROTOCOL_DECISION,
    FILTER_PROTOCOL_IMPL_NOT_ALLOWED,
    FILTER_PROTOCOL_REQUIRES_HUMAN,
    FILTER_PROTOCOL_SAFE_TO_EXECUTE_TRUE,
    FILTER_PROTOCOL_ERROR,
    FILTER_INVALID_PROPOSAL_SHAPE,
)


# Ranking key 1: risk_class. LOW before MEDIUM. (HIGH already
# filtered out — its position here is unreachable in practice.)
_RISK_RANK: dict[str, int] = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2,
    "UNKNOWN": 3,
}


# Ranking key 2: proposal_type. Most-leveraged unblockers first
# (observability before reporting before docs before tests before
# UX before everything else). The full taxonomy from
# ``reporting.proposal_queue`` is included so a future type does
# not silently land at the bottom — unknown types get the
# highest numerical rank (last).
_PROPOSAL_TYPE_RANK: dict[str, int] = {
    # Most-leveraged unblockers — these make later work observable
    # and reviewable.
    "observability_addition": 0,
    "observability_gap": 1,
    # Read-only reporting / docs.
    "reporting_read_only": 2,
    "docs_only": 3,
    # Test gaps — close before running new code.
    "testing_gap": 4,
    "test_only": 5,
    # UX surface only (reads existing data).
    "ux_gap": 6,
    "frontend_read_only": 7,
    # CI / dependency hygiene.
    "ci_hygiene": 8,
    "dependency_cleanup": 9,
    # Release candidates — bigger scope, last.
    "release_candidate": 10,
    # Anything else → last; this also covers types we explicitly
    # never want to auto-select (governance_change,
    # roadmap_adoption, roadmap_diff, tooling_intake,
    # approval_required, blocked_unknown). The protocol filter
    # above will already reject most of these via the
    # implementation_allowed gate.
}
_FALLBACK_TYPE_RANK: int = 99


# ---------------------------------------------------------------------------
# Time + path helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace(
            "\\", "/"
        )
    except ValueError:
        return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Proposal-queue read (passive; never invokes the producer)
# ---------------------------------------------------------------------------


def _read_proposal_queue(
    path: Path = SOURCE_PROPOSAL_QUEUE,
) -> tuple[dict[str, Any] | None, str | None]:
    """Read ``logs/proposal_queue/latest.json``. Returns
    ``(snapshot, None)`` on success or ``(None, reason)`` on any
    error. Never raises."""
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


# ---------------------------------------------------------------------------
# Eligibility + protocol classification
# ---------------------------------------------------------------------------


def _proposal_to_protocol_input(p: Mapping[str, Any]) -> dict[str, Any]:
    """Lift a proposal_queue record into the input shape that
    ``roadmap_execution_protocol.plan_item`` accepts. We pass only
    the title + summary + affected_files + a few boolean overrides;
    the protocol classifier owns the actual decision."""
    return {
        "item_id": p.get("proposal_id"),
        "source": "reporting.roadmap_priority",
        "source_type": "proposal_queue_record",
        "title": p.get("title"),
        "summary": p.get("summary"),
        "affected_files": p.get("affected_files") or [],
        "labels": p.get("labels") or [],
        "risk_class": p.get("risk_class"),
        # The proposal_queue already classified governance / live /
        # paid / telemetry concerns into its own status; we forward
        # the conservative defaults so the protocol re-checks from
        # the file paths and prose. We never mark a flag True from
        # this side.
        "requires_secret": False,
        "requires_external_account": False,
        "requires_paid_tool": False,
        "has_telemetry_or_data_egress": False,
        "touches_governance": False,
        "touches_frozen_contract": False,
        "touches_live_paper_shadow_risk": False,
        "touches_ci_or_tests": False,
        "changes_canonical_roadmap": False,
        "pr_author": "claude-code",
    }


def _classify_via_protocol(
    p: Mapping[str, Any], *, frozen_utc: str | None = None
) -> tuple[dict[str, Any] | None, str | None]:
    """Call ``roadmap_execution_protocol.plan_item`` for a single
    proposal. Returns ``(plan, None)`` on success or
    ``(None, error_reason)`` if the protocol call raises. Never
    raises."""
    try:
        plan = _rep.plan_item(
            _proposal_to_protocol_input(p), frozen_utc=frozen_utc
        )
    except Exception as e:  # noqa: BLE001 — defensive fence
        return (None, f"{type(e).__name__}: {e!s}"[:200])
    if not isinstance(plan, dict):
        return (None, "protocol_returned_non_dict")
    return (plan, None)


def _eligibility_filter(
    p: Mapping[str, Any], plan: Mapping[str, Any] | None, plan_error: str | None
) -> str | None:
    """Return the first eligibility filter that rejects this
    proposal, or ``None`` if every filter passes."""
    # Filter 1: shape sanity. The queue should never produce a row
    # without a proposal_id, but defensively reject anyway.
    if not isinstance(p.get("proposal_id"), str) or not p.get("proposal_id"):
        return FILTER_INVALID_PROPOSAL_SHAPE

    # Filter 2: status must be exactly "proposed". Anything else
    # (needs_human / blocked / approved / rejected / superseded /
    # done / unknown) is excluded.
    if p.get("status") != "proposed":
        return FILTER_STATUS_NOT_PROPOSED

    # Filter 3: risk_class must not be HIGH. The proposal_queue's
    # own classification is the first signal; the protocol's
    # classification is the second signal (Filter 5+) and may
    # downgrade or upgrade.
    if p.get("risk_class") == "HIGH":
        return FILTER_RISK_HIGH

    # Filter 4: the protocol call itself must have succeeded.
    if plan_error is not None or plan is None:
        return FILTER_PROTOCOL_ERROR

    # Filter 5: protocol decision must be allowed_read_only.
    if plan.get("decision") != "allowed_read_only":
        return FILTER_PROTOCOL_DECISION

    # Filter 6: protocol must explicitly mark
    # implementation_allowed=True. This rejects governance /
    # canonical-roadmap / live-path / secret / telemetry / paid
    # items even when the prose did not classify them via the
    # proposal queue.
    if not plan.get("implementation_allowed"):
        return FILTER_PROTOCOL_IMPL_NOT_ALLOWED

    # Filter 7: protocol must explicitly mark requires_human=False.
    if plan.get("requires_human"):
        return FILTER_PROTOCOL_REQUIRES_HUMAN

    # Filter 8: protocol must report safe_to_execute=False. The
    # protocol always sets this to False at the digest level; if
    # it ever returns True, that is itself a contract breach we
    # surface as a rejected candidate rather than silently picking.
    if plan.get("safe_to_execute"):
        return FILTER_PROTOCOL_SAFE_TO_EXECUTE_TRUE

    return None


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def _rank_key(
    p: Mapping[str, Any], plan: Mapping[str, Any]
) -> tuple[int, int, str]:
    """Stable sort key. Tuple ordering: (risk_rank, type_rank,
    proposal_id). Lower is better."""
    # Trust the protocol's risk classification when it disagrees
    # with the proposal queue (it is the canonical arbiter).
    risk = plan.get("risk_class") or p.get("risk_class") or "UNKNOWN"
    risk_rank = _RISK_RANK.get(str(risk), _RISK_RANK["UNKNOWN"])
    ptype = p.get("proposal_type") or "unknown"
    type_rank = _PROPOSAL_TYPE_RANK.get(str(ptype), _FALLBACK_TYPE_RANK)
    pid = str(p.get("proposal_id") or "")
    return (risk_rank, type_rank, pid)


# ---------------------------------------------------------------------------
# Snapshot construction
# ---------------------------------------------------------------------------


def _plan_summary(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Project a small, operator-readable subset of the protocol
    plan onto the priority digest. We never copy the full plan —
    the operator can run the protocol CLI for the full record.

    Note: this summary intentionally does NOT include
    ``safe_to_execute``. The digest's top-level ``safe_to_execute``
    field is the single canonical source of that signal and is
    pinned to literal ``False`` by a unit test; duplicating it
    here would double-write the same fact while also triggering
    the literal-False source-text guard against any
    ``bool(...)`` projection."""
    return {
        "decision": plan.get("decision"),
        "implementation_allowed": bool(plan.get("implementation_allowed")),
        "requires_human": bool(plan.get("requires_human")),
        "risk_class": plan.get("risk_class"),
        "item_type": plan.get("item_type"),
        "proposed_branch": plan.get("proposed_branch"),
        "proposed_release_id": plan.get("proposed_release_id"),
        "required_tests": list(plan.get("required_tests") or []),
        "expected_artifacts": list(plan.get("expected_artifacts") or []),
        "rollback_plan": list(plan.get("rollback_plan") or []),
    }


def _build_chosen_next_up(
    p: Mapping[str, Any], plan: Mapping[str, Any], rank: int
) -> dict[str, Any]:
    return {
        "proposal_id": p.get("proposal_id"),
        "title": p.get("title"),
        "summary": p.get("summary"),
        "source": p.get("source"),
        "proposal_type": p.get("proposal_type"),
        "risk_class": plan.get("risk_class") or p.get("risk_class"),
        "affected_files": list(p.get("affected_files") or []),
        "rank": rank,
        "rationale": _rationale(p, plan),
        "protocol_plan_summary": _plan_summary(plan),
    }


def _rationale(
    p: Mapping[str, Any], plan: Mapping[str, Any]
) -> str:
    """One-line operator-readable explanation of why this item won
    the ranking. Static phrasing — does not summarise the whole
    plan, just the dominant signal."""
    risk = plan.get("risk_class") or p.get("risk_class") or "UNKNOWN"
    ptype = p.get("proposal_type") or "unknown"
    return (
        f"risk {risk}, type {ptype}, "
        f"protocol decision {plan.get('decision')}; "
        "lowest-rank eligible candidate by deterministic policy"
    )


def _build_candidate_record(
    *, p: Mapping[str, Any], plan: Mapping[str, Any], rank: int
) -> dict[str, Any]:
    """One row in the ``candidates`` list (eligible items, ranked)."""
    return {
        "proposal_id": p.get("proposal_id"),
        "title": p.get("title"),
        "proposal_type": p.get("proposal_type"),
        "risk_class": plan.get("risk_class") or p.get("risk_class"),
        "rank": rank,
        "score_signals": {
            "risk_rank": _RISK_RANK.get(
                str(plan.get("risk_class") or p.get("risk_class") or "UNKNOWN"),
                _RISK_RANK["UNKNOWN"],
            ),
            "type_rank": _PROPOSAL_TYPE_RANK.get(
                str(p.get("proposal_type") or "unknown"),
                _FALLBACK_TYPE_RANK,
            ),
        },
    }


def _build_filtered_record(
    *, p: Mapping[str, Any], filter_reason: str, plan_error: str | None
) -> dict[str, Any]:
    """One row in the ``filtered_out`` list (rejected items)."""
    return {
        "proposal_id": p.get("proposal_id"),
        "title": p.get("title"),
        "proposal_type": p.get("proposal_type"),
        "risk_class": p.get("risk_class"),
        "filter_reason": filter_reason,
        "protocol_error": plan_error,
    }


def collect_snapshot(
    *,
    frozen_utc: str | None = None,
    proposals_override: Sequence[Mapping[str, Any]] | None = None,
    proposal_source_override: Path | None = None,
) -> dict[str, Any]:
    """Build the full priority digest. Pure function. Test fixtures
    can use ``proposals_override`` to skip the file read.
    ``proposal_source_override`` allows tests to point at a custom
    proposal_queue artifact path."""
    generated = frozen_utc or _utcnow()

    # Source ingestion. Tests can short-circuit via override.
    if proposals_override is not None:
        proposals: list[Mapping[str, Any]] = list(proposals_override)
        source_status = "ok"
        source_error: str | None = None
        source_path = "test_override"
        source_module_version: str | None = None
    else:
        path = proposal_source_override or SOURCE_PROPOSAL_QUEUE
        snap, err = _read_proposal_queue(path)
        if snap is None:
            return _build_not_available_digest(
                generated_at_utc=generated,
                reason=err or "unknown",
                source_path=_rel(path),
            )
        raw_proposals = snap.get("proposals")
        if not isinstance(raw_proposals, list):
            return _build_not_available_digest(
                generated_at_utc=generated,
                reason="proposals_field_not_a_list",
                source_path=_rel(path),
            )
        proposals = [p for p in raw_proposals if isinstance(p, dict)]
        source_status = "ok"
        source_error = None
        source_path = _rel(path)
        source_module_version = snap.get("module_version")

    eligible: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    filtered: list[dict[str, Any]] = []

    for p in proposals:
        plan, plan_error = _classify_via_protocol(p, frozen_utc=frozen_utc)
        reason = _eligibility_filter(p, plan, plan_error)
        if reason is None and plan is not None:
            eligible.append((p, plan))
        else:
            filtered.append(
                _build_filtered_record(
                    p=p,
                    filter_reason=reason or FILTER_PROTOCOL_ERROR,
                    plan_error=plan_error,
                )
            )

    # Stable rank: tuple sort, deterministic across runs.
    eligible.sort(key=lambda pp: _rank_key(pp[0], pp[1]))

    candidates: list[dict[str, Any]] = []
    for idx, (p, plan) in enumerate(eligible, start=1):
        candidates.append(
            _build_candidate_record(p=p, plan=plan, rank=idx)
        )

    chosen_next_up: dict[str, Any] | None = None
    if eligible:
        top_p, top_plan = eligible[0]
        chosen_next_up = _build_chosen_next_up(top_p, top_plan, rank=1)

    final_recommendation = (
        REC_READY if chosen_next_up is not None else REC_NOTHING_READY
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "roadmap_priority_digest",
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated,
        "mode": "dry-run",
        "source_proposal_queue": {
            "path": source_path,
            "status": source_status,
            "error": source_error,
            "module_version": source_module_version,
            "proposal_count": len(proposals),
        },
        "policy": {
            "filters": list(FILTER_REASONS),
            "ranking": [
                "risk_low_first",
                "observability_first",
                "reporting_first",
                "docs_first",
                "test_first",
                "ux_first",
                "frontend_first",
                "ci_hygiene_first",
                "dependency_cleanup_first",
                "release_candidate_last",
                "stable_proposal_id_tiebreak",
            ],
            "protocol_module_version": _rep.MODULE_VERSION,
        },
        "counts": {
            "proposals_total": len(proposals),
            "eligible_total": len(eligible),
            "filtered_out_total": len(filtered),
            "filtered_out_by_reason": _counts_by_reason(filtered),
        },
        "chosen_next_up": chosen_next_up,
        "candidates": candidates,
        "filtered_out": filtered,
        "final_recommendation": final_recommendation,
        "safe_to_execute": False,
    }


def _build_not_available_digest(
    *, generated_at_utc: str, reason: str, source_path: str
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "roadmap_priority_digest",
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated_at_utc,
        "mode": "dry-run",
        "source_proposal_queue": {
            "path": source_path,
            "status": "not_available",
            "error": reason,
            "module_version": None,
            "proposal_count": 0,
        },
        "policy": {
            "filters": list(FILTER_REASONS),
            "ranking": [],
            "protocol_module_version": _rep.MODULE_VERSION,
        },
        "counts": {
            "proposals_total": 0,
            "eligible_total": 0,
            "filtered_out_total": 0,
            "filtered_out_by_reason": {},
        },
        "chosen_next_up": None,
        "candidates": [],
        "filtered_out": [],
        "final_recommendation": REC_NOT_AVAILABLE,
        "safe_to_execute": False,
    }


def _counts_by_reason(filtered: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in filtered:
        r = row.get("filter_reason")
        if isinstance(r, str):
            counts[r] = counts.get(r, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def write_outputs(snapshot: Mapping[str, Any]) -> dict[str, str]:
    """Atomic write of latest.json + timestamped copy + history
    append. Mirrors the atomic-write pattern used by the rest of
    the reporting modules."""
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
        prog="reporting.roadmap_priority",
        description=(
            "Read-only roadmap priority projection "
            f"({MODULE_VERSION}). Stdlib-only. Never executes "
            "implementation; always projects."
        ),
    )
    g = parser.add_mutually_exclusive_group(required=False)
    g.add_argument(
        "--mode",
        type=str,
        default="dry-run",
        choices=["dry-run"],
        help=(
            "Operating mode (default: dry-run). The execute path is "
            "intentionally absent in this release: the prioritizer "
            "never starts work."
        ),
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
