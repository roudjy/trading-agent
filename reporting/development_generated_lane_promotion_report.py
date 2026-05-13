"""A18 promotion-readiness report (read-only / report-only).

Pure stdlib projector that reads the existing A18c artefact at
``logs/development_generated_lane_a18c/latest.json`` and emits a
closed-schema **report-only** snapshot at
``logs/development_generated_lane_promotion_report/latest.json``.

This module is the Phase 5a slice. It surfaces what *would* be
required to promote any A18c-projected row into the queue
admission path, **without ever promoting anything**. The
hard-pinned safety property is: for **every** row this module
emits, ``promotion_allowed = False``. Promotion remains a
separate operator-paced future step gated by the explicit
operator-go phrase ``GO A18 promotion operator-promote``.

Hard guarantees pinned by the companion tests
---------------------------------------------

* Stdlib + ``reporting.development_generated_lane_a18c`` (closed
  vocab + artefact path constants) +
  ``reporting.development_queue_admission_policy`` (closed
  ADMISSION_DECISIONS / ADMISSION_REASONS for vocab pinning) +
  ``reporting.agent_audit_summary.assert_no_secrets`` (read-only
  redactor guard).
* No subprocess, no network, no ``gh``, no ``git``.
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``,
  ``shadow``, ``trading``, ``reporting.approval_token_gate``,
  ``reporting.approval_token_runtime``,
  ``reporting.development_generated_lane_writer`` (this module
  never touches A18b; it consumes A18c's already-projected
  artefact).
* Atomic write only under
  ``logs/development_generated_lane_promotion_report/...``.
* The closed envelope schema carries every report row's
  ``promotion_allowed`` field as **hard-pinned False** —
  regardless of the A18c admission decision, even an A18c row
  that ever returned ``admissible`` would have
  ``promotion_allowed=False`` in the report. The report is
  forensic / oversight only; the report module itself NEVER
  enables a promotion path.
* The closed envelope carries the required operator-go phrase
  literally (``"GO A18 promotion operator-promote"``) so a
  consumer can render it verbatim.
* Closed ``BLOCK_REASONS`` and ``READINESS_NOTES`` vocabularies.
* Per-row schema is closed and exact; bounded scalars only.
* ``step5_implementation_allowed`` remains ``False`` and
  ``STEP5_ENABLED_SUBSTAGE`` remains ``"none"``.
* Level 6 is permanently disabled per ADR-015 §Doctrine 1.

What this module is NOT
-----------------------

* It is **not** a promotion engine. It never writes to
  ``generated_seed.jsonl`` (A18b territory). It never admits a
  queue row (A17 territory). It never executes work.
* It is **not** an A18c re-projector. It reads A18c's
  ``latest.json`` once per call and never triggers A18c.
* It is **not** an A17 mutation. The A17 admission policy
  module's artefact is never created, mutated, or read for
  writing by this module.
* It is **not** authorised to promote the Phase-2 diagnostic
  row (``a18b-phase2-smoke-2026-05-13-001``). Every row the
  report emits carries ``promotion_allowed=False``.
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

from reporting import development_generated_lane_a18c as a18c
from reporting import development_queue_admission_policy as a17
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A18.promotion_report"
REPORT_KIND: Final[str] = "development_generated_lane_promotion_report"


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Pinned safety constants
# ---------------------------------------------------------------------------

#: For every report row, promotion_allowed is hard-pinned to False.
#: This module never enables a promotion path. The constant exists
#: so consumers (and the companion test) can pin it explicitly.
PROMOTION_ALLOWED_DEFAULT: Final[bool] = False

#: Exact operator-go phrase a future PR would issue to actually
#: build operator-promote functionality. The report surfaces this
#: phrase verbatim so a consumer can render it. The phrase itself
#: is NOT issued by this module; it identifies the future-go.
OPERATOR_GO_PHRASE: Final[str] = "GO A18 promotion operator-promote"


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed per-row block-reason vocabulary. The first four values
#: mirror A17's admission_decision outcomes via a deterministic
#: mapping. The fifth value is defense-in-depth: even if an A18c
#: row ever carried admission_decision="admissible", this report
#: would emit promotion_disabled_by_default and STILL set
#: promotion_allowed=False.
BLOCK_REASONS: Final[tuple[str, ...]] = (
    "needs_human_per_a17_policy",
    "blocked_per_a17_policy",
    "duplicate_per_a17_policy",
    "not_eligible_upstream_per_a17_policy",
    "promotion_disabled_by_default",
)

#: Closed envelope-level readiness-note vocabulary.
READINESS_NOTES: Final[tuple[str, ...]] = (
    "a18c_artifact_absent",
    "a18c_artifact_malformed",
    "no_source_rows",
    "rows_present_none_promotable",
)


# ---------------------------------------------------------------------------
# Per-row closed schema
# ---------------------------------------------------------------------------

REPORT_ROW_KEYS: Final[tuple[str, ...]] = (
    "candidate_id",
    "source_kind",
    "candidate_kind",
    "admission_decision",
    "admission_reason",
    "would_target_lane",
    "human_needed",
    "human_needed_reason",
    "risk_level",
    "promotion_allowed",
    "block_reason",
    "required_operator_go_phrase",
    "readiness_reason",
    "evaluated_at",
)


# ---------------------------------------------------------------------------
# Repo-relative paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "development_generated_lane_promotion_report"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_generated_lane_promotion_report/latest.json"
)

#: Atomic-write allowlist (substring form). Any attempt to write
#: outside this prefix raises ``ValueError``.
_WRITE_PREFIX: Final[str] = (
    "logs/development_generated_lane_promotion_report/"
)


# ---------------------------------------------------------------------------
# Discipline invariants
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool | str]] = {
    "default_disabled": False,
    "promotes_anything": False,
    "writes_to_seed_jsonl": False,
    "writes_to_delegation_seed_jsonl": False,
    "writes_to_generated_seed_jsonl": False,
    "mutates_a18c_artifact": False,
    "mutates_a17_artifact": False,
    "admits_to_queue": False,
    "executes_work": False,
    "creates_branches": False,
    "opens_prs": False,
    "merges_prs": False,
    "deploys": False,
    "calls_network": False,
    "uses_subprocess": False,
    "touches_step5_flags": False,
    "level6_enabled": False,
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


def _read_a18c_artifact(
    path: Path,
) -> tuple[str, dict[str, Any] | None]:
    """Return ``("ok", payload)``, ``("absent", None)``, or
    ``("malformed", None)``. Never raises."""
    if not path.is_file():
        return ("absent", None)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ("malformed", None)
    try:
        data = json.loads(text)
    except (ValueError, json.JSONDecodeError):
        return ("malformed", None)
    if not isinstance(data, dict):
        return ("malformed", None)
    return ("ok", data)


# ---------------------------------------------------------------------------
# Per-row block-reason mapping
# ---------------------------------------------------------------------------


def _map_block_reason(admission_decision: str) -> str:
    """Map an A17 admission_decision to this report's closed
    ``BLOCK_REASONS`` vocabulary.

    The default-deny case (any decision not in the closed map,
    including the hypothetical ``"admissible"`` value that the
    A18c first-cut posture never emits) returns
    ``"promotion_disabled_by_default"`` — the defense-in-depth
    catch-all that still asserts the report does not promote.
    """
    mapping = {
        "needs_human": "needs_human_per_a17_policy",
        "blocked": "blocked_per_a17_policy",
        "duplicate_of_existing": "duplicate_per_a17_policy",
        "not_eligible_upstream": "not_eligible_upstream_per_a17_policy",
    }
    return mapping.get(admission_decision, "promotion_disabled_by_default")


# ---------------------------------------------------------------------------
# Per-row construction
# ---------------------------------------------------------------------------


def _build_report_row(
    a18c_row: dict[str, Any],
) -> dict[str, Any]:
    """Build a single closed-schema report row from an A18c row.
    Hard-pinned: ``promotion_allowed=False`` regardless of the
    A18c decision."""
    admission_decision = str(a18c_row.get("admission_decision") or "")
    admission_reason = str(a18c_row.get("admission_reason") or "")
    candidate_id = str(a18c_row.get("candidate_id") or "")
    source_kind = str(a18c_row.get("source_kind") or "")
    candidate_kind = str(a18c_row.get("candidate_kind") or "")
    would_target_lane = str(a18c_row.get("would_target_lane") or "none")
    human_needed = bool(a18c_row.get("human_needed"))
    human_needed_reason = str(a18c_row.get("human_needed_reason") or "")
    risk_level = str(a18c_row.get("risk_level") or "")
    evaluated_at = str(a18c_row.get("evaluated_at") or "")

    block_reason = _map_block_reason(admission_decision)

    # The readiness-reason mirrors the block-reason for forensic
    # clarity; both are emitted because consumers may prefer one
    # framing over the other (block-reason answers "why blocked?",
    # readiness-reason answers "what would it take to ready?").
    readiness_reason = block_reason

    row: dict[str, Any] = {
        "candidate_id": candidate_id,
        "source_kind": source_kind,
        "candidate_kind": candidate_kind,
        "admission_decision": admission_decision,
        "admission_reason": admission_reason,
        "would_target_lane": would_target_lane,
        "human_needed": human_needed,
        "human_needed_reason": human_needed_reason,
        "risk_level": risk_level,
        # HARD-PINNED False — this module never promotes.
        "promotion_allowed": PROMOTION_ALLOWED_DEFAULT,
        "block_reason": block_reason,
        "required_operator_go_phrase": OPERATOR_GO_PHRASE,
        "readiness_reason": readiness_reason,
        "evaluated_at": evaluated_at,
    }
    assert set(row.keys()) == set(REPORT_ROW_KEYS), (
        "report row key drift: "
        f"{sorted(row.keys())!r} vs {sorted(REPORT_ROW_KEYS)!r}"
    )
    # Defense in depth — this module never promotes; pin again.
    assert row["promotion_allowed"] is False
    return row


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _aggregate_by_decision(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {d: 0 for d in a17.ADMISSION_DECISIONS}
    for r in rows:
        d = r.get("admission_decision")
        if d in counts:
            counts[d] += 1
    return counts


# ---------------------------------------------------------------------------
# Envelope assembly
# ---------------------------------------------------------------------------


def _build_envelope(
    *,
    a18c_artifact_path: Path,
    a18c_artifact_available: bool,
    a18c_module_version: str | None,
    a17_policy_version: str | None,
    rows: list[dict[str, Any]],
    readiness_note: str,
    validation_warnings: list[str],
    generated_at_utc: str,
) -> dict[str, Any]:
    """Build the closed-schema envelope. Always carries the
    discipline invariants and the report's safety constants."""
    source_row_count = len(rows)
    # Hard-pinned: zero promotable rows in this report module.
    promotable_row_count = sum(
        1 for r in rows if r["promotion_allowed"] is True
    )
    blocked_row_count = source_row_count - promotable_row_count
    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "a18c_artifact_path": str(a18c_artifact_path),
        "a18c_artifact_available": a18c_artifact_available,
        "a18c_module_version": a18c_module_version,
        "a17_policy_version": a17_policy_version,
        "source_row_count": source_row_count,
        "promotable_row_count": promotable_row_count,
        "blocked_row_count": blocked_row_count,
        "rows_by_admission_decision": _aggregate_by_decision(rows),
        "rows": rows,
        "readiness_note": readiness_note,
        "validation_warnings": list(validation_warnings),
        "operator_go_phrase_required": OPERATOR_GO_PHRASE,
        "policy_version": a17.MODULE_VERSION,
        "a18c_module_version_pin": a18c.MODULE_VERSION,
        "promotion_allowed_default": PROMOTION_ALLOWED_DEFAULT,
        "vocabularies": {
            "block_reasons": list(BLOCK_REASONS),
            "readiness_notes": list(READINESS_NOTES),
            "admission_decisions": list(a17.ADMISSION_DECISIONS),
            "admission_reasons": list(a17.ADMISSION_REASONS),
            "row_keys": list(REPORT_ROW_KEYS),
        },
        "step5_implementation_allowed": step5_implementation_allowed,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "level6_enabled": False,
        "dry_run_only": True,
        "live_merge_implemented": False,
        "deploy_coupled": False,
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
    }
    # Hard pin: defense-in-depth.
    assert snapshot["promotable_row_count"] == 0, (
        "promotable_row_count must be 0 — this module never promotes"
    )
    # Scrub the envelope before write.
    assert_no_secrets(snapshot)
    return snapshot


