from __future__ import annotations

from typing import Any


def build_discovery_view(observation: Any) -> dict[str, Any]:
    return {
        "observation_snapshot_id": observation.observation_snapshot_id,
        "market_diagnostics": observation.market_diagnostics,
        "regime_diagnostics": observation.regime_diagnostics,
        "cross_asset_diagnostics": observation.cross_asset_diagnostics,
        "data_coverage": observation.data_coverage,
        "source_quality": observation.source_quality,
        "identity_readiness": observation.identity_readiness,
        "mechanism_coverage": observation.mechanism_coverage,
        "behavior_family_coverage": observation.behavior_family_coverage,
        "primitive_inventory": observation.primitive_inventory,
        "executor_inventory": observation.executor_inventory,
        "relevant_research_memory": observation.relevant_research_memory,
        "active_contradictions": observation.active_contradictions,
        "resolved_contradictions": observation.resolved_contradictions,
        "content_identity": observation.content_identity,
    }


def build_validation_view(*, experiment_id: str, strategy_spec_id: str, dataset_id: str) -> dict[str, Any]:
    return {
        "experiment_id": experiment_id,
        "strategy_spec_id": strategy_spec_id,
        "dataset_id": dataset_id,
        "access_policy": "post_preregistration_only",
    }


def build_locked_oos_view(*, experiment_id: str, strategy_spec_id: str) -> dict[str, Any]:
    return {
        "experiment_id": experiment_id,
        "strategy_spec_id": strategy_spec_id,
        "access_policy": "canonical_orchestrator_only",
    }
