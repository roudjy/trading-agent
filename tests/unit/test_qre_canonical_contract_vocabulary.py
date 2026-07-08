from __future__ import annotations

from pathlib import Path

from packages.qre_research import canonical_contracts as contracts

REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_OBJECTS = {
    "DataProvider",
    "SourceManifest",
    "SourceSnapshot",
    "DatasetFingerprint",
    "ObservationSnapshot",
    "Hypothesis",
    "HypothesisSeed",
    "ResearchInputContract",
    "CandidateSpec",
    "StrategySpec",
    "StrategyIR",
    "PresetSpec",
    "CampaignSpec",
    "CampaignRun",
    "ScreeningResult",
    "EvidencePack",
    "EvidenceLedger",
    "Disposition",
    "FeedbackRecord",
    "LessonMemory",
    "ResearchMemory",
    "DailyDigestInput",
    "OperatorSummary",
    "RegistryEntry",
    "StrategyMatrixRow",
}


def test_canonical_vocabulary_contains_required_objects() -> None:
    assert set(contracts.contract_names()) == REQUIRED_OBJECTS


def test_each_contract_has_owner_status_and_recommendation() -> None:
    for contract in contracts.CANONICAL_CONTRACTS:
        assert contract.current_known_owner
        assert contract.status in {"present", "inferred", "missing", "ambiguous"}
        assert contract.recommendation in {
            "KEEP",
            "DEFINE_CANONICAL_SCHEMA",
            "BRIDGE",
            "GENERALIZE",
            "OPERATOR_DECISION_REQUIRED",
            "KEEP_AS_OBSERVABILITY",
            "KEEP_AS_LEGACY_OUTPUT_CONTRACT",
        }


def test_provider_specific_fields_stop_at_allowed_layers() -> None:
    for contract in contracts.CANONICAL_CONTRACTS:
        assert contracts.provider_specific_fields_are_allowed(contract)


def test_provider_specific_fields_are_forbidden_in_semantic_contracts() -> None:
    for name in contracts.PROVIDER_SPECIFIC_FORBIDDEN_OBJECTS:
        contract = contracts.contract_by_name(name)
        assert contract.provider_specific_fields_allowed == ()


def test_daily_digest_contracts_are_observability_only() -> None:
    for name in contracts.OBSERVABILITY_ONLY_OBJECTS:
        contract = contracts.contract_by_name(name)
        assert contracts.observability_contract_is_read_only(contract)
        assert contract.recommendation == "KEEP_AS_OBSERVABILITY"


def test_legacy_frozen_outputs_are_documented_and_unchanged_by_validation() -> None:
    before = {
        path: (REPO_ROOT / path).read_bytes()
        for path in contracts.FROZEN_LEGACY_OUTPUTS
    }

    assert contracts.validate_vocabulary() == []

    after = {
        path: (REPO_ROOT / path).read_bytes()
        for path in contracts.FROZEN_LEGACY_OUTPUTS
    }
    assert after == before


def test_vocabulary_has_no_active_runtime_authority() -> None:
    assert all(
        not contracts.contract_has_active_authority(contract)
        for contract in contracts.CANONICAL_CONTRACTS
    )


def test_tiingo_owned_contracts_require_bridge_or_generalization() -> None:
    tiingo_owned = [
        contract
        for contract in contracts.CANONICAL_CONTRACTS
        if "qre_tiingo" in contract.current_known_owner
    ]

    assert tiingo_owned
    assert {contract.recommendation for contract in tiingo_owned} <= {"BRIDGE", "GENERALIZE"}


def test_current_ambiguous_objects_are_explicitly_marked_for_decision() -> None:
    for name in (
        "Hypothesis",
        "StrategySpec",
        "StrategyIR",
        "PresetSpec",
        "CampaignSpec",
        "EvidencePack",
        "LessonMemory",
        "ResearchMemory",
    ):
        contract = contracts.contract_by_name(name)
        assert contract.status == "ambiguous"
        assert contract.recommendation == "OPERATOR_DECISION_REQUIRED"


def test_vocabulary_serializes_as_plain_dict() -> None:
    payload = contracts.vocabulary_as_dict()

    assert payload["CandidateSpec"]["canonical_name"] == "CandidateSpec"
    assert "minimum_required_fields" in payload["CandidateSpec"]
    assert payload["StrategyMatrixRow"]["recommendation"] == "KEEP_AS_LEGACY_OUTPUT_CONTRACT"
