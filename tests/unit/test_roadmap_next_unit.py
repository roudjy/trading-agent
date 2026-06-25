"""Unit tests for A20e — Deterministic Next-Buildable-Unit Selector.

Pins:

* closed vocabularies (NEXT_UNIT_SELECTION_STATUS,
  NEXT_UNIT_BLOCK_REASON, NEXT_UNIT_ELIGIBILITY,
  NEXT_UNIT_SOURCE, NEXT_UNIT_SELECTOR_MODE);
* schema integrity (NextBuildableUnitCandidate,
  NextBuildableUnitSelection, NextBuildableUnitProjection);
* deterministic output with injected ``generated_at_utc``;
* byte-identical output for identical input;
* atomic write only under ``logs/roadmap_next_unit/``;
* ``--no-write`` does not write; ``--status`` does not write;
* missing unit artefact -> UPSTREAM_UNAVAILABLE, fail_closed=True;
* missing authority artefact -> UPSTREAM_UNAVAILABLE,
  fail_closed=True;
* every candidate carries deterministic_sort_key;
* selected candidate is stable across runs;
* PERMANENTLY_DENIED units are never selected;
* unknown authority -> BLOCKED;
* missing authority decision -> BLOCKED;
* duplicate authority decisions -> BLOCKED with
  ``duplicate_authority_decision``;
* missing prerequisite target -> BLOCKED;
* unsatisfied prerequisite (status != "merged") -> BLOCKED;
* satisfied prerequisite (all merged) -> not blocked on that
  account;
* NEEDS_HUMAN units may be selected only as operator-gated
  candidate; ``requires_operator_go`` is True for any selected
  unit whose authority is NEEDS_HUMAN or whose operator_gate is
  not "none";
* the selector never executes work, never creates branches /
  PRs, never merges or deploys;
* selector_invariants pin no Step 5, no Level 6, no production
  merge authority, no runtime/trading authority, no mutation
  routes, no approval buttons;
* no forbidden imports / runtime tokens in module source.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import roadmap_next_unit as rnu
from reporting import roadmap_task_units as rtu
from reporting import roadmap_unit_authority as rua


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_FROZEN_UTC = "2026-05-18T20:00:00Z"


def _baseline_unit(**overrides: Any) -> dict[str, Any]:
    """Synthetic A20b-shape unit. Every field A20e reads is present."""
    base: dict[str, Any] = {
        "id": "syn_unit_a",
        "roadmap_task_id": "phase_v3_15_16",
        "title": "Synthetic eligible unit",
        "phase": "v3.15.16",
        "unit_kind": "reporting_module",
        "target_layer": "reporting",
        "source_requirement_ids": [],
        "expected_files": ["reporting/synthetic.py"],
        "forbidden_files": [],
        "forbidden_surface_reasons": [],
        "required_tests": [],
        "definition_of_done": [],
        "stop_conditions": [],
        "prerequisites": [],
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    }
    base.update(overrides)
    return base


def _baseline_decision(**overrides: Any) -> dict[str, Any]:
    """Synthetic A20c-shape authority decision."""
    base: dict[str, Any] = {
        "implementation_unit_id": "syn_unit_a",
        "roadmap_task_id": "phase_v3_15_16",
        "phase": "v3.15.16",
        "final_authority_class": "AUTO_ALLOWED",
        "max_severity": 0,
        "evidence": [],
        "requires_operator_go": False,
        "permanently_denied": False,
        "deny_reasons": [],
        "classifier_used": True,
        "fail_closed": False,
    }
    base.update(overrides)
    return base


def _write_units_artifact(
    tmp_path: Path, units: list[dict[str, Any]]
) -> Path:
    target = tmp_path / "logs" / "roadmap_task_units" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "module_version": "v3.15.16.A20b",
                "report_kind": "roadmap_task_units",
                "generated_at_utc": "2026-05-18T08:00:00Z",
                "implementation_units": units,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return target


def _write_authority_artifact(
    tmp_path: Path, decisions: list[dict[str, Any]]
) -> Path:
    target = tmp_path / "logs" / "roadmap_unit_authority" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "module_version": "v3.15.16.A20c",
                "report_kind": "roadmap_unit_authority",
                "generated_at_utc": "2026-05-18T08:00:00Z",
                "authority_decisions": decisions,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return target


def _snap(tmp_path: Path) -> dict[str, Any]:
    return rnu.collect_snapshot(
        repo_root=tmp_path, generated_at_utc=_FROZEN_UTC
    )


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_selection_status_vocab_is_closed_exact() -> None:
    assert rnu.NEXT_UNIT_SELECTION_STATUS == (
        "OK_SELECTED",
        "ALL_NEEDS_HUMAN_GATED",
        "NO_ELIGIBLE_UNITS",
        "ALL_PERMANENTLY_DENIED",
        "ALL_BLOCKED_BY_PREREQUISITES",
        "UPSTREAM_UNAVAILABLE",
        "FAIL_CLOSED_INVARIANT",
    )


def test_block_reason_vocab_is_closed_exact() -> None:
    assert rnu.NEXT_UNIT_BLOCK_REASON == (
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


def test_eligibility_vocab_is_closed_exact() -> None:
    assert rnu.NEXT_UNIT_ELIGIBILITY == (
        "ELIGIBLE",
        "NEEDS_HUMAN_GATED",
        "BLOCKED",
    )


def test_source_vocab_is_closed_exact() -> None:
    assert rnu.NEXT_UNIT_SOURCE == (
        "logs/roadmap_task_units/latest.json",
        "logs/roadmap_unit_authority/latest.json",
        "logs/roadmap_unit_status/latest.json",
    )


def test_dynamic_status_source_vocab_is_closed_exact() -> None:
    assert rnu.NEXT_UNIT_DYNAMIC_STATUS_SOURCE == (
        "",
        "pr_merge",
        "operator_override",
        "loop_state",
        "ci_failure",
        "operator_block",
    )


def test_selector_mode_vocab_is_closed_exact() -> None:
    assert rnu.NEXT_UNIT_SELECTOR_MODE == ("default",)


def test_phase_order_matches_a20a_phase_list() -> None:
    """Phase order must include every PHASE value A20b can emit."""
    # A20a defines the canonical phase list. A20b mirrors it via
    # rtu.collect_snapshot()'s catalog cross-reference.
    for phase in (
        "ade_qre_017a",
        "ade_qre_017b",
        "ade_qre_017c",
        "ade_qre_017d",
        "ade_qre_017e",
        "v3.15.16",
        "v3.15.17",
        "v3.15.18",
        "v3.15.19",
        "v3.15.20",
        "addendum_1",
    ):
        assert phase in rnu._PHASE_ORDER


def test_authority_order_does_not_include_permanently_denied() -> None:
    """PERMANENTLY_DENIED is never used as a sort tier; it is a
    block-only verdict and is filtered out before sorting. A22 adds
    STRATEGICALLY_PREAPPROVED between AUTO_ALLOWED and NEEDS_HUMAN."""
    assert "PERMANENTLY_DENIED" not in rnu._AUTHORITY_ORDER
    assert rnu._AUTHORITY_ORDER == (
        "AUTO_ALLOWED",
        "STRATEGICALLY_PREAPPROVED",
        "NEEDS_HUMAN",
    )


def test_risk_order_matches_classifier_enum() -> None:
    assert rnu._RISK_ORDER == ("LOW", "MEDIUM", "HIGH", "UNKNOWN")


def test_operator_gate_order_matches_a20b_enum() -> None:
    assert rnu._OPERATOR_GATE_ORDER == rtu.OPERATOR_GATE


def test_buildable_status_subset_of_a20b_unit_status() -> None:
    for s in rnu._BUILDABLE_STATUS:
        assert s in rtu.UNIT_STATUS


# ---------------------------------------------------------------------------
# Schema integrity
# ---------------------------------------------------------------------------


def test_candidate_field_list_exact() -> None:
    assert rnu.NEXT_BUILDABLE_UNIT_CANDIDATE_FIELDS == (
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


def test_selection_field_list_exact() -> None:
    assert rnu.NEXT_BUILDABLE_UNIT_SELECTION_FIELDS == (
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


def test_projection_field_list_exact() -> None:
    assert rnu.NEXT_BUILDABLE_UNIT_PROJECTION_FIELDS == (
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


def test_every_candidate_has_every_field(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    snap = _snap(tmp_path)
    for c in snap["candidates"]:
        assert set(c.keys()) == set(
            rnu.NEXT_BUILDABLE_UNIT_CANDIDATE_FIELDS
        ), c


def test_selection_has_every_field(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    snap = _snap(tmp_path)
    assert set(snap["selection"].keys()) == set(
        rnu.NEXT_BUILDABLE_UNIT_SELECTION_FIELDS
    )


def test_projection_carries_every_top_level_field(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    snap = _snap(tmp_path)
    for field in rnu.NEXT_BUILDABLE_UNIT_PROJECTION_FIELDS:
        assert field in snap, field


# ---------------------------------------------------------------------------
# Happy path: AUTO_ALLOWED unit gets selected
# ---------------------------------------------------------------------------


def test_auto_allowed_unit_is_selected(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    snap = _snap(tmp_path)
    sel = snap["selection"]
    assert sel["selection_status"] == "OK_SELECTED"
    assert sel["selected_unit_id"] == "syn_unit_a"
    assert sel["selected_authority_class"] == "AUTO_ALLOWED"
    assert sel["requires_operator_go"] is False
    assert sel["fail_closed"] is False


def test_ade_qre_phase_is_preferred_over_legacy_phase(tmp_path: Path) -> None:
    ade_unit = _baseline_unit(
        id="u_ade_qre_017a_maturity_matrix_reporter_001",
        roadmap_task_id="ade_qre_017a_baseline_reconciliation",
        phase="ade_qre_017a",
        title="ADE-QRE-017A baseline unit",
    )
    legacy_unit = _baseline_unit(
        id="u_v3_15_16_legacy",
        roadmap_task_id="phase_v3_15_16",
        phase="v3.15.16",
        title="legacy unit",
    )
    _write_units_artifact(tmp_path, [legacy_unit, ade_unit])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(
                implementation_unit_id=legacy_unit["id"],
                roadmap_task_id=legacy_unit["roadmap_task_id"],
                phase=legacy_unit["phase"],
            ),
            _baseline_decision(
                implementation_unit_id=ade_unit["id"],
                roadmap_task_id=ade_unit["roadmap_task_id"],
                phase=ade_unit["phase"],
            ),
        ],
    )
    snap = _snap(tmp_path)
    assert snap["selection"]["selected_unit_id"] == ade_unit["id"]


def test_eligibility_marker_on_candidate(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    snap = _snap(tmp_path)
    assert snap["candidates"][0]["eligibility"] == "ELIGIBLE"
    assert snap["candidates"][0]["block_reasons"] == []
    assert snap["candidates"][0]["prerequisites_satisfied"] is True


# ---------------------------------------------------------------------------
# PERMANENTLY_DENIED units are never selected
# ---------------------------------------------------------------------------


def test_permanently_denied_unit_is_never_selected(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(
                final_authority_class="PERMANENTLY_DENIED",
                permanently_denied=True,
                deny_reasons=["denied_live_path_modification"],
            )
        ],
    )
    snap = _snap(tmp_path)
    sel = snap["selection"]
    assert sel["selected_unit_id"] == ""
    assert sel["selection_status"] == "ALL_PERMANENTLY_DENIED"
    assert sel["fail_closed"] is True
    assert snap["candidates"][0]["eligibility"] == "BLOCKED"
    assert (
        "permanently_denied_authority"
        in snap["candidates"][0]["block_reasons"]
    )


def test_mixed_pool_picks_auto_allowed_not_denied(tmp_path: Path) -> None:
    """A pool with one PERMANENTLY_DENIED + one AUTO_ALLOWED must
    select the AUTO_ALLOWED unit."""
    auto_unit = _baseline_unit(id="syn_auto", title="auto-allowed unit")
    denied_unit = _baseline_unit(
        id="syn_denied", title="denied unit", phase="v3.15.17"
    )
    _write_units_artifact(tmp_path, [auto_unit, denied_unit])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(implementation_unit_id="syn_auto"),
            _baseline_decision(
                implementation_unit_id="syn_denied",
                phase="v3.15.17",
                final_authority_class="PERMANENTLY_DENIED",
                permanently_denied=True,
                deny_reasons=["denied_live_path_modification"],
            ),
        ],
    )
    snap = _snap(tmp_path)
    assert snap["selection"]["selected_unit_id"] == "syn_auto"


# ---------------------------------------------------------------------------
# Unknown / missing / duplicate authority fail closed
# ---------------------------------------------------------------------------


def test_unknown_authority_blocks_candidate(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(
        tmp_path,
        [_baseline_decision(final_authority_class="NOT_A_REAL_CLASS")],
    )
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert cand["eligibility"] == "BLOCKED"
    assert "unknown_authority" in cand["block_reasons"]
    assert snap["selection"]["selection_status"] == "FAIL_CLOSED_INVARIANT"
    assert snap["selection"]["fail_closed"] is True


def test_missing_authority_decision_blocks_candidate(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [])
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert cand["eligibility"] == "BLOCKED"
    assert "missing_authority_decision" in cand["block_reasons"]
    assert snap["selection"]["fail_closed"] is True


def test_duplicate_authority_decisions_block_candidate(
    tmp_path: Path,
) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(
        tmp_path,
        [_baseline_decision(), _baseline_decision()],
    )
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert cand["eligibility"] == "BLOCKED"
    assert "duplicate_authority_decision" in cand["block_reasons"]
    assert snap["selection"]["selection_status"] == "FAIL_CLOSED_INVARIANT"
    assert snap["selection"]["fail_closed"] is True


# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------


def test_missing_prerequisite_target_blocks_candidate(tmp_path: Path) -> None:
    unit = _baseline_unit(prerequisites=["nonexistent_unit"])
    _write_units_artifact(tmp_path, [unit])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert cand["eligibility"] == "BLOCKED"
    assert cand["prerequisites_satisfied"] is False
    assert "unknown_prerequisite_target" in cand["block_reasons"]


def test_unsatisfied_prerequisite_blocks_candidate(tmp_path: Path) -> None:
    prereq = _baseline_unit(id="prereq_unit", status="in_flight")
    unit = _baseline_unit(prerequisites=["prereq_unit"])
    _write_units_artifact(tmp_path, [prereq, unit])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(implementation_unit_id="prereq_unit"),
            _baseline_decision(),
        ],
    )
    snap = _snap(tmp_path)
    main_cand = next(
        c
        for c in snap["candidates"]
        if c["implementation_unit_id"] == "syn_unit_a"
    )
    assert main_cand["eligibility"] == "BLOCKED"
    assert main_cand["prerequisites_satisfied"] is False
    assert "unsatisfied_prerequisite" in main_cand["block_reasons"]


def test_satisfied_prerequisite_allows_candidate(tmp_path: Path) -> None:
    prereq = _baseline_unit(id="prereq_unit", status="merged")
    unit = _baseline_unit(prerequisites=["prereq_unit"])
    _write_units_artifact(tmp_path, [prereq, unit])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(implementation_unit_id="prereq_unit"),
            _baseline_decision(),
        ],
    )
    snap = _snap(tmp_path)
    main_cand = next(
        c
        for c in snap["candidates"]
        if c["implementation_unit_id"] == "syn_unit_a"
    )
    assert main_cand["prerequisites_satisfied"] is True
    # The prereq itself has status=merged which is not buildable, so
    # only the main unit can be picked.
    assert snap["selection"]["selected_unit_id"] == "syn_unit_a"


def test_all_blocked_by_prerequisites_status(tmp_path: Path) -> None:
    """If every candidate is blocked by unsatisfied / unknown
    prerequisites, the selection_status is
    ALL_BLOCKED_BY_PREREQUISITES."""
    u1 = _baseline_unit(id="u1", prerequisites=["missing"])
    u2 = _baseline_unit(
        id="u2", prerequisites=["missing2"], phase="v3.15.17"
    )
    _write_units_artifact(tmp_path, [u1, u2])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(implementation_unit_id="u1"),
            _baseline_decision(implementation_unit_id="u2", phase="v3.15.17"),
        ],
    )
    snap = _snap(tmp_path)
    assert snap["selection"]["selection_status"] == "ALL_BLOCKED_BY_PREREQUISITES"


def test_ade_qre_future_units_are_blocked_until_prior_unit_is_merged(
    tmp_path: Path,
) -> None:
    u_a = _baseline_unit(
        id="u_ade_qre_017a_maturity_matrix_reporter_001",
        roadmap_task_id="ade_qre_017a_baseline_reconciliation",
        phase="ade_qre_017a",
        status="ready",
    )
    u_b = _baseline_unit(
        id="u_ade_qre_017b_evidence_density_inventory_001",
        roadmap_task_id="ade_qre_017b_evidence_density_population",
        phase="ade_qre_017b",
        prerequisites=["u_ade_qre_017a_maturity_matrix_reporter_001"],
    )
    _write_units_artifact(tmp_path, [u_a, u_b])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(
                implementation_unit_id=u_a["id"],
                roadmap_task_id=u_a["roadmap_task_id"],
                phase=u_a["phase"],
            ),
            _baseline_decision(
                implementation_unit_id=u_b["id"],
                roadmap_task_id=u_b["roadmap_task_id"],
                phase=u_b["phase"],
            ),
        ],
    )
    snap = _snap(tmp_path)
    by_id = {c["implementation_unit_id"]: c for c in snap["candidates"]}
    assert snap["selection"]["selected_unit_id"] == u_a["id"]
    assert by_id[u_b["id"]]["eligibility"] == "BLOCKED"
    assert "unsatisfied_prerequisite" in by_id[u_b["id"]]["block_reasons"]


def test_materialized_current_a20_stack_selects_ade_qre_017c_after_017b_merge(
    tmp_path: Path,
) -> None:
    units_path = tmp_path / "logs" / "roadmap_task_units" / "latest.json"
    units_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path = tmp_path / "logs" / "roadmap_unit_authority" / "latest.json"
    auth_path.parent.mkdir(parents=True, exist_ok=True)

    units_payload = rtu.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    auth_payload = rua.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    units_path.write_text(json.dumps(units_payload, sort_keys=True), encoding="utf-8")
    auth_path.write_text(json.dumps(auth_payload, sort_keys=True), encoding="utf-8")

    snap = _snap(tmp_path)
    assert snap["selection"]["selected_unit_id"] == "u_ade_qre_017c_reason_record_maturity_reporter_001"
    assert snap["selection"]["selected_phase"] == "ade_qre_017c"


# ---------------------------------------------------------------------------
# NEEDS_HUMAN gated selection
# ---------------------------------------------------------------------------


def test_needs_human_units_can_be_selected_only_as_gated(tmp_path: Path) -> None:
    unit = _baseline_unit(authority_hint="NEEDS_HUMAN_CANDIDATE")
    _write_units_artifact(tmp_path, [unit])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(
                final_authority_class="NEEDS_HUMAN",
                requires_operator_go=True,
            )
        ],
    )
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert cand["eligibility"] == "NEEDS_HUMAN_GATED"
    sel = snap["selection"]
    assert sel["selection_status"] == "ALL_NEEDS_HUMAN_GATED"
    assert sel["selected_unit_id"] == "syn_unit_a"
    assert sel["requires_operator_go"] is True
    assert sel["fail_closed"] is False


def test_operator_gate_required_makes_unit_needs_human_gated(
    tmp_path: Path,
) -> None:
    """An AUTO_ALLOWED authority with operator_gate != none must
    classify as NEEDS_HUMAN_GATED, not ELIGIBLE."""
    unit = _baseline_unit(operator_gate="operator_go_required")
    _write_units_artifact(tmp_path, [unit])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert cand["eligibility"] == "NEEDS_HUMAN_GATED"
    assert snap["selection"]["requires_operator_go"] is True


def test_eligible_preferred_over_gated(tmp_path: Path) -> None:
    """When both pure-ELIGIBLE and NEEDS_HUMAN_GATED candidates
    exist, the selector picks the ELIGIBLE one even if the gated
    candidate would otherwise come earlier in the sort key."""
    # Eligible unit in phase v3.15.20 (later in phase order).
    eligible = _baseline_unit(
        id="eligible_late", phase="v3.15.20", risk_class="LOW"
    )
    # Gated unit in phase v3.15.16 (would normally come first).
    gated = _baseline_unit(
        id="gated_early",
        phase="v3.15.16",
        authority_hint="NEEDS_HUMAN_CANDIDATE",
        operator_gate="operator_go_required",
    )
    _write_units_artifact(tmp_path, [gated, eligible])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(
                implementation_unit_id="gated_early",
                phase="v3.15.16",
                final_authority_class="NEEDS_HUMAN",
                requires_operator_go=True,
            ),
            _baseline_decision(
                implementation_unit_id="eligible_late",
                phase="v3.15.20",
            ),
        ],
    )
    snap = _snap(tmp_path)
    assert snap["selection"]["selected_unit_id"] == "eligible_late"


# ---------------------------------------------------------------------------
# Non-buildable status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "non_buildable_status",
    ["in_flight", "merged", "blocked", "human_needed", "permanently_denied"],
)
def test_non_buildable_status_blocks_candidate(
    tmp_path: Path, non_buildable_status: str
) -> None:
    unit = _baseline_unit(status=non_buildable_status)
    _write_units_artifact(tmp_path, [unit])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert cand["eligibility"] == "BLOCKED"
    assert "non_buildable_status" in cand["block_reasons"]


def test_unknown_unit_status_blocks_candidate(tmp_path: Path) -> None:
    unit = _baseline_unit(status="not_a_real_status")
    _write_units_artifact(tmp_path, [unit])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert cand["eligibility"] == "BLOCKED"
    assert "unknown_unit_status" in cand["block_reasons"]
    assert snap["selection"]["fail_closed"] is True


# ---------------------------------------------------------------------------
# Deterministic sort key
# ---------------------------------------------------------------------------


def test_every_candidate_has_deterministic_sort_key(tmp_path: Path) -> None:
    units = [
        _baseline_unit(id="ux", phase="v3.15.17"),
        _baseline_unit(id="uy", phase="v3.15.16"),
    ]
    decisions = [
        _baseline_decision(implementation_unit_id="ux", phase="v3.15.17"),
        _baseline_decision(implementation_unit_id="uy", phase="v3.15.16"),
    ]
    _write_units_artifact(tmp_path, units)
    _write_authority_artifact(tmp_path, decisions)
    snap = _snap(tmp_path)
    for c in snap["candidates"]:
        assert isinstance(c["deterministic_sort_key"], list)
        assert len(c["deterministic_sort_key"]) == 5


def test_candidates_sorted_by_phase_then_authority_then_risk(
    tmp_path: Path,
) -> None:
    # Three units with different phases; the v3.15.16 one wins.
    u_late = _baseline_unit(id="u_late", phase="v3.15.20")
    u_early = _baseline_unit(id="u_early", phase="v3.15.16")
    u_mid = _baseline_unit(id="u_mid", phase="v3.15.18")
    _write_units_artifact(tmp_path, [u_late, u_mid, u_early])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(implementation_unit_id="u_late", phase="v3.15.20"),
            _baseline_decision(implementation_unit_id="u_mid", phase="v3.15.18"),
            _baseline_decision(implementation_unit_id="u_early", phase="v3.15.16"),
        ],
    )
    snap = _snap(tmp_path)
    assert snap["selection"]["selected_unit_id"] == "u_early"


def test_sort_breaks_ties_with_id_lex_order(tmp_path: Path) -> None:
    u_b = _baseline_unit(id="u_b")
    u_a = _baseline_unit(id="u_a")
    _write_units_artifact(tmp_path, [u_b, u_a])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(implementation_unit_id="u_b"),
            _baseline_decision(implementation_unit_id="u_a"),
        ],
    )
    snap = _snap(tmp_path)
    # Same phase / authority / risk / gate → id lex order picks "u_a".
    assert snap["selection"]["selected_unit_id"] == "u_a"


def test_selection_stable_across_runs(tmp_path: Path) -> None:
    units = [_baseline_unit(id="u1"), _baseline_unit(id="u2")]
    decisions = [
        _baseline_decision(implementation_unit_id="u1"),
        _baseline_decision(implementation_unit_id="u2"),
    ]
    _write_units_artifact(tmp_path, units)
    _write_authority_artifact(tmp_path, decisions)
    snap_a = _snap(tmp_path)
    snap_b = _snap(tmp_path)
    assert (
        snap_a["selection"]["selected_unit_id"]
        == snap_b["selection"]["selected_unit_id"]
    )


# ---------------------------------------------------------------------------
# Fail-closed on missing artefacts
# ---------------------------------------------------------------------------


def test_missing_unit_artifact_fails_closed(tmp_path: Path) -> None:
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    snap = _snap(tmp_path)
    sel = snap["selection"]
    assert sel["selection_status"] == "UPSTREAM_UNAVAILABLE"
    assert sel["fail_closed"] is True
    assert sel["selected_unit_id"] == ""
    assert "missing_unit_artifact" in sel["selection_reason"]


def test_missing_authority_artifact_fails_closed(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    snap = _snap(tmp_path)
    sel = snap["selection"]
    assert sel["selection_status"] == "UPSTREAM_UNAVAILABLE"
    assert sel["fail_closed"] is True
    assert "missing_authority_artifact" in sel["selection_reason"]


def test_both_artifacts_missing_fails_closed(tmp_path: Path) -> None:
    snap = _snap(tmp_path)
    sel = snap["selection"]
    assert sel["selection_status"] == "UPSTREAM_UNAVAILABLE"
    assert sel["fail_closed"] is True


def test_malformed_unit_artifact_fails_closed(tmp_path: Path) -> None:
    target = tmp_path / "logs" / "roadmap_task_units" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{not valid json", encoding="utf-8")
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    snap = _snap(tmp_path)
    assert snap["selection"]["selection_status"] == "UPSTREAM_UNAVAILABLE"
    assert snap["selection"]["fail_closed"] is True


def test_empty_units_returns_no_eligible(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [])
    _write_authority_artifact(tmp_path, [])
    snap = _snap(tmp_path)
    assert snap["selection"]["selection_status"] == "NO_ELIGIBLE_UNITS"
    assert snap["selection"]["fail_closed"] is True


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_snapshot_deterministic_with_injected_ts(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    a = _snap(tmp_path)
    b = _snap(tmp_path)
    assert a == b


def test_serialised_output_byte_identical_with_injected_ts(
    tmp_path: Path,
) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    a = _snap(tmp_path)
    b = _snap(tmp_path)
    out_a = json.dumps(a, indent=2, sort_keys=True) + "\n"
    out_b = json.dumps(b, indent=2, sort_keys=True) + "\n"
    assert out_a == out_b


def test_no_timestamps_in_sort_keys(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    snap = _snap(tmp_path)
    for c in snap["candidates"]:
        for value in c["deterministic_sort_key"]:
            text = str(value)
            assert "T" not in text or "Z" not in text  # no ISO 8601
            assert "2026" not in text


# ---------------------------------------------------------------------------
# Atomic write allowlist
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_path_outside_allowlist(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "elsewhere" / "latest.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        rnu._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_frozen_contract_paths(tmp_path: Path) -> None:
    for forbidden in (
        "research/research_latest.json",
        "research/strategy_matrix.csv",
    ):
        target = tmp_path / forbidden
        target.parent.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError):
            rnu._atomic_write_json(target, {"x": 1})


def test_atomic_write_accepts_allowlisted_path(tmp_path: Path) -> None:
    good = tmp_path / "logs" / "roadmap_next_unit" / "latest.json"
    good.parent.mkdir(parents=True, exist_ok=True)
    rnu._atomic_write_json(good, {"x": 1})
    assert good.is_file()


# ---------------------------------------------------------------------------
# CLI behaviour
# ---------------------------------------------------------------------------


def test_cli_no_write_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_next_unit" / "latest.json"
    monkeypatch.setattr(rnu, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rnu, "ARTIFACT_DIR", sentinel.parent)
    rc = rnu.main(["--no-write"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert '"roadmap_next_unit"' in out


def test_cli_status_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_next_unit" / "latest.json"
    monkeypatch.setattr(rnu, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rnu, "ARTIFACT_DIR", sentinel.parent)
    rc = rnu.main(["--status"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert "roadmap_next_unit" in out
    assert "no_runtime_trading_authority=True" in out
    assert "no_step5_runtime=True" in out
    assert "no_level6=True" in out
    assert "no_production_merge_authority=True" in out
    assert "deterministic_selection=True" in out
    assert "permanently_denied_units_never_selected=True" in out


def test_cli_default_writes_to_allowlisted_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_next_unit" / "latest.json"
    monkeypatch.setattr(rnu, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rnu, "ARTIFACT_DIR", sentinel.parent)
    rc = rnu.main([])
    assert rc == 0
    assert sentinel.is_file()
    payload = json.loads(sentinel.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "roadmap_next_unit"
    assert payload["module_version"].endswith("A20e")


def test_cli_indent_zero_compact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_next_unit" / "latest.json"
    monkeypatch.setattr(rnu, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rnu, "ARTIFACT_DIR", sentinel.parent)
    rc = rnu.main(["--no-write", "--indent", "0"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "\n  " not in out


# ---------------------------------------------------------------------------
# Read-only invariants
# ---------------------------------------------------------------------------


def test_collect_snapshot_does_not_mutate_upstream_artifacts(
    tmp_path: Path,
) -> None:
    units_path = _write_units_artifact(tmp_path, [_baseline_unit()])
    auth_path = _write_authority_artifact(tmp_path, [_baseline_decision()])
    before_units = hashlib.sha256(units_path.read_bytes()).hexdigest()
    before_auth = hashlib.sha256(auth_path.read_bytes()).hexdigest()
    _snap(tmp_path)
    after_units = hashlib.sha256(units_path.read_bytes()).hexdigest()
    after_auth = hashlib.sha256(auth_path.read_bytes()).hexdigest()
    assert before_units == after_units
    assert before_auth == after_auth


# ---------------------------------------------------------------------------
# Selector invariants (no execution, no Step 5, no Level 6, etc.)
# ---------------------------------------------------------------------------


def test_invariants_pin_no_work_execution(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    inv = _snap(tmp_path)["selector_invariants"]
    assert inv["no_work_execution"] is True
    assert inv["no_branch_creation"] is True
    assert inv["no_pr_creation"] is True
    assert inv["no_merge_or_deploy"] is True


def test_invariants_pin_no_mutation_routes_or_approval_buttons(
    tmp_path: Path,
) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    inv = _snap(tmp_path)["selector_invariants"]
    assert inv["no_mutation_routes"] is True
    assert inv["no_approval_buttons"] is True


def test_invariants_pin_no_runtime_trading_authority(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    inv = _snap(tmp_path)["selector_invariants"]
    assert inv["no_runtime_trading_authority"] is True


def test_invariants_pin_no_step5_no_level6_no_production_merge(
    tmp_path: Path,
) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    snap = _snap(tmp_path)
    inv = snap["selector_invariants"]
    assert inv["no_step5_runtime"] is True
    assert inv["no_level6"] is True
    assert inv["no_production_merge_authority"] is True
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"


def test_invariants_pin_no_upstream_mutation(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    inv = _snap(tmp_path)["selector_invariants"]
    assert inv["mutates_a20b_artifact"] is False
    assert inv["mutates_a20c_artifact"] is False


def test_invariants_pin_no_seed_jsonl_writes(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    inv = _snap(tmp_path)["selector_invariants"]
    assert inv["writes_to_seed_jsonl"] is False
    assert inv["writes_to_delegation_seed_jsonl"] is False
    assert inv["writes_to_generated_seed_jsonl"] is False


def test_invariants_pin_fail_closed_contracts(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    inv = _snap(tmp_path)["selector_invariants"]
    assert inv["fail_closed_on_unknown_evidence"] is True
    assert inv["fail_closed_on_duplicate_authority"] is True
    assert inv["fail_closed_on_missing_artifact"] is True


def test_invariants_pin_permanently_denied_never_selected(
    tmp_path: Path,
) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    inv = _snap(tmp_path)["selector_invariants"]
    assert inv["permanently_denied_units_never_selected"] is True
    assert inv["needs_human_units_require_operator_go"] is True


def test_invariants_pin_calls_execution_authority_classifier_false(
    tmp_path: Path,
) -> None:
    """A20e is a downstream consumer of A20c. It does not itself
    call the canonical classifier — A20c is the only call site."""
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    inv = _snap(tmp_path)["selector_invariants"]
    assert inv["calls_execution_authority_classifier"] is False


def test_invariants_pin_dynamic_status_ledger_consumed(
    tmp_path: Path,
) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    inv = _snap(tmp_path)["selector_invariants"]
    assert inv["consumes_dynamic_status_ledger"] is True
    assert inv["dynamic_status_overrides_static_when_valid"] is True
    assert inv["fail_closed_on_invalid_dynamic_status"] is True
    assert inv["fail_closed_on_duplicate_dynamic_status"] is True
    assert inv["dynamic_status_absence_falls_back_to_static"] is True
    assert inv["merged_units_never_reselected"] is True


# ---------------------------------------------------------------------------
# A21a dynamic-status overlay integration
# ---------------------------------------------------------------------------


def _write_dynamic_status_artifact(
    tmp_path: Path, records: list[dict[str, Any]]
) -> Path:
    target = tmp_path / "logs" / "roadmap_unit_status" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "module_version": "v3.15.16.A21a",
                "report_kind": "roadmap_unit_status",
                "generated_at_utc": "2026-05-18T08:00:00Z",
                "ledger_records": records,
                "fail_closed": False,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return target


def _dyn_merged_record(unit_id: str, pr_number: int = 999) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "status": "merged",
        "source": "pr_merge",
        "updated_at_utc": "2026-05-18T10:00:00Z",
        "pr_number": pr_number,
        "merge_sha": "abc1234def567890abc1234def567890abc1234d",
        "reason": "implemented by synthetic PR",
        "evidence": ["github_pr_number=" + str(pr_number)],
        "valid": True,
        "validation_reason": "",
    }


def test_dynamic_merged_status_excludes_unit_from_selector(
    tmp_path: Path,
) -> None:
    """Static A20b says ``not_started``; dynamic ledger says
    ``merged``. The selector must treat the unit as merged and not
    select it."""
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    _write_dynamic_status_artifact(
        tmp_path, [_dyn_merged_record("syn_unit_a")]
    )
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert cand["status"] == "not_started"  # A20b static unchanged
    assert cand["effective_status"] == "merged"
    assert cand["dynamic_status_source"] == "pr_merge"
    assert cand["eligibility"] == "BLOCKED"
    assert "dynamic_status_terminal" in cand["block_reasons"]
    assert snap["selection"]["selected_unit_id"] == ""


def test_dynamic_status_absent_falls_back_to_static(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    # No dynamic ledger artefact.
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert cand["status"] == "not_started"
    assert cand["effective_status"] == "not_started"
    assert cand["dynamic_status_source"] == ""
    assert cand["eligibility"] == "ELIGIBLE"
    assert snap["selection"]["selected_unit_id"] == "syn_unit_a"


def test_invalid_dynamic_status_fails_closed(tmp_path: Path) -> None:
    """A dynamic record with ``valid = False`` blocks the unit and
    surfaces fail-closed at the selection level."""
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    bad = _dyn_merged_record("syn_unit_a")
    bad["valid"] = False
    bad["validation_reason"] = "merged_without_merge_sha"
    _write_dynamic_status_artifact(tmp_path, [bad])
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert "invalid_dynamic_status" in cand["block_reasons"]
    assert cand["eligibility"] == "BLOCKED"
    assert snap["selection"]["selection_status"] == "FAIL_CLOSED_INVARIANT"
    assert snap["selection"]["fail_closed"] is True


def test_unknown_dynamic_status_value_fails_closed(tmp_path: Path) -> None:
    """A dynamic record whose ``status`` is outside the closed
    DYNAMIC_UNIT_STATUS vocab fails closed even if ``valid=True``
    (defence in depth)."""
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    rec = _dyn_merged_record("syn_unit_a")
    rec["status"] = "not_a_real_dynamic_status"
    _write_dynamic_status_artifact(tmp_path, [rec])
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert "invalid_dynamic_status" in cand["block_reasons"]


def test_dynamic_pr_open_status_blocks_candidate(tmp_path: Path) -> None:
    """``pr_open`` is a valid non-buildable dynamic status."""
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    rec = _dyn_merged_record("syn_unit_a")
    rec["status"] = "pr_open"
    rec["pr_number"] = 0
    rec["merge_sha"] = ""
    rec["reason"] = ""
    _write_dynamic_status_artifact(tmp_path, [rec])
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert cand["effective_status"] == "pr_open"
    assert cand["eligibility"] == "BLOCKED"
    assert "non_buildable_status" in cand["block_reasons"]


def test_dynamic_in_progress_status_blocks_candidate(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    rec = _dyn_merged_record("syn_unit_a")
    rec["status"] = "in_progress"
    rec["source"] = "loop_state"
    rec["pr_number"] = 0
    rec["merge_sha"] = ""
    rec["reason"] = ""
    _write_dynamic_status_artifact(tmp_path, [rec])
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert cand["effective_status"] == "in_progress"
    assert cand["eligibility"] == "BLOCKED"
    assert "non_buildable_status" in cand["block_reasons"]


def test_dynamic_failed_status_blocks_candidate(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    rec = _dyn_merged_record("syn_unit_a")
    rec["status"] = "failed"
    rec["source"] = "ci_failure"
    rec["pr_number"] = 0
    rec["merge_sha"] = ""
    rec["reason"] = ""
    _write_dynamic_status_artifact(tmp_path, [rec])
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert cand["effective_status"] == "failed"
    assert cand["eligibility"] == "BLOCKED"


def test_dynamic_merged_satisfies_prerequisite(tmp_path: Path) -> None:
    """A unit whose static prereq is ``not_started`` but whose
    dynamic prereq is ``merged`` must be considered satisfied."""
    prereq = _baseline_unit(id="prereq_unit", status="not_started")
    unit = _baseline_unit(prerequisites=["prereq_unit"])
    _write_units_artifact(tmp_path, [prereq, unit])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(implementation_unit_id="prereq_unit"),
            _baseline_decision(),
        ],
    )
    _write_dynamic_status_artifact(
        tmp_path, [_dyn_merged_record("prereq_unit", pr_number=100)]
    )
    snap = _snap(tmp_path)
    main_cand = next(
        c
        for c in snap["candidates"]
        if c["implementation_unit_id"] == "syn_unit_a"
    )
    assert main_cand["prerequisites_satisfied"] is True
    assert main_cand["eligibility"] == "ELIGIBLE"
    assert snap["selection"]["selected_unit_id"] == "syn_unit_a"


def test_pinned_three_merged_units_are_not_reselected(tmp_path: Path) -> None:
    """The bootstrap A21a seed pins the three v3.15.16 routing-layer
    units as merged. When the live ledger artefact carries those
    records, the selector must not reselect any of them."""
    schema_unit = _baseline_unit(
        id="u_v3_15_16_diagnostic_routing_signals_schema_001",
        phase="v3.15.16",
    )
    expl_unit = _baseline_unit(
        id="u_v3_15_16_routing_explanation_reporter_001",
        phase="v3.15.16",
    )
    gov_unit = _baseline_unit(
        id="u_v3_15_16_routing_governance_doc_001",
        phase="v3.15.16",
    )
    next_unit = _baseline_unit(
        id="u_v3_15_17_synthetic_next",
        phase="v3.15.17",
    )
    _write_units_artifact(
        tmp_path, [schema_unit, expl_unit, gov_unit, next_unit]
    )
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(
                implementation_unit_id=schema_unit["id"]
            ),
            _baseline_decision(
                implementation_unit_id=expl_unit["id"]
            ),
            _baseline_decision(
                implementation_unit_id=gov_unit["id"]
            ),
            _baseline_decision(
                implementation_unit_id=next_unit["id"],
                phase="v3.15.17",
            ),
        ],
    )
    _write_dynamic_status_artifact(
        tmp_path,
        [
            _dyn_merged_record(schema_unit["id"], pr_number=250),
            _dyn_merged_record(expl_unit["id"], pr_number=252),
            _dyn_merged_record(gov_unit["id"], pr_number=254),
        ],
    )
    snap = _snap(tmp_path)
    # The three merged units must not appear as the selection.
    merged_ids = {schema_unit["id"], expl_unit["id"], gov_unit["id"]}
    assert snap["selection"]["selected_unit_id"] not in merged_ids
    assert snap["selection"]["selected_unit_id"] == next_unit["id"]


def test_malformed_dynamic_status_artifact_fails_closed(
    tmp_path: Path,
) -> None:
    """If the dynamic ledger artefact is corrupt JSON, fail closed
    with UPSTREAM_UNAVAILABLE (same posture as units / authority)."""
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    target = tmp_path / "logs" / "roadmap_unit_status" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{not valid json", encoding="utf-8")
    snap = _snap(tmp_path)
    assert snap["selection"]["selection_status"] == "UPSTREAM_UNAVAILABLE"
    assert snap["selection"]["fail_closed"] is True
    assert (
        "malformed_dynamic_status_artifact"
        in snap["selection"]["selection_reason"]
    )


def test_static_status_field_unchanged_by_dynamic_overlay(
    tmp_path: Path,
) -> None:
    """The candidate's ``status`` field always carries the A20b
    static value verbatim. Only ``effective_status`` reflects the
    overlay. This preserves traceability."""
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    _write_dynamic_status_artifact(
        tmp_path, [_dyn_merged_record("syn_unit_a")]
    )
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert cand["status"] == "not_started"  # A20b static
    assert cand["effective_status"] == "merged"  # dynamic overlay


def test_dynamic_status_artifact_path_pinned(tmp_path: Path) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert (
        cand["source_status_artifact"]
        == "logs/roadmap_unit_status/latest.json"
    )


def test_top_level_projection_carries_status_schema_version(
    tmp_path: Path,
) -> None:
    _write_units_artifact(tmp_path, [_baseline_unit()])
    _write_authority_artifact(tmp_path, [_baseline_decision()])
    _write_dynamic_status_artifact(
        tmp_path, [_dyn_merged_record("syn_unit_a")]
    )
    snap = _snap(tmp_path)
    assert snap["source_status_schema_version"] == "1.0"


# ---------------------------------------------------------------------------
# A22 strategic-mandate selector integration
# ---------------------------------------------------------------------------


def test_strategically_preapproved_unit_is_eligible(tmp_path: Path) -> None:
    """A unit with final_authority_class STRATEGICALLY_PREAPPROVED
    and operator_gate=none must be ELIGIBLE (not NEEDS_HUMAN_GATED)."""
    unit = _baseline_unit()
    _write_units_artifact(tmp_path, [unit])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(
                final_authority_class="STRATEGICALLY_PREAPPROVED",
                requires_operator_go=False,
            )
        ],
    )
    snap = _snap(tmp_path)
    cand = snap["candidates"][0]
    assert cand["eligibility"] == "ELIGIBLE"
    assert cand["final_authority_class"] == "STRATEGICALLY_PREAPPROVED"
    assert snap["selection"]["selection_status"] == "OK_SELECTED"
    assert snap["selection"]["requires_operator_go"] is False


def test_auto_allowed_preferred_over_strategically_preapproved(
    tmp_path: Path,
) -> None:
    """When both an AUTO_ALLOWED and a STRATEGICALLY_PREAPPROVED
    candidate exist, the AUTO_ALLOWED one wins via the
    authority-order sort key (severity 0 vs 1)."""
    auto_unit = _baseline_unit(id="u_auto", phase="v3.15.16")
    strat_unit = _baseline_unit(id="u_strat", phase="v3.15.16")
    _write_units_artifact(tmp_path, [auto_unit, strat_unit])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(implementation_unit_id="u_auto"),
            _baseline_decision(
                implementation_unit_id="u_strat",
                final_authority_class="STRATEGICALLY_PREAPPROVED",
                requires_operator_go=False,
            ),
        ],
    )
    snap = _snap(tmp_path)
    assert snap["selection"]["selected_unit_id"] == "u_auto"


def test_strategically_preapproved_picked_before_needs_human(
    tmp_path: Path,
) -> None:
    """STRATEGICALLY_PREAPPROVED is ELIGIBLE; NEEDS_HUMAN is
    NEEDS_HUMAN_GATED. The selector prefers ELIGIBLE so the
    mandate-promoted unit wins over the gated one."""
    strat_unit = _baseline_unit(id="u_strat", phase="v3.15.16")
    gated_unit = _baseline_unit(
        id="u_gated",
        phase="v3.15.16",
        authority_hint="NEEDS_HUMAN_CANDIDATE",
        operator_gate="operator_go_required",
    )
    _write_units_artifact(tmp_path, [strat_unit, gated_unit])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(
                implementation_unit_id="u_strat",
                final_authority_class="STRATEGICALLY_PREAPPROVED",
                requires_operator_go=False,
            ),
            _baseline_decision(
                implementation_unit_id="u_gated",
                final_authority_class="NEEDS_HUMAN",
                requires_operator_go=True,
            ),
        ],
    )
    snap = _snap(tmp_path)
    assert snap["selection"]["selected_unit_id"] == "u_strat"
    assert snap["selection"]["selection_status"] == "OK_SELECTED"


def test_permanently_denied_still_wins_over_strategically_preapproved(
    tmp_path: Path,
) -> None:
    """PERMANENTLY_DENIED units remain BLOCKED — they never get
    selected even if STRATEGICALLY_PREAPPROVED options exist
    (defence in depth; the post-process never overrides hard
    denial, so this case shouldn't happen in practice but the
    selector still handles it correctly)."""
    strat_unit = _baseline_unit(id="u_strat", phase="v3.15.16")
    denied_unit = _baseline_unit(id="u_denied", phase="v3.15.16")
    _write_units_artifact(tmp_path, [strat_unit, denied_unit])
    _write_authority_artifact(
        tmp_path,
        [
            _baseline_decision(
                implementation_unit_id="u_strat",
                final_authority_class="STRATEGICALLY_PREAPPROVED",
                requires_operator_go=False,
            ),
            _baseline_decision(
                implementation_unit_id="u_denied",
                final_authority_class="PERMANENTLY_DENIED",
                permanently_denied=True,
                deny_reasons=["denied_live_path_modification"],
            ),
        ],
    )
    snap = _snap(tmp_path)
    # u_strat wins; u_denied is BLOCKED.
    assert snap["selection"]["selected_unit_id"] == "u_strat"
    denied_candidate = next(
        c
        for c in snap["candidates"]
        if c["implementation_unit_id"] == "u_denied"
    )
    assert denied_candidate["eligibility"] == "BLOCKED"


# ---------------------------------------------------------------------------
# Module-source forbidden-import / forbidden-token scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(rnu.__file__).read_text(encoding="utf-8")


def _module_imports() -> list[str]:
    import ast as _ast

    tree = _ast.parse(_module_source())
    out: list[str] = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for alias in node.names:
                out.append(alias.name)
        elif isinstance(node, _ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                out.append(f"{mod}.{alias.name}" if mod else alias.name)
    return out


def test_no_subprocess_in_module() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src
    assert "subprocess." not in src


def test_no_socket_or_urllib_or_http_or_requests() -> None:
    src = _module_source()
    for forbidden in (
        "import socket",
        "from socket",
        "import urllib",
        "from urllib",
        "import http",
        "from http",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
    ):
        assert forbidden not in src, forbidden


def test_no_forbidden_runtime_imports_via_ast() -> None:
    forbidden_prefixes = (
        "dashboard",
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "live",
        "paper",
        "shadow",
        "trading",
        "reporting.intelligent_routing",
        "reporting.development_queue_admission_policy",
        "reporting.development_agent_activity_timeline",
        "reporting.execution_authority",
    )
    for module in _module_imports():
        for prefix in forbidden_prefixes:
            assert not (
                module == prefix or module.startswith(prefix + ".")
            ), f"forbidden import: {module}"


def test_no_gh_or_git_cli_calls() -> None:
    src = _module_source()
    for forbidden in (
        "subprocess.run",
        "subprocess.Popen",
        "os.system(",
        "os.popen(",
        "shell=True",
        "eval(",
        "exec(",
    ):
        assert forbidden not in src, forbidden


def test_no_github_api_or_external_api_calls() -> None:
    src = _module_source()
    for forbidden in (
        "api.github.com",
        "anthropic",
        "openai",
        "Bearer ",
        "X-API-Key",
        "X-GitHub-Token",
    ):
        assert forbidden not in src, forbidden


def test_module_imports_only_canonical_upstreams() -> None:
    """A20e may only import from A20b + A20c + A21a (read-only). It
    MUST NOT import from reporting.execution_authority directly."""
    allowed = {
        "reporting.roadmap_task_units",
        "reporting.roadmap_unit_authority",
        "reporting.roadmap_unit_status",
    }
    for module in _module_imports():
        if module.startswith("reporting."):
            assert module in allowed, module


def test_module_imports_cleanly() -> None:
    importlib.reload(rnu)
    assert callable(rnu.collect_snapshot)
    assert callable(rnu.write_outputs)
    assert callable(rnu.main)


def test_schema_and_module_version_strings() -> None:
    assert isinstance(rnu.SCHEMA_VERSION, str) and rnu.SCHEMA_VERSION
    assert isinstance(rnu.MODULE_VERSION, str) and rnu.MODULE_VERSION
    assert rnu.MODULE_VERSION.endswith("A20e")
