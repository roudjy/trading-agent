"""A18c — generated_seed.jsonl admission projector (default-disabled).

Read-only projector that reads the existing A18b-written
``generated_seed.jsonl`` file and projects eligible rows into the
existing A17 admission flow as an additional, closed-vocab admission
source. A17 remains authoritative; A18c never modifies A17's
``reporting.development_queue_admission_policy`` module, never
relaxes any A17 filter, and never bypasses A17's policy table.

Hard, default-deny posture
--------------------------

The projector is **disabled by default**. It only reads
``generated_seed.jsonl`` when the operator has explicitly exported
the exact-string env value::

    ADE_GENERATED_LANE_A18C_ENABLED=true

Anything else — empty, ``"false"``, ``"1"``, ``"yes"``, ``"True"``,
``"TRUE"``, unset — leaves the projector in zero-projection mode.
The public ``collect_snapshot`` returns immediately with an
``enabled=False`` envelope and **does not read** the seed file.

Hard guarantees pinned by the companion tests
---------------------------------------------

* Default-disabled unless the env var matches the exact literal
  string ``"true"`` (case-sensitive, no aliases).
* Env-off: zero file reads of ``generated_seed.jsonl``, zero
  projections, no admission rows.
* Env-on + seed file absent → safe ``generated_seed_absent``
  envelope.
* Env-on + seed file malformed line → default-deny
  ``generated_seed_malformed`` envelope, zero rows, no crash.
* Env-on + seed file ok → A18c constructs A17-shaped upstream
  rows and calls
  ``a17.evaluate_promotion_record(synth_upstream)`` verbatim.
* **Defense in depth**: any A18b row with
  ``would_require_operator_go=True`` whose A17 decision comes
  back ``admissible`` is forced to ``needs_human`` /
  ``needs_human_authority_decision``. A17's rule #5 already
  fires for the same condition because A18c sets
  ``human_needed=True`` on the synth upstream; the post-A17
  check is belt-and-braces.
* Writes only to ``logs/development_generated_lane_a18c/`` via
  atomic tmp + ``os.replace``. The write-path sentinel refuses
  any other prefix.
* Per-tick cap of 8 projections. Per-day cap of 32 projections,
  applied by reading the prior ``latest.json`` snapshot's
  ``counts.total`` when its ``generated_at_utc`` is the same
  UTC day.
* Deterministic A18c candidate id derived from the A18b row's
  ``generated_candidate_id`` + first 16 hex chars of
  ``evidence_hash``.
* Duplicate candidate-id within a single tick is hard-suppressed
  (forensic-safe; no second row emitted).
* Duplicate ``evidence_hash`` across different A18b rows surfaces
  the closed warning ``duplicate_evidence_hash_in_a18b``.
* ``assert_no_secrets`` runs on every envelope before write.
* No subprocess, no network, no GitHub CLI, no ``git``, no
  ``approval-token`` runtime/gate import, no dashboard import,
  no frontend import, no execution surface.
* ``step5_implementation_allowed`` remains ``False`` and
  ``STEP5_ENABLED_SUBSTAGE`` remains ``"none"``.
* Level 6 is permanently disabled per ADR-015 §Doctrine 1.

What this module is NOT
-----------------------

* It is **not** a queue admission engine. A17 remains the only
  authority that decides whether a record is admissible; A18c
  projects through A17's existing closed vocabulary.
* It is **not** an executor. No work is started.
* It is **not** a PR / branch / merge / deploy surface.
* It is **not** authorised to admit the Phase-2 diagnostic row
  (``a18b-phase2-smoke-2026-05-13-001``); that row carries
  ``would_require_operator_go=True`` and therefore maps to
  ``needs_human`` regardless of other attributes.
* It is **not** a writer. ``generated_seed.jsonl`` is read-only
  to A18c; A18b is the only authority that appends to that file.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final, Mapping

from reporting import development_generated_lane_writer as a18b
from reporting import development_queue_admission_policy as a17
from reporting import execution_authority as ea
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A18c"
REPORT_KIND: Final[str] = "development_generated_lane_a18c"


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Env-gate constants
# ---------------------------------------------------------------------------

ENV_GATE: Final[str] = "ADE_GENERATED_LANE_A18C_ENABLED"
_ENABLED_VALUE: Final[str] = "true"


# ---------------------------------------------------------------------------
# Bounded caps
# ---------------------------------------------------------------------------

PER_TICK_CAP: Final[int] = 8
PER_DAY_CAP: Final[int] = 32


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

NOTES: Final[tuple[str, ...]] = (
    "env_gate_off",
    "generated_seed_absent",
    "generated_seed_malformed",
    "no_eligible_a18b_rows",
    "candidates_projected",
)

WARNINGS: Final[tuple[str, ...]] = (
    "env_gate_off_no_op",
    "generated_seed_absent",
    "generated_seed_malformed",
    "per_tick_cap_reached",
    "per_day_cap_reached",
    "duplicate_evidence_hash_in_a18b",
)


# ---------------------------------------------------------------------------
# Repo-relative paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "development_generated_lane_a18c"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_generated_lane_a18c/latest.json"
)

#: Atomic-write allowlist (substring form). Any attempt to write
#: outside this prefix raises ``ValueError``.
_WRITE_PREFIX: Final[str] = "logs/development_generated_lane_a18c/"


# ---------------------------------------------------------------------------
# Discipline invariants — emitted into every envelope.
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool | str]] = {
    "default_disabled": True,
    "reads_generated_seed_only_when_enabled": True,
    "writes_to_seed_jsonl": False,
    "writes_to_delegation_seed_jsonl": False,
    "writes_to_generated_seed_jsonl": False,
    "modifies_a17_admission_policy": False,
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
    "always_needs_human_in_first_cut": True,
    "bypasses_a17_filters": False,
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


def _utc_date_prefix(ts: str) -> str:
    """Return the ``YYYY-MM-DD`` prefix of an ISO-8601 UTC string,
    or an empty string if the input is not parseable."""
    if not isinstance(ts, str) or len(ts) < 10:
        return ""
    return ts[:10]


# ---------------------------------------------------------------------------
# Public API: env gate
# ---------------------------------------------------------------------------


def env_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return True iff the operator has exported the exact-string
    env value enabling A18c projection.

    Reads the env mapping at *call time*, not at import time."""
    source: Mapping[str, str] = env if env is not None else os.environ
    value = source.get(ENV_GATE)
    if not isinstance(value, str):
        return False
    return value == _ENABLED_VALUE


