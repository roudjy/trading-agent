"""Unit tests for A20c — Roadmap Unit Authority Classifier Integration.

Pins:

* closed vocabularies (AUTHORITY_CLASS, AUTHORITY_REASON,
  AUTHORITY_EVIDENCE_KIND, AUTHORITY_PROJECTION_STATUS);
* schema integrity (UnitAuthorityEvidence,
  UnitAuthorityDecision, UnitAuthorityProjection);
* deterministic byte-identical output with injected
  generated_at_utc;
* atomic write only under logs/roadmap_unit_authority/;
* --no-write does not write; --status does not write;
* every A20b ImplementationUnit receives exactly one
  UnitAuthorityDecision;
* final authority class is one of AUTO_ALLOWED / NEEDS_HUMAN /
  PERMANENTLY_DENIED;
* aggregation max severity works (synthetic units cover each tier);
* unknown evidence fails closed to NEEDS_HUMAN;
* docs/tests/reporting-only units can be AUTO_ALLOWED only if no
  protected/runtime surface is present;
* protected governance surfaces require NEEDS_HUMAN or stricter;
* frozen contract surfaces become PERMANENTLY_DENIED;
* live/broker/order/capital/risk/execution surfaces become
  PERMANENTLY_DENIED via the canonical classifier;
* paper/shadow runtime activation is not AUTO_ALLOWED;
* no unit grants QRE runtime/trading/paper/shadow/live authority;
* classifier_used is true for normal decisions;
* fail_closed is true for unknown/unsupported evidence;
* A20d visibility remains false; A20e selector remains false;
* no forbidden imports or runtime tokens in the module source.

The strings ``research/research_latest.json``,
``research/strategy_matrix.csv``, ``live/**``, ``paper/**``,
``shadow/**``, ``broker/**``, ``agent/risk/**``, and
``agent/execution/**`` are explicitly allowed inside evidence
values and inside this test file. They are forbidden as imports,
write targets, runtime calls, or authority-granting semantics —
those are pinned separately.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest

from reporting import execution_authority as ea
from reporting import roadmap_task_units as rtu
from reporting import roadmap_unit_authority as rua


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_FROZEN_UTC = "2026-05-18T18:00:00Z"


@pytest.fixture
def snap() -> dict:
    return rua.collect_snapshot(generated_at_utc=_FROZEN_UTC)


@pytest.fixture
def units_snap() -> dict:
    return rtu.collect_snapshot(generated_at_utc=_FROZEN_UTC)


def _baseline_unit(**overrides) -> dict:
    """Synthetic A20b-shape unit used by aggregation tests. Every
    field A20c reads is present."""
    base = {
        "id": "syn_unit_001",
        "roadmap_task_id": "phase_v3_15_16",
        "phase": "v3.15.16",
        "title": "synthetic test unit",
        "unit_kind": "reporting_module",
        "target_layer": "reporting",
        "source_requirement_ids": [],
        "expected_files": [
            "reporting/synthetic_module.py",
            "tests/unit/test_synthetic_module.py",
            "docs/governance/synthetic_module.md",
        ],
        "forbidden_files": [
            ".claude/**",
            "dashboard/dashboard.py",
            "research/research_latest.json",
            "research/strategy_matrix.csv",
            "automation/live_gate.py",
            "broker/**",
            "agent/risk/**",
            "agent/execution/**",
            "live/**",
            "paper/**",
            "shadow/**",
            "trading/**",
        ],
        "forbidden_surface_reasons": ["frozen_contract", "live_path"],
        "required_tests": [],
        "definition_of_done": [],
        "stop_conditions": ["fail-closed sample"],
        "prerequisites": [],
        "risk_class": "LOW",
        "authority_hint": "AUTO_ALLOWED_CANDIDATE",
        "operator_gate": "none",
        "status": "not_started",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_authority_class_matches_canonical_decisions_verbatim() -> None:
    assert rua.AUTHORITY_CLASS == ea.DECISIONS
    assert rua.AUTHORITY_CLASS == (
        "AUTO_ALLOWED",
        "NEEDS_HUMAN",
        "PERMANENTLY_DENIED",
    )


def test_authority_evidence_kind_is_closed_exact() -> None:
    assert rua.AUTHORITY_EVIDENCE_KIND == (
        "expected_file_classifier",
        "forbidden_file_classifier",
        "target_layer",
        "risk_class",
        "operator_gate",
        "authority_hint",
        "unit_kind",
        "stop_conditions",
    )


def test_authority_projection_status_is_closed_exact() -> None:
    assert rua.AUTHORITY_PROJECTION_STATUS == (
        "ok",
        "no_units",
        "upstream_unavailable",
        "fail_closed_invariant",
    )


def test_authority_reason_includes_canonical_reasons() -> None:
    for canonical in ea.REASONS:
        assert canonical in rua.AUTHORITY_REASON, canonical


def test_authority_reason_includes_a20c_specific_reasons() -> None:
    required = (
        "paper_runtime_activation_not_authorised",
        "shadow_runtime_activation_not_authorised",
        "live_runtime_activation_not_authorised",
        "operator_gate_required",
        "governance_bootstrap_pr_required",
        "fail_closed_unknown_evidence",
        "fail_closed_unknown_risk_class",
        "fail_closed_unknown_target_layer",
        "fail_closed_unknown_operator_gate",
        "fail_closed_unknown_authority_hint",
        "fail_closed_unknown_unit_kind",
        "research_module_requires_human_review",
        "external_intelligence_source_requires_human_review",
        "diagnostic_primitive_requires_human_review",
        "stop_conditions_informational_only",
        "non_path_evidence_baseline",
    )
    for r in required:
        assert r in rua.AUTHORITY_REASON, r


def test_authority_reason_has_no_duplicates() -> None:
    assert len(rua.AUTHORITY_REASON) == len(set(rua.AUTHORITY_REASON))


def test_severity_ordering_matches_canonical_decisions() -> None:
    assert rua._SEVERITY == {
        ea.DECISION_AUTO_ALLOWED: 0,
        ea.DECISION_NEEDS_HUMAN: 1,
        ea.DECISION_PERMANENTLY_DENIED: 2,
    }


def test_aggregating_evidence_kinds_subset_of_vocab() -> None:
    assert rua._AGGREGATING_EVIDENCE_KINDS.issubset(
        set(rua.AUTHORITY_EVIDENCE_KIND)
    )


def test_informational_evidence_kinds_subset_of_vocab() -> None:
    assert rua._INFORMATIONAL_EVIDENCE_KINDS.issubset(
        set(rua.AUTHORITY_EVIDENCE_KIND)
    )


def test_aggregating_and_informational_partition_the_vocab() -> None:
    union = rua._AGGREGATING_EVIDENCE_KINDS | rua._INFORMATIONAL_EVIDENCE_KINDS
    assert union == set(rua.AUTHORITY_EVIDENCE_KIND)
    assert rua._AGGREGATING_EVIDENCE_KINDS.isdisjoint(
        rua._INFORMATIONAL_EVIDENCE_KINDS
    )


# ---------------------------------------------------------------------------
# Schema integrity
# ---------------------------------------------------------------------------


def test_unit_authority_evidence_field_list_exact() -> None:
    assert rua.UNIT_AUTHORITY_EVIDENCE_FIELDS == (
        "kind",
        "value",
        "decision",
        "reason",
        "source",
    )


def test_unit_authority_decision_field_list_exact() -> None:
    assert rua.UNIT_AUTHORITY_DECISION_FIELDS == (
        "implementation_unit_id",
        "roadmap_task_id",
        "phase",
        "final_authority_class",
        "max_severity",
        "evidence",
        "requires_operator_go",
        "permanently_denied",
        "deny_reasons",
        "classifier_used",
        "fail_closed",
    )


def test_unit_authority_projection_field_list_exact() -> None:
    assert rua.UNIT_AUTHORITY_PROJECTION_FIELDS == (
        "generated_at_utc",
        "schema_version",
        "module_version",
        "source_units_schema_version",
        "authority_decisions",
        "authority_invariants",
    )


def test_every_decision_has_every_field(snap: dict) -> None:
    for d in snap["authority_decisions"]:
        assert set(d.keys()) == set(rua.UNIT_AUTHORITY_DECISION_FIELDS), d


def test_every_evidence_record_has_every_field(snap: dict) -> None:
    for d in snap["authority_decisions"]:
        for ev in d["evidence"]:
            assert set(ev.keys()) == set(
                rua.UNIT_AUTHORITY_EVIDENCE_FIELDS
            ), ev


def test_projection_carries_every_required_top_level_field(snap: dict) -> None:
    for field in rua.UNIT_AUTHORITY_PROJECTION_FIELDS:
        assert field in snap, field


# ---------------------------------------------------------------------------
# Coverage: every A20b unit gets exactly one decision
# ---------------------------------------------------------------------------


def test_every_a20b_unit_receives_exactly_one_decision(
    snap: dict, units_snap: dict
) -> None:
    unit_ids = [u["id"] for u in units_snap["implementation_units"]]
    decided_ids = [d["implementation_unit_id"] for d in snap["authority_decisions"]]
    assert sorted(unit_ids) == sorted(decided_ids)
    assert len(decided_ids) == len(set(decided_ids))


def test_decision_phase_and_task_id_match_upstream(
    snap: dict, units_snap: dict
) -> None:
    by_id = {u["id"]: u for u in units_snap["implementation_units"]}
    for d in snap["authority_decisions"]:
        u = by_id[d["implementation_unit_id"]]
        assert d["roadmap_task_id"] == u["roadmap_task_id"]
        assert d["phase"] == u["phase"]


# ---------------------------------------------------------------------------
# Final authority class is from the closed vocab
# ---------------------------------------------------------------------------


def test_every_final_class_is_in_authority_class_vocab(snap: dict) -> None:
    for d in snap["authority_decisions"]:
        assert d["final_authority_class"] in rua.AUTHORITY_CLASS


def test_every_max_severity_matches_final_class(snap: dict) -> None:
    for d in snap["authority_decisions"]:
        assert d["max_severity"] == rua._SEVERITY[d["final_authority_class"]]


def test_requires_operator_go_iff_needs_human(snap: dict) -> None:
    for d in snap["authority_decisions"]:
        assert d["requires_operator_go"] == (
            d["final_authority_class"] == ea.DECISION_NEEDS_HUMAN
        )


def test_permanently_denied_flag_consistent(snap: dict) -> None:
    for d in snap["authority_decisions"]:
        assert d["permanently_denied"] == (
            d["final_authority_class"] == ea.DECISION_PERMANENTLY_DENIED
        )
        if d["permanently_denied"]:
            assert d["deny_reasons"], d
        else:
            assert d["deny_reasons"] == [], d


# ---------------------------------------------------------------------------
# Aggregation max-severity rules — synthetic units
# ---------------------------------------------------------------------------


def test_auto_allowed_unit_aggregates_to_auto_allowed() -> None:
    unit = _baseline_unit(
        expected_files=[
            "reporting/synthetic_module.py",
            "tests/unit/test_synthetic_module.py",
            "docs/governance/synthetic_module.md",
        ],
        risk_class="LOW",
        operator_gate="none",
        authority_hint="AUTO_ALLOWED_CANDIDATE",
        unit_kind="reporting_module",
        target_layer="reporting",
    )
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_AUTO_ALLOWED
    assert d["max_severity"] == 0
    assert d["requires_operator_go"] is False
    assert d["permanently_denied"] is False
    assert d["classifier_used"] is True
    assert d["fail_closed"] is False


def test_needs_human_unit_elevates_via_canonical_policy_doc() -> None:
    """A LOW-risk reporting unit that lists a canonical_policy_doc in
    expected_files MUST elevate to NEEDS_HUMAN (the canonical
    classifier emits high_risk_canonical_policy_change for that
    path)."""
    unit = _baseline_unit(
        expected_files=[
            "reporting/synthetic_module.py",
            "docs/governance/execution_authority.md",
        ],
    )
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_NEEDS_HUMAN
    assert d["max_severity"] == 1
    assert d["requires_operator_go"] is True


def test_permanently_denied_unit_via_live_path() -> None:
    unit = _baseline_unit(
        expected_files=[
            "reporting/synthetic_module.py",
            "broker/synthetic_broker.py",  # live_path -> PERMANENTLY_DENIED
        ],
    )
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_PERMANENTLY_DENIED
    assert d["max_severity"] == 2
    assert d["permanently_denied"] is True
    assert "denied_live_path_modification" in d["deny_reasons"]


def test_permanently_denied_unit_via_frozen_contract() -> None:
    unit = _baseline_unit(
        expected_files=[
            "reporting/synthetic_module.py",
            "research/research_latest.json",
        ],
    )
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_PERMANENTLY_DENIED
    assert "denied_frozen_contract_mutation" in d["deny_reasons"]


def test_strategy_matrix_csv_is_permanently_denied_too() -> None:
    unit = _baseline_unit(
        expected_files=[
            "reporting/synthetic_module.py",
            "research/strategy_matrix.csv",
        ],
    )
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_PERMANENTLY_DENIED
    assert "denied_frozen_contract_mutation" in d["deny_reasons"]


@pytest.mark.parametrize(
    "path",
    [
        "broker/foo.py",
        "agent/risk/policy.py",
        "agent/execution/runner.py",
        "automation/live_gate.py",
    ],
)
def test_runtime_trading_paths_drive_unit_to_permanently_denied(
    path: str,
) -> None:
    unit = _baseline_unit(
        expected_files=["reporting/synthetic_module.py", path],
    )
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_PERMANENTLY_DENIED


def test_live_target_layer_drives_unit_to_permanently_denied() -> None:
    unit = _baseline_unit(target_layer="live")
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_PERMANENTLY_DENIED
    assert any(
        r == "live_runtime_activation_not_authorised" for r in d["deny_reasons"]
    )


def test_paper_target_layer_is_needs_human_not_auto_allowed() -> None:
    unit = _baseline_unit(target_layer="paper")
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_NEEDS_HUMAN
    assert d["final_authority_class"] != ea.DECISION_AUTO_ALLOWED


def test_shadow_target_layer_is_needs_human_not_auto_allowed() -> None:
    unit = _baseline_unit(target_layer="shadow")
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_NEEDS_HUMAN
    assert d["final_authority_class"] != ea.DECISION_AUTO_ALLOWED


def test_operator_gate_operator_go_required_elevates_to_needs_human() -> None:
    unit = _baseline_unit(operator_gate="operator_go_required")
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_NEEDS_HUMAN


def test_operator_gate_governance_bootstrap_pr_required_elevates() -> None:
    unit = _baseline_unit(operator_gate="governance_bootstrap_pr_required")
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_NEEDS_HUMAN


def test_research_module_unit_kind_elevates_to_needs_human() -> None:
    """A unit_kind of 'research_module' must elevate even if the
    expected_files happen to be auto-allowed by path classification."""
    unit = _baseline_unit(unit_kind="research_module")
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_NEEDS_HUMAN


def test_external_intelligence_source_unit_kind_elevates() -> None:
    unit = _baseline_unit(unit_kind="external_intelligence_source")
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_NEEDS_HUMAN


def test_diagnostic_primitive_unit_kind_elevates() -> None:
    unit = _baseline_unit(unit_kind="diagnostic_primitive")
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_NEEDS_HUMAN


# ---------------------------------------------------------------------------
# Unknown / unsupported evidence fails closed to NEEDS_HUMAN
# ---------------------------------------------------------------------------


def test_unknown_risk_class_string_fails_closed() -> None:
    unit = _baseline_unit(risk_class="NOT_A_RISK_CLASS")
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_NEEDS_HUMAN
    assert d["fail_closed"] is True


def test_risk_class_unknown_fails_closed() -> None:
    unit = _baseline_unit(risk_class="UNKNOWN")
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_NEEDS_HUMAN


def test_unknown_target_layer_fails_closed() -> None:
    unit = _baseline_unit(target_layer="not_a_layer")
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_NEEDS_HUMAN
    assert d["fail_closed"] is True


def test_unknown_operator_gate_fails_closed() -> None:
    unit = _baseline_unit(operator_gate="not_a_gate")
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_NEEDS_HUMAN
    assert d["fail_closed"] is True


def test_unknown_authority_hint_fails_closed() -> None:
    unit = _baseline_unit(authority_hint="MAYBE")
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_NEEDS_HUMAN
    assert d["fail_closed"] is True


def test_unknown_unit_kind_fails_closed() -> None:
    unit = _baseline_unit(unit_kind="not_a_kind")
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_NEEDS_HUMAN
    assert d["fail_closed"] is True


# ---------------------------------------------------------------------------
# Forbidden_files records are informational only (do not elevate)
# ---------------------------------------------------------------------------


def test_forbidden_file_classifier_evidence_is_recorded_but_not_aggregating(
    snap: dict,
) -> None:
    """Every emitted decision should carry forbidden_file_classifier
    evidence (transparency) AND that evidence kind must be in
    _INFORMATIONAL_EVIDENCE_KINDS."""
    assert "forbidden_file_classifier" in rua._INFORMATIONAL_EVIDENCE_KINDS
    for d in snap["authority_decisions"]:
        forbidden_evidence = [
            e for e in d["evidence"] if e["kind"] == "forbidden_file_classifier"
        ]
        # A20b always seeds at least baseline forbidden_files; A20c
        # must have classified them.
        assert forbidden_evidence


def test_baseline_unit_does_not_get_elevated_by_its_forbidden_files() -> None:
    """The baseline synthetic unit lists every protected/runtime/
    frozen path in forbidden_files. Those paths classify as
    PERMANENTLY_DENIED in the canonical classifier — but they MUST
    NOT elevate this unit, because forbidden_file_classifier is
    informational only."""
    unit = _baseline_unit()
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] == ea.DECISION_AUTO_ALLOWED


# ---------------------------------------------------------------------------
# Real A20b units: no AUTO_ALLOWED decision rests on a protected surface
# ---------------------------------------------------------------------------


def test_no_auto_allowed_decision_in_main_rests_on_protected_path(
    snap: dict,
) -> None:
    protected_categories = {
        "live_path",
        "frozen_contract",
        "branch_protection_config",
    }
    for d in snap["authority_decisions"]:
        if d["final_authority_class"] != ea.DECISION_AUTO_ALLOWED:
            continue
        for ev in d["evidence"]:
            if ev["kind"] != "expected_file_classifier":
                continue
            decision = ea.classify(
                action_type="file_edit",
                target_path=ev["value"],
                risk_class=ea.RISK_LOW,
            )
            assert decision.target_path_category not in protected_categories, (
                d["implementation_unit_id"],
                ev["value"],
            )


def test_canonical_policy_doc_in_expected_files_blocks_auto_allowed() -> None:
    """A docs/tests/reporting-only unit can be AUTO_ALLOWED only if no
    protected surface is present. Adding a canonical_policy_doc path
    must demote the unit to NEEDS_HUMAN."""
    unit = _baseline_unit(
        expected_files=[
            "reporting/synthetic_module.py",
            "docs/governance/no_touch_paths.md",  # canonical_policy_doc
        ],
    )
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] != ea.DECISION_AUTO_ALLOWED


def test_canonical_roadmap_in_expected_files_blocks_auto_allowed() -> None:
    unit = _baseline_unit(
        expected_files=[
            "reporting/synthetic_module.py",
            "docs/roadmap/Roadmap v6.md",  # canonical_roadmap
        ],
    )
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] != ea.DECISION_AUTO_ALLOWED


def test_dashboard_wiring_in_expected_files_blocks_auto_allowed() -> None:
    unit = _baseline_unit(
        expected_files=[
            "reporting/synthetic_module.py",
            "dashboard/dashboard.py",
        ],
    )
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] != ea.DECISION_AUTO_ALLOWED


def test_claude_governance_hook_in_expected_files_blocks_auto_allowed() -> None:
    unit = _baseline_unit(
        expected_files=[
            "reporting/synthetic_module.py",
            ".claude/hooks/foo.py",
        ],
    )
    d = rua._decide_for_unit(unit)
    assert d["final_authority_class"] != ea.DECISION_AUTO_ALLOWED


# ---------------------------------------------------------------------------
# classifier_used and fail_closed flags
# ---------------------------------------------------------------------------


def test_classifier_used_is_true_for_normal_decisions(snap: dict) -> None:
    """Every decision in the on-disk projection must have called the
    canonical classifier (each unit has non-empty expected_files)."""
    for d in snap["authority_decisions"]:
        assert d["classifier_used"] is True


def test_fail_closed_is_true_when_unknown_evidence_detected() -> None:
    unit = _baseline_unit(risk_class="NOT_A_RISK")
    d = rua._decide_for_unit(unit)
    assert d["fail_closed"] is True


def test_fail_closed_is_false_for_well_formed_auto_allowed_unit() -> None:
    unit = _baseline_unit()
    d = rua._decide_for_unit(unit)
    assert d["fail_closed"] is False


# ---------------------------------------------------------------------------
# Invariants pin authority chain
# ---------------------------------------------------------------------------


def test_invariants_flip_calls_execution_authority_classifier(snap: dict) -> None:
    assert snap["authority_invariants"]["calls_execution_authority_classifier"] is True


def test_invariants_flip_final_authority_classified(snap: dict) -> None:
    assert snap["authority_invariants"]["final_authority_classified"] is True


def test_invariants_pin_no_runtime_trading_authority(snap: dict) -> None:
    assert snap["authority_invariants"]["no_runtime_trading_authority"] is True


def test_invariants_pin_no_step5_runtime(snap: dict) -> None:
    assert snap["authority_invariants"]["no_step5_runtime"] is True
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"


def test_invariants_pin_no_level6(snap: dict) -> None:
    assert snap["authority_invariants"]["no_level6"] is True


def test_invariants_pin_no_production_merge_authority(snap: dict) -> None:
    assert snap["authority_invariants"]["no_production_merge_authority"] is True


def test_invariants_pin_writes_only_roadmap_unit_authority_log(
    snap: dict,
) -> None:
    assert (
        snap["authority_invariants"]["writes_only_roadmap_unit_authority_log"]
        is True
    )


def test_invariants_pin_aac_and_next_buildable_remain_false(snap: dict) -> None:
    inv = snap["authority_invariants"]
    assert inv["aac_visibility_present"] is False
    assert inv["next_buildable_selector_present"] is False


def test_invariants_pin_no_seed_jsonl_writes(snap: dict) -> None:
    inv = snap["authority_invariants"]
    assert inv["writes_to_seed_jsonl"] is False
    assert inv["writes_to_delegation_seed_jsonl"] is False
    assert inv["writes_to_generated_seed_jsonl"] is False


def test_invariants_pin_no_upstream_mutation(snap: dict) -> None:
    inv = snap["authority_invariants"]
    assert inv["mutates_a20a_artifact"] is False
    assert inv["mutates_a20b_artifact"] is False


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_snapshot_deterministic_with_injected_ts() -> None:
    a = rua.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    b = rua.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    assert a == b


def test_serialised_output_byte_identical_with_injected_ts() -> None:
    a = rua.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    b = rua.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    out_a = json.dumps(a, indent=2, sort_keys=True) + "\n"
    out_b = json.dumps(b, indent=2, sort_keys=True) + "\n"
    assert out_a == out_b


def test_decisions_sorted_stably(snap: dict) -> None:
    sorted_pairs = [
        (d["phase"], d["implementation_unit_id"])
        for d in snap["authority_decisions"]
    ]
    assert sorted_pairs == sorted(sorted_pairs)


def test_source_units_versions_match(snap: dict, units_snap: dict) -> None:
    assert snap["source_units_module_version"] == units_snap["module_version"]
    assert snap["source_units_schema_version"] == units_snap["schema_version"]


# ---------------------------------------------------------------------------
# Upstream mutation: sha256 before/after
# ---------------------------------------------------------------------------


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_collect_snapshot_does_not_mutate_a20b_artifact_in_memory() -> None:
    before = json.dumps(
        rtu.collect_snapshot(generated_at_utc=_FROZEN_UTC),
        sort_keys=True,
    ).encode("utf-8")
    rua.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    after = json.dumps(
        rtu.collect_snapshot(generated_at_utc=_FROZEN_UTC),
        sort_keys=True,
    ).encode("utf-8")
    assert _sha256(before) == _sha256(after)


# ---------------------------------------------------------------------------
# Atomic write allowlist
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_path_outside_allowlist(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "elsewhere" / "latest.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        rua._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_frozen_contract_paths(tmp_path: Path) -> None:
    for forbidden in (
        "research/research_latest.json",
        "research/strategy_matrix.csv",
    ):
        target = tmp_path / forbidden
        target.parent.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError):
            rua._atomic_write_json(target, {"x": 1})


def test_atomic_write_accepts_allowlisted_path(tmp_path: Path) -> None:
    good = tmp_path / "logs" / "roadmap_unit_authority" / "latest.json"
    good.parent.mkdir(parents=True, exist_ok=True)
    rua._atomic_write_json(good, {"x": 1})
    assert good.is_file()
    assert json.loads(good.read_text(encoding="utf-8")) == {"x": 1}


def test_atomic_write_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "logs" / "roadmap_unit_authority" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    rua._atomic_write_json(target, {"x": 1})
    rua._atomic_write_json(target, {"x": 2})
    siblings = list(target.parent.iterdir())
    assert siblings == [target]


# ---------------------------------------------------------------------------
# CLI behaviour
# ---------------------------------------------------------------------------


def test_cli_no_write_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_unit_authority" / "latest.json"
    monkeypatch.setattr(rua, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rua, "ARTIFACT_DIR", sentinel.parent)
    rc = rua.main(["--no-write"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert '"roadmap_unit_authority"' in out


def test_cli_status_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_unit_authority" / "latest.json"
    monkeypatch.setattr(rua, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rua, "ARTIFACT_DIR", sentinel.parent)
    rc = rua.main(["--status"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert "roadmap_unit_authority" in out
    assert "calls_execution_authority_classifier=True" in out
    assert "final_authority_classified=True" in out
    assert "no_runtime_trading_authority=True" in out
    assert "aac_visibility_present=False" in out
    assert "next_buildable_selector_present=False" in out


def test_cli_default_writes_to_allowlisted_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_unit_authority" / "latest.json"
    monkeypatch.setattr(rua, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rua, "ARTIFACT_DIR", sentinel.parent)
    rc = rua.main([])
    assert rc == 0
    assert sentinel.is_file()
    payload = json.loads(sentinel.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "roadmap_unit_authority"
    assert payload["module_version"].endswith("A20c")


def test_cli_indent_zero_compact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_unit_authority" / "latest.json"
    monkeypatch.setattr(rua, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rua, "ARTIFACT_DIR", sentinel.parent)
    rc = rua.main(["--no-write", "--indent", "0"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "\n  " not in out


# ---------------------------------------------------------------------------
# Module-source forbidden-import / forbidden-token scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(rua.__file__).read_text(encoding="utf-8")


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
    allowed_reporting_imports = {
        "reporting.execution_authority",
        "reporting.roadmap_task_units",
    }
    for module in _module_imports():
        if module.startswith("reporting."):
            assert module in allowed_reporting_imports, module


def test_module_imports_cleanly() -> None:
    importlib.reload(rua)
    assert callable(rua.collect_snapshot)
    assert callable(rua.write_outputs)
    assert callable(rua.main)


def test_schema_and_module_version_strings() -> None:
    assert isinstance(rua.SCHEMA_VERSION, str) and rua.SCHEMA_VERSION
    assert isinstance(rua.MODULE_VERSION, str) and rua.MODULE_VERSION
    assert rua.MODULE_VERSION.endswith("A20c")
