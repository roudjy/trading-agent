from __future__ import annotations

from dataclasses import replace

from packages.qre_research import architecture_registry as registry
from packages.qre_research import maturity_gate


def _entry(entry_id: str) -> registry.ArchitectureRegistryEntry:
    return registry.registry_by_id(entry_id)


def _with_flag(
    entry: registry.ArchitectureRegistryEntry,
    flag: str,
    value: bool = True,
) -> registry.ArchitectureRegistryEntry:
    flags = dict(entry.authority_flags)
    flags[flag] = value
    return replace(entry, authority_flags=flags)


def test_current_registry_passes_maturity_gate() -> None:
    assert maturity_gate.validate_maturity_gate() == []


def test_policy_exposes_required_evidence_requirements() -> None:
    policy = maturity_gate.load_maturity_policy()

    assert set(maturity_gate.EVIDENCE_REQUIREMENTS) <= set(policy["evidence_requirements"])


def test_scaffold_may_not_claim_operator_trusted() -> None:
    entry = replace(
        _entry("canonical_contract_vocabulary"),
        maturity_level="scaffold",
        status="operator_trusted_claim",
    )

    assert "scaffold_claims_operator_trusted:canonical_contract_vocabulary" in maturity_gate.validate_maturity_entry(entry)


def test_working_capability_may_not_claim_strategy_authoritative() -> None:
    entry = _with_flag(_entry("canonical_contract_vocabulary"), "creates_strategies")

    assert (
        "working_capability_claims_strategy_authoritative:canonical_contract_vocabulary"
        in maturity_gate.validate_maturity_entry(entry)
    )


def test_working_capability_may_not_claim_deployment_authoritative() -> None:
    entry = _with_flag(_entry("canonical_contract_vocabulary"), "trading_authority")

    assert (
        "working_capability_claims_deployment_authoritative:canonical_contract_vocabulary"
        in maturity_gate.validate_maturity_entry(entry)
    )


def test_operator_trusted_requires_evidence_requirements() -> None:
    entry = _entry("empirical_research_flywheel_v7_1")
    policy = maturity_gate.load_maturity_policy()
    policy["evidence_requirements"] = []

    errors = maturity_gate.validate_maturity_entry(entry, policy)

    assert "operator_trusted_missing_policy_requirements:empirical_research_flywheel_v7_1" in errors


def test_operator_trusted_requires_reason_evidence_and_lineage() -> None:
    entry = replace(
        _entry("empirical_research_flywheel_v7_1"),
        notes="",
        artifact_paths=(),
        canonical_objects_consumed=(),
    )

    errors = maturity_gate.validate_maturity_entry(entry)

    assert "operator_trusted_missing_reason:empirical_research_flywheel_v7_1" in errors
    assert "operator_trusted_missing_evidence:empirical_research_flywheel_v7_1" in errors
    assert "operator_trusted_missing_lineage:empirical_research_flywheel_v7_1" in errors


def test_operator_trusted_remains_slice_specific() -> None:
    entry = replace(
        _entry("canonical_contract_vocabulary"),
        maturity_level="operator_trusted_capability",
    )

    assert "operator_trusted_not_slice_specific:canonical_contract_vocabulary" in maturity_gate.validate_maturity_entry(entry)


def test_synthesis_consideration_requires_bounded_non_executable_eligibility() -> None:
    entry = _with_flag(
        replace(
            _entry("bounded_strategy_synthesis_readiness"),
            operator_decision_required=False,
            canonical_objects_consumed=(),
        ),
        "strategy_synthesis_authority",
    )

    errors = maturity_gate.validate_maturity_entry(entry)

    assert "synthesis_consideration_without_operator_decision:bounded_strategy_synthesis_readiness" in errors
    assert (
        "synthesis_consideration_claims_executable_strategy_authority:bounded_strategy_synthesis_readiness"
        in errors
    )
    assert "synthesis_consideration_missing_evidence_backed_eligibility:bounded_strategy_synthesis_readiness" in errors


def test_shadow_ready_requires_default_disabled_gate_and_no_order_or_capital() -> None:
    entry = _with_flag(
        _with_flag(
            replace(_entry("canonical_contract_vocabulary"), maturity_level="shadow_ready"),
            "order_authority",
        ),
        "capital_allocation_authority",
    )
    policy = maturity_gate.load_maturity_policy()
    policy["shadow_ready_default_disabled_required"] = False

    errors = maturity_gate.validate_maturity_entry(entry, policy)

    assert "shadow_ready_missing_default_disabled_gate:canonical_contract_vocabulary" in errors
    assert "shadow_ready_claims_order_or_capital_authority:canonical_contract_vocabulary" in errors


def test_paper_and_live_ready_remain_blocked() -> None:
    paper = replace(_entry("canonical_contract_vocabulary"), maturity_level="paper_ready")
    live = replace(_entry("canonical_contract_vocabulary"), maturity_level="live_ready")

    assert "paper_ready_blocked_in_architecture_sequence:canonical_contract_vocabulary" in maturity_gate.validate_maturity_entry(paper)
    assert "live_ready_blocked_in_architecture_sequence:canonical_contract_vocabulary" in maturity_gate.validate_maturity_entry(live)


def test_dashboard_mutation_authority_remains_blocked() -> None:
    entry = _with_flag(_entry("canonical_contract_vocabulary"), "dashboard_mutation_authority")

    assert "dashboard_mutation_authority_blocked:canonical_contract_vocabulary" in maturity_gate.validate_maturity_entry(entry)
