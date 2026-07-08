"""Canonical QRE contract vocabulary metadata.

This module defines the provider-agnostic contract vocabulary used to settle
QRE funnel ownership before bridge work. It is intentionally declarative: it
does not create research artifacts, run screening, register strategies, or
grant trading authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

SCHEMA_VERSION: Final[int] = 1

ContractStatus = Literal["present", "inferred", "missing", "ambiguous"]
ContractRecommendation = Literal[
    "KEEP",
    "DEFINE_CANONICAL_SCHEMA",
    "BRIDGE",
    "GENERALIZE",
    "OPERATOR_DECISION_REQUIRED",
    "KEEP_AS_OBSERVABILITY",
    "KEEP_AS_LEGACY_OUTPUT_CONTRACT",
]

PROVIDER_SPECIFIC_ALLOWED_LAYERS: Final[frozenset[str]] = frozenset(
    {
        "provider_adapter",
        "source_manifest",
        "source_snapshot",
        "dataset_fingerprint",
        "provenance",
    }
)

PROVIDER_SPECIFIC_FORBIDDEN_OBJECTS: Final[frozenset[str]] = frozenset(
    {
        "CandidateSpec",
        "StrategySpec",
        "StrategyIR",
        "PresetSpec",
        "CampaignSpec",
        "EvidencePack",
        "EvidenceLedger",
        "Disposition",
        "FeedbackRecord",
        "LessonMemory",
        "ResearchMemory",
    }
)

OBSERVABILITY_ONLY_OBJECTS: Final[frozenset[str]] = frozenset(
    {
        "DailyDigestInput",
        "OperatorSummary",
    }
)

FROZEN_LEGACY_OUTPUTS: Final[tuple[str, ...]] = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)


@dataclass(frozen=True, slots=True)
class CanonicalContract:
    canonical_name: str
    purpose: str
    minimum_required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    producer_layer: str
    consumer_layer: str
    provider_agnostic_fields: tuple[str, ...]
    provider_specific_fields_allowed: tuple[str, ...]
    allowed_provenance_fields: tuple[str, ...]
    forbidden_leakage: tuple[str, ...]
    current_known_owner: str
    status: ContractStatus
    recommendation: ContractRecommendation

    def as_dict(self) -> dict[str, object]:
        return {
            "canonical_name": self.canonical_name,
            "purpose": self.purpose,
            "minimum_required_fields": list(self.minimum_required_fields),
            "optional_fields": list(self.optional_fields),
            "producer_layer": self.producer_layer,
            "consumer_layer": self.consumer_layer,
            "provider_agnostic_fields": list(self.provider_agnostic_fields),
            "provider_specific_fields_allowed": list(self.provider_specific_fields_allowed),
            "allowed_provenance_fields": list(self.allowed_provenance_fields),
            "forbidden_leakage": list(self.forbidden_leakage),
            "current_known_owner": self.current_known_owner,
            "status": self.status,
            "recommendation": self.recommendation,
        }


def _contract(
    name: str,
    *,
    purpose: str,
    required: tuple[str, ...],
    optional: tuple[str, ...] = (),
    producer: str,
    consumer: str,
    agnostic: tuple[str, ...],
    provider_specific: tuple[str, ...] = (),
    provenance: tuple[str, ...] = (),
    owner: str,
    status: ContractStatus,
    recommendation: ContractRecommendation,
) -> CanonicalContract:
    return CanonicalContract(
        canonical_name=name,
        purpose=purpose,
        minimum_required_fields=required,
        optional_fields=optional,
        producer_layer=producer,
        consumer_layer=consumer,
        provider_agnostic_fields=agnostic,
        provider_specific_fields_allowed=provider_specific,
        allowed_provenance_fields=provenance,
        forbidden_leakage=(
            "provider-specific semantics outside adapter/source/provenance layers",
            "broker/risk/order/trading authority",
            "validation/promotion/paper/shadow/live readiness claims",
        ),
        current_known_owner=owner,
        status=status,
        recommendation=recommendation,
    )


CANONICAL_CONTRACTS: Final[tuple[CanonicalContract, ...]] = (
    _contract(
        "DataProvider",
        purpose="Names an external or local data provider capability.",
        required=("provider_id", "provider_kind", "capabilities"),
        optional=("adapter_module", "license_scope", "credential_requirement"),
        producer="provider_adapter",
        consumer="source_manifest",
        agnostic=("provider_kind", "capabilities"),
        provider_specific=("provider_id", "adapter_module"),
        owner="packages/qre_data/contracts.py",
        status="inferred",
        recommendation="DEFINE_CANONICAL_SCHEMA",
    ),
    _contract(
        "SourceManifest",
        purpose="Declares a source, its scope, license, and admissible use.",
        required=("source_id", "provider_id", "asset_scope", "license_scope", "quality_policy"),
        optional=("adapter_version", "credential_policy", "refresh_policy"),
        producer="source_manifest",
        consumer="source_snapshot",
        agnostic=("asset_scope", "license_scope", "quality_policy"),
        provider_specific=("source_id", "provider_id"),
        owner="research/external_intelligence/source_manifest_schema.py",
        status="present",
        recommendation="KEEP",
    ),
    _contract(
        "SourceSnapshot",
        purpose="Captures immutable source state and lineage for a data cut.",
        required=("source_snapshot_id", "source_id", "snapshot_time", "lineage_refs"),
        optional=("coverage", "quality_flags", "schema_refs"),
        producer="source_snapshot",
        consumer="observation_snapshot",
        agnostic=("snapshot_time", "coverage", "quality_flags"),
        provider_specific=("source_snapshot_id", "source_id"),
        provenance=("source_id", "source_snapshot_id", "lineage_refs"),
        owner="packages/qre_research/alpha_discovery/contracts.py",
        status="present",
        recommendation="KEEP",
    ),
    _contract(
        "DatasetFingerprint",
        purpose="Identifies the exact dataset content used by research.",
        required=("dataset_fingerprint_id", "source_snapshot_id", "content_digest"),
        optional=("row_count", "coverage_window", "partition_refs"),
        producer="dataset_fingerprint",
        consumer="observation_snapshot",
        agnostic=("content_digest", "row_count", "coverage_window"),
        provider_specific=("source_snapshot_id",),
        provenance=("source_snapshot_id", "partition_refs"),
        owner="ambiguous",
        status="inferred",
        recommendation="DEFINE_CANONICAL_SCHEMA",
    ),
    _contract(
        "ObservationSnapshot",
        purpose="Provider-neutral research observation context.",
        required=("observation_snapshot_id", "dataset_fingerprint_id", "diagnostics"),
        optional=("regime_context", "coverage_summary", "research_memory_refs"),
        producer="research_observation",
        consumer="hypothesis_generation",
        agnostic=("diagnostics", "regime_context", "coverage_summary"),
        provenance=("dataset_fingerprint_id",),
        owner="packages/qre_research/alpha_discovery/contracts.py",
        status="present",
        recommendation="BRIDGE",
    ),
    _contract(
        "Hypothesis",
        purpose="Provider-neutral statement of a mechanism to falsify.",
        required=("hypothesis_id", "mechanism", "predicted_effect", "falsification_conditions"),
        optional=("confounders", "supporting_observations", "novelty_dimensions"),
        producer="hypothesis_generation",
        consumer="admission_boundary",
        agnostic=("mechanism", "predicted_effect", "falsification_conditions"),
        provenance=("observation_snapshot_id",),
        owner="ambiguous: Tiingo generator and alpha discovery both claim semantics",
        status="ambiguous",
        recommendation="OPERATOR_DECISION_REQUIRED",
    ),
    _contract(
        "HypothesisSeed",
        purpose="Stable admitted seed identity derived from a hypothesis.",
        required=("hypothesis_seed_id", "source_hypothesis_id", "source_snapshot_id"),
        optional=("feature_family", "source_hypothesis_digest"),
        producer="admission_boundary",
        consumer="research_input_contract",
        agnostic=("hypothesis_seed_id", "source_hypothesis_id", "feature_family"),
        provenance=("source_snapshot_id", "source_hypothesis_digest"),
        owner="research/qre_tiingo_hypothesis_lifecycle.py",
        status="present",
        recommendation="BRIDGE",
    ),
    _contract(
        "ResearchInputContract",
        purpose="Admission-boundary contract for candidate formulation.",
        required=("contract_id", "hypothesis_seed_id", "decision", "required_candidate_spec_fields"),
        optional=("allowed_candidate_families", "forbidden_authorities"),
        producer="admission_boundary",
        consumer="candidate_materializer",
        agnostic=("contract_id", "decision", "required_candidate_spec_fields"),
        provenance=("hypothesis_seed_id", "source_snapshot_id"),
        owner="research/qre_tiingo_candidate_research_loop.py",
        status="present",
        recommendation="BRIDGE",
    ),
    _contract(
        "CandidateSpec",
        purpose="Provider-neutral research candidate semantics for screening.",
        required=("candidate_id", "parent_contract_id", "signal_definition", "selection_rule"),
        optional=("rebalance_rule", "holding_period", "benchmark", "variant_parameters"),
        producer="candidate_materializer",
        consumer="strategy_spec_builder",
        agnostic=("signal_definition", "selection_rule", "rebalance_rule", "benchmark"),
        provenance=("parent_contract_id", "source_snapshot_id"),
        owner="research/qre_tiingo_candidate_research_loop.py",
        status="present",
        recommendation="GENERALIZE",
    ),
    _contract(
        "StrategySpec",
        purpose="Provider-neutral strategy semantics compiled from a candidate.",
        required=("strategy_spec_id", "candidate_id", "signal_semantics", "position_semantics"),
        optional=("entry_semantics", "exit_semantics", "portfolio_semantics"),
        producer="strategy_spec_builder",
        consumer="preset_builder",
        agnostic=("signal_semantics", "position_semantics", "entry_semantics"),
        provenance=("candidate_id",),
        owner="ambiguous",
        status="ambiguous",
        recommendation="OPERATOR_DECISION_REQUIRED",
    ),
    _contract(
        "StrategyIR",
        purpose="Intermediate representation for strategy compilation.",
        required=("strategy_ir_id", "strategy_spec_id", "primitive_graph"),
        optional=("compiler_version", "safety_annotations"),
        producer="strategy_compiler",
        consumer="preset_builder",
        agnostic=("primitive_graph", "safety_annotations"),
        provenance=("strategy_spec_id",),
        owner="packages/qre_research/alpha_discovery/strategy_ir.py",
        status="ambiguous",
        recommendation="OPERATOR_DECISION_REQUIRED",
    ),
    _contract(
        "PresetSpec",
        purpose="Provider-neutral runnable research preset configuration.",
        required=("preset_id", "strategy_spec_id", "parameter_values", "execution_tier"),
        optional=("cost_model_ref", "slippage_model_ref"),
        producer="preset_builder",
        consumer="campaign_planner",
        agnostic=("parameter_values", "execution_tier", "cost_model_ref"),
        provenance=("strategy_spec_id",),
        owner="ambiguous",
        status="ambiguous",
        recommendation="OPERATOR_DECISION_REQUIRED",
    ),
    _contract(
        "CampaignSpec",
        purpose="Provider-neutral bounded research campaign plan.",
        required=("campaign_spec_id", "preset_id", "screening_protocol", "evidence_requirements"),
        optional=("budget", "null_controls", "stopping_rules"),
        producer="campaign_planner",
        consumer="campaign_runner",
        agnostic=("screening_protocol", "evidence_requirements", "null_controls"),
        provenance=("preset_id",),
        owner="ambiguous",
        status="ambiguous",
        recommendation="OPERATOR_DECISION_REQUIRED",
    ),
    _contract(
        "CampaignRun",
        purpose="Execution record for a bounded research campaign.",
        required=("campaign_run_id", "campaign_spec_id", "run_status", "artifact_refs"),
        optional=("started_at", "completed_at", "resource_usage"),
        producer="campaign_runner",
        consumer="evidence_evaluator",
        agnostic=("run_status", "artifact_refs", "resource_usage"),
        provenance=("campaign_spec_id",),
        owner="ambiguous",
        status="inferred",
        recommendation="DEFINE_CANONICAL_SCHEMA",
    ),
    _contract(
        "ScreeningResult",
        purpose="Provider-neutral summary of research screening metrics.",
        required=("screening_result_id", "candidate_id", "decision", "metrics"),
        optional=("null_control", "blocked_reasons", "decision_reasons"),
        producer="campaign_runner",
        consumer="evidence_evaluator",
        agnostic=("decision", "metrics", "null_control"),
        provenance=("candidate_id", "campaign_run_id"),
        owner="research/qre_tiingo_candidate_research_loop.py",
        status="present",
        recommendation="GENERALIZE",
    ),
    _contract(
        "EvidencePack",
        purpose="Provider-neutral collection of evidence for a research decision.",
        required=("evidence_pack_id", "campaign_run_id", "screening_result_refs", "decision_basis"),
        optional=("diagnostics_refs", "ledger_refs"),
        producer="evidence_evaluator",
        consumer="disposition_policy",
        agnostic=("decision_basis", "screening_result_refs", "diagnostics_refs"),
        provenance=("campaign_run_id",),
        owner="ambiguous",
        status="ambiguous",
        recommendation="OPERATOR_DECISION_REQUIRED",
    ),
    _contract(
        "EvidenceLedger",
        purpose="Appendable research-only evidence index.",
        required=("evidence_id", "evidence_kind", "metrics_digest", "evidence_decision"),
        optional=("metrics_summary", "null_control_summary", "audit_flags"),
        producer="evidence_evaluator",
        consumer="disposition_policy",
        agnostic=("evidence_kind", "metrics_digest", "evidence_decision"),
        provenance=("candidate_id", "source_snapshot_id"),
        owner="research/qre_tiingo_candidate_research_loop.py",
        status="present",
        recommendation="BRIDGE",
    ),
    _contract(
        "Disposition",
        purpose="Provider-neutral terminal or interim research decision.",
        required=("disposition_id", "evidence_pack_id", "decision", "reason_codes"),
        optional=("next_actions", "operator_notes"),
        producer="disposition_policy",
        consumer="feedback_memory",
        agnostic=("decision", "reason_codes", "next_actions"),
        provenance=("evidence_pack_id",),
        owner="ambiguous",
        status="inferred",
        recommendation="DEFINE_CANONICAL_SCHEMA",
    ),
    _contract(
        "FeedbackRecord",
        purpose="Provider-neutral feedback record consumable by a later research run.",
        required=("feedback_id", "subject_id", "feedback_decision", "next_action"),
        optional=("feedback_reasons", "consumable_by_next_run"),
        producer="feedback_memory",
        consumer="hypothesis_generation",
        agnostic=("feedback_decision", "next_action", "feedback_reasons"),
        provenance=("subject_id", "disposition_id"),
        owner="research/qre_tiingo_candidate_research_loop.py",
        status="present",
        recommendation="BRIDGE",
    ),
    _contract(
        "LessonMemory",
        purpose="Compressed research lesson for future hypothesis generation.",
        required=("lesson_id", "disposition_id", "lesson_type", "do_not_repeat"),
        optional=("generator_constraints", "recommended_next_question"),
        producer="feedback_memory",
        consumer="hypothesis_generation",
        agnostic=("lesson_type", "do_not_repeat", "generator_constraints"),
        provenance=("disposition_id",),
        owner="packages/qre_research/alpha_discovery/contracts.py",
        status="ambiguous",
        recommendation="OPERATOR_DECISION_REQUIRED",
    ),
    _contract(
        "ResearchMemory",
        purpose="Provider-neutral store of prior outcomes and lessons.",
        required=("research_memory_id", "lesson_refs", "feedback_refs"),
        optional=("terminal_outcomes", "active_contradictions"),
        producer="feedback_memory",
        consumer="hypothesis_generation",
        agnostic=("lesson_refs", "feedback_refs", "terminal_outcomes"),
        provenance=("memory_snapshot_id",),
        owner="ambiguous",
        status="ambiguous",
        recommendation="OPERATOR_DECISION_REQUIRED",
    ),
    _contract(
        "DailyDigestInput",
        purpose="Read-only observability input from sidecar reports.",
        required=("digest_kind", "source", "counts", "authority_summary"),
        optional=("next_actions", "status"),
        producer="research_sidecar",
        consumer="daily_digest",
        agnostic=("digest_kind", "counts", "authority_summary"),
        provenance=("source", "source_snapshot_id"),
        owner="research/qre_daily_status_digest.py",
        status="present",
        recommendation="KEEP_AS_OBSERVABILITY",
    ),
    _contract(
        "OperatorSummary",
        purpose="Human-readable read-only status summary.",
        required=("summary_path", "source_report_kind", "status_lines"),
        optional=("tables", "warnings"),
        producer="observability",
        consumer="operator",
        agnostic=("status_lines", "tables", "warnings"),
        provenance=("source_report_kind",),
        owner="research/qre_daily_status_digest.py",
        status="present",
        recommendation="KEEP_AS_OBSERVABILITY",
    ),
    _contract(
        "RegistryEntry",
        purpose="Protected strategy registration entry.",
        required=("strategy_id", "strategy_callable", "enabled"),
        optional=("metadata", "eligibility"),
        producer="registry",
        consumer="run_research",
        agnostic=("strategy_id", "enabled", "metadata"),
        provenance=("registry.py",),
        owner="registry.py",
        status="present",
        recommendation="KEEP",
    ),
    _contract(
        "StrategyMatrixRow",
        purpose="Frozen legacy research matrix row output.",
        required=("strategy_id", "metric_columns", "status"),
        optional=("diagnostics", "run_metadata"),
        producer="run_research",
        consumer="operator_report",
        agnostic=("strategy_id", "metric_columns", "status"),
        provenance=("research/strategy_matrix.csv",),
        owner="research/strategy_matrix.csv",
        status="present",
        recommendation="KEEP_AS_LEGACY_OUTPUT_CONTRACT",
    ),
)


def contract_names() -> tuple[str, ...]:
    return tuple(contract.canonical_name for contract in CANONICAL_CONTRACTS)


def contract_by_name(name: str) -> CanonicalContract:
    for contract in CANONICAL_CONTRACTS:
        if contract.canonical_name == name:
            return contract
    raise KeyError(name)


def vocabulary_as_dict() -> dict[str, dict[str, object]]:
    return {contract.canonical_name: contract.as_dict() for contract in CANONICAL_CONTRACTS}


def provider_specific_fields_are_allowed(contract: CanonicalContract) -> bool:
    if not contract.provider_specific_fields_allowed:
        return True
    return contract.producer_layer in PROVIDER_SPECIFIC_ALLOWED_LAYERS


def observability_contract_is_read_only(contract: CanonicalContract) -> bool:
    if contract.canonical_name not in OBSERVABILITY_ONLY_OBJECTS:
        return True
    return contract.producer_layer in {"research_sidecar", "observability"} and contract.consumer_layer in {
        "daily_digest",
        "operator",
    }


def contract_has_active_authority(contract: CanonicalContract) -> bool:
    authority_terms = (
        "broker",
        "risk",
        "order",
        "trading",
        "validation authority",
        "promotion",
        "paper",
        "shadow",
        "live",
    )
    haystack = " ".join(
        (
            contract.purpose,
            contract.producer_layer,
            contract.consumer_layer,
            " ".join(contract.minimum_required_fields),
            " ".join(contract.optional_fields),
        )
    ).lower()
    return any(term in haystack for term in authority_terms)


def validate_vocabulary() -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for contract in CANONICAL_CONTRACTS:
        if contract.canonical_name in seen:
            errors.append(f"duplicate_contract:{contract.canonical_name}")
        seen.add(contract.canonical_name)
        if contract.canonical_name in PROVIDER_SPECIFIC_FORBIDDEN_OBJECTS and contract.provider_specific_fields_allowed:
            errors.append(f"provider_specific_forbidden:{contract.canonical_name}")
        if not provider_specific_fields_are_allowed(contract):
            errors.append(f"provider_specific_layer_violation:{contract.canonical_name}")
        if not observability_contract_is_read_only(contract):
            errors.append(f"observability_not_read_only:{contract.canonical_name}")
        if contract_has_active_authority(contract):
            errors.append(f"active_authority_term:{contract.canonical_name}")
    return errors


__all__ = [
    "CANONICAL_CONTRACTS",
    "FROZEN_LEGACY_OUTPUTS",
    "OBSERVABILITY_ONLY_OBJECTS",
    "PROVIDER_SPECIFIC_ALLOWED_LAYERS",
    "PROVIDER_SPECIFIC_FORBIDDEN_OBJECTS",
    "SCHEMA_VERSION",
    "CanonicalContract",
    "contract_by_name",
    "contract_has_active_authority",
    "contract_names",
    "observability_contract_is_read_only",
    "provider_specific_fields_are_allowed",
    "validate_vocabulary",
    "vocabulary_as_dict",
]
