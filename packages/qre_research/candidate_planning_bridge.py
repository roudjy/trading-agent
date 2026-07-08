"""Bridge canonical CandidateSpec records into planning contracts.

The bridge produces deterministic StrategySpec, PresetSpec, and CampaignSpec
payloads for research planning. It is schema-level only: no registry mutation,
campaign execution, screening, validation, promotion, or trading authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

SCHEMA_VERSION: Final[int] = 1
PROVIDER_TERMS: Final[tuple[str, ...]] = ("tiingo", "yfinance", "alpaca", "binance", "kraken", "coinbase")
SAFETY: Final[dict[str, bool]] = {
    "research_only": True,
    "planning_only": True,
    "creates_candidates": False,
    "creates_strategies": False,
    "creates_presets": False,
    "creates_campaigns": False,
    "mutates_registry": False,
    "runs_campaign": False,
    "runs_screening": False,
    "trading_authority": False,
    "validation_authority": False,
    "paper_authority": False,
    "shadow_authority": False,
    "live_authority": False,
}


class CandidatePlanningBridgeError(ValueError):
    """Raised when a canonical candidate cannot be safely planned."""


def _stable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable(value[key]) for key in sorted(value)}
    if isinstance(value, list | tuple):
        return [_stable(item) for item in value]
    return value


def _digest(value: Any) -> str:
    payload = json.dumps(_stable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _required(payload: Mapping[str, Any], fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if payload.get(field) in (None, "", [])]
    if missing:
        raise CandidatePlanningBridgeError("missing_required_fields:" + ",".join(missing))


def _assert_no_provider_leakage(payload: Any, path: tuple[str, ...] = ()) -> None:
    if "provenance" in path:
        return
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if any(term in str(key).lower() for term in PROVIDER_TERMS):
                raise CandidatePlanningBridgeError("provider_leakage:" + ".".join((*path, str(key))))
            _assert_no_provider_leakage(value, (*path, str(key)))
        return
    if isinstance(payload, list | tuple):
        for index, value in enumerate(payload):
            _assert_no_provider_leakage(value, (*path, str(index)))
        return
    if any(term in str(payload).lower() for term in PROVIDER_TERMS):
        raise CandidatePlanningBridgeError("provider_leakage:" + ".".join(path))


def validate_canonical_candidate(candidate: Mapping[str, Any]) -> None:
    _required(candidate, ("canonical_name", "candidate_id", "signal_definition", "selection_rule"))
    if candidate.get("canonical_name") != "CandidateSpec":
        raise CandidatePlanningBridgeError("not_candidate_spec")
    if candidate.get("trading_authority") is True or candidate.get("research_only") is False:
        raise CandidatePlanningBridgeError("unsafe_candidate_authority")
    _assert_no_provider_leakage(candidate)


def candidate_to_strategy_spec(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Map canonical CandidateSpec to provider-agnostic StrategySpec."""

    validate_canonical_candidate(candidate)
    semantics = {
        "signal_semantics": candidate["signal_definition"],
        "selection_semantics": candidate["selection_rule"],
        "rebalance_semantics": candidate.get("rebalance_rule", {}),
        "holding_semantics": candidate.get("holding_period", {}),
        "benchmark_semantics": candidate.get("benchmark", {}),
    }
    payload = {
        "canonical_name": "StrategySpec",
        "schema_version": SCHEMA_VERSION,
        "strategy_spec_id": "strat_" + _digest({"candidate_id": candidate["candidate_id"], "semantics": semantics}),
        "candidate_id": candidate["candidate_id"],
        "signal_semantics": semantics["signal_semantics"],
        "position_semantics": {
            "selection_rule": semantics["selection_semantics"],
            "holding_period": semantics["holding_semantics"],
        },
        "entry_semantics": {"derived_from": "candidate_selection_rule"},
        "exit_semantics": {"derived_from": "candidate_rebalance_and_holding_period"},
        "portfolio_semantics": {"benchmark": semantics["benchmark_semantics"]},
        "provenance": {"candidate_id": candidate["candidate_id"], "parent_contract_id": candidate.get("parent_contract_id")},
        "safety": dict(SAFETY),
    }
    _assert_no_provider_leakage(payload)
    return payload


