from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Protocol

from packages.qre_research.generated_strategy_paths import validate_write_target

SCHEMA_VERSION = "1.1"
POLICY_VERSION = "qre_alpha_discovery_followup_pr1_v1"
REPORT_KIND = "qre_alpha_discovery_mvp"
DEFAULT_OUTPUT_ROOT = Path("generated_research/alpha_discovery")

EXECUTION_TIER_COMPILER_ONLY = "COMPILER_ONLY"
EXECUTION_TIER_EXECUTOR_SMOKE = "EXECUTOR_SMOKE"
EXECUTION_TIER_EMPIRICAL_SCREENING = "EMPIRICAL_SCREENING"
EXECUTION_TIER_LOCKED_OOS_VALIDATION = "LOCKED_OOS_VALIDATION"
EXECUTION_TIERS = (
    EXECUTION_TIER_COMPILER_ONLY,
    EXECUTION_TIER_EXECUTOR_SMOKE,
    EXECUTION_TIER_EMPIRICAL_SCREENING,
    EXECUTION_TIER_LOCKED_OOS_VALIDATION,
)

LESSON_TYPE_PROCESS = "PROCESS_LESSON"
LESSON_TYPE_DATA = "DATA_LESSON"
LESSON_TYPE_CAPABILITY = "CAPABILITY_LESSON"
LESSON_TYPE_EMPIRICAL_MECHANISM = "EMPIRICAL_MECHANISM_LESSON"
LESSON_TYPE_EVIDENCE_DESIGN = "EVIDENCE_DESIGN_LESSON"
LESSON_TYPES = (
    LESSON_TYPE_PROCESS,
    LESSON_TYPE_DATA,
    LESSON_TYPE_CAPABILITY,
    LESSON_TYPE_EMPIRICAL_MECHANISM,
    LESSON_TYPE_EVIDENCE_DESIGN,
)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def stable_digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def content_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{stable_digest(value)[:16]}"


def canonical_payload(value: Any) -> Any:
    if is_dataclass(value):
        return canonical_payload(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): canonical_payload(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonical_payload(item) for item in value]
    if isinstance(value, tuple):
        return [canonical_payload(item) for item in value]
    return value


def payload_identity(value: Any, *, prefix: str) -> str:
    return content_id(prefix, canonical_payload(value))


def write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8-sig") == text:
                return
        except OSError:
            pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


@dataclass(frozen=True, slots=True)
class DiscoveryContext:
    repo_root: Path
    observation_budget: int = 1
    generation_budget: int = 3
    execution_budget: int = 1
    dry_run: bool = False
    max_hypotheses: int = 3
    requested_execution_tier: str = EXECUTION_TIER_EMPIRICAL_SCREENING


@dataclass(frozen=True, slots=True)
class ObservationSnapshot:
    observation_snapshot_id: str
    schema_version: str
    policy_version: str
    market_diagnostics: dict[str, Any]
    regime_diagnostics: dict[str, Any]
    cross_asset_diagnostics: dict[str, Any]
    data_coverage: dict[str, Any]
    source_quality: dict[str, Any]
    identity_readiness: str
    current_queue: list[dict[str, Any]]
    recent_terminal_outcomes: list[dict[str, Any]]
    active_contradictions: list[dict[str, Any]]
    resolved_contradictions: list[dict[str, Any]]
    mechanism_coverage: dict[str, Any]
    behavior_family_coverage: dict[str, Any]
    primitive_inventory: dict[str, Any]
    executor_inventory: dict[str, Any]
    relevant_research_memory: dict[str, Any]
    content_identity: str

    def to_payload(self) -> dict[str, Any]:
        return canonical_payload(self)


