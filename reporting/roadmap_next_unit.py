"""A20e — Deterministic Next-Buildable-Unit Selector (read-only).

Pure stdlib-only read-only consumer of the A20b implementation-unit
projection, the A20c unit-authority projection, and the optional
A21a dynamic unit-status ledger. Emits a deterministic projection
at ``logs/roadmap_next_unit/latest.json`` that names the single
``NextBuildableUnitSelection`` (or no selection at all if no unit
is eligible) and the full filterable candidate list.

A21a integration (Step 5 / A21 foundation):

* When ``logs/roadmap_unit_status/latest.json`` is present, the
  selector overlays the dynamic ledger on top of the A20b static
  status: a unit marked ``merged`` in the dynamic ledger is treated
  as ``merged`` for buildable purposes, even if A20b's seed still
  says ``not_started``. This removes the need for a manual A20b
  seed-status PR after every merge.
* Dynamic ledger absence is silent: every unit falls back to its
  A20b static status. Dynamic ledger top-level malformedness fails
  closed with ``UPSTREAM_UNAVAILABLE``. Per-record invalidity
  surfaces as the new ``invalid_dynamic_status`` block reason for
  the affected unit.
* The selector still does not execute work, does not create
  branches, does not open PRs, does not merge or deploy. Step 5
  implementation remains BLOCKED.

A20e MUST NOT:

* execute work;
* create branches;
* open PRs;
* run tests or governance lint;
* merge or deploy anything;
* mutate any approval inbox, seed JSONL, queue, or upstream
  artefact;
* call the canonical ``execution_authority`` classifier (A20c is
  the only authority surface);
* activate Step 5 or Level 6 or grant N5b production-merge
  authority;
* grant runtime / trading / paper / shadow / live authority.

A20e MAY:

* read ``logs/roadmap_task_units/latest.json`` (A20b output);
* read ``logs/roadmap_unit_authority/latest.json`` (A20c output);
* read ``logs/roadmap_unit_status/latest.json`` (A21a output;
  optional);
* apply deterministic filter + sort rules pinned by tests;
* emit a sorted candidates[] list and at most one selected unit;
* fail closed loudly with ``selection_status`` in a closed enum
  and ``fail_closed = true`` on any ambiguity.

Selection rules (pinned by tests):

1. A unit is **BLOCKED** when:
   - the A20b ``status`` is not in ``{"not_started", "ready"}``
     (non-buildable status);
   - no matching A20c authority decision exists;
   - more than one matching A20c authority decision exists
     (defence in depth);
   - the A20c ``final_authority_class`` is
     ``"PERMANENTLY_DENIED"``;
   - the A20c ``final_authority_class`` is not in
     ``{"AUTO_ALLOWED", "NEEDS_HUMAN"}``;
   - any prerequisite is unknown (no unit by that id), or any
     prerequisite has ``status != "merged"``.
2. A unit is **NEEDS_HUMAN_GATED** when:
   - it is not BLOCKED, and
   - ``final_authority_class == "NEEDS_HUMAN"`` or
     ``operator_gate != "none"``.
3. A unit is **ELIGIBLE** when it is neither BLOCKED nor
   NEEDS_HUMAN_GATED — i.e. ``AUTO_ALLOWED`` + ``operator_gate ==
   "none"``.

Selection prefers ``ELIGIBLE`` over ``NEEDS_HUMAN_GATED``. Ties
within a tier are broken by the deterministic sort key:

1. Roadmap phase order: v3.15.16, v3.15.17, …, v3.15.20,
   addendum_1, addendum_2, addendum_3.
2. Authority order: AUTO_ALLOWED before NEEDS_HUMAN.
3. Risk order: LOW before MEDIUM before HIGH before UNKNOWN.
4. Operator gate order: none before operator_go_required before
   governance_bootstrap_pr_required.
5. Implementation-unit id lex order.

There are no hidden heuristics, no random ordering, and no
timestamps anywhere except ``generated_at_utc``.

CLI::

    python -m reporting.roadmap_next_unit
    python -m reporting.roadmap_next_unit --no-write
    python -m reporting.roadmap_next_unit --status
    python -m reporting.roadmap_next_unit --indent 2
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

from reporting import roadmap_task_units as rtu
from reporting import roadmap_unit_authority as rua
from reporting import roadmap_unit_status as rus

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A20e"
REPORT_KIND: Final[str] = "roadmap_next_unit"


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants (Final constants — never flipped at runtime)
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Selection-status vocabulary. Exactly seven values.
NEXT_UNIT_SELECTION_STATUS: Final[tuple[str, ...]] = (
    "OK_SELECTED",
    "ALL_NEEDS_HUMAN_GATED",
    "NO_ELIGIBLE_UNITS",
    "ALL_PERMANENTLY_DENIED",
    "ALL_BLOCKED_BY_PREREQUISITES",
    "UPSTREAM_UNAVAILABLE",
    "FAIL_CLOSED_INVARIANT",
)

#: Closed per-candidate block-reason vocabulary.
NEXT_UNIT_BLOCK_REASON: Final[tuple[str, ...]] = (
    "missing_unit_artifact",
    "missing_authority_artifact",
    "unknown_unit_status",
    "non_buildable_status",
    "permanently_denied_authority",
    "unknown_authority",
    "missing_authority_decision",
    "duplicate_authority_decision",
    "unsatisfied_prerequisite",
    "unknown_prerequisite_target",
    "operator_gate_required",
    "fail_closed_unknown_evidence",
    "invalid_dynamic_status",
    "dynamic_status_terminal",
)

#: Per-candidate eligibility vocabulary.
NEXT_UNIT_ELIGIBILITY: Final[tuple[str, ...]] = (
    "ELIGIBLE",
    "NEEDS_HUMAN_GATED",
    "BLOCKED",
)

#: Closed source-artifact vocabulary. Three upstreams: A20b units,
#: A20c authority, and the optional A21a dynamic status ledger.
NEXT_UNIT_SOURCE: Final[tuple[str, ...]] = (
    "logs/roadmap_task_units/latest.json",
    "logs/roadmap_unit_authority/latest.json",
    "logs/roadmap_unit_status/latest.json",
)

#: Closed dynamic-status overlay-source vocabulary surfaced on
#: each candidate. ``""`` denotes no dynamic record exists for
#: that unit (selector falls back to the A20b static status).
NEXT_UNIT_DYNAMIC_STATUS_SOURCE: Final[tuple[str, ...]] = (
    "",
    "pr_merge",
    "operator_override",
    "loop_state",
    "ci_failure",
    "operator_block",
)

#: Selector-mode vocabulary. Today exactly one mode: ``default``
#: (deterministic phase order). Future modes may be added under
#: separate operator-go PRs.
NEXT_UNIT_SELECTOR_MODE: Final[tuple[str, ...]] = ("default",)


# ---------------------------------------------------------------------------
# Pinned deterministic orderings
# ---------------------------------------------------------------------------

#: Roadmap-phase order as defined by A20a/A20b.
_PHASE_ORDER: Final[tuple[str, ...]] = (
    "v3.15.16",
    "v3.15.17",
    "v3.15.18",
    "v3.15.19",
    "v3.15.20",
    "addendum_1",
    "addendum_2",
    "addendum_3",
)

#: Authority priority: AUTO_ALLOWED before NEEDS_HUMAN.
#: ``PERMANENTLY_DENIED`` is never used in the sort key because
#: such units are BLOCKED and never reach the eligible tier.
_AUTHORITY_ORDER: Final[tuple[str, ...]] = (
    "AUTO_ALLOWED",
    "NEEDS_HUMAN",
)

#: Risk priority: LOW before MEDIUM before HIGH; UNKNOWN last.
_RISK_ORDER: Final[tuple[str, ...]] = (
    "LOW",
    "MEDIUM",
    "HIGH",
    "UNKNOWN",
)

#: Operator-gate priority: none before operator_go_required before
#: governance_bootstrap_pr_required.
_OPERATOR_GATE_ORDER: Final[tuple[str, ...]] = (
    "none",
    "operator_go_required",
    "governance_bootstrap_pr_required",
)

#: A unit's A20b status is **buildable** when it is in this closed
#: set. Other A20b status values (``in_flight``, ``merged``,
#: ``blocked``, ``human_needed``, ``permanently_denied``) keep the
#: unit out of the candidate pool.
_BUILDABLE_STATUS: Final[frozenset[str]] = frozenset({"not_started", "ready"})


# ---------------------------------------------------------------------------
# Schema field tuples (exact, ordered)
# ---------------------------------------------------------------------------

#: Per-candidate schema.
NEXT_BUILDABLE_UNIT_CANDIDATE_FIELDS: Final[tuple[str, ...]] = (
    "implementation_unit_id",
    "roadmap_task_id",
    "phase",
    "title",
    "status",
    "effective_status",
    "dynamic_status_source",
    "risk_class",
    "final_authority_class",
    "operator_gate",
    "prerequisites",
    "prerequisites_satisfied",
    "eligibility",
    "block_reasons",
    "deterministic_sort_key",
    "source_units_artifact",
    "source_authority_artifact",
    "source_status_artifact",
)

#: Selection record schema.
NEXT_BUILDABLE_UNIT_SELECTION_FIELDS: Final[tuple[str, ...]] = (
    "selected_unit_id",
    "selected_roadmap_task_id",
    "selected_phase",
    "selected_title",
    "selection_status",
    "selection_reason",
    "selected_authority_class",
    "selected_risk_class",
    "selected_operator_gate",
    "requires_operator_go",
    "deterministic_sort_key",
    "candidate_count",
    "eligible_candidate_count",
    "blocked_candidate_count",
    "fail_closed",
)

#: Top-level projection schema.
NEXT_BUILDABLE_UNIT_PROJECTION_FIELDS: Final[tuple[str, ...]] = (
    "generated_at_utc",
    "schema_version",
    "module_version",
    "source_units_schema_version",
    "source_authority_schema_version",
    "source_status_schema_version",
    "selector_mode",
    "candidates",
    "selection",
    "selector_invariants",
)


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

MAX_TITLE_LEN: Final[int] = 200
MAX_REASON_LEN: Final[int] = 80
MAX_CANDIDATES: Final[int] = 256
MAX_BLOCK_REASONS_PER_CANDIDATE: Final[int] = 8


# ---------------------------------------------------------------------------
# Artefact paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "roadmap_next_unit"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = "logs/roadmap_next_unit/latest.json"

#: Atomic-write allowlist (POSIX substring). Any write target whose
#: path does not contain this substring is refused with
#: ``ValueError``.
_WRITE_PREFIX: Final[str] = "logs/roadmap_next_unit/"

#: Upstream relative paths.
_UNITS_REL_PATH: Final[str] = "logs/roadmap_task_units/latest.json"
_AUTHORITY_REL_PATH: Final[str] = "logs/roadmap_unit_authority/latest.json"
_STATUS_REL_PATH: Final[str] = "logs/roadmap_unit_status/latest.json"


# ---------------------------------------------------------------------------
# Selector invariants emitted on every projection
# ---------------------------------------------------------------------------

_BASE_SELECTOR_INVARIANTS: Final[dict[str, bool]] = {
    "deterministic_selection": True,
    "no_random_ordering": True,
    "no_llm_judgment": True,
    "no_fuzzy_parsing": True,
    "no_work_execution": True,
    "no_branch_creation": True,
    "no_pr_creation": True,
    "no_merge_or_deploy": True,
    "no_mutation_routes": True,
    "no_approval_buttons": True,
    "no_runtime_trading_authority": True,
    "no_step5_runtime": True,
    "no_level6": True,
    "no_production_merge_authority": True,
    "step5_implementation_allowed": False,
    "mutates_a20b_artifact": False,
    "mutates_a20c_artifact": False,
    "writes_only_roadmap_next_unit_log": True,
    "writes_to_seed_jsonl": False,
    "writes_to_delegation_seed_jsonl": False,
    "writes_to_generated_seed_jsonl": False,
    "calls_llm_or_external_api": False,
    "uses_subprocess_or_network": False,
    "calls_execution_authority_classifier": False,  # A20c is the only classifier call site
    "fail_closed_on_unknown_evidence": True,
    "fail_closed_on_duplicate_authority": True,
    "fail_closed_on_missing_artifact": True,
    "permanently_denied_units_never_selected": True,
    "needs_human_units_require_operator_go": True,
    "consumes_dynamic_status_ledger": True,
    "dynamic_status_overrides_static_when_valid": True,
    "fail_closed_on_invalid_dynamic_status": True,
    "fail_closed_on_duplicate_dynamic_status": True,
    "dynamic_status_absence_falls_back_to_static": True,
    "merged_units_never_reselected": True,
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


def _bounded_str(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    if len(value) <= max_len:
        return value
    return value[:max_len]


def _order_index(value: Any, ordering: tuple[str, ...]) -> int:
    """Return the index of ``value`` in ``ordering``, or
    ``len(ordering)`` for unknown values (sorts last)."""
    if not isinstance(value, str):
        return len(ordering)
    try:
        return ordering.index(value)
    except ValueError:
        return len(ordering)


def _load_json_artifact(
    path: Path,
) -> tuple[str, dict[str, Any] | None, str | None]:
    """Best-effort JSON read. Returns ``(status, payload, error)``
    where ``status ∈ {"ok", "absent", "malformed"}``. Never raises.
    """
    if not path.is_file():
        return ("absent", None, None)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return ("malformed", None, _bounded_str(repr(exc), MAX_REASON_LEN))
    try:
        payload = json.loads(text)
    except (TypeError, ValueError) as exc:
        return ("malformed", None, _bounded_str(str(exc), MAX_REASON_LEN))
    if not isinstance(payload, dict):
        return ("malformed", None, "payload_is_not_a_dict")
    return ("ok", payload, None)


# ---------------------------------------------------------------------------
# Candidate construction
# ---------------------------------------------------------------------------


def _build_candidate(
    unit: dict[str, Any],
    *,
    units_by_id: dict[str, dict[str, Any]],
    decisions_by_unit_id: dict[str, list[dict[str, Any]]],
    dynamic_status_by_unit_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build one ``NextBuildableUnitCandidate`` record.

    The dynamic-status overlay (A21a) is applied on top of the
    A20b static status:

    * If a valid dynamic record exists, its status overrides the
      static A20b status for buildable purposes (the static value
      is still emitted on ``status`` for traceability).
    * If a dynamic record exists but is invalid, the candidate is
      blocked with ``invalid_dynamic_status`` (fail-closed).
    * If no dynamic record exists, the candidate falls back to
      A20b's static status (legacy behaviour).
    """
    unit_id = _bounded_str(unit.get("id"), 200)
    task_id = _bounded_str(unit.get("roadmap_task_id"), 200)
    phase = _bounded_str(unit.get("phase"), 64)
    title = _bounded_str(unit.get("title"), MAX_TITLE_LEN)
    status = _bounded_str(unit.get("status"), 32)
    risk_class = _bounded_str(unit.get("risk_class"), 16)
    operator_gate = _bounded_str(unit.get("operator_gate"), 64)
    raw_prereqs = unit.get("prerequisites") or []
    if isinstance(raw_prereqs, list):
        prerequisites = [
            _bounded_str(p, 200) for p in raw_prereqs if isinstance(p, str)
        ]
    else:
        prerequisites = []

    block_reasons: list[str] = []

    # --- A21a dynamic-status overlay --------------------------------------
    dyn_record = dynamic_status_by_unit_id.get(unit_id)
    dyn_status_source = ""
    if dyn_record is None:
        # No dynamic record. Fall back to A20b static status.
        effective_status = status
    else:
        dyn_valid = bool(dyn_record.get("valid"))
        if not dyn_valid:
            # Fail closed: invalid dynamic record blocks the unit.
            block_reasons.append("invalid_dynamic_status")
            effective_status = status
        else:
            dyn_status_raw = _bounded_str(dyn_record.get("status"), 32)
            dyn_source_raw = _bounded_str(dyn_record.get("source"), 64)
            if dyn_status_raw not in rus.DYNAMIC_UNIT_STATUS:
                block_reasons.append("invalid_dynamic_status")
                effective_status = status
            else:
                effective_status = dyn_status_raw
                if dyn_source_raw in rus.DYNAMIC_STATUS_SOURCE:
                    dyn_status_source = dyn_source_raw
                # Surface terminal-dynamic-status as a distinct reason
                # so the operator can see at a glance why a unit no
                # longer appears in the candidate list.
                if dyn_status_raw in {"merged", "blocked", "skipped"}:
                    block_reasons.append("dynamic_status_terminal")

    # --- A20b status check (applied to effective_status) -------------------
    # The unknown-unit-status check still fires only on truly unknown
    # A20b static values; the dynamic overlay extends the valid-status
    # universe but never resurrects an unknown A20b record.
    if status not in rtu.UNIT_STATUS:
        block_reasons.append("unknown_unit_status")
    elif (
        effective_status != status
        and effective_status not in rus.DYNAMIC_UNIT_STATUS
    ):
        block_reasons.append("invalid_dynamic_status")
    elif effective_status not in _BUILDABLE_STATUS:
        # Both static "non_buildable" (e.g. merged in A20b seed) and
        # dynamic-overlay "non_buildable" (e.g. in_progress / pr_open
        # / failed) end up here. ``dynamic_status_terminal`` already
        # covered the explicit terminal case above.
        if "dynamic_status_terminal" not in block_reasons:
            block_reasons.append("non_buildable_status")

    # --- A20c authority lookup --------------------------------------------
    matching = decisions_by_unit_id.get(unit_id, [])
    final_authority_class = ""
    if not matching:
        block_reasons.append("missing_authority_decision")
    elif len(matching) > 1:
        block_reasons.append("duplicate_authority_decision")
    else:
        decision = matching[0]
        final_authority_class = _bounded_str(
            decision.get("final_authority_class"), 32
        )
        if final_authority_class == "PERMANENTLY_DENIED":
            block_reasons.append("permanently_denied_authority")
        elif final_authority_class not in _AUTHORITY_ORDER:
            # Unknown / missing / fail-safe value.
            block_reasons.append("unknown_authority")

    # --- Prerequisite check ------------------------------------------------
    # A prerequisite is "satisfied" when its effective status is
    # ``merged`` — either via the A20b static seed or via a valid
    # A21a dynamic ledger record. This is what makes the dynamic
    # overlay useful: a prereq merged through the ledger no longer
    # requires editing the A20b static seed.
    prereqs_satisfied = True
    if prerequisites:
        for prereq_id in prerequisites:
            prereq_unit = units_by_id.get(prereq_id)
            if prereq_unit is None:
                if "unknown_prerequisite_target" not in block_reasons:
                    block_reasons.append("unknown_prerequisite_target")
                prereqs_satisfied = False
                continue
            prereq_static = prereq_unit.get("status")
            prereq_dyn = dynamic_status_by_unit_id.get(prereq_id)
            prereq_effective = prereq_static
            if (
                prereq_dyn is not None
                and prereq_dyn.get("valid")
                and prereq_dyn.get("status") in rus.DYNAMIC_UNIT_STATUS
            ):
                prereq_effective = prereq_dyn["status"]
            if prereq_effective != "merged":
                if "unsatisfied_prerequisite" not in block_reasons:
                    block_reasons.append("unsatisfied_prerequisite")
                prereqs_satisfied = False

    # --- Eligibility -------------------------------------------------------
    if block_reasons:
        eligibility = "BLOCKED"
    elif (
        final_authority_class == "NEEDS_HUMAN"
        or operator_gate != "none"
    ):
        eligibility = "NEEDS_HUMAN_GATED"
        # Annotate the gate reason as a non-blocking note (does not
        # appear in block_reasons because the unit is not BLOCKED).
    else:
        eligibility = "ELIGIBLE"

    # --- Deterministic sort key -------------------------------------------
    # The eligibility tier (ELIGIBLE first, then NEEDS_HUMAN_GATED,
    # then BLOCKED) is applied at selection time, not in this key.
    # This key gives a fully deterministic intra-tier ordering.
    sort_key: list[Any] = [
        _order_index(phase, _PHASE_ORDER),
        _order_index(final_authority_class, _AUTHORITY_ORDER),
        _order_index(risk_class, _RISK_ORDER),
        _order_index(operator_gate, _OPERATOR_GATE_ORDER),
        unit_id,
    ]

    # Bound the block-reasons list.
    bounded_block_reasons = block_reasons[:MAX_BLOCK_REASONS_PER_CANDIDATE]
    # Defensive: every block reason must be in the closed vocab.
    bounded_block_reasons = [
        r for r in bounded_block_reasons if r in NEXT_UNIT_BLOCK_REASON
    ]

    return {
        "implementation_unit_id": unit_id,
        "roadmap_task_id": task_id,
        "phase": phase,
        "title": title,
        "status": status,
        "effective_status": effective_status,
        "dynamic_status_source": dyn_status_source,
        "risk_class": risk_class,
        "final_authority_class": final_authority_class,
        "operator_gate": operator_gate,
        "prerequisites": list(prerequisites),
        "prerequisites_satisfied": prereqs_satisfied,
        "eligibility": eligibility,
        "block_reasons": bounded_block_reasons,
        "deterministic_sort_key": sort_key,
        "source_units_artifact": _UNITS_REL_PATH,
        "source_authority_artifact": _AUTHORITY_REL_PATH,
        "source_status_artifact": _STATUS_REL_PATH,
    }


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def _empty_selection(
    *,
    status: str,
    reason: str,
    candidate_count: int,
    eligible_count: int,
    blocked_count: int,
    fail_closed: bool,
) -> dict[str, Any]:
    return {
        "selected_unit_id": "",
        "selected_roadmap_task_id": "",
        "selected_phase": "",
        "selected_title": "",
        "selection_status": status,
        "selection_reason": _bounded_str(reason, MAX_REASON_LEN),
        "selected_authority_class": "",
        "selected_risk_class": "",
        "selected_operator_gate": "",
        "requires_operator_go": False,
        "deterministic_sort_key": [],
        "candidate_count": candidate_count,
        "eligible_candidate_count": eligible_count,
        "blocked_candidate_count": blocked_count,
        "fail_closed": fail_closed,
    }


