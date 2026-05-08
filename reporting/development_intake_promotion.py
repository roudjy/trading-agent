"""A16a — Intake Candidate Promotion Staging (read-only projector).

Pure, deterministic, stdlib-only **projection** module that reads
eligible candidates from the upstream Roadmap Intake Bridge artefact
(``logs/development_roadmap_intake/latest.json``) and emits a
deterministic *promotion-intent* artefact under
``logs/development_intake_promotion/latest.json``.

This is the staging-only A16a slice. **No queue seed file is
mutated.** Operator promotion of any record into
``docs/development_work_queue/seed.jsonl`` or
``docs/development_work_queue/delegation_seed.jsonl`` remains an
explicit manual action.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + ``reporting.execution_authority`` (read-only) +
  ``reporting.development_roadmap_intake`` (read-only) +
  ``reporting.notification_event`` (read-only).
* No subprocess, no network, no ``gh``, no ``git``.
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  or ``trading``.
* No mutation of any upstream roadmap or seed file.
* Atomic write only under
  ``logs/development_intake_promotion/...``.
* Per-candidate **re-classification** via
  ``execution_authority.classify(...)``. The upstream-recorded
  decision is **never trusted blindly** — drift forces
  ``decision_state="blocked"`` with a ``classification_drift``
  warning.
* N1 ``notification_event.route_for(...)`` integration only —
  this module emits no notifications.
* ``step5_implementation_allowed`` remains ``False`` and
  ``STEP5_ENABLED_SUBSTAGE`` remains ``"none"``. Step 5.1 / 5.2 stay
  BLOCKED. Level 6 stays permanently disabled per ADR-015 §Doctrine 1.

CLI
---

::

    python -m reporting.development_intake_promotion
    python -m reporting.development_intake_promotion --no-write
    python -m reporting.development_intake_promotion --indent 0
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import development_roadmap_intake as dri
from reporting import execution_authority as ea
from reporting import notification_event as ne

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A16a"
REPORT_KIND: Final[str] = "development_intake_promotion"

# ---------------------------------------------------------------------------
# Step 5 invariants (re-asserted on every artefact)
# ---------------------------------------------------------------------------

#: Mirrors the ``development_step5_loop`` constant so the artefact is
#: self-attesting.
STEP5_ENABLED_SUBSTAGE: Final[str] = "none"

#: Hard-pinned literal: Step 5 implementation remains BLOCKED.
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed decision-state vocabulary for promotion staging.
#:
#: * ``pending``           — candidate seen but not yet classified.
#: * ``eligible``          — passed re-classification + dedupe and is
#:                           ready for explicit operator promotion.
#: * ``human_needed``      — upstream or re-classification decision
#:                           requires operator approval.
#: * ``blocked``           — re-classification disagrees (drift) OR
#:                           authority is ``PERMANENTLY_DENIED``.
#: * ``rejected``          — operator-set terminal state on the
#:                           upstream candidate (``intake_status``).
#: * ``already_promoted``  — already present in operator-authored
#:                           ``seed.jsonl`` or ``delegation_seed.jsonl``.
DECISION_STATES: Final[tuple[str, ...]] = (
    "pending",
    "eligible",
    "human_needed",
    "blocked",
    "rejected",
    "already_promoted",
)

#: Closed validation-warning kinds.
VALIDATION_WARNINGS: Final[tuple[str, ...]] = (
    "intake_artifact_absent",
    "intake_artifact_unparseable",
    "classification_drift",
    "duplicate_candidate_id_in_cycle",
    "duplicate_unchanged_history_entry",
    "candidate_missing_target_path",
    "candidate_invalid_risk_level",
    "candidate_invalid_intake_status",
)

#: Closed promotion-target vocabulary. ``none`` is the only legal
#: value for A16a — promotion to a queue lane is A16b territory and
#: not implemented.
PROMOTION_TARGETS: Final[tuple[str, ...]] = (
    "none",
    "development_work_queue",
    "development_delegation",
)

#: Per-row schema, exact and ordered.
PROMOTION_SCHEMA_KEYS: Final[tuple[str, ...]] = (
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
    "upstream_execution_authority_decision",
    "reclassified_execution_authority_decision",
    "reclassified_execution_authority_reason",
    "classification_drift",
    "human_needed",
    "human_needed_reason",
    "acceptance_criteria",
    "evidence_hash",
    "notification_event_kind",
    "notification_event_severity",
    "already_in_seed_jsonl",
    "already_in_delegation_seed",
    "duplicate_of_history_entry",
    "decision_state",
    "promotion_target",
    "notes",
)

#: Wrapper-level note vocabulary.
NOTE_NO_INTAKE_ARTIFACT: Final[str] = "intake_artifact_absent"
NOTE_NO_CANDIDATES: Final[str] = "no_candidates_to_project"
NOTE_CANDIDATES_PRESENT: Final[str] = "promotion_intents_present"

#: Bounded length for free-text fields.
MAX_NOTES_LEN: Final[int] = 1000

#: Bounded history window. Mirrors A12 / A14 patterns.
MAX_HISTORY_ENTRIES: Final[int] = 90

# ---------------------------------------------------------------------------
# Repo-relative paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "development_intake_promotion"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_intake_promotion/latest.json"
)
HISTORY_PATH: Final[Path] = ARTIFACT_DIR / "history.jsonl"
HISTORY_RELATIVE_PATH: Final[str] = (
    "logs/development_intake_promotion/history.jsonl"
)

#: Read-only sources (never opened for writing).
SEED_PATH: Final[Path] = (
    REPO_ROOT / "docs" / "development_work_queue" / "seed.jsonl"
)
DELEGATION_SEED_PATH: Final[Path] = (
    REPO_ROOT / "docs" / "development_work_queue" / "delegation_seed.jsonl"
)

#: Atomic-write allowlist (substring form). Any write target whose
#: POSIX path does not contain this substring is refused with
#: ``ValueError``.
_WRITE_PREFIX: Final[str] = "logs/development_intake_promotion/"


# ---------------------------------------------------------------------------
# Discipline invariants emitted into every artefact
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool | str]] = {
    "writes_to_seed_jsonl": False,
    "writes_to_delegation_seed_jsonl": False,
    "writes_to_generated_seed_jsonl": False,
    "actually_modifies_target": False,
    "creates_real_branches": False,
    "opens_real_prs": False,
    "mergeable_by_agent": False,
    "deployable_by_agent": False,
    "fuzzy_parsing": False,
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


def _read_seed_ids(path: Path, *, id_field: str) -> set[str]:
    """Read operator-authored seed JSONL **for reading only** and
    return the set of identifier strings present. Best-effort:
    malformed lines are silently skipped (the seed parser is the
    authority on validity; this helper is for dedupe only)."""
    out: set[str] = set()
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        try:
            payload = json.loads(s)
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        value = payload.get(id_field)
        if isinstance(value, str) and value:
            out.add(value)
    return out


def _evidence_hash(candidate: dict[str, Any]) -> str:
    """sha256 over a canonical evidence projection. Tests pin
    determinism; this hash also drives history-based dedupe.
    """
    canonical = {
        "candidate_id": candidate.get("candidate_id"),
        "title": candidate.get("title"),
        "source_document": candidate.get("source_document"),
        "source_kind": candidate.get("source_kind"),
        "roadmap_phase": candidate.get("roadmap_phase"),
        "candidate_kind": candidate.get("candidate_kind"),
        "required_agent_role": candidate.get("required_agent_role"),
        "risk_level": candidate.get("risk_level"),
        "target_path": candidate.get("target_path"),
        "human_needed": candidate.get("human_needed"),
        "human_needed_reason": candidate.get("human_needed_reason"),
        "acceptance_criteria": list(candidate.get("acceptance_criteria") or []),
    }
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Re-classification + decision-state derivation
# ---------------------------------------------------------------------------


def _reclassify(candidate: dict[str, Any]) -> ea.ExecutionDecision:
    """Re-run the closed Execution Authority classifier on the
    candidate. Never trusts the upstream-recorded decision."""
    return ea.classify(
        action_type="file_edit",
        target_path=candidate.get("target_path") or None,
        risk_class=candidate.get("risk_level") or ea.RISK_UNKNOWN,
    )


def _decision_state(
    *,
    upstream_intake_status: str,
    reclassified: ea.ExecutionDecision,
    upstream_execution_authority_decision: str | None,
    human_needed: bool,
    already_in_seed: bool,
    already_in_delegation: bool,
) -> tuple[str, list[str]]:
    """Derive the closed ``decision_state`` value plus any per-row
    validation warnings. Default-deny: anything not explicitly
    eligible falls into ``human_needed`` / ``blocked`` / ``pending``.
    """
    warnings: list[str] = []

    # Already-in-queue dedupe wins over everything else (the operator
    # has already promoted; we must not duplicate intent).
    if already_in_seed or already_in_delegation:
        return ("already_promoted", warnings)

    # Authority drift detection: compare upstream-recorded decision
    # against fresh re-classification. Mismatch fails closed.
    drift = False
    if upstream_execution_authority_decision is not None:
        if upstream_execution_authority_decision != reclassified.decision:
            drift = True
            warnings.append("classification_drift")
    if drift:
        return ("blocked", warnings)

    # Authority-level guards.
    if reclassified.decision == ea.DECISION_PERMANENTLY_DENIED:
        return ("blocked", warnings)
    if reclassified.decision == ea.DECISION_NEEDS_HUMAN:
        return ("human_needed", warnings)

    # Upstream status guards. ``rejected`` is operator-terminal.
    if upstream_intake_status == "rejected":
        return ("rejected", warnings)
    if upstream_intake_status == "blocked":
        return ("blocked", warnings)
    if upstream_intake_status == "human_needed":
        return ("human_needed", warnings)
    if upstream_intake_status not in {"eligible", "proposed"}:
        warnings.append("candidate_invalid_intake_status")
        return ("pending", warnings)

    # Operator-explicit human_needed flag overrides AUTO_ALLOWED.
    if human_needed:
        return ("human_needed", warnings)

    # Default-deny: only ``eligible`` upstream + AUTO_ALLOWED reclass +
    # ``human_needed=False`` becomes eligible for staging.
    if (
        upstream_intake_status == "eligible"
        and reclassified.decision == ea.DECISION_AUTO_ALLOWED
    ):
        return ("eligible", warnings)

    return ("pending", warnings)


# ---------------------------------------------------------------------------
# Notification-severity routing (N1 integration; we do NOT emit)
# ---------------------------------------------------------------------------


def _notification_event_for(
    *,
    decision_state: str,
    risk_level: str,
    reclassified_decision: str,
) -> tuple[str, str]:
    """Pure mapping ``decision_state → (event_kind, severity)`` using
    only ``notification_event.route_for(...)``. This module never
    emits a notification; the dispatcher (future N2) does."""
    if decision_state == "blocked":
        kind = "intake_candidate_blocked"
    elif decision_state == "human_needed":
        kind = "queue_item_human_needed"
    elif decision_state == "already_promoted":
        kind = "intake_candidate_eligible"
    elif decision_state == "eligible":
        kind = "intake_candidate_eligible"
    else:
        # ``pending`` / ``rejected`` route through the fail-safe
        # ``unknown_state`` surface so the operator sees the gap.
        kind = "unknown_state"
    severity = ne.route_for(
        kind,
        risk_class=risk_level if isinstance(risk_level, str) else None,
        execution_authority_decision=reclassified_decision,
    )
    return (kind, severity)


# ---------------------------------------------------------------------------
# Per-row construction
# ---------------------------------------------------------------------------


def _build_row(
    candidate: dict[str, Any],
    *,
    seed_ids: set[str],
    delegation_ids: set[str],
    history_seen_pairs: set[tuple[str, str]],
) -> tuple[dict[str, Any], list[str]]:
    """Construct one promotion-intent row from one upstream
    candidate. Returns ``(row, warnings)``."""
    warnings: list[str] = []

    candidate_id = str(candidate.get("candidate_id") or "")
    target_path = str(candidate.get("target_path") or "")
    if not target_path:
        warnings.append("candidate_missing_target_path")

    risk_level = str(candidate.get("risk_level") or "UNKNOWN")
    if risk_level not in ea.RISK_CLASSES:
        warnings.append("candidate_invalid_risk_level")

    reclassified = _reclassify(candidate)
    upstream_decision = (
        candidate.get("execution_authority_decision")
        if isinstance(candidate.get("execution_authority_decision"), str)
        else None
    )
    upstream_intake_status = str(candidate.get("intake_status") or "")
    human_needed = bool(candidate.get("human_needed"))

    already_in_seed = candidate_id in seed_ids
    already_in_delegation = candidate_id in delegation_ids

    decision_state, ds_warnings = _decision_state(
        upstream_intake_status=upstream_intake_status,
        reclassified=reclassified,
        upstream_execution_authority_decision=upstream_decision,
        human_needed=human_needed,
        already_in_seed=already_in_seed,
        already_in_delegation=already_in_delegation,
    )
    warnings.extend(ds_warnings)

    classification_drift = "classification_drift" in ds_warnings

    evidence_hash = _evidence_hash(candidate)
    duplicate_history = (candidate_id, evidence_hash) in history_seen_pairs
    if duplicate_history:
        warnings.append("duplicate_unchanged_history_entry")

    event_kind, event_severity = _notification_event_for(
        decision_state=decision_state,
        risk_level=risk_level,
        reclassified_decision=reclassified.decision,
    )

    row = {
        "candidate_id": candidate_id,
        "title": str(candidate.get("title") or ""),
        "source_document": str(candidate.get("source_document") or ""),
        "source_kind": str(candidate.get("source_kind") or ""),
        "roadmap_phase": str(candidate.get("roadmap_phase") or ""),
        "candidate_kind": str(candidate.get("candidate_kind") or ""),
        "required_agent_role": str(candidate.get("required_agent_role") or ""),
        "risk_level": risk_level,
        "target_path": target_path,
        "upstream_intake_status": upstream_intake_status,
        "upstream_execution_authority_decision": upstream_decision or "",
        "reclassified_execution_authority_decision": reclassified.decision,
        "reclassified_execution_authority_reason": reclassified.reason,
        "classification_drift": classification_drift,
        "human_needed": human_needed,
        "human_needed_reason": str(candidate.get("human_needed_reason") or ""),
        "acceptance_criteria": list(candidate.get("acceptance_criteria") or []),
        "evidence_hash": evidence_hash,
        "notification_event_kind": event_kind,
        "notification_event_severity": event_severity,
        "already_in_seed_jsonl": already_in_seed,
        "already_in_delegation_seed": already_in_delegation,
        "duplicate_of_history_entry": duplicate_history,
        "decision_state": decision_state,
        "promotion_target": "none",
        "notes": "",
    }
    return (row, warnings)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "eligible": 0,
        "human_needed": 0,
        "blocked": 0,
        "already_promoted": 0,
        "by_decision_state": {s: 0 for s in DECISION_STATES},
        "by_notification_event_kind": {},
        "by_notification_event_severity": {
            s: 0 for s in ne.EVENT_SEVERITIES
        },
        "by_reclassified_execution_authority_decision": {
            ea.DECISION_AUTO_ALLOWED: 0,
            ea.DECISION_NEEDS_HUMAN: 0,
            ea.DECISION_PERMANENTLY_DENIED: 0,
        },
        "already_in_seed_jsonl": 0,
        "already_in_delegation_seed": 0,
        "classification_drift": 0,
    }


def _aggregate_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _empty_counts()
    counts["total"] = len(rows)
    for row in rows:
        ds = row["decision_state"]
        counts["by_decision_state"][ds] += 1
        if ds == "eligible":
            counts["eligible"] += 1
        elif ds == "human_needed":
            counts["human_needed"] += 1
        elif ds == "blocked":
            counts["blocked"] += 1
        elif ds == "already_promoted":
            counts["already_promoted"] += 1
        kind = row["notification_event_kind"]
        counts["by_notification_event_kind"][kind] = (
            counts["by_notification_event_kind"].get(kind, 0) + 1
        )
        sev = row["notification_event_severity"]
        if sev in counts["by_notification_event_severity"]:
            counts["by_notification_event_severity"][sev] += 1
        rd = row["reclassified_execution_authority_decision"]
        if rd in counts["by_reclassified_execution_authority_decision"]:
            counts["by_reclassified_execution_authority_decision"][rd] += 1
        if row["already_in_seed_jsonl"]:
            counts["already_in_seed_jsonl"] += 1
        if row["already_in_delegation_seed"]:
            counts["already_in_delegation_seed"] += 1
        if row["classification_drift"]:
            counts["classification_drift"] += 1
    return counts


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def _read_history_pairs(path: Path) -> set[tuple[str, str]]:
    """Read prior ``(candidate_id, evidence_hash)`` pairs from
    bounded history JSONL. Best-effort; malformed lines skipped."""
    pairs: set[tuple[str, str]] = set()
    if not path.is_file():
        return pairs
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return pairs
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        try:
            entry = json.loads(s)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        cid = entry.get("candidate_id")
        eh = entry.get("evidence_hash")
        if isinstance(cid, str) and isinstance(eh, str):
            pairs.add((cid, eh))
    return pairs


def collect_snapshot(
    *,
    intake_artifact_path: Path | None = None,
    seed_path: Path | None = None,
    delegation_seed_path: Path | None = None,
    history_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic promotion-intent snapshot.

    Args:
        intake_artifact_path: override
            ``logs/development_roadmap_intake/latest.json``.
        seed_path: override the operator-authored
            ``docs/development_work_queue/seed.jsonl`` (read-only).
        delegation_seed_path: override the operator-authored
            ``docs/development_work_queue/delegation_seed.jsonl``.
        history_path: override the bounded
            ``logs/development_intake_promotion/history.jsonl``.
        generated_at_utc: override the wrapper's report timestamp.
    """
    ip = (
        intake_artifact_path
        if intake_artifact_path is not None
        else dri.ARTIFACT_LATEST
    )
    sp = seed_path if seed_path is not None else SEED_PATH
    dp = (
        delegation_seed_path
        if delegation_seed_path is not None
        else DELEGATION_SEED_PATH
    )
    hp = history_path if history_path is not None else HISTORY_PATH
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    seed_ids = _read_seed_ids(sp, id_field="item_id")
    delegation_ids = _read_seed_ids(dp, id_field="delegation_id")
    history_pairs = _read_history_pairs(hp)

    payload = _read_json(ip)
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    seen_ids_in_cycle: set[str] = set()

    if payload is None:
        warnings.append("intake_artifact_absent")
        candidates: list[dict[str, Any]] = []
    elif not isinstance(payload, dict) or not isinstance(
        payload.get("candidates"), list
    ):
        warnings.append("intake_artifact_unparseable")
        candidates = []
    else:
        candidates = [
            c for c in payload["candidates"] if isinstance(c, dict)
        ]

    for cand in candidates:
        cid = str(cand.get("candidate_id") or "")
        if not cid:
            continue
        if cid in seen_ids_in_cycle:
            warnings.append(f"duplicate_candidate_id_in_cycle:{cid}")
            continue
        seen_ids_in_cycle.add(cid)

        row, row_warnings = _build_row(
            cand,
            seed_ids=seed_ids,
            delegation_ids=delegation_ids,
            history_seen_pairs=history_pairs,
        )
        for w in row_warnings:
            warnings.append(f"{cid}:{w}")
        rows.append(row)

    rows.sort(key=lambda r: (r["source_kind"], r["candidate_id"]))

    counts = _aggregate_counts(rows)

    if payload is None:
        note = NOTE_NO_INTAKE_ARTIFACT
    elif not rows:
        note = NOTE_NO_CANDIDATES
    else:
        note = NOTE_CANDIDATES_PRESENT

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "intake_artifact_path": str(ip),
        "intake_artifact_available": payload is not None,
        "seed_path": str(sp),
        "seed_present": sp.is_file(),
        "delegation_seed_path": str(dp),
        "delegation_seed_present": dp.is_file(),
        "history_path": str(hp),
        "note": note,
        "validation_warnings": warnings,
        "vocabularies": {
            "decision_states": list(DECISION_STATES),
            "validation_warnings": list(VALIDATION_WARNINGS),
            "promotion_targets": list(PROMOTION_TARGETS),
            "notification_event_kinds": list(ne.EVENT_KINDS),
            "notification_event_severities": list(ne.EVENT_SEVERITIES),
            "intake_module_source_kinds": list(dri.SOURCE_KINDS),
            "intake_module_candidate_kinds": list(dri.CANDIDATE_KINDS),
        },
        "counts": counts,
        "rows": rows,
        "execution_authority_module_version": ea.MODULE_VERSION,
        "intake_module_version": dri.MODULE_VERSION,
        "notification_event_module_version": ne.MODULE_VERSION,
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
    }