# ---------------------------------------------------------------------------
# Internal: read generated_seed.jsonl
# ---------------------------------------------------------------------------


def _read_generated_seed(
    path: Path,
) -> tuple[str, list[dict[str, Any]]]:
    """Return ``("ok", rows)``, ``("absent", [])``, or
    ``("malformed", [])``. Never raises.

    Rows are filtered to those whose key-set matches A18b's
    closed ``GENERATED_RECORD_KEYS`` exactly; any line that fails
    A18b's closed-schema shape triggers a full-file default-deny
    (``malformed``)."""
    if not path.is_file():
        return ("absent", [])
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ("malformed", [])
    out: list[dict[str, Any]] = []
    expected_keys = set(a18b.GENERATED_RECORD_KEYS)
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except ValueError:
            return ("malformed", [])
        if not isinstance(obj, dict):
            return ("malformed", [])
        if set(obj.keys()) != expected_keys:
            return ("malformed", [])
        out.append(obj)
    return ("ok", out)


# ---------------------------------------------------------------------------
# Internal: read prior per-day count
# ---------------------------------------------------------------------------


def _read_prior_today_total(
    prior_path: Path,
    *,
    today_utc_prefix: str,
) -> int:
    """Read the prior A18c ``latest.json`` snapshot (if any) and
    return ``counts.total`` only when its ``generated_at_utc``
    starts with ``today_utc_prefix``. Returns 0 on any error /
    missing / different-day / malformed."""
    if not prior_path.is_file():
        return 0
    try:
        text = prior_path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, ValueError):
        return 0
    if not isinstance(data, dict):
        return 0
    prior_ts = data.get("generated_at_utc")
    if not isinstance(prior_ts, str) or not prior_ts.startswith(
        today_utc_prefix
    ):
        return 0
    counts = data.get("counts")
    if not isinstance(counts, dict):
        return 0
    total = counts.get("total")
    if not isinstance(total, int) or total < 0:
        return 0
    return total


