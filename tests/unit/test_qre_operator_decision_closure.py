from __future__ import annotations

from packages.qre_research import architecture_registry as registry
from packages.qre_research import maturity_gate
from tools import qre_architecture_impact_report as impact

OPERATOR_DECISION_SURFACES = (
    "run_research_registry_matrix",
    "alpha_discovery_generated_lifecycle",
    "empirical_research_flywheel_v7_1",
    "bounded_strategy_synthesis_readiness",
)


def _entry(entry_id: str) -> registry.ArchitectureRegistryEntry:
    return registry.registry_by_id(entry_id)


def test_operator_decision_surfaces_are_all_explicitly_classified() -> None:
    for entry_id in OPERATOR_DECISION_SURFACES:
        entry = _entry(entry_id)
        assert entry.role in registry.ALLOWED_ROLES
        assert entry.maturity_level in registry.ALLOWED_MATURITY_LEVELS
        assert entry.notes


def test_settled_surfaces_no_longer_require_operator_decision() -> None:
    assert _entry("run_research_registry_matrix").operator_decision_required is False
    assert _entry("empirical_research_flywheel_v7_1").operator_decision_required is False


def test_high_risk_unsettled_surfaces_remain_operator_decision_explicit() -> None:
    alpha = _entry("alpha_discovery_generated_lifecycle")
    synthesis = _entry("bounded_strategy_synthesis_readiness")

    assert alpha.operator_decision_required is True
    assert alpha.role == "governance_only"
    assert alpha.canonical_objects_owned == ()
    assert "no independent canonical loop ownership" in alpha.notes

    assert synthesis.operator_decision_required is True
    assert synthesis.role == "governance_only"
    assert synthesis.maturity_level == "synthesis_consideration"
    assert synthesis.canonical_objects_owned == ()
    assert "no executable synthesis" in synthesis.notes


def test_operator_decision_surfaces_have_no_hidden_canonical_ownership() -> None:
    for entry_id in OPERATOR_DECISION_SURFACES:
        assert _entry(entry_id).canonical_objects_owned == ()


def test_operator_decision_surfaces_do_not_grant_blocked_authority() -> None:
    for entry_id in OPERATOR_DECISION_SURFACES:
        entry = _entry(entry_id)
        for flag in registry.BLOCKED_AUTHORITY_FLAGS:
            assert entry.authority_flags[flag] is False
        assert entry.authority_flags["research_object_producer_authority"] is False
        assert entry.authority_flags["empirical_evidence_authority"] is False


def test_operator_decision_surfaces_cannot_mutate_frozen_outputs() -> None:
    for entry_id in OPERATOR_DECISION_SURFACES:
        entry = _entry(entry_id)
        if entry.id == "run_research_registry_matrix":
            assert entry.role == "legacy_surface"
            assert set(entry.artifact_paths) == set(registry.FROZEN_LEGACY_OUTPUTS)
            assert entry.authority_flags["runtime_behavior_changed"] is False
            continue
        assert set(registry.FROZEN_LEGACY_OUTPUTS) <= set(entry.forbidden_outputs)


def test_registry_and_maturity_gates_accept_operator_decision_closure() -> None:
    assert registry.validate_registry() == []
    assert registry.validate_closed_world_audit() == []
    assert maturity_gate.validate_maturity_gate() == []


def test_impact_report_surfaces_registry_classification_review() -> None:
    report = impact.build_report(("docs/architecture/qre_architecture_registry.v1.json",))

    assert report["verdict"] == "review_required"
    assert "docs/architecture/qre_architecture_registry.v1.json" in report["changed_qre_files"]
    assert report["protected_outputs_touched"] == []