@dataclass(frozen=True, slots=True)
class MechanisticHypothesis:
    hypothesis_id: str
    schema_version: str
    provider_id: str
    generation_policy_version: str
    parent_hypothesis_id: str | None
    mechanism_family: str
    behavior_family: str
    causal_mechanism_statement: str
    predicted_observable_effect: str
    expected_direction: str
    universe_intent: str
    timeframe_intent: str
    regime_scope: str
    required_features: tuple[str, ...]
    required_controls: tuple[str, ...]
    null_hypothesis: str
    falsification_conditions: tuple[str, ...]
    confounders: tuple[str, ...]
    minimum_activity_expectation: str
    cost_sensitivity_expectation: str
    support_observation_refs: tuple[str, ...]
    contradicting_observation_refs: tuple[str, ...]
    related_hypotheses: tuple[str, ...]
    related_campaigns: tuple[str, ...]
    novelty_dimensions: tuple[str, ...]
    parameter_schema: tuple[dict[str, Any], ...]
    parameter_count: int
    content_identity: str
    stable_fingerprint: str

    def to_payload(self) -> dict[str, Any]:
        return canonical_payload(self)


@dataclass(frozen=True, slots=True)
class HypothesisCritique:
    critique_id: str
    hypothesis_id: str
    strongest_counter_hypothesis: str
    mechanism_weaknesses: tuple[str, ...]
    alternative_explanations: tuple[str, ...]
    missing_confounders: tuple[str, ...]
    data_leakage_risks: tuple[str, ...]
    selection_bias_risks: tuple[str, ...]
    survivorship_bias_risks: tuple[str, ...]
    data_feasibility_risks: tuple[str, ...]
    primitive_gaps: tuple[str, ...]
    executor_gaps: tuple[str, ...]
    cost_risks: tuple[str, ...]
    activity_risks: tuple[str, ...]
    overfitting_risks: tuple[str, ...]
    semantic_duplicate_risks: tuple[str, ...]
    required_repairs: tuple[str, ...]
    fatal_objections: tuple[str, ...]
    content_identity: str


@dataclass(frozen=True, slots=True)
class HypothesisRevision:
    original_hypothesis_id: str
    critique_id: str
    revised_hypothesis_id: str
    changes_applied: tuple[str, ...]
    changes_rejected: tuple[str, ...]
    content_identity: str


@dataclass(frozen=True, slots=True)
class HypothesisScorecard:
    hypothesis_id: str
    mechanistic_clarity: float
    falsifiability: float
    novelty: float
    observation_grounding: float
    data_feasibility: float
    identity_readiness: float
    primitive_readiness: float
    executor_readiness: float
    confounder_coverage: float
    leakage_safety: float
    complexity: float
    expected_information_gain: float
    expected_decisiveness: float
    portfolio_orthogonality: float
    prior_failure_distance: float
    estimated_compute_cost: float
    overall_score: float
    hard_blockers: tuple[str, ...]
    reason_codes: tuple[str, ...]
    content_identity: str


@dataclass(frozen=True, slots=True)
class ExperimentContract:
    experiment_id: str
    hypothesis_id: str
    research_question: str
    predicted_observable: str
    counter_hypothesis: str
    universe_spec: str
    timeframe: str
    sampling_frequency: str
    required_data_fields: tuple[str, ...]
    required_history: str
    required_point_in_time_metadata: tuple[str, ...]
    required_features: tuple[str, ...]
    signal_semantics: str
    position_semantics: str
    entry_semantics: str
    exit_semantics: str
    portfolio_semantics: str
    null_models: tuple[str, ...]
    falsification_tests: tuple[str, ...]
    confounder_controls: tuple[str, ...]
    transaction_cost_model: str
    slippage_model: str
    IS_policy: str
    validation_policy: str
    locked_OOS_policy: str
    embargo_policy: str
    warmup_policy: str
    minimum_signal_count: int
    minimum_trade_count: int
    success_criteria: tuple[str, ...]
    failure_criteria: tuple[str, ...]
    required_evidence_families: tuple[str, ...]
    requested_execution_tier: str
    content_identity: str