# ---------------------------------------------------------------------------
# A17 row synthesis + projection
# ---------------------------------------------------------------------------


def _a18c_candidate_id(generated_candidate_id: str, evidence_hash: str) -> str:
    """Deterministic A18c candidate-id. The hash short prefix is
    capped at 16 chars; the full hash stays in the projected row's
    `evidence_hash` field for forensic traceability."""
    hash_prefix = ""
    if isinstance(evidence_hash, str):
        hash_prefix = evidence_hash[:16]
    return f"a18c-{generated_candidate_id}-{hash_prefix}"


def _synth_a17_upstream(
    a18b_row: dict[str, Any],
    *,
    a18c_candidate_id: str,
) -> dict[str, Any]:
    """Build an A17-shaped upstream row from an A18b record. The
    shape mirrors what A17's `evaluate_promotion_record` reads;
    every field is conservative by default so the projection
    defaults to `needs_human` in this first cut."""
    requires_op_go = bool(a18b_row.get("would_require_operator_go"))
    return {
        "candidate_id": a18c_candidate_id,
        "title": str(a18b_row.get("proposed_title") or ""),
        "source_document": str(a18b.GENERATED_SEED_PATH),
        "source_kind": "generated_seed_lane",
        "roadmap_phase": "",
        "candidate_kind": str(a18b_row.get("proposed_kind") or ""),
        "required_agent_role": (
            "operator" if requires_op_go else ""
        ),
        # Conservative default: UNKNOWN forces A17 rule #9 →
        # needs_human. A future Phase-5 promotion rule may
        # override this for explicitly authorised rows.
        "risk_level": ea.RISK_UNKNOWN,
        "target_path": "",
        "upstream_intake_status": "generated_seed_present",
        # Not "eligible" → A17 rule #7 fires.
        "decision_state": "needs_human",
        # Both upstream and reclassified are NEEDS_HUMAN by
        # default → A17 rule #4 fires.
        "upstream_execution_authority_decision": ea.DECISION_NEEDS_HUMAN,
        "reclassified_execution_authority_decision": (
            ea.DECISION_NEEDS_HUMAN
        ),
        "classification_drift": False,
        # human_needed=True when would_require_operator_go=True
        # → A17 rule #5 fires deterministically.
        "human_needed": requires_op_go,
        "human_needed_reason": (
            "would_require_operator_go" if requires_op_go else ""
        ),
        # A18c's first cut does NOT cross-reference seed/delegation
        # presence; A17's `already_in_*` fields would require an
        # additional read of seed.jsonl/delegation_seed.jsonl which
        # is out of scope for the default-disabled posture.
        "already_in_seed_jsonl": False,
        "already_in_delegation_seed": False,
    }


