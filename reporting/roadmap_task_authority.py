"""A20c — Authority / Risk Classifier Integration (read-only, deterministic).

Per-unit projection that joins the A20b implementation-unit
decomposition with the canonical Execution Authority classifier
(:func:`reporting.execution_authority.classify`). Emits a
deterministic artefact at ``logs/roadmap_task_authority/latest.json``.

This module is a **pure consumer** of two read-only upstreams:

* :mod:`reporting.roadmap_task_units` — the A20b implementation
  units (which themselves derive from the A20a catalog);
* :mod:`reporting.execution_authority` — the canonical agent
  execution-authority classifier and the only source of truth for
  per-action / per-target authority verdicts.

A20c MUST NOT create a second source of truth for authority. Every
per-file decision is the verbatim ``ExecutionDecision`` returned by
``execution_authority.classify(...)``. Aggregation is a pure
max-severity reduction (``AUTO_ALLOWED < NEEDS_HUMAN <
PERMANENTLY_DENIED``).

A20b's ``authority_hint`` is preserved as **non-authoritative
metadata only**, side-by-side with the canonical aggregate. The
hint never overrides the classifier verdict.

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.execution_authority`` (read-only) +
  ``reporting.roadmap_task_units`` (read-only) +
  ``reporting.roadmap_task_catalog`` (read-only, version pin only)
  only.
* No subprocess, no network, no ``gh``, no ``git``, no GitHub API.
* No imports of ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``, ``live``,
  ``paper``, ``shadow``, ``trading``,
  ``reporting.intelligent_routing``,
  ``reporting.development_queue_admission_policy``,
  ``reporting.development_agent_activity_timeline``.
* No LLM, no external API, no fuzzy parsing, no file-content
  parsing of any canonical document at runtime.
* Atomic write only under ``logs/roadmap_task_authority/``.
* Deterministic output: same upstream + injected
  ``generated_at_utc`` → byte-identical artefact.
* No mutation of A20a or A20b artefacts (pinned by sha256
  before/after tests).
* No runtime / trading / paper / shadow / broker / risk / live
  authority granted; pinned by closed invariants on every
  projection.
* ``step5_implementation_allowed`` remains ``False``;
  ``STEP5_ENABLED_SUBSTAGE`` remains ``"none"``.

CLI::

    python -m reporting.roadmap_task_authority
    python -m reporting.roadmap_task_authority --no-write
    python -m reporting.roadmap_task_authority --status
    python -m reporting.roadmap_task_authority --indent 2
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import execution_authority as ea
from reporting import roadmap_task_catalog as rtc
from reporting import roadmap_task_units as rtu

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A20c"
REPORT_KIND: Final[str] = "roadmap_task_authority"


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants (Final constants — never flipped at runtime)
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies (re-exported from the canonical classifier)
# ---------------------------------------------------------------------------

#: Verbatim re-export from the canonical classifier. Pinned by tests.
DECISIONS: Final[tuple[str, ...]] = ea.DECISIONS

#: Verbatim re-export from the canonical classifier. Pinned by tests.
RISK_CLASSES: Final[tuple[str, ...]] = ea.RISK_CLASSES

#: Action type passed for every per-file classification. ``file_edit``
#: is the modify-action that A20b's emitted units describe (writing
#: new files into a unit's ``expected_files`` set).
_ACTION_TYPE: Final[str] = "file_edit"

#: Severity ordering for unit-level aggregation. Higher value = more
#: restrictive. Pinned by a unit test.
_SEVERITY: Final[dict[str, int]] = {
    ea.DECISION_AUTO_ALLOWED: 0,
    ea.DECISION_NEEDS_HUMAN: 1,
    ea.DECISION_PERMANENTLY_DENIED: 2,
}

#: Fail-closed authority value emitted when a unit declares an
#: empty ``expected_files`` list (defence in depth — A20b's tests
#: forbid empty ``expected_files``, but A20c stays safe even if a
#: future A20b regression slipped one through).
_AGGREGATE_FAIL_CLOSED: Final[str] = ea.DECISION_NEEDS_HUMAN
_AGGREGATE_FAIL_CLOSED_REASON: Final[str] = "unknown_risk_or_target_fail_safe"


# ---------------------------------------------------------------------------
# Schema field tuples (exact, ordered)
# ---------------------------------------------------------------------------

#: Per-file ``ExecutionDecision`` record shape (the bounded-scalar
#: projection of an :class:`ea.ExecutionDecision`).
PER_FILE_DECISION_FIELDS: Final[tuple[str, ...]] = (
    "path",
    "action_type",
    "risk_class",
    "decision",
    "reason",
    "target_path_category",
)

#: ``UnitAuthorityDecision`` field list. Exact and ordered.
UNIT_AUTHORITY_DECISION_FIELDS: Final[tuple[str, ...]] = (
    "unit_id",
    "parent_task_id",
    "expected_files_decisions",
    "forbidden_files_decisions",
    "aggregate_decision",
    "aggregate_reason",
    "authority_hint_from_a20b",
    "classifier_schema_version",
    "classifier_module",
    "forbidden_surface_reasons",
)

#: ``UnitAuthorityProjection`` field list. Exact and ordered.
UNIT_AUTHORITY_PROJECTION_FIELDS: Final[tuple[str, ...]] = (
    "generated_at_utc",
    "schema_version",
    "module_version",
    "source_catalog_module_version",
    "source_units_module_version",
    "authority_decisions",
    "classification_invariants",
)


# ---------------------------------------------------------------------------
# Artefact paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "roadmap_task_authority"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = "logs/roadmap_task_authority/latest.json"

#: Atomic-write allowlist (POSIX path substring form). Any write
#: target whose path does not contain this substring is refused with
#: ``ValueError``.
_WRITE_PREFIX: Final[str] = "logs/roadmap_task_authority/"


# ---------------------------------------------------------------------------
# Classification invariants emitted on every projection
# ---------------------------------------------------------------------------

_BASE_CLASSIFICATION_INVARIANTS: Final[dict[str, bool]] = {
    # The two flips A20c performs vs A20b's invariants:
    "calls_execution_authority_classifier": True,
    "final_authority_classified": True,
    # Authority chain — carry forward A20b's posture verbatim:
    "no_runtime_trading_authority": True,
    "no_step5_runtime": True,
    "no_level6": True,
    "no_production_merge_authority": True,
    "writes_only_roadmap_task_authority_log": True,
    "step5_implementation_allowed": False,
    # Upstream-mutation invariants (pinned by sha256 before/after
    # tests):
    "mutates_a20a_artifact": False,
    "mutates_a20b_artifact": False,
    "mutates_roadmap_status_fields": False,
    "marks_phase_complete": False,
    "fuzzy_parsing": False,
    "uses_subprocess_or_network": False,
    "calls_llm_or_external_api": False,
    "writes_to_seed_jsonl": False,
    "writes_to_delegation_seed_jsonl": False,
    "writes_to_generated_seed_jsonl": False,
    # Downstream surfaces not yet implemented; A20d / A20e will
    # flip these when they land.
    "aac_visibility_present": False,
    "next_buildable_selector_present": False,
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


def _project_decision(
    decision: ea.ExecutionDecision,
    *,
    path: str,
    risk_class: str,
) -> dict[str, Any]:
    """Project an :class:`ea.ExecutionDecision` into a bounded-scalar
    record. Schema is :data:`PER_FILE_DECISION_FIELDS`."""
    return {
        "path": path,
        "action_type": _ACTION_TYPE,
        "risk_class": risk_class,
        "decision": decision.decision,
        "reason": decision.reason,
        "target_path_category": decision.target_path_category,
    }


def _classify_one(
    path: str, *, risk_class: str
) -> tuple[ea.ExecutionDecision, dict[str, Any]]:
    """Single per-path call into the canonical classifier. Returns
    both the raw decision (for aggregation) and the bounded-scalar
    projection (for the artefact)."""
    decision = ea.classify(
        action_type=_ACTION_TYPE,
        target_path=path,
        risk_class=risk_class,
    )
    return decision, _project_decision(decision, path=path, risk_class=risk_class)


def _aggregate_expected_decisions(
    expected_decisions: list[ea.ExecutionDecision],
) -> tuple[str, str]:
    """Reduce per-file decisions on ``expected_files`` to a unit-level
    ``(aggregate_decision, aggregate_reason)`` pair using max-severity
    over the canonical ``DECISIONS`` ordering.

    Fail-closed contract:

    * empty list (defence in depth — A20b forbids empty
      ``expected_files`` but A20c stays safe) → ``NEEDS_HUMAN`` /
      ``unknown_risk_or_target_fail_safe``;
    * any ``PERMANENTLY_DENIED`` → ``PERMANENTLY_DENIED`` (with that
      decision's reason);
    * any ``NEEDS_HUMAN`` and no denied → ``NEEDS_HUMAN`` (with that
      decision's reason);
    * all ``AUTO_ALLOWED`` → ``AUTO_ALLOWED`` (with the first
      decision's reason in input order; A20a/A20b emit deterministic
      ordered ``expected_files``).
    """
    if not expected_decisions:
        return _AGGREGATE_FAIL_CLOSED, _AGGREGATE_FAIL_CLOSED_REASON

    # First-match wins per severity tier.
    for d in expected_decisions:
        if d.decision == ea.DECISION_PERMANENTLY_DENIED:
            return d.decision, d.reason
    for d in expected_decisions:
        if d.decision == ea.DECISION_NEEDS_HUMAN:
            return d.decision, d.reason
    # All AUTO_ALLOWED — pick the first decision's reason.
    return expected_decisions[0].decision, expected_decisions[0].reason


def _decide_for_unit(unit: dict[str, Any]) -> dict[str, Any]:
    """Build one ``UnitAuthorityDecision`` from one A20b unit."""
    raw_risk = unit.get("risk_class")
    risk_class = raw_risk if raw_risk in RISK_CLASSES else ea.RISK_UNKNOWN

    expected_decisions: list[ea.ExecutionDecision] = []
    expected_records: list[dict[str, Any]] = []
    for path in unit.get("expected_files", []):
        decision, record = _classify_one(path, risk_class=risk_class)
        expected_decisions.append(decision)
        expected_records.append(record)

    forbidden_decisions: list[ea.ExecutionDecision] = []
    forbidden_records: list[dict[str, Any]] = []
    for path in unit.get("forbidden_files", []):
        decision, record = _classify_one(path, risk_class=risk_class)
        forbidden_decisions.append(decision)
        forbidden_records.append(record)

    aggregate_decision, aggregate_reason = _aggregate_expected_decisions(
        expected_decisions
    )

    return {
        "unit_id": unit["id"],
        "parent_task_id": unit["roadmap_task_id"],
        "expected_files_decisions": expected_records,
        "forbidden_files_decisions": forbidden_records,
        "aggregate_decision": aggregate_decision,
        "aggregate_reason": aggregate_reason,
        "authority_hint_from_a20b": unit.get("authority_hint", ""),
        "classifier_schema_version": ea.SCHEMA_VERSION,
        "classifier_module": "reporting.execution_authority",
        "forbidden_surface_reasons": list(
            unit.get("forbidden_surface_reasons", [])
        ),
    }


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic Roadmap-task-authority projection.

    Args:
        generated_at_utc: override the report timestamp. Tests inject
            this for byte-stable output.
    """
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    # Read upstream A20b units. The A20b snapshot already reads A20a
    # transitively; we do not re-read the A20a catalog content here
    # except to record its module_version for cross-reference.
    units_snapshot = rtu.collect_snapshot(generated_at_utc=ts)
    catalog_snapshot = rtc.collect_snapshot(generated_at_utc=ts)

    decisions = [_decide_for_unit(u) for u in units_snapshot["implementation_units"]]
    decisions.sort(key=lambda r: (r["parent_task_id"], r["unit_id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "source_catalog_module_version": catalog_snapshot["module_version"],
        "source_catalog_schema_version": catalog_snapshot["schema_version"],
        "source_units_module_version": units_snapshot["module_version"],
        "source_units_schema_version": units_snapshot["schema_version"],
        "classifier_module_version": ea.MODULE_VERSION,
        "classifier_schema_version": ea.SCHEMA_VERSION,
        "vocabularies": {
            "decisions": list(DECISIONS),
            "risk_classes": list(RISK_CLASSES),
            "action_type": [_ACTION_TYPE],
            "severity_ordering": [
                ea.DECISION_AUTO_ALLOWED,
                ea.DECISION_NEEDS_HUMAN,
                ea.DECISION_PERMANENTLY_DENIED,
            ],
        },
        "authority_decisions": decisions,
        "classification_invariants": dict(_BASE_CLASSIFICATION_INVARIANTS),
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` as sorted-key indented JSON to ``path``,
    atomically, refusing any path outside
    ``logs/roadmap_task_authority/``."""
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix:
        raise ValueError(
            "roadmap_task_authority._atomic_write_json refuses "
            f"non-authority-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".roadmap_task_authority.",
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
# Status renderer
# ---------------------------------------------------------------------------


def _render_status(snapshot: dict[str, Any]) -> str:
    decisions = snapshot["authority_decisions"]
    inv = snapshot["classification_invariants"]
    by_aggregate: dict[str, int] = {d: 0 for d in DECISIONS}
    by_hint: dict[str, int] = {}
    for d in decisions:
        by_aggregate[d["aggregate_decision"]] += 1
        hint = d["authority_hint_from_a20b"] or "(none)"
        by_hint[hint] = by_hint.get(hint, 0) + 1
    lines = [
        f"roadmap_task_authority {snapshot['module_version']} "
        f"schema={snapshot['schema_version']}",
        f"generated_at_utc={snapshot['generated_at_utc']}",
        f"authority_decisions={len(decisions)}",
        (
            "step5_implementation_allowed="
            f"{snapshot['step5_implementation_allowed']} "
            f"step5_enabled_substage={snapshot['step5_enabled_substage']}"
        ),
        (
            "calls_execution_authority_classifier="
            f"{inv['calls_execution_authority_classifier']} "
            "final_authority_classified="
            f"{inv['final_authority_classified']}"
        ),
        (
            "no_runtime_trading_authority="
            f"{inv['no_runtime_trading_authority']} "
            f"no_step5_runtime={inv['no_step5_runtime']} "
            f"no_level6={inv['no_level6']} "
            "no_production_merge_authority="
            f"{inv['no_production_merge_authority']}"
        ),
        (
            "writes_only_roadmap_task_authority_log="
            f"{inv['writes_only_roadmap_task_authority_log']}"
        ),
        f"by_aggregate_decision={dict(sorted(by_aggregate.items()))}",
        f"by_authority_hint={dict(sorted(by_hint.items()))}",
    ]
    for d in decisions:
        lines.append(
            f"  unit {d['unit_id']} parent={d['parent_task_id']} "
            f"aggregate={d['aggregate_decision']} "
            f"hint={d['authority_hint_from_a20b']}"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.roadmap_task_authority",
        description=(
            "A20c Authority/Risk Classifier Integration. Read-only "
            "deterministic projection that classifies every A20b "
            "implementation unit's expected_files and forbidden_files "
            "via the canonical reporting.execution_authority "
            "classifier. No second source of truth for authority. "
            "Step 5 implementation remains BLOCKED."
        ),
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent for stdout output (0 for compact).",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist logs/roadmap_task_authority/latest.json "
            "(stdout only)."
        ),
    )
    p.add_argument(
        "--status",
        action="store_true",
        help=(
            "Render a compact human-readable status summary to stdout "
            "and exit. Does not write any artefact."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snap = collect_snapshot()
    if args.status:
        sys.stdout.write(_render_status(snap))
        return 0
    indent = args.indent if args.indent and args.indent > 0 else None
    if not args.no_write:
        write_outputs(snap)
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