@dataclass(frozen=True, slots=True)
class DataRequirement:
    requirement_id: str
    experiment_id: str
    universe_plan_id: str
    universe_selector: str
    resolved_instrument_ids: tuple[str, ...]
    instrument_requirements: tuple[str, ...]
    timeframe: str
    base_timeframe: str
    required_timeframes: tuple[str, ...]
    required_fields: tuple[str, ...]
    required_history_start: str
    required_history_end: str
    required_history_span: str
    minimum_rows: int
    minimum_rows_per_asset: int
    minimum_assets: int
    target_assets: int
    minimum_common_history: str
    requested_execution_tier: str
    minimum_history_span: str
    minimum_expected_signals: int
    minimum_expected_trades: int
    minimum_validation_rows: int
    minimum_locked_oos_rows: int
    minimum_locked_oos_activity: int
    validation_requirement: str
    locked_oos_requirement: str
    embargo_requirement: str
    warmup_requirement: str
    required_source_quality: str
    required_identity_status: str
    required_cost_model: str
    required_slippage_model: str
    point_in_time_requirement: str
    corporate_action_requirement: str
    session_calendar_requirement: str
    PIT_requirement: str
    cost_data_requirement: str
    slippage_data_requirement: str
    regime_context_requirement: str
    quality_policy: str
    identity_policy: str
    preferred_sources: tuple[str, ...]
    content_identity: str


@dataclass(frozen=True, slots=True)
class CoverageDecision:
    decision: str
    coverage_decision: str
    requested_execution_tier: str
    admissible_execution_tier: str
    tier_downgrade_reasons: tuple[str, ...]
    reason_codes: tuple[str, ...]
    selected_data: dict[str, Any]
    approved_fetch: bool
    dataset_inventory: tuple[dict[str, Any], ...]
    content_identity: str


@dataclass(frozen=True, slots=True)
class UniversePlan:
    universe_plan_id: str
    experiment_id: str
    universe_type: str
    canonical_universe_id: str
    selection_date: str
    membership_effective_dates: tuple[str, ...]
    requested_assets: tuple[str, ...]
    resolved_assets: tuple[str, ...]
    excluded_assets: tuple[dict[str, str], ...]
    exclusion_reasons: tuple[str, ...]
    minimum_assets: int
    target_assets: int
    liquidity_requirements: str
    identity_requirements: str
    point_in_time_required: bool
    point_in_time_status: str
    sector_or_group_metadata_required: bool
    corporate_actions_required: bool
    session_calendar_required: bool
    survivorship_bias_status: str
    selection_bias_status: str
    final_universe_decision: str
    content_identity: str


@dataclass(frozen=True, slots=True)
class CoverageAssessment:
    coverage_assessment_id: str
    requirement_id: str
    universe_plan_id: str
    decision: str
    rows: tuple[dict[str, Any], ...]
    highest_admissible_tier: str
    content_identity: str


@dataclass(frozen=True, slots=True)
class AcquisitionPlan:
    acquisition_plan_id: str
    requirement_id: str
    source_ids: tuple[str, ...]
    instrument_ids: tuple[str, ...]
    base_timeframe: str
    start: str
    end: str
    expected_rows: int
    incremental: bool
    backfill: bool
    resample_targets: tuple[str, ...]
    corporate_action_actions: tuple[str, ...]
    identity_actions: tuple[str, ...]
    quality_checks: tuple[str, ...]
    request_batches: tuple[dict[str, Any], ...]
    rate_limit_budget: int
    retry_budget: int
    estimated_bytes: int
    estimated_calls: int
    expected_unlock: str
    source_selection_decision: str
    external_boundary: str | None
    reason_codes: tuple[str, ...]
    content_identity: str


@dataclass(frozen=True, slots=True)
class MechanismImplementationAlignment:
    predicted_observable: str
    strategy_observable: str
    signal_alignment: str
    holding_horizon_alignment: str
    universe_alignment: str
    regime_alignment: str
    control_alignment: str
    falsification_alignment: str
    alignment_status: str
    reason_codes: tuple[str, ...]
    content_identity: str


@dataclass(frozen=True, slots=True)
class ExperimentAdmissionDecision:
    hypothesis_id: str
    experiment_id: str
    strategy_spec_id: str
    data_requirement_id: str
    requested_tier: str
    admitted_tier: str
    source_quality: str
    identity_readiness: str
    history_sufficiency: str
    activity_sufficiency: str
    validation_sufficiency: str
    OOS_sufficiency: str
    cost_model_sufficiency: str
    slippage_model_sufficiency: str
    null_control_readiness: str
    stability_readiness: str
    fragility_readiness: str
    outlier_readiness: str
    requested_tier_not_met: bool
    empirical_campaign_created: bool
    smoke_execution_created: bool
    mechanism_learning_allowed: bool
    decision: str
    reason_codes: tuple[str, ...]
    content_identity: str