def _build_a18c_row(
    a18b_row: dict[str, Any],
    *,
    evaluated_at: str,
) -> dict[str, Any]:
    """Build a single A18c admission row (matches A17's
    ADMISSION_SCHEMA_KEYS verbatim).

    Calls A17's public `evaluate_promotion_record` and applies
    a defense-in-depth force: any row with A18b's
    `would_require_operator_go=True` whose A17 decision came
    back `admissible` is rewritten to `needs_human`."""
    requires_op_go = bool(a18b_row.get("would_require_operator_go"))
    a18c_id = _a18c_candidate_id(
        str(a18b_row.get("generated_candidate_id") or ""),
        str(a18b_row.get("evidence_hash") or ""),
    )
    synth = _synth_a17_upstream(a18b_row, a18c_candidate_id=a18c_id)
    decision, reason = a17.evaluate_promotion_record(synth)

    # ---- Defense-in-depth: would_require_operator_go=True
    #      can NEVER be admissible, even if A17's policy table
    #      ever changes upstream.
    if requires_op_go and decision == "admissible":
        decision = "needs_human"
        reason = "needs_human_authority_decision"

    row: dict[str, Any] = {
        "candidate_id": synth["candidate_id"],
        "title": synth["title"],
        "source_document": synth["source_document"],
        "source_kind": synth["source_kind"],
        "roadmap_phase": synth["roadmap_phase"],
        "candidate_kind": synth["candidate_kind"],
        "required_agent_role": synth["required_agent_role"],
        "risk_level": synth["risk_level"],
        "target_path": synth["target_path"],
        "upstream_intake_status": synth["upstream_intake_status"],
        "upstream_decision_state": synth["decision_state"],
        "upstream_execution_authority_decision": (
            synth["upstream_execution_authority_decision"]
        ),
        "reclassified_execution_authority_decision": (
            synth["reclassified_execution_authority_decision"]
        ),
        "classification_drift": synth["classification_drift"],
        "human_needed": synth["human_needed"],
        "human_needed_reason": synth["human_needed_reason"],
        "admission_decision": decision,
        "admission_reason": reason,
        "would_target_lane": (
            "development_work_queue"
            if decision == "admissible"
            else "none"
        ),
        "already_in_seed_jsonl": synth["already_in_seed_jsonl"],
        "already_in_delegation_seed": synth["already_in_delegation_seed"],
        "policy_version": a17.POLICY_VERSION,
        "evaluated_at": evaluated_at,
    }
    # Closed-schema invariant: every key in A17's
    # ADMISSION_SCHEMA_KEYS must be present.
    assert set(row.keys()) == set(a17.ADMISSION_SCHEMA_KEYS), (
        "A18c row key-set drift versus A17 ADMISSION_SCHEMA_KEYS: "
        f"{sorted(row.keys())!r} vs {sorted(a17.ADMISSION_SCHEMA_KEYS)!r}"
    )
    return row


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _empty_counts() -> dict[str, Any]:
    counts: dict[str, Any] = {
        "total": 0,
        "admissible": 0,
        "needs_human": 0,
        "blocked": 0,
        "duplicate_of_existing": 0,
        "not_eligible_upstream": 0,
        "by_admission_decision": {d: 0 for d in a17.ADMISSION_DECISIONS},
        "by_admission_reason": {r: 0 for r in a17.ADMISSION_REASONS},
        "by_promotion_target": {t: 0 for t in a17.PROMOTION_TARGETS},
    }
    return counts


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
        target = r.get("would_target_lane")
        if target in counts["by_promotion_target"]:
            counts["by_promotion_target"][target] += 1
    return counts


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def _build_envelope(
    *,
    enabled: bool,
    generated_seed_path: Path,
    rows: list[dict[str, Any]],
    note: str,
    warnings: list[str],
    generated_at_utc: str,
) -> dict[str, Any]:
    """Build the closed-schema envelope. Always carries the
    discipline invariants."""
    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "enabled": enabled,
        "env_gate_name": ENV_GATE,
        "generated_seed_path": str(generated_seed_path),
        "rows": rows,
        "counts": _aggregate_counts(rows),
        "note": note,
        "validation_warnings": list(warnings),
        "vocabularies": {
            "notes": list(NOTES),
            "warnings": list(WARNINGS),
            "admission_decisions": list(a17.ADMISSION_DECISIONS),
            "admission_reasons": list(a17.ADMISSION_REASONS),
            "promotion_targets": list(a17.PROMOTION_TARGETS),
        },
        "policy_version": a17.POLICY_VERSION,
        "a18b_writer_module_version": a18b.MODULE_VERSION,
        "per_tick_cap": PER_TICK_CAP,
        "per_day_cap": PER_DAY_CAP,
        "step5_implementation_allowed": step5_implementation_allowed,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "level6_enabled": False,
        "dry_run_only": True,
        "live_merge_implemented": False,
        "deploy_coupled": False,
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
    }
    # Defense in depth: scrub the envelope before write.
    assert_no_secrets(snapshot)
    return snapshot


