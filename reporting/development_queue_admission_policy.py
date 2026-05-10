"""A17 — Queue Admission Policy (read-only, deterministic projector).

Pure, stdlib-only **policy** module that classifies whether an A16a
promotion-intent record is admissible for queue promotion. Reports
the decision and the rule that fired; **does NOT promote**, **does
NOT mutate any seed file**, **does NOT write to the active queue**.

This module sits between A16a (intake-promotion staging) and the
future, operator-gated A18 (generated queue channel). It is the
*policy* — the closed rule table that says "these candidates are
admissible, those need a human, those are blocked outright" — that
A18 will consult before appending to ``generated_seed.jsonl``.

Today A17 is consulted by no one in production: it is a read-only
projector that emits ``logs/development_queue_admission_policy/latest.json``
plus a status sibling. Operators inspect the artefact and decide.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + ``reporting.development_intake_promotion`` (read-only) +
  ``reporting.execution_authority`` (read-only) +
  ``reporting.development_work_queue`` (read-only) +
  ``reporting.agent_audit_summary.assert_no_secrets`` (read-only
  redactor guard).
* No subprocess, no network, no ``gh``, no ``git``.
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  ``trading``.
* No mutation of any upstream artefact.
* Atomic write only under
  ``logs/development_queue_admission_policy/...``.
* Closed ``admission_decision`` and ``admission_reason``
  vocabularies; per-row schema is exact and ordered.
* A17 NEVER writes to ``docs/development_work_queue/seed.jsonl``,
  ``docs/development_work_queue/delegation_seed.jsonl``, or any
  ``generated_seed.jsonl``.
* ``step5_implementation_allowed`` remains ``False`` and
  ``STEP5_ENABLED_SUBSTAGE`` remains ``"none"``.

CLI
---

::

    python -m reporting.development_queue_admission_policy
    python -m reporting.development_queue_admission_policy --no-write
    python -m reporting.development_queue_admission_policy --indent 0
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

from reporting import development_intake_promotion as dip
from reporting import development_work_queue as dwq
from reporting import execution_authority as ea
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A17"
REPORT_KIND: Final[str] = "development_queue_admission_policy"

# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed admission-decision vocabulary.
ADMISSION_DECISIONS: Final[tuple[str, ...]] = (
    "admissible",
    "needs_human",
    "blocked",
    "duplicate_of_existing",
    "not_eligible_upstream",
)

#: Closed admission-reason vocabulary. Adding a value requires a
#: code change pinned by an updated unit test.
ADMISSION_REASONS: Final[tuple[str, ...]] = (
    # admissible
    "auto_allowed_low_risk_eligible_promotion",
    # needs_human
    "needs_human_authority_decision",
    "needs_human_unknown_or_invalid_risk",
    "needs_human_classification_drift",
    "needs_human_protected_target_path",
    # blocked
    "blocked_authority_permanently_denied",
    "blocked_classification_drift_to_denied",
    # already-promoted / duplicates
    "already_in_seed_jsonl",
    "already_in_delegation_seed",
    # upstream filter
    "upstream_intake_status_not_eligible",
    "upstream_decision_state_not_eligible",
)

#: Closed promotion-target vocabulary mirrored from
#: ``development_intake_promotion``. A17 never writes to any of
#: these, but the artefact records which target a future A18 would
#: consider.
PROMOTION_TARGETS: Final[tuple[str, ...]] = (
    "none",
    "development_work_queue",
    "development_delegation",
)

#: Per-row schema, exact and ordered.
ADMISSION_SCHEMA_KEYS: Final[tuple[str, ...]] = (
    "candidate_id",
    "title",
    "source_document",
    "source_kind",
    "roadmap_phase",
    "candidate_kind",
    "required_agent_role",
    "risk_level",
    "target_path",
    "upstream_intake_status",
    "upstream_decision_state",
    "upstream_execution_authority_decision",
    "reclassified_execution_authority_decision",
    "classification_drift",
    "human_needed",
    "human_needed_reason",
    "admission_decision",
    "admission_reason",
    "would_target_lane",
    "already_in_seed_jsonl",
    "already_in_delegation_seed",
    "policy_version",
    "evaluated_at",
)

#: A17's own MODULE_VERSION pinned in the artefact for traceability.
POLICY_VERSION: Final[str] = MODULE_VERSION

#: Wrapper-level note vocabulary.
NOTE_NO_PROMOTION_ARTIFACT: Final[str] = "promotion_artifact_absent"
NOTE_NO_RECORDS: Final[str] = "no_promotion_records_to_evaluate"
NOTE_RECORDS_PRESENT: Final[str] = "admission_records_present"

#: Repo-relative paths.
ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "development_queue_admission_policy"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_queue_admission_policy/latest.json"
)

#: Atomic-write allowlist (substring form).
_WRITE_PREFIX: Final[str] = "logs/development_queue_admission_policy/"


# ---------------------------------------------------------------------------
# Discipline invariants
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool | str]] = {
    "writes_to_seed_jsonl": False,
    "writes_to_delegation_seed_jsonl": False,
    "writes_to_generated_seed_jsonl": False,
    "actually_modifies_target": False,
    "creates_real_branches": False,
    "opens_real_prs": False,
    "uses_subprocess_or_network": False,
    "calls_llm_or_external_api": False,
    "mutates_research_artifacts": False,
    "mutates_roadmap_status_fields": False,
    "marks_phase_complete": False,
    "operator_promotion_required": True,
    "step5_implementation_allowed": False,
    "step5_enabled_substage": "none",
    "diagnostics_do_not_trade": True,
}


# ---------------------------------------------------------------------------
# Utility helpers
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


# ---------------------------------------------------------------------------
# Policy decision (closed table; first match wins)
# ---------------------------------------------------------------------------


def evaluate_promotion_record(
    row: dict[str, Any],
) -> tuple[str, str]:
    """Evaluate one A16a promotion-intent record against the closed
    admission policy. Returns ``(decision, reason)`` where both
    values come from :data:`ADMISSION_DECISIONS` /
    :data:`ADMISSION_REASONS`.

    Priority order (first match wins):

    1. Already-in-queue dedupe → ``duplicate_of_existing``
    2. Upstream PERMANENTLY_DENIED → ``blocked``
    3. Classification drift to PERMANENTLY_DENIED → ``blocked``
    4. Upstream NEEDS_HUMAN → ``needs_human``
    5. Operator-explicit ``human_needed=true`` → ``needs_human``
    6. Classification drift (non-denied) → ``needs_human``
    7. Upstream ``decision_state`` not in {eligible} →
       ``not_eligible_upstream``
    8. Upstream ``intake_status`` not in {eligible} →
       ``not_eligible_upstream``
    9. Risk class UNKNOWN or invalid → ``needs_human``
    10. AUTO_ALLOWED + LOW + eligible → ``admissible``
    11. Default-deny → ``needs_human`` (fail-safe; never silently
        admissible)
    """
    if not isinstance(row, dict):
        return ("not_eligible_upstream", "upstream_decision_state_not_eligible")

    upstream_decision_state = row.get("decision_state")
    upstream_intake_status = row.get("upstream_intake_status")
    upstream_decision = row.get("upstream_execution_authority_decision")
    reclassified = row.get("reclassified_execution_authority_decision")
    classification_drift = bool(row.get("classification_drift"))
    human_needed = bool(row.get("human_needed"))
    risk_level = row.get("risk_level")
    already_in_seed = bool(row.get("already_in_seed_jsonl"))
    already_in_delegation = bool(row.get("already_in_delegation_seed"))

    # 1. Already-in-queue dedupe.
    if already_in_seed:
        return ("duplicate_of_existing", "already_in_seed_jsonl")
    if already_in_delegation:
        return ("duplicate_of_existing", "already_in_delegation_seed")

    # 2. PERMANENTLY_DENIED upstream.
    if (
        upstream_decision == ea.DECISION_PERMANENTLY_DENIED
        or reclassified == ea.DECISION_PERMANENTLY_DENIED
    ):
        return ("blocked", "blocked_authority_permanently_denied")

    # 3. Drift toward PERMANENTLY_DENIED.
    if classification_drift and reclassified == ea.DECISION_PERMANENTLY_DENIED:
        return ("blocked", "blocked_classification_drift_to_denied")

    # 4. NEEDS_HUMAN upstream or reclassification.
    if (
        upstream_decision == ea.DECISION_NEEDS_HUMAN
        or reclassified == ea.DECISION_NEEDS_HUMAN
    ):
        # NEEDS_HUMAN often correlates with a protected target path;
        # surface that reason when applicable for operator visibility.
        target = row.get("target_path") or ""
        decision_obj = ea.classify(
            action_type="file_edit",
            target_path=target if isinstance(target, str) and target else None,
            risk_class=risk_level if isinstance(risk_level, str) else ea.RISK_UNKNOWN,
        )
        if decision_obj.target_path_category in {
            "claude_governance_hook",
            "dashboard_wiring",
            "frozen_contract",
            "live_path",
            "branch_protection_config",
            "deploy_script",
            "canonical_policy_doc",
            "canonical_roadmap",
            "ci_workflow",
        }:
            return ("needs_human", "needs_human_protected_target_path")
        return ("needs_human", "needs_human_authority_decision")

    # 5. Operator-explicit human_needed.
    if human_needed:
        return ("needs_human", "needs_human_authority_decision")

    # 6. Drift (non-denied).
    if classification_drift:
        return ("needs_human", "needs_human_classification_drift")

    # 7. Upstream decision_state filter.
    if upstream_decision_state != "eligible":
        return ("not_eligible_upstream", "upstream_decision_state_not_eligible")

    # 8. Upstream intake_status filter.
    if upstream_intake_status != "eligible":
        return ("not_eligible_upstream", "upstream_intake_status_not_eligible")

    # 9. Risk-class guard.
    if risk_level not in ea.RISK_CLASSES or risk_level == ea.RISK_UNKNOWN:
        return ("needs_human", "needs_human_unknown_or_invalid_risk")

    # 10. The happy path.
    if (
        reclassified == ea.DECISION_AUTO_ALLOWED
        and risk_level == ea.RISK_LOW
    ):
        return ("admissible", "auto_allowed_low_risk_eligible_promotion")

    # 11. Default-deny fail-safe.
    return ("needs_human", "needs_human_authority_decision")


# ---------------------------------------------------------------------------
# Per-row construction
# ---------------------------------------------------------------------------


def _build_row(
    upstream: dict[str, Any], *, evaluated_at: str
) -> dict[str, Any]:
    decision, reason = evaluate_promotion_record(upstream)
    return {
        "candidate_id": str(upstream.get("candidate_id") or ""),
        "title": str(upstream.get("title") or ""),
        "source_document": str(upstream.get("source_document") or ""),
        "source_kind": str(upstream.get("source_kind") or ""),
        "roadmap_phase": str(upstream.get("roadmap_phase") or ""),
        "candidate_kind": str(upstream.get("candidate_kind") or ""),
        "required_agent_role": str(upstream.get("required_agent_role") or ""),
        "risk_level": str(upstream.get("risk_level") or ""),
        "target_path": str(upstream.get("target_path") or ""),
        "upstream_intake_status": str(upstream.get("upstream_intake_status") or ""),
        "upstream_decision_state": str(upstream.get("decision_state") or ""),
        "upstream_execution_authority_decision": str(
            upstream.get("upstream_execution_authority_decision") or ""
        ),
        "reclassified_execution_authority_decision": str(
            upstream.get("reclassified_execution_authority_decision") or ""
        ),
        "classification_drift": bool(upstream.get("classification_drift")),
        "human_needed": bool(upstream.get("human_needed")),
        "human_needed_reason": str(upstream.get("human_needed_reason") or ""),
        "admission_decision": decision,
        "admission_reason": reason,
        "would_target_lane": (
            "development_work_queue"
            if decision == "admissible"
            else "none"
        ),
        "already_in_seed_jsonl": bool(upstream.get("already_in_seed_jsonl")),
        "already_in_delegation_seed": bool(upstream.get("already_in_delegation_seed")),
        "policy_version": POLICY_VERSION,
        "evaluated_at": evaluated_at,
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "admissible": 0,
        "needs_human": 0,
        "blocked": 0,
        "duplicate_of_existing": 0,
        "not_eligible_upstream": 0,
        "by_admission_decision": {d: 0 for d in ADMISSION_DECISIONS},
        "by_admission_reason": {r: 0 for r in ADMISSION_REASONS},
        "by_required_agent_role": {r: 0 for r in dwq.AGENT_ROLES},
        "by_promotion_target": {t: 0 for t in PROMOTION_TARGETS},
    }


def _aggregate_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _empty_counts()
    counts["total"] = len(rows)
    for r in rows:
        d = r.get("admission_decision")
        if d in counts:
            counts[d] += 1
        if d in counts["by_admission_decision"]:
            counts["by_admission_decision"][d] += 1
        reason = r.get("admission_reason")
        if reason in counts["by_admission_reason"]:
            counts["by_admission_reason"][reason] += 1
        role = r.get("required_agent_role")
        if isinstance(role, str) and role in counts["by_required_agent_role"]:
            counts["by_required_agent_role"][role] += 1
        target = r.get("would_target_lane")
        if target in counts["by_promotion_target"]:
            counts["by_promotion_target"][target] += 1
    return counts


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    promotion_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic admission-policy snapshot.

    Reads ``logs/development_intake_promotion/latest.json``
    (read-only) and emits one admission row per promotion-intent
    record. Never mutates upstream.
    """
    pp = (
        promotion_artifact_path
        if promotion_artifact_path is not None
        else dip.ARTIFACT_LATEST
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    payload = _read_json(pp)
    rows: list[dict[str, Any]] = []
    if payload is None:
        upstream_rows: list[dict[str, Any]] = []
        note = NOTE_NO_PROMOTION_ARTIFACT
    else:
        raw = payload.get("rows") if isinstance(payload, dict) else None
        upstream_rows = (
            [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []
        )
        note = NOTE_NO_RECORDS

    for ur in upstream_rows:
        rows.append(_build_row(ur, evaluated_at=ts))

    rows.sort(key=lambda r: (r["source_kind"], r["candidate_id"]))

    if rows:
        note = NOTE_RECORDS_PRESENT

    counts = _aggregate_counts(rows)

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "promotion_artifact_path": str(pp),
        "promotion_artifact_available": payload is not None,
        "policy_version": POLICY_VERSION,
        "note": note,
        "validation_warnings": [],
        "vocabularies": {
            "admission_decisions": list(ADMISSION_DECISIONS),
            "admission_reasons": list(ADMISSION_REASONS),
            "promotion_targets": list(PROMOTION_TARGETS),
            "agent_roles": list(dwq.AGENT_ROLES),
        },
        "counts": counts,
        "rows": rows,
        "intake_promotion_module_version": dip.MODULE_VERSION,
        "execution_authority_module_version": ea.MODULE_VERSION,
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
    }
    assert_no_secrets(snapshot)
    return snapshot


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "development_queue_admission_policy._atomic_write_json refuses "
            f"non-policy-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_queue_admission_policy.",
        suffix=".tmp",
        dir=str(path.parent),
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


def write_outputs(snapshot: dict[str, Any]) -> Path:
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.development_queue_admission_policy",
        description=(
            "A17 Queue Admission Policy. Read-only deterministic "
            "projector. Reads logs/development_intake_promotion/"
            "latest.json and emits an admission decision per "
            "promotion-intent record under "
            "logs/development_queue_admission_policy/. Mutates no "
            "queue seed file. Decides nothing autonomously."
        ),
    )
    p.add_argument(
        "--indent", type=int, default=2, help="JSON indent (0 for compact)."
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist "
            "logs/development_queue_admission_policy/latest.json "
            "(stdout only)."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    indent = args.indent if args.indent and args.indent > 0 else None
    snap = collect_snapshot()
    if not args.no_write:
        write_outputs(snap)
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
