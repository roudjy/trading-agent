from __future__ import annotations

from pathlib import Path

from packages.qre_research import architecture_registry as registry

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_registry_loads_and_validates_cleanly() -> None:
    assert registry.registry_entries()
    assert registry.validate_registry() == []


def test_registry_schema_metadata_is_stable() -> None:
    summary = registry.registry_summary()

    assert summary["registry_kind"] == "qre_architecture_registry"
    assert summary["schema_version"] == 1


def test_all_roles_are_known() -> None:
    assert {entry.role for entry in registry.registry_entries()} <= set(registry.ALLOWED_ROLES)


def test_all_maturity_levels_are_known() -> None:
    assert {entry.maturity_level for entry in registry.registry_entries()} <= set(registry.ALLOWED_MATURITY_LEVELS)


def test_authority_flags_are_explicit() -> None:
    required = set(registry.AUTHORITY_FLAGS)

    for entry in registry.registry_entries():
        assert set(entry.authority_flags) == required
        assert all(isinstance(value, bool) for value in entry.authority_flags.values())


def test_entry_ids_are_unique() -> None:
    ids = [entry.id for entry in registry.registry_entries()]

    assert len(ids) == len(set(ids))


def test_required_surfaces_are_classified() -> None:
    ids = set(registry.registry_as_dict())

    assert {
        "canonical_contract_vocabulary",
        "tiingo_hypothesis_candidate_research_mini_loop",
        "daily_status_digest_observability",
        "run_research_registry_matrix",
        "alpha_discovery_generated_lifecycle",
        "empirical_research_flywheel_v7_1",
        "bounded_strategy_synthesis_readiness",
        "funnel_architecture_audit",
        "test_smoke_fixture_paths",
        "canonical_funnel_verification",
        "rejection_reason_intelligence",
        "hypothesis_generator_governance",
        "research_throughput_controls",
        "offline_research_dry_run",
        "governed_candidate_batch",
        "evidence_memory_accumulation",
        "operator_trust_multirun_report",
        "governed_offline_artifacts",
    } <= ids


def test_observability_only_entries_have_no_research_object_producer_authority() -> None:
    for entry in registry.registry_entries():
        if entry.role == "observability_only":
            assert entry.authority_flags["research_object_producer_authority"] is False


def test_fixture_only_entries_have_no_empirical_evidence_authority() -> None:
    for entry in registry.registry_entries():
        if entry.role == "fixture_only":
            assert entry.authority_flags["empirical_evidence_authority"] is False


def test_provider_adapters_do_not_own_canonical_semantics() -> None:
    for entry in registry.registry_entries():
        if entry.role == "provider_adapter":
            assert entry.canonical_objects_owned == ()
            assert entry.provider_scope != "provider_agnostic"


def test_legacy_surfaces_do_not_silently_claim_modern_canonical_ownership() -> None:
    for entry in registry.registry_entries():
        if entry.role == "legacy_surface" and entry.canonical_objects_owned:
            assert entry.operator_decision_required is True


def test_operator_decision_required_entries_are_explicit() -> None:
    operator_entries = {entry.id for entry in registry.operator_decision_entries()}

    assert "run_research_registry_matrix" not in operator_entries
    assert "empirical_research_flywheel_v7_1" not in operator_entries
    assert "alpha_discovery_generated_lifecycle" not in operator_entries
    assert "bounded_strategy_synthesis_readiness" not in operator_entries


def test_frozen_outputs_are_identified_as_protected() -> None:
    protected = set(registry.protected_outputs())

    assert set(registry.FROZEN_LEGACY_OUTPUTS) <= protected


def test_validation_does_not_mutate_frozen_outputs() -> None:
    before = {
        path: (REPO_ROOT / path).read_bytes()
        for path in registry.FROZEN_LEGACY_OUTPUTS
    }

    assert registry.validate_registry() == []

    after = {
        path: (REPO_ROOT / path).read_bytes()
        for path in registry.FROZEN_LEGACY_OUTPUTS
    }
    assert after == before


def test_no_blocked_runtime_or_execution_authority_is_enabled() -> None:
    for entry in registry.registry_entries():
        for flag in registry.BLOCKED_AUTHORITY_FLAGS:
            assert entry.authority_flags[flag] is False


def test_registry_indexes_expose_pr2_handoff_surfaces() -> None:
    producers = registry.registered_producer_modules()
    artifacts = registry.registered_artifact_paths()
    owners = registry.canonical_ownership_index()

    assert producers["tools/qre_funnel_architecture_audit.py"] == "funnel_architecture_audit"
    assert artifacts["research/research_latest.json"] == "run_research_registry_matrix"
    assert owners["CandidateSpec"] == "canonical_contract_vocabulary"