def collect_snapshot(
    *,
    env: Mapping[str, str] | None = None,
    generated_seed_path: Path | None = None,
    prior_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the A18c projection snapshot. Default-disabled — when
    the env-gate is off, returns immediately without reading any
    seed file."""
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()
    seed_path = (
        generated_seed_path
        if generated_seed_path is not None
        else a18b.GENERATED_SEED_PATH
    )
    prior_path = (
        prior_artifact_path
        if prior_artifact_path is not None
        else ARTIFACT_LATEST
    )

    enabled = env_enabled(env)

    if not enabled:
        # ENV-OFF PATH: no file read, no projection, no error.
        return _build_envelope(
            enabled=False,
            generated_seed_path=seed_path,
            rows=[],
            note="env_gate_off",
            warnings=["env_gate_off_no_op"],
            generated_at_utc=ts,
        )

    # ---- Env enabled: read generated_seed.jsonl ----
    read_status, a18b_rows = _read_generated_seed(seed_path)

    if read_status == "absent":
        return _build_envelope(
            enabled=True,
            generated_seed_path=seed_path,
            rows=[],
            note="generated_seed_absent",
            warnings=["generated_seed_absent"],
            generated_at_utc=ts,
        )

    if read_status == "malformed":
        return _build_envelope(
            enabled=True,
            generated_seed_path=seed_path,
            rows=[],
            note="generated_seed_malformed",
            warnings=["generated_seed_malformed"],
            generated_at_utc=ts,
        )

    # ---- Per-day cap: read prior latest.json (best-effort) ----
    today_prefix = _utc_date_prefix(ts)
    prior_today = _read_prior_today_total(
        prior_path, today_utc_prefix=today_prefix
    )
    per_day_remaining = max(0, PER_DAY_CAP - prior_today)

    warnings: list[str] = []

    # ---- Per-tick cap ----
    pre_cap_count = len(a18b_rows)
    if pre_cap_count > PER_TICK_CAP:
        a18b_rows = a18b_rows[:PER_TICK_CAP]
        warnings.append("per_tick_cap_reached")

    # ---- Per-day cap (binding limit after per-tick) ----
    if len(a18b_rows) > per_day_remaining:
        a18b_rows = a18b_rows[:per_day_remaining]
        warnings.append("per_day_cap_reached")

    # ---- Project each row through A17 (with idempotency + dedup) ----
    rows: list[dict[str, Any]] = []
    seen_candidate_ids: set[str] = set()
    seen_evidence_hashes: dict[str, str] = {}

    for a18b_row in a18b_rows:
        gen_id = str(a18b_row.get("generated_candidate_id") or "")
        ev_hash = str(a18b_row.get("evidence_hash") or "")
        a18c_id = _a18c_candidate_id(gen_id, ev_hash)

        # Hard suppress duplicates within the same tick (defense
        # in depth against an unusual A18b file shape).
        if a18c_id in seen_candidate_ids:
            continue
        seen_candidate_ids.add(a18c_id)

        # Soft warning on duplicate evidence_hash with a different
        # generated_candidate_id (mirrors A18b's pattern).
        if ev_hash and ev_hash in seen_evidence_hashes and (
            seen_evidence_hashes[ev_hash] != gen_id
        ):
            if "duplicate_evidence_hash_in_a18b" not in warnings:
                warnings.append("duplicate_evidence_hash_in_a18b")
        seen_evidence_hashes.setdefault(ev_hash, gen_id)

        rows.append(_build_a18c_row(a18b_row, evaluated_at=ts))

    note = "candidates_projected" if rows else "no_eligible_a18b_rows"

    return _build_envelope(
        enabled=True,
        generated_seed_path=seed_path,
        rows=rows,
        note=note,
        warnings=warnings,
        generated_at_utc=ts,
    )


# ---------------------------------------------------------------------------
# Atomic write (sentinel-restricted)
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "development_generated_lane_a18c._atomic_write_json refuses "
            f"non-a18c-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_generated_lane_a18c.",
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
    ``logs/development_generated_lane_a18c/latest.json``.
    Sentinel-restricted via :func:`_atomic_write_json`."""
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.development_generated_lane_a18c",
        description=(
            "A18c admission projector — default-disabled, env-gated. "
            "Reads generated_seed.jsonl only when "
            "ADE_GENERATED_LANE_A18C_ENABLED=true (exact match); "
            "otherwise emits a no-op envelope without reading the "
            "seed file. NEVER admits, executes, merges, deploys, "
            "or mutates upstream state. A17 remains authoritative."
        ),
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist "
            "logs/development_generated_lane_a18c/latest.json "
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
