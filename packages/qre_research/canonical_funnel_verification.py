"""Static verification for the provider-agnostic QRE research funnel.

This module declares the expected canonical route and verifies synthetic
fixture traces against it. It does not run research, screen candidates, create
production artifacts, or grant synthesis/trading authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from packages.qre_research import architecture_registry as registry
from packages.qre_research import canonical_contracts
from packages.qre_research import maturity_gate

ObjectKind = Literal["canonical_object", "read_model"]

PROVIDER_SPECIFIC_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "adapter_module",
        "broker",
        "exchange",
        "provider",
        "provider_id",
        "source_id",
        "source_snapshot_id",
        "ticker",
        "tiingo_symbol",
    }
)


@dataclass(frozen=True, slots=True)
class FunnelStage:
    stage_id: str
    consumes: str
    emits: str
    output_kind: ObjectKind = "canonical_object"


@dataclass(frozen=True, slots=True)
class FixtureObject:
    object_type: str
    object_id: str
    fields: dict[str, object]
    fixture_only: bool = True


CANONICAL_FUNNEL_RULES: Final[tuple[FunnelStage, ...]] = (
    FunnelStage("hypothesis_admission", "Hypothesis", "ResearchInputContract"),
    FunnelStage("candidate_materialization", "ResearchInputContract", "CandidateSpec"),
    FunnelStage("strategy_specification", "CandidateSpec", "StrategySpec"),
    FunnelStage("strategy_ir_compilation", "StrategySpec", "StrategyIR"),
    FunnelStage("preset_planning", "StrategyIR", "PresetSpec"),
    FunnelStage("campaign_planning", "PresetSpec", "CampaignSpec"),
    FunnelStage("campaign_run", "CampaignSpec", "CampaignRun"),
    FunnelStage("screening_result", "CampaignRun", "ScreeningResult"),
    FunnelStage("evidence_packaging", "ScreeningResult", "EvidencePack"),
    FunnelStage("evidence_ledgering", "EvidencePack", "EvidenceLedger"),
    FunnelStage("disposition", "EvidenceLedger", "Disposition"),
    FunnelStage("feedback_recording", "Disposition", "FeedbackRecord"),
    FunnelStage("lesson_memory_update", "FeedbackRecord", "LessonMemory"),
    FunnelStage("research_memory_update", "LessonMemory", "ResearchMemory"),
    FunnelStage("next_hypothesis_batch", "ResearchMemory", "NextHypothesisBatch", "read_model"),
)


def canonical_funnel_order() -> tuple[str, ...]:
    return (
        CANONICAL_FUNNEL_RULES[0].consumes,
        *(stage.emits for stage in CANONICAL_FUNNEL_RULES),
    )


def _provider_specific_fields(fields: dict[str, object]) -> tuple[str, ...]:
    return tuple(sorted(set(fields) & PROVIDER_SPECIFIC_FIELD_NAMES))


def synthetic_fixture_trace() -> tuple[FixtureObject, ...]:
    return tuple(
        FixtureObject(
            object_type=object_type,
            object_id=f"fixture-{index:02d}-{object_type.lower()}",
            fields={
                "object_id": f"fixture-{index:02d}",
                "parent_object_type": canonical_funnel_order()[index - 1] if index else None,
                "mechanism": "synthetic trend persistence" if object_type == "Hypothesis" else None,
            },
        )
        for index, object_type in enumerate(canonical_funnel_order())
    )


def verify_stage_order(stages: tuple[FunnelStage, ...] = CANONICAL_FUNNEL_RULES) -> list[str]:
    errors: list[str] = []
    for prior, current in zip(stages, stages[1:]):
        if prior.emits != current.consumes:
            errors.append(f"stage_order_break:{prior.stage_id}:{current.stage_id}")
    known = set(canonical_contracts.contract_names())
    for stage in stages:
        if stage.consumes not in known:
            errors.append(f"unknown_stage_input:{stage.stage_id}:{stage.consumes}")
        if stage.output_kind == "canonical_object" and stage.emits not in known:
            errors.append(f"unknown_stage_output:{stage.stage_id}:{stage.emits}")
        if stage.output_kind == "read_model" and stage.emits in known:
            errors.append(f"read_model_redeclares_canonical_object:{stage.stage_id}:{stage.emits}")
    return errors


def verify_fixture_trace(
    trace: tuple[FixtureObject, ...] = synthetic_fixture_trace(),
    stages: tuple[FunnelStage, ...] = CANONICAL_FUNNEL_RULES,
) -> list[str]:
    errors = verify_stage_order(stages)
    expected_order = canonical_funnel_order()
    actual_order = tuple(item.object_type for item in trace)
    if actual_order != expected_order:
        errors.append("fixture_trace_order_mismatch")
    for item in trace:
        if not item.fixture_only:
            errors.append(f"fixture_claims_empirical_evidence:{item.object_type}:{item.object_id}")
        if item.object_type in canonical_contracts.PROVIDER_SPECIFIC_FORBIDDEN_OBJECTS:
            leaked = _provider_specific_fields(item.fields)
            if leaked:
                errors.append(f"provider_leakage:{item.object_type}:{','.join(leaked)}")
    return errors


def verify_architecture_boundaries() -> list[str]:
    errors: list[str] = []
    errors.extend(registry.validate_closed_world_audit())
    errors.extend(maturity_gate.validate_maturity_gate())
    for entry in registry.registry_entries():
        if entry.role == "observability_only" and entry.authority_flags["research_object_producer_authority"]:
            errors.append(f"observability_writes_research_object:{entry.id}")
        if entry.role == "fixture_only" and entry.authority_flags["empirical_evidence_authority"]:
            errors.append(f"fixture_claims_empirical_evidence:{entry.id}")
        if entry.role == "legacy_surface" and entry.canonical_objects_owned:
            errors.append(f"legacy_claims_canonical_ownership:{entry.id}")
    return errors


def verify_canonical_funnel() -> list[str]:
    return [
        *verify_fixture_trace(),
        *verify_architecture_boundaries(),
    ]


__all__ = [
    "CANONICAL_FUNNEL_RULES",
    "FixtureObject",
    "FunnelStage",
    "canonical_funnel_order",
    "synthetic_fixture_trace",
    "verify_architecture_boundaries",
    "verify_canonical_funnel",
    "verify_fixture_trace",
    "verify_stage_order",
]
