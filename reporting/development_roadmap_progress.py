"""A19 — Roadmap Progress Tracker (read-only, deterministic projector).

Pure stdlib-only projector that joins the existing read-only ADE
artefacts:

* Roadmap Intake Bridge (`logs/development_roadmap_intake/latest.json`)
* A16a Promotion Staging (`logs/development_intake_promotion/latest.json`)
* A17 Queue Admission Policy (`logs/development_queue_admission_policy/latest.json`)
* Step 5.0 plan history (`logs/step5_plan/history.jsonl`)

…and emits a per-roadmap-phase progress snapshot. **Reports only;
mutates nothing; promotes nothing; flips no roadmap status field.**

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + read-only `reporting.development_roadmap_intake`,
  `reporting.development_intake_promotion`,
  `reporting.development_queue_admission_policy`,
  `reporting.development_step5_loop`,
  `reporting.agent_audit_summary.assert_no_secrets`.
* No subprocess, no network, no `gh`, no `git`.
* No imports of `dashboard`, `frontend`, `automation`, `broker`,
  `agent.risk`, `agent.execution`, `research`,
  `reporting.intelligent_routing`, `live`, `paper`, `shadow`,
  `trading`.
* Atomic write only under
  `logs/development_roadmap_progress/...`.
* Never edits canonical roadmap status fields. Never marks any
  phase complete. Never mutates upstream artefacts.
* `step5_implementation_allowed` remains `False` and
  `STEP5_ENABLED_SUBSTAGE` remains `"none"`.
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
from reporting import development_queue_admission_policy as qap
from reporting import development_roadmap_intake as dri
from reporting import development_step5_loop as dsl
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A19"
REPORT_KIND: Final[str] = "development_roadmap_progress"

# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed phase-progress-state vocabulary. Adding a value requires
#: a code change pinned by an updated unit test. Note: A19 NEVER
#: assigns ``complete`` autonomously — it is reserved for the future
#: where an operator marks a phase complete in the canonical roadmap.
#: Today every phase A19 sees lands in ``not_started`` /
#: ``intake_only`` / ``promotion_active`` / ``admission_active`` /
#: ``planning_active`` based on observed signal in upstream artefacts.
PHASE_PROGRESS_STATES: Final[tuple[str, ...]] = (
    "not_started",
    "intake_only",
    "promotion_active",
    "admission_active",
    "planning_active",
    "complete",
)

#: Per-phase row schema, exact and ordered.
PHASE_ROW_KEYS: Final[tuple[str, ...]] = (
    "roadmap_phase",
    "intake_candidate_count",
    "intake_eligible_count",
    "intake_blocked_count",
    "intake_human_needed_count",
    "promotion_total",
    "promotion_eligible_count",
    "promotion_blocked_count",
    "admission_total",
    "admission_admissible_count",
    "admission_blocked_count",
    "admission_needs_human_count",
    "step5_planned_count",
    "step5_halted_count",
    "phase_progress_state",
)

#: Wrapper-level note vocabulary.
NOTE_NO_PHASES: Final[str] = "no_roadmap_phases_observed"
NOTE_PHASES_PRESENT: Final[str] = "roadmap_phases_present"
NOTE_NO_UPSTREAM_ARTIFACTS: Final[str] = "no_upstream_artifacts"

#: Repo-relative paths.
ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "development_roadmap_progress"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_roadmap_progress/latest.json"
)

#: Atomic-write allowlist (substring form).
_WRITE_PREFIX: Final[str] = "logs/development_roadmap_progress/"


# ---------------------------------------------------------------------------
# Discipline invariants
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool | str]] = {
    "writes_to_seed_jsonl": False,
    "writes_to_delegation_seed_jsonl": False,
    "writes_to_generated_seed_jsonl": False,
    "mutates_canonical_roadmap_status_fields": False,
    "marks_any_phase_complete": False,
    "actually_modifies_target": False,
    "uses_subprocess_or_network": False,
    "calls_llm_or_external_api": False,
    "mutates_research_artifacts": False,
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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        try:
            entry = json.loads(s)
        except ValueError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


# ---------------------------------------------------------------------------
# Phase-progress derivation
# ---------------------------------------------------------------------------


def _derive_phase_state(row: dict[str, Any]) -> str:
    """Closed-table derivation of `phase_progress_state` from observed
    signal in upstream artefacts.

    Priority order (first match wins):

    1. Step 5.0 has produced a `plan_emitted` for any candidate in
       this phase → `planning_active`.
    2. Admission policy has at least one row in this phase →
       `admission_active`.
    3. Promotion staging has at least one row in this phase →
       `promotion_active`.
    4. Intake bridge has at least one candidate in this phase →
       `intake_only`.
    5. Otherwise (no signal anywhere) → `not_started`.

    A19 never assigns `complete` — that remains an operator-marked
    state in the canonical roadmap, never inferred by the agent.
    """
    if int(row.get("step5_planned_count", 0)) > 0:
        return "planning_active"
    if int(row.get("admission_total", 0)) > 0:
        return "admission_active"
    if int(row.get("promotion_total", 0)) > 0:
        return "promotion_active"
    if int(row.get("intake_candidate_count", 0)) > 0:
        return "intake_only"
    return "not_started"


# ---------------------------------------------------------------------------
# Per-phase aggregation
# ---------------------------------------------------------------------------


def _empty_row(phase: str) -> dict[str, Any]:
    return {
        "roadmap_phase": phase,
        "intake_candidate_count": 0,
        "intake_eligible_count": 0,
        "intake_blocked_count": 0,
        "intake_human_needed_count": 0,
        "promotion_total": 0,
        "promotion_eligible_count": 0,
        "promotion_blocked_count": 0,
        "admission_total": 0,
        "admission_admissible_count": 0,
        "admission_blocked_count": 0,
        "admission_needs_human_count": 0,
        "step5_planned_count": 0,
        "step5_halted_count": 0,
        "phase_progress_state": "not_started",
    }


def _accumulate_intake(
    rows: dict[str, dict[str, Any]],
    intake_payload: dict[str, Any] | None,
) -> None:
    if not isinstance(intake_payload, dict):
        return
    candidates = intake_payload.get("candidates")
    if not isinstance(candidates, list):
        return
    for c in candidates:
        if not isinstance(c, dict):
            continue
        phase = str(c.get("roadmap_phase") or "")
        if not phase:
            continue
        row = rows.setdefault(phase, _empty_row(phase))
        row["intake_candidate_count"] += 1
        status = c.get("intake_status")
        if status == "eligible":
            row["intake_eligible_count"] += 1
        elif status == "blocked":
            row["intake_blocked_count"] += 1
        elif status == "human_needed":
            row["intake_human_needed_count"] += 1


def _accumulate_promotion(
    rows: dict[str, dict[str, Any]],
    promotion_payload: dict[str, Any] | None,
) -> None:
    if not isinstance(promotion_payload, dict):
        return
    promo_rows = promotion_payload.get("rows")
    if not isinstance(promo_rows, list):
        return
    for r in promo_rows:
        if not isinstance(r, dict):
            continue
        phase = str(r.get("roadmap_phase") or "")
        if not phase:
            continue
        row = rows.setdefault(phase, _empty_row(phase))
        row["promotion_total"] += 1
        ds = r.get("decision_state")
        if ds == "eligible":
            row["promotion_eligible_count"] += 1
        elif ds == "blocked":
            row["promotion_blocked_count"] += 1


def _accumulate_admission(
    rows: dict[str, dict[str, Any]],
    admission_payload: dict[str, Any] | None,
) -> None:
    if not isinstance(admission_payload, dict):
        return
    adm_rows = admission_payload.get("rows")
    if not isinstance(adm_rows, list):
        return
    for r in adm_rows:
        if not isinstance(r, dict):
            continue
        phase = str(r.get("roadmap_phase") or "")
        if not phase:
            continue
        row = rows.setdefault(phase, _empty_row(phase))
        row["admission_total"] += 1
        d = r.get("admission_decision")
        if d == "admissible":
            row["admission_admissible_count"] += 1
        elif d == "blocked":
            row["admission_blocked_count"] += 1
        elif d == "needs_human":
            row["admission_needs_human_count"] += 1


def _accumulate_step5(
    rows: dict[str, dict[str, Any]],
    step5_history: list[dict[str, Any]],
    promotion_payload: dict[str, Any] | None,
    intake_payload: dict[str, Any] | None,
) -> None:
    """Step 5.0 history rows reference candidates by `source_id` /
    `cycle_id`, not directly by phase. Resolve the phase by looking
    up the source_id in the upstream promotion + intake artefacts."""
    candidate_phase: dict[str, str] = {}
    if isinstance(intake_payload, dict):
        for c in (intake_payload.get("candidates") or []):
            if isinstance(c, dict):
                cid = str(c.get("candidate_id") or "")
                ph = str(c.get("roadmap_phase") or "")
                if cid and ph:
                    candidate_phase[cid] = ph
    if isinstance(promotion_payload, dict):
        for r in (promotion_payload.get("rows") or []):
            if isinstance(r, dict):
                cid = str(r.get("candidate_id") or "")
                ph = str(r.get("roadmap_phase") or "")
                if cid and ph:
                    candidate_phase[cid] = ph

    for entry in step5_history:
        outcome = str(entry.get("outcome") or "")
        source_id = str(entry.get("source_id") or "")
        if not source_id:
            continue
        phase = candidate_phase.get(source_id, "")
        if not phase:
            continue
        row = rows.setdefault(phase, _empty_row(phase))
        if outcome == "plan_emitted":
            row["step5_planned_count"] += 1
        elif outcome.startswith("halt_"):
            row["step5_halted_count"] += 1


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    intake_artifact_path: Path | None = None,
    promotion_artifact_path: Path | None = None,
    admission_artifact_path: Path | None = None,
    step5_history_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic phase-progress snapshot.

    Reads four upstream artefacts read-only. Every path argument is
    overridable for tests; defaults point at the production paths.
    """
    ip = intake_artifact_path if intake_artifact_path is not None else dri.ARTIFACT_LATEST
    pp = promotion_artifact_path if promotion_artifact_path is not None else dip.ARTIFACT_LATEST
    ap = admission_artifact_path if admission_artifact_path is not None else qap.ARTIFACT_LATEST
    hp = step5_history_path if step5_history_path is not None else dsl.HISTORY_PATH
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    intake_payload = _read_json(ip)
    promotion_payload = _read_json(pp)
    admission_payload = _read_json(ap)
    step5_history = _read_jsonl(hp)

    rows: dict[str, dict[str, Any]] = {}
    _accumulate_intake(rows, intake_payload)
    _accumulate_promotion(rows, promotion_payload)
    _accumulate_admission(rows, admission_payload)
    _accumulate_step5(rows, step5_history, promotion_payload, intake_payload)

    # Derive phase_progress_state for every row.
    for r in rows.values():
        r["phase_progress_state"] = _derive_phase_state(r)
        # Closed shape check.
        assert set(r.keys()) == set(PHASE_ROW_KEYS)

    rows_sorted = sorted(rows.values(), key=lambda r: r["roadmap_phase"])

    sources_present = {
        "intake": intake_payload is not None,
        "promotion": promotion_payload is not None,
        "admission": admission_payload is not None,
        "step5_history": bool(step5_history),
    }
    if not any(sources_present.values()):
        note = NOTE_NO_UPSTREAM_ARTIFACTS
    elif not rows_sorted:
        note = NOTE_NO_PHASES
    else:
        note = NOTE_PHASES_PRESENT

    counts = {
        "phase_count": len(rows_sorted),
        "by_phase_progress_state": {s: 0 for s in PHASE_PROGRESS_STATES},
    }
    for r in rows_sorted:
        s = r["phase_progress_state"]
        if s in counts["by_phase_progress_state"]:
            counts["by_phase_progress_state"][s] += 1

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "sources_read": [
            {"source": "intake", "path": str(ip), "available": intake_payload is not None},
            {"source": "promotion", "path": str(pp), "available": promotion_payload is not None},
            {"source": "admission", "path": str(ap), "available": admission_payload is not None},
            {"source": "step5_history", "path": str(hp), "available": bool(step5_history)},
        ],
        "note": note,
        "validation_warnings": [],
        "vocabularies": {
            "phase_progress_states": list(PHASE_PROGRESS_STATES),
            "phase_row_keys": list(PHASE_ROW_KEYS),
        },
        "counts": counts,
        "rows": rows_sorted,
        "intake_module_version": dri.MODULE_VERSION,
        "promotion_module_version": dip.MODULE_VERSION,
        "admission_module_version": qap.MODULE_VERSION,
        "step5_module_version": dsl.MODULE_VERSION,
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
            "development_roadmap_progress._atomic_write_json refuses "
            f"non-progress-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_roadmap_progress.",
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
        prog="python -m reporting.development_roadmap_progress",
        description=(
            "A19 Roadmap Progress Tracker. Read-only deterministic "
            "projector that joins intake / promotion / admission / "
            "step5 artefacts and emits a per-phase progress snapshot. "
            "Mutates no roadmap status field; never marks a phase "
            "complete."
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
            "logs/development_roadmap_progress/latest.json "
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