@dataclass(frozen=True, slots=True)
class CampaignEvidence:
    campaign_id: str
    experiment_id: str
    strategy_spec_id: str
    execution_tier: str
    empirical: bool
    backtest_result: dict[str, Any]
    data_plan: dict[str, Any]
    content_identity: str


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    assessment_id: str
    hypothesis_id: str
    experiment_id: str
    campaign_id: str
    execution_tier: str
    empirical: bool
    evidence_grade: str
    prediction_tested: str
    supporting_evidence: tuple[str, ...]
    contradicting_evidence: tuple[str, ...]
    inconclusive_evidence: tuple[str, ...]
    null_presence: str
    null_applicability: str
    null_sufficiency: str
    null_outcome: str
    mechanism_support_outcome: str
    OOS_presence: str
    OOS_sufficiency: str
    OOS_outcome: str
    cost_presence: str
    cost_sufficiency: str
    slippage_presence: str
    slippage_sufficiency: str
    cost_effect: str
    activity_effect: str
    regime_effect: str
    asset_effect: str
    fragility_effect: str
    outlier_effect: str
    confidence_update: str
    prior_adjustment_allowed: bool
    prior_adjustment_basis: str
    qualifying_evidence_refs: tuple[str, ...]
    terminal_disposition: str
    reason_codes: tuple[str, ...]
    content_identity: str


@dataclass(frozen=True, slots=True)
class ResearchLesson:
    lesson_id: str
    hypothesis_id: str
    experiment_id: str
    strategy_spec_id: str
    campaign_id: str
    lesson_type: str
    terminal_disposition: str
    mechanism_supported: str
    mechanism_contradicted: str
    decisive_evidence: tuple[str, ...]
    unresolved_uncertainty: tuple[str, ...]
    failure_mode: str
    actionable_cause: str
    non_actionable_cause: str
    do_not_repeat: tuple[str, ...]
    generator_constraints: tuple[str, ...]
    new_falsification_requirements: tuple[str, ...]
    prior_adjustment_allowed: bool
    prior_adjustment_basis: str
    prior_adjustments: tuple[str, ...]
    recommended_next_question: str
    supporting_artifact_refs: tuple[str, ...]
    content_identity: str


@dataclass(frozen=True, slots=True)
class RunBudgetUsage:
    observation_snapshots: int = 0
    raw_hypotheses: int = 0
    critiques: int = 0
    rewrites: int = 0
    scorecards: int = 0
    selected_hypotheses: int = 0
    compiled_experiments: int = 0
    strategy_specs: int = 0
    data_refresh_retries: int = 0
    campaigns_executed: int = 0
    lessons_written: int = 0


class ObservationBuilder(Protocol):
    def build(self, context: DiscoveryContext) -> ObservationSnapshot: ...


class HypothesisProposalProvider(Protocol):
    def propose(
        self,
        observation: ObservationSnapshot,
        memory: dict[str, Any],
        budget: int,
    ) -> list[MechanisticHypothesis]: ...


class HypothesisCritic(Protocol):
    def critique(
        self,
        hypothesis: MechanisticHypothesis,
        observation: ObservationSnapshot,
        memory: dict[str, Any],
    ) -> HypothesisCritique: ...


class HypothesisRewriter(Protocol):
    def revise(
        self,
        hypothesis: MechanisticHypothesis,
        critique: HypothesisCritique,
    ) -> MechanisticHypothesis: ...


class HypothesisEvaluator(Protocol):
    def evaluate(
        self,
        hypothesis: MechanisticHypothesis,
        critique: HypothesisCritique,
        context: ObservationSnapshot,
    ) -> HypothesisScorecard: ...


class ExperimentPlanner(Protocol):
    def plan(self, hypothesis: MechanisticHypothesis, *, requested_execution_tier: str) -> ExperimentContract: ...


class EvidenceEvaluator(Protocol):
    def evaluate(
        self,
        experiment: ExperimentContract,
        campaign_evidence: CampaignEvidence,
        admission: ExperimentAdmissionDecision,
    ) -> EvidenceAssessment: ...


class LessonCompressor(Protocol):
    def compress(
        self,
        assessment: EvidenceAssessment,
        prior_memory: dict[str, Any],
    ) -> ResearchLesson: ...