def _select_from_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(candidates)
    eligible = [c for c in candidates if c["eligibility"] != "BLOCKED"]
    blocked = [c for c in candidates if c["eligibility"] == "BLOCKED"]
    eligible_count = len(eligible)
    blocked_count = len(blocked)

    if total == 0:
        return _empty_selection(
            status="NO_ELIGIBLE_UNITS",
            reason="upstream_returned_zero_units",
            candidate_count=0,
            eligible_count=0,
            blocked_count=0,
            fail_closed=True,
        )

    if not eligible:
        # All blocked. Drill into the dominant reason category.
        reasons: set[str] = set()
        for c in candidates:
            for r in c["block_reasons"]:
                reasons.add(r)
        if reasons == {"permanently_denied_authority"}:
            status = "ALL_PERMANENTLY_DENIED"
            reason_str = "all_units_permanently_denied_by_a20c"
        elif reasons and reasons.issubset(
            {"unsatisfied_prerequisite", "unknown_prerequisite_target"}
        ):
            status = "ALL_BLOCKED_BY_PREREQUISITES"
            reason_str = "all_units_blocked_by_unresolved_prerequisites"
        elif reasons & {
            "duplicate_authority_decision",
            "unknown_authority",
            "missing_authority_decision",
            "unknown_unit_status",
            "fail_closed_unknown_evidence",
            "invalid_dynamic_status",
        }:
            status = "FAIL_CLOSED_INVARIANT"
            reason_str = "fail_closed_on_unknown_or_duplicate_evidence"
        else:
            status = "NO_ELIGIBLE_UNITS"
            reason_str = "no_buildable_unit_among_candidates"
        return _empty_selection(
            status=status,
            reason=reason_str,
            candidate_count=total,
            eligible_count=0,
            blocked_count=blocked_count,
            fail_closed=True,
        )

    # Have eligible — prefer ELIGIBLE over NEEDS_HUMAN_GATED.
    # The candidates list is already sorted by deterministic_sort_key
    # ascending; partition stably to preserve intra-tier order.
    pure_eligible = [c for c in eligible if c["eligibility"] == "ELIGIBLE"]
    gated_eligible = [
        c for c in eligible if c["eligibility"] == "NEEDS_HUMAN_GATED"
    ]

    if pure_eligible:
        selected = pure_eligible[0]
        status = "OK_SELECTED"
        reason_str = "auto_allowed_candidate_selected_by_deterministic_sort"
    else:
        # Every eligible candidate needs operator-go. Still
        # deterministic; still read-only; still no execution.
        selected = gated_eligible[0]
        status = "ALL_NEEDS_HUMAN_GATED"
        reason_str = "all_eligible_candidates_require_operator_go"

    requires_go = bool(
        selected["final_authority_class"] == "NEEDS_HUMAN"
        or selected["operator_gate"] != "none"
    )

    return {
        "selected_unit_id": selected["implementation_unit_id"],
        "selected_roadmap_task_id": selected["roadmap_task_id"],
        "selected_phase": selected["phase"],
        "selected_title": selected["title"],
        "selection_status": status,
        "selection_reason": _bounded_str(reason_str, MAX_REASON_LEN),
        "selected_authority_class": selected["final_authority_class"],
        "selected_risk_class": selected["risk_class"],
        "selected_operator_gate": selected["operator_gate"],
        "requires_operator_go": requires_go,
        "deterministic_sort_key": list(selected["deterministic_sort_key"]),
        "candidate_count": total,
        "eligible_candidate_count": eligible_count,
        "blocked_candidate_count": blocked_count,
        "fail_closed": False,
    }


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    repo_root: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic next-buildable-unit projection.

    Reads ``logs/roadmap_task_units/latest.json``,
    ``logs/roadmap_unit_authority/latest.json``, and (optionally)
    ``logs/roadmap_unit_status/latest.json`` from disk. Fails closed
    if A20b or A20c is absent or malformed. The A21a dynamic-status
    artefact is optional: absence is silent (legacy fallback);
    top-level malformedness fails closed UPSTREAM_UNAVAILABLE.
    """
    root = repo_root if repo_root is not None else REPO_ROOT
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    units_status, units_payload, units_err = _load_json_artifact(
        root / _UNITS_REL_PATH
    )
    auth_status, auth_payload, auth_err = _load_json_artifact(
        root / _AUTHORITY_REL_PATH
    )
    status_status, status_payload, status_err = _load_json_artifact(
        root / _STATUS_REL_PATH
    )

    units_schema_version: str | int = ""
    auth_schema_version: str | int = ""
    status_schema_version: str | int = ""

    if units_status != "ok" or auth_status != "ok":
        # Fail closed loudly. Record the missing artefact in
        # selection_reason; selection_status carries the closed-vocab
        # signal.
        if units_status != "ok":
            block_reason = "missing_unit_artifact"
            err_detail = units_err or units_status
        else:
            block_reason = "missing_authority_artifact"
            err_detail = auth_err or auth_status
        selection = _empty_selection(
            status="UPSTREAM_UNAVAILABLE",
            reason=f"{block_reason}:{err_detail}",
            candidate_count=0,
            eligible_count=0,
            blocked_count=0,
            fail_closed=True,
        )
        return _envelope(
            ts=ts,
            units_schema_version=units_schema_version,
            auth_schema_version=auth_schema_version,
            status_schema_version=status_schema_version,
            candidates=[],
            selection=selection,
        )

    # A21a is optional. Absence => empty mapping, every unit falls
    # back to A20b static status. Top-level malformedness => fail
    # closed (treat as corrupt upstream).
    if status_status == "malformed":
        selection = _empty_selection(
            status="UPSTREAM_UNAVAILABLE",
            reason=f"malformed_dynamic_status_artifact:{status_err}",
            candidate_count=0,
            eligible_count=0,
            blocked_count=0,
            fail_closed=True,
        )
        return _envelope(
            ts=ts,
            units_schema_version=units_schema_version,
            auth_schema_version=auth_schema_version,
            status_schema_version=status_schema_version,
            candidates=[],
            selection=selection,
        )

    units = units_payload.get("implementation_units") or []
    decisions = auth_payload.get("authority_decisions") or []
    units_schema_version = units_payload.get("schema_version", "")
    auth_schema_version = auth_payload.get("schema_version", "")

    if not isinstance(units, list):
        units = []
    if not isinstance(decisions, list):
        decisions = []

    # Index helpers.
    units_by_id: dict[str, dict[str, Any]] = {}
    for u in units:
        if isinstance(u, dict):
            uid = u.get("id")
            if isinstance(uid, str) and uid:
                units_by_id[uid] = u

    decisions_by_unit_id: dict[str, list[dict[str, Any]]] = {}
    for d in decisions:
        if isinstance(d, dict):
            did = d.get("implementation_unit_id")
            if isinstance(did, str) and did:
                decisions_by_unit_id.setdefault(did, []).append(d)

    # A21a dynamic status overlay (optional).
    dynamic_status_by_unit_id: dict[str, dict[str, Any]] = {}
    if status_status == "ok" and isinstance(status_payload, dict):
        status_schema_version = status_payload.get("schema_version", "")
        ledger_records = status_payload.get("ledger_records") or []
        if isinstance(ledger_records, list):
            for rec in ledger_records:
                if not isinstance(rec, dict):
                    continue
                ruid = rec.get("unit_id")
                if not isinstance(ruid, str) or not ruid:
                    continue
                # Last-wins is fine because the ledger module itself
                # surfaces duplicates as ``valid=False`` for every
                # affected record. Either the existing entry or this
                # one is already invalid; the candidate will block.
                dynamic_status_by_unit_id[ruid] = rec

    # Build candidates.
    candidates: list[dict[str, Any]] = []
    for u in units[:MAX_CANDIDATES]:
        if not isinstance(u, dict):
            continue
        uid = u.get("id")
        if not isinstance(uid, str) or not uid:
            continue
        cand = _build_candidate(
            u,
            units_by_id=units_by_id,
            decisions_by_unit_id=decisions_by_unit_id,
            dynamic_status_by_unit_id=dynamic_status_by_unit_id,
        )
        candidates.append(cand)

    candidates.sort(key=lambda c: tuple(c["deterministic_sort_key"]))

    selection = _select_from_candidates(candidates)

    return _envelope(
        ts=ts,
        units_schema_version=units_schema_version,
        auth_schema_version=auth_schema_version,
        status_schema_version=status_schema_version,
        candidates=candidates,
        selection=selection,
    )


def _envelope(
    *,
    ts: str,
    units_schema_version: str | int,
    auth_schema_version: str | int,
    status_schema_version: str | int,
    candidates: list[dict[str, Any]],
    selection: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "source_units_module_version": rtu.MODULE_VERSION,
        "source_units_schema_version": units_schema_version,
        "source_authority_module_version": rua.MODULE_VERSION,
        "source_authority_schema_version": auth_schema_version,
        "source_status_module_version": rus.MODULE_VERSION,
        "source_status_schema_version": status_schema_version,
        "selector_mode": "default",
        "vocabularies": {
            "next_unit_selection_status": list(NEXT_UNIT_SELECTION_STATUS),
            "next_unit_block_reason": list(NEXT_UNIT_BLOCK_REASON),
            "next_unit_eligibility": list(NEXT_UNIT_ELIGIBILITY),
            "next_unit_source": list(NEXT_UNIT_SOURCE),
            "next_unit_selector_mode": list(NEXT_UNIT_SELECTOR_MODE),
            "next_unit_dynamic_status_source": list(
                NEXT_UNIT_DYNAMIC_STATUS_SOURCE
            ),
            "phase_order": list(_PHASE_ORDER),
            "authority_order": list(_AUTHORITY_ORDER),
            "risk_order": list(_RISK_ORDER),
            "operator_gate_order": list(_OPERATOR_GATE_ORDER),
            "buildable_status": sorted(_BUILDABLE_STATUS),
        },
        "candidates": candidates,
        "selection": selection,
        "selector_invariants": dict(_BASE_SELECTOR_INVARIANTS),
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write ``payload`` as sorted-key indented JSON.
    Refuses any path outside ``logs/roadmap_next_unit/``."""
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix:
        raise ValueError(
            "roadmap_next_unit._atomic_write_json refuses "
            f"non-selector-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".roadmap_next_unit.",
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
    sel = snapshot["selection"]
    inv = snapshot["selector_invariants"]
    cands = snapshot["candidates"]
    lines = [
        f"roadmap_next_unit {snapshot['module_version']} "
        f"schema={snapshot['schema_version']}",
        f"generated_at_utc={snapshot['generated_at_utc']}",
        f"selector_mode={snapshot['selector_mode']}",
        f"candidates={len(cands)} eligible={sel['eligible_candidate_count']} "
        f"blocked={sel['blocked_candidate_count']}",
        f"selection_status={sel['selection_status']}",
        f"selection_reason={sel['selection_reason']}",
        f"selected_unit_id={sel['selected_unit_id']}",
        f"selected_phase={sel['selected_phase']}",
        f"selected_authority_class={sel['selected_authority_class']}",
        f"selected_risk_class={sel['selected_risk_class']}",
        f"selected_operator_gate={sel['selected_operator_gate']}",
        f"requires_operator_go={sel['requires_operator_go']}",
        f"fail_closed={sel['fail_closed']}",
        (
            "no_runtime_trading_authority="
            f"{inv['no_runtime_trading_authority']} "
            f"no_step5_runtime={inv['no_step5_runtime']} "
            f"no_level6={inv['no_level6']} "
            "no_production_merge_authority="
            f"{inv['no_production_merge_authority']}"
        ),
        (
            "no_work_execution="
            f"{inv['no_work_execution']} "
            f"no_branch_creation={inv['no_branch_creation']} "
            f"no_pr_creation={inv['no_pr_creation']} "
            f"no_merge_or_deploy={inv['no_merge_or_deploy']}"
        ),
        (
            "deterministic_selection="
            f"{inv['deterministic_selection']} "
            "permanently_denied_units_never_selected="
            f"{inv['permanently_denied_units_never_selected']}"
        ),
    ]
    for c in cands:
        lines.append(
            f"  cand {c['implementation_unit_id']} phase={c['phase']} "
            f"eligibility={c['eligibility']} "
            f"authority={c['final_authority_class']} "
            f"risk={c['risk_class']} "
            f"gate={c['operator_gate']}"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.roadmap_next_unit",
        description=(
            "A20e Deterministic Next-Buildable-Unit Selector. Read-only "
            "deterministic projection over the A20b unit decomposition "
            "and A20c authority verdicts. Does NOT execute work, "
            "does NOT create branches, does NOT open PRs, does NOT "
            "merge or deploy. Step 5 implementation remains BLOCKED."
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
            "Do not persist logs/roadmap_next_unit/latest.json "
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
