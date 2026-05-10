"""A20 — Step 5.1 readiness *report* (read-only projector).

Pure stdlib-only projector that **reports** whether the conditions
for a future Step 5.1 enablement are met. Reports only — A20 NEVER
flips ``step5_implementation_allowed``, NEVER changes
``STEP5_ENABLED_SUBSTAGE``, NEVER mutates any roadmap status field.

The output is an artefact at
``logs/development_step5_1_readiness/latest.json`` that the operator
can inspect to decide whether a separately authorised
governance-bootstrap PR should later flip the cap. A20 makes no
such decision and exposes no callable that could effect it.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + read-only ``reporting.development_intake_promotion``,
  ``reporting.development_queue_admission_policy``,
  ``reporting.development_roadmap_progress``,
  ``reporting.development_step5_loop``,
  ``reporting.agent_audit_summary.assert_no_secrets``.
* No subprocess, no network, no ``gh``, no ``git``.
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  ``trading``.
* Atomic write only under
  ``logs/development_step5_1_readiness/...``.
* The literal token ``step5_implementation_allowed = True`` does
  NOT appear anywhere in this module. Pinned by source-text scan.
* The constant ``CURRENT_STEP5_IMPLEMENTATION_ALLOWED`` is read
  verbatim from ``reporting.development_step5_loop`` and re-emitted
  read-only. A20 has no path to mutate it.
* ``readiness_overall`` is reported, never enforced. A
  ``ready_pending_operator_authorization`` value still requires an
  explicit operator-authored governance-bootstrap PR before any
  cap flip; A20 itself triggers nothing.
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
from reporting import development_roadmap_progress as drp
from reporting import development_step5_loop as dsl
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A20"
REPORT_KIND: Final[str] = "development_step5_1_readiness"

# ---------------------------------------------------------------------------
# Step 5 invariants (re-asserted on every artefact)
# ---------------------------------------------------------------------------

#: Mirrored from ``development_step5_loop`` so the artefact is
#: self-attesting.
STEP5_ENABLED_SUBSTAGE: Final[str] = "none"

#: Hard-pinned literal. Step 5 implementation remains BLOCKED.
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed readiness-overall vocabulary.
READINESS_OVERALL: Final[tuple[str, ...]] = (
    "not_ready",
    "preconditions_partially_met",
    "ready_pending_operator_authorization",
)

#: Closed per-check status vocabulary.
CHECK_STATUSES: Final[tuple[str, ...]] = (
    "pass",
    "fail",
    "not_applicable",
)

#: Closed check-id vocabulary. Each check is named so the operator
#: can scan the artefact and immediately see which preconditions
#: have been met. Adding a check requires an updated unit test.
CHECK_IDS: Final[tuple[str, ...]] = (
    "step5_implementation_allowed_currently_false",
    "step5_enabled_substage_currently_none",
    "intake_bridge_artifact_present",
    "promotion_artifact_present",
    "admission_artifact_present",
    "progress_artifact_present",
    "step5_history_present",
    "at_least_one_eligible_intake_candidate",
    "at_least_one_admissible_admission_row",
    "at_least_one_step5_plan_emitted_cycle",
    "no_classification_drift_in_promotion_rows",
    "no_blocked_admission_rows",
    "no_phase_marked_complete_by_a19",
)

#: Per-check row schema, exact and ordered.
CHECK_ROW_KEYS: Final[tuple[str, ...]] = (
    "check_id",
    "status",
    "value",
    "threshold",
    "note",
)

#: Wrapper-level note vocabulary.
NOTE_NO_UPSTREAM: Final[str] = "no_upstream_artifacts"
NOTE_PRECONDITIONS_REPORTED: Final[str] = "preconditions_reported"

#: Repo-relative paths.
ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "development_step5_1_readiness"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_step5_1_readiness/latest.json"
)

#: Atomic-write allowlist (substring form).
_WRITE_PREFIX: Final[str] = "logs/development_step5_1_readiness/"


# ---------------------------------------------------------------------------
# Discipline invariants
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool | str]] = {
    "flips_step5_implementation_allowed": False,
    "changes_step5_enabled_substage": False,
    "marks_any_phase_complete": False,
    "writes_to_seed_jsonl": False,
    "writes_to_delegation_seed_jsonl": False,
    "writes_to_generated_seed_jsonl": False,
    "mutates_canonical_roadmap_status_fields": False,
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


def _check(
    check_id: str,
    *,
    status: str,
    value: Any,
    threshold: Any = None,
    note: str = "",
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "check_id": check_id,
        "status": status,
        "value": value,
        "threshold": threshold,
        "note": note,
    }
    assert set(row.keys()) == set(CHECK_ROW_KEYS)
    return row


# ---------------------------------------------------------------------------
# Per-check evaluators
# ---------------------------------------------------------------------------


def _check_step5_invariants() -> list[dict[str, Any]]:
    """Re-emit (read-only) the live Step 5 invariants. PASS means
    they currently sit at the BLOCKED defaults — which is the
    *required* state for any future flip to be safe to author."""
    return [
        _check(
            "step5_implementation_allowed_currently_false",
            status="pass" if dsl.step5_implementation_allowed is False else "fail",
            value=bool(dsl.step5_implementation_allowed),
            threshold=False,
            note="must currently be False; flipping requires a separate operator-authored governance-bootstrap PR",
        ),
        _check(
            "step5_enabled_substage_currently_none",
            status="pass" if dsl.STEP5_ENABLED_SUBSTAGE == "none" else "fail",
            value=str(dsl.STEP5_ENABLED_SUBSTAGE),
            threshold="none",
            note="must currently be \"none\"; flipping requires a separate operator-authored governance-bootstrap PR",
        ),
    ]


def _check_artifact_presence(
    *,
    intake_payload: dict[str, Any] | None,
    promotion_payload: dict[str, Any] | None,
    admission_payload: dict[str, Any] | None,
    progress_payload: dict[str, Any] | None,
    step5_history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        _check(
            "intake_bridge_artifact_present",
            status="pass" if intake_payload is not None else "fail",
            value=intake_payload is not None,
            threshold=True,
        ),
        _check(
            "promotion_artifact_present",
            status="pass" if promotion_payload is not None else "fail",
            value=promotion_payload is not None,
            threshold=True,
        ),
        _check(
            "admission_artifact_present",
            status="pass" if admission_payload is not None else "fail",
            value=admission_payload is not None,
            threshold=True,
        ),
        _check(
            "progress_artifact_present",
            status="pass" if progress_payload is not None else "fail",
            value=progress_payload is not None,
            threshold=True,
        ),
        _check(
            "step5_history_present",
            status="pass" if step5_history else "fail",
            value=len(step5_history),
            threshold=">=1",
        ),
    ]


def _check_pipeline_signal(
    *,
    intake_payload: dict[str, Any] | None,
    admission_payload: dict[str, Any] | None,
    step5_history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    eligible = 0
    if isinstance(intake_payload, dict):
        for c in (intake_payload.get("candidates") or []):
            if isinstance(c, dict) and c.get("intake_status") == "eligible":
                eligible += 1
    admissible = 0
    if isinstance(admission_payload, dict):
        for r in (admission_payload.get("rows") or []):
            if isinstance(r, dict) and r.get("admission_decision") == "admissible":
                admissible += 1
    plan_emitted = sum(
        1
        for e in step5_history
        if isinstance(e, dict) and e.get("outcome") == "plan_emitted"
    )
    return [
        _check(
            "at_least_one_eligible_intake_candidate",
            status="pass" if eligible >= 1 else "fail",
            value=eligible,
            threshold=">=1",
        ),
        _check(
            "at_least_one_admissible_admission_row",
            status="pass" if admissible >= 1 else "fail",
            value=admissible,
            threshold=">=1",
        ),
        _check(
            "at_least_one_step5_plan_emitted_cycle",
            status="pass" if plan_emitted >= 1 else "fail",
            value=plan_emitted,
            threshold=">=1",
        ),
    ]


def _check_quality_gates(
    *,
    promotion_payload: dict[str, Any] | None,
    admission_payload: dict[str, Any] | None,
    progress_payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    drift = 0
    if isinstance(promotion_payload, dict):
        for r in (promotion_payload.get("rows") or []):
            if isinstance(r, dict) and r.get("classification_drift"):
                drift += 1
    blocked = 0
    if isinstance(admission_payload, dict):
        for r in (admission_payload.get("rows") or []):
            if isinstance(r, dict) and r.get("admission_decision") == "blocked":
                blocked += 1
    phase_complete = 0
    if isinstance(progress_payload, dict):
        for r in (progress_payload.get("rows") or []):
            if (
                isinstance(r, dict)
                and r.get("phase_progress_state") == "complete"
            ):
                phase_complete += 1
    return [
        _check(
            "no_classification_drift_in_promotion_rows",
            status="pass" if drift == 0 else "fail",
            value=drift,
            threshold=0,
            note="any drift means upstream + reclassified authority disagree",
        ),
        _check(
            "no_blocked_admission_rows",
            status="pass" if blocked == 0 else "fail",
            value=blocked,
            threshold=0,
        ),
        _check(
            "no_phase_marked_complete_by_a19",
            status="pass" if phase_complete == 0 else "fail",
            value=phase_complete,
            threshold=0,
            note="A19 NEVER assigns complete; non-zero here is a bug",
        ),
    ]


# ---------------------------------------------------------------------------
# Readiness overall derivation
# ---------------------------------------------------------------------------


def _derive_readiness_overall(checks: list[dict[str, Any]]) -> str:
    """Closed-table derivation. The output is a *report*, not a
    decision."""
    pass_count = sum(1 for c in checks if c.get("status") == "pass")
    fail_count = sum(1 for c in checks if c.get("status") == "fail")
    total = len(checks)
    if pass_count == total:
        # All preconditions met. Still requires explicit operator
        # authorisation before any cap flip — A20 emits the readiness
        # signal; the operator-authored PR remains the only path that
        # can change ``step5_implementation_allowed``.
        return "ready_pending_operator_authorization"
    if fail_count == total:
        return "not_ready"
    return "preconditions_partially_met"


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    intake_artifact_path: Path | None = None,
    promotion_artifact_path: Path | None = None,
    admission_artifact_path: Path | None = None,
    progress_artifact_path: Path | None = None,
    step5_history_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic readiness-report snapshot."""
    from reporting import development_roadmap_intake as dri

    ip = intake_artifact_path if intake_artifact_path is not None else dri.ARTIFACT_LATEST
    pp = promotion_artifact_path if promotion_artifact_path is not None else dip.ARTIFACT_LATEST
    ap = admission_artifact_path if admission_artifact_path is not None else qap.ARTIFACT_LATEST
    rp = progress_artifact_path if progress_artifact_path is not None else drp.ARTIFACT_LATEST
    hp = step5_history_path if step5_history_path is not None else dsl.HISTORY_PATH
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    intake_payload = _read_json(ip)
    promotion_payload = _read_json(pp)
    admission_payload = _read_json(ap)
    progress_payload = _read_json(rp)
    step5_history = _read_jsonl(hp)

    checks: list[dict[str, Any]] = []
    checks.extend(_check_step5_invariants())
    checks.extend(
        _check_artifact_presence(
            intake_payload=intake_payload,
            promotion_payload=promotion_payload,
            admission_payload=admission_payload,
            progress_payload=progress_payload,
            step5_history=step5_history,
        )
    )
    checks.extend(
        _check_pipeline_signal(
            intake_payload=intake_payload,
            admission_payload=admission_payload,
            step5_history=step5_history,
        )
    )
    checks.extend(
        _check_quality_gates(
            promotion_payload=promotion_payload,
            admission_payload=admission_payload,
            progress_payload=progress_payload,
        )
    )

    # Pin coverage: every check_id is closed-vocab.
    seen = {c["check_id"] for c in checks}
    assert seen == set(CHECK_IDS), (
        f"check coverage drift: missing={set(CHECK_IDS) - seen} "
        f"extra={seen - set(CHECK_IDS)}"
    )

    overall = _derive_readiness_overall(checks)

    counts = {
        "total_checks": len(checks),
        "pass": sum(1 for c in checks if c.get("status") == "pass"),
        "fail": sum(1 for c in checks if c.get("status") == "fail"),
        "not_applicable": sum(
            1 for c in checks if c.get("status") == "not_applicable"
        ),
        "by_status": {s: 0 for s in CHECK_STATUSES},
    }
    for c in checks:
        s = c.get("status")
        if s in counts["by_status"]:
            counts["by_status"][s] += 1

    sources_present = {
        "intake": intake_payload is not None,
        "promotion": promotion_payload is not None,
        "admission": admission_payload is not None,
        "progress": progress_payload is not None,
        "step5_history": bool(step5_history),
    }
    note = (
        NOTE_NO_UPSTREAM
        if not any(sources_present.values())
        else NOTE_PRECONDITIONS_REPORTED
    )

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "current_step5_implementation_allowed": (
            dsl.step5_implementation_allowed
        ),
        "current_step5_enabled_substage": str(dsl.STEP5_ENABLED_SUBSTAGE),
        "readiness_overall": overall,
        "sources_read": [
            {"source": "intake", "path": str(ip), "available": intake_payload is not None},
            {"source": "promotion", "path": str(pp), "available": promotion_payload is not None},
            {"source": "admission", "path": str(ap), "available": admission_payload is not None},
            {"source": "progress", "path": str(rp), "available": progress_payload is not None},
            {"source": "step5_history", "path": str(hp), "available": bool(step5_history)},
        ],
        "note": note,
        "validation_warnings": [],
        "vocabularies": {
            "readiness_overall": list(READINESS_OVERALL),
            "check_statuses": list(CHECK_STATUSES),
            "check_ids": list(CHECK_IDS),
            "check_row_keys": list(CHECK_ROW_KEYS),
        },
        "counts": counts,
        "checks": checks,
        "intake_promotion_module_version": dip.MODULE_VERSION,
        "admission_module_version": qap.MODULE_VERSION,
        "progress_module_version": drp.MODULE_VERSION,
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
            "development_step5_1_readiness._atomic_write_json refuses "
            f"non-readiness-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_step5_1_readiness.",
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
        prog="python -m reporting.development_step5_1_readiness",
        description=(
            "A20 Step 5.1 readiness report. Read-only; reports "
            "preconditions for a future operator-authored Step 5.1 "
            "enablement. NEVER flips step5_implementation_allowed. "
            "NEVER changes STEP5_ENABLED_SUBSTAGE."
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
            "logs/development_step5_1_readiness/latest.json "
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