# ---------------------------------------------------------------------------
# Atomic write + bounded history append
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` atomically; refuse any path outside
    ``logs/development_intake_promotion/...``."""
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "development_intake_promotion._atomic_write_json refuses "
            f"non-promotion-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_intake_promotion.",
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


def _append_history(path: Path, rows: list[dict[str, Any]]) -> None:
    """Append a compact projection of each row to a bounded JSONL
    file. Truncates to the last :data:`MAX_HISTORY_ENTRIES` lines on
    every write. Refuses any path outside the promotion logs prefix.
    """
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "development_intake_promotion._append_history refuses "
            f"non-promotion-logs path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[str] = []
    if path.is_file():
        try:
            existing = [
                line for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except OSError:
            existing = []
    for row in rows:
        entry = {
            "candidate_id": row["candidate_id"],
            "evidence_hash": row["evidence_hash"],
            "decision_state": row["decision_state"],
        }
        existing.append(json.dumps(entry, sort_keys=True, ensure_ascii=False))
    if len(existing) > MAX_HISTORY_ENTRIES:
        existing = existing[-MAX_HISTORY_ENTRIES:]
    text = "\n".join(existing) + ("\n" if existing else "")
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_intake_promotion.history.",
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


def write_outputs(snapshot: dict[str, Any]) -> tuple[Path, Path]:
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    _append_history(HISTORY_PATH, snapshot.get("rows") or [])
    return (ARTIFACT_LATEST, HISTORY_PATH)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.development_intake_promotion",
        description=(
            "A16a Intake Candidate Promotion Staging. Read-only "
            "deterministic projector that converts eligible "
            "Roadmap Intake Bridge candidates into bounded "
            "promotion-intent records under "
            "logs/development_intake_promotion/. Mutates no queue "
            "seed file. Decides nothing; emits no notifications. "
            "Step 5 implementation remains BLOCKED."
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
            "logs/development_intake_promotion/latest.json or history "
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