def collect_snapshot(
    *,
    a18c_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic promotion-readiness report
    snapshot. Pure — reads one read-only artefact (A18c's
    ``latest.json``), performs no write of any kind."""
    a18c_path = (
        a18c_artifact_path
        if a18c_artifact_path is not None
        else a18c.ARTIFACT_LATEST
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    status, payload = _read_a18c_artifact(a18c_path)

    if status == "absent":
        return _build_envelope(
            a18c_artifact_path=a18c_path,
            a18c_artifact_available=False,
            a18c_module_version=None,
            a17_policy_version=None,
            rows=[],
            readiness_note="a18c_artifact_absent",
            validation_warnings=["a18c_artifact_absent"],
            generated_at_utc=ts,
        )

    if status == "malformed":
        return _build_envelope(
            a18c_artifact_path=a18c_path,
            a18c_artifact_available=False,
            a18c_module_version=None,
            a17_policy_version=None,
            rows=[],
            readiness_note="a18c_artifact_malformed",
            validation_warnings=["a18c_artifact_malformed"],
            generated_at_utc=ts,
        )

    # payload is a dict (status="ok")
    assert payload is not None  # type narrowing
    a18c_module_version = (
        str(payload.get("module_version") or "")
        or None
    )
    a17_policy_version = (
        str(payload.get("policy_version") or "")
        or None
    )

    raw_rows = payload.get("rows")
    a18c_rows: list[dict[str, Any]] = []
    if isinstance(raw_rows, list):
        for r in raw_rows:
            if isinstance(r, dict):
                a18c_rows.append(r)

    rows: list[dict[str, Any]] = [_build_report_row(r) for r in a18c_rows]

    if not rows:
        return _build_envelope(
            a18c_artifact_path=a18c_path,
            a18c_artifact_available=True,
            a18c_module_version=a18c_module_version,
            a17_policy_version=a17_policy_version,
            rows=[],
            readiness_note="no_source_rows",
            validation_warnings=[],
            generated_at_utc=ts,
        )

    return _build_envelope(
        a18c_artifact_path=a18c_path,
        a18c_artifact_available=True,
        a18c_module_version=a18c_module_version,
        a17_policy_version=a17_policy_version,
        rows=rows,
        readiness_note="rows_present_none_promotable",
        validation_warnings=[],
        generated_at_utc=ts,
    )


# ---------------------------------------------------------------------------
# Atomic write (sentinel-restricted)
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "development_generated_lane_promotion_report._atomic_write_json "
            f"refuses non-report-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_generated_lane_promotion_report.",
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
    """Persist the snapshot to
    ``logs/development_generated_lane_promotion_report/latest.json``.
    Sentinel-restricted via :func:`_atomic_write_json`."""
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.development_generated_lane_promotion_report",
        description=(
            "A18 promotion-readiness report (read-only / "
            "report-only). Reads the existing A18c artefact at "
            "logs/development_generated_lane_a18c/latest.json "
            "and emits a closed-schema report at "
            "logs/development_generated_lane_promotion_report/latest.json. "
            "NEVER promotes, NEVER mutates A18c or A17 artefacts, "
            "NEVER writes to generated_seed.jsonl / seed.jsonl / "
            "delegation_seed.jsonl, NEVER admits queue rows, "
            "NEVER executes work, NEVER opens / merges a PR, "
            "NEVER deploys. The report surfaces the exact "
            "operator-go phrase that a future PR would issue to "
            "build operator-promote functionality, but the phrase "
            "itself is NOT issued here."
        ),
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist "
            "logs/development_generated_lane_promotion_report/latest.json "
            "(stdout only)."
        ),
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent (0 for compact).",
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
