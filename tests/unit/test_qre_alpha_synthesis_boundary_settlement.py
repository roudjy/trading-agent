from __future__ import annotations

from packages.qre_research import architecture_registry as registry
from packages.qre_research import maturity_gate

CANONICAL_FUNNEL_OBJECTS = {
    "Hypothesis",
    "CandidateSpec",
    "StrategySpec",
    "PresetSpec",
    "CampaignSpec",
    "EvidencePack",
    "Disposition",
    "FeedbackRecord",
    "LessonMemory",
    "ResearchMemory",
}


def _entry(entry_id: str) -> registry.ArchitectureRegistryEntry:
    return registry.registry_by_id(entry_id)


def test_alpha_discovery_is_settled_as_bridge_read_model_only() -> None:
    entry = _entry("alpha_discovery_generated_lifecycle")

    assert entry.role == "governance_only"
    assert entry.maturity_level == "blocked"
    assert entry.status == "settled_bridge_read_model_only"
    assert entry.operator_decision_required is False
    assert entry.canonical_objects_owned == ()
    assert set(entry.canonical_objects_consumed) <= CANONICAL_FUNNEL_OBJECTS | {"StrategyIR"}
    assert "bridge/read-model contracts" in entry.notes


def test_alpha_discovery_cannot_independently_own_canonical_funnel_objects() -> None:
    entry = _entry("alpha_discovery_generated_lifecycle")

    assert set(entry.canonical_objects_owned).isdisjoint(CANONICAL_FUNNEL_OBJECTS)
    assert entry.authority_flags["research_object_producer_authority"] is False
    assert entry.authority_flags["creates_candidates"] is False
    assert entry.authority_flags["creates_strategies"] is False
    assert entry.authority_flags["creates_presets"] is False
    assert entry.authority_flags["creates_campaigns"] is False


def test_bounded_synthesis_readiness_is_non_executable_governance_only() -> None:
    entry = _entry("bounded_strategy_synthesis_readiness")

    assert entry.role == "governance_only"
    assert entry.maturity_level == "synthesis_consideration"
    assert entry.status == "settled_non_executable_synthesis_consideration"
    assert entry.operator_decision_required is False
    assert entry.canonical_objects_owned == ()
    assert "may report readiness" in entry.notes
    assert "may not execute strategy synthesis" in entry.notes
    assert maturity_gate.validate_maturity_entry(entry) == []


def test_settled_surfaces_grant_no_execution_or_deployment_authority() -> None:
    for entry_id in ("alpha_discovery_generated_lifecycle", "bounded_strategy_synthesis_readiness"):
        entry = _entry(entry_id)
        for flag in registry.BLOCKED_AUTHORITY_FLAGS:
            assert entry.authority_flags[flag] is False
        assert entry.authority_flags["creates_strategies"] is False
        assert entry.authority_flags["creates_presets"] is False
        assert entry.authority_flags["creates_campaigns"] is False
        assert entry.authority_flags["runs_screening"] is False
        assert entry.authority_flags["research_object_producer_authority"] is False


def test_settlement_keeps_architecture_and_maturity_gates_green() -> None:
    assert registry.validate_registry() == []
    assert registry.validate_closed_world_audit() == []
    assert maturity_gate.validate_maturity_gate() == []