def strategy_spec_to_preset_spec(strategy_spec: Mapping[str, Any]) -> dict[str, Any]:
    """Map StrategySpec to deterministic declarative PresetSpec."""

    _required(strategy_spec, ("canonical_name", "strategy_spec_id", "candidate_id", "signal_semantics", "position_semantics"))
    if strategy_spec.get("canonical_name") != "StrategySpec":
        raise CandidatePlanningBridgeError("not_strategy_spec")
    _assert_no_provider_leakage(strategy_spec)
    parameters = {
        "signal_semantics": strategy_spec["signal_semantics"],
        "position_semantics": strategy_spec["position_semantics"],
    }
    payload = {
        "canonical_name": "PresetSpec",
        "schema_version": SCHEMA_VERSION,
        "preset_id": "preset_" + _digest({"strategy_spec_id": strategy_spec["strategy_spec_id"], "parameters": parameters}),
        "strategy_spec_id": strategy_spec["strategy_spec_id"],
        "parameter_values": parameters,
        "execution_tier": "research_screening_only",
        "cost_model_ref": "research_cost_model_required",
        "slippage_model_ref": "research_slippage_model_required",
        "provenance": {"strategy_spec_id": strategy_spec["strategy_spec_id"]},
        "safety": dict(SAFETY),
    }
    _assert_no_provider_leakage(payload)
    return payload


def preset_spec_to_campaign_spec(preset_spec: Mapping[str, Any]) -> dict[str, Any]:
    """Map PresetSpec to bounded policy-inspectable CampaignSpec."""

    _required(preset_spec, ("canonical_name", "preset_id", "strategy_spec_id", "execution_tier"))
    if preset_spec.get("canonical_name") != "PresetSpec":
        raise CandidatePlanningBridgeError("not_preset_spec")
    _assert_no_provider_leakage(preset_spec)
    policy = {
        "max_windows": 3,
        "max_parameter_variants": 1,
        "requires_null_controls": True,
        "requires_cost_model": True,
        "screening_only": True,
    }
    payload = {
        "canonical_name": "CampaignSpec",
        "schema_version": SCHEMA_VERSION,
        "campaign_spec_id": "campaign_" + _digest({"preset_id": preset_spec["preset_id"], "policy": policy}),
        "preset_id": preset_spec["preset_id"],
        "screening_protocol": "canonical_research_screening_v1",
        "evidence_requirements": ["screening_metrics", "null_controls", "cost_and_slippage_notes"],
        "budget": policy,
        "null_controls": {"required": True, "minimum_iterations": 16},
        "stopping_rules": ["stop_on_missing_required_evidence", "stop_on_provider_leakage"],
        "provenance": {"preset_id": preset_spec["preset_id"], "strategy_spec_id": preset_spec["strategy_spec_id"]},
        "safety": dict(SAFETY),
    }
    _assert_no_provider_leakage(payload)
    return payload


def candidate_to_planning_bundle(candidate: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Build the full deterministic planning bundle for one canonical candidate."""

    strategy = candidate_to_strategy_spec(candidate)
    preset = strategy_spec_to_preset_spec(strategy)
    campaign = preset_spec_to_campaign_spec(preset)
    return {"strategy_spec": strategy, "preset_spec": preset, "campaign_spec": campaign}


__all__ = [
    "CandidatePlanningBridgeError",
    "SAFETY",
    "candidate_to_planning_bundle",
    "candidate_to_strategy_spec",
    "preset_spec_to_campaign_spec",
    "strategy_spec_to_preset_spec",
    "validate_canonical_candidate",
]
