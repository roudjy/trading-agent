from __future__ import annotations

from pathlib import Path

import pytest

from packages.qre_research import canonical_contracts
from packages.qre_research.candidate_planning_bridge import (
    CandidatePlanningBridgeError,
    candidate_to_planning_bundle,
    candidate_to_strategy_spec,
    preset_spec_to_campaign_spec,
    strategy_spec_to_preset_spec,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _candidate() -> dict[str, object]:
    return {
        "canonical_name": "CandidateSpec",
        "schema_version": 1,
        "candidate_id": "cand_123",
        "parent_contract_id": "ric_123",
        "signal_definition": {"lookback_window": 60, "return_basis": "adjusted_return"},
        "selection_rule": {"rank": "top", "count": 3},
        "rebalance_rule": {"every_n_trading_days": 20},
        "holding_period": {"trading_days": 20},
        "benchmark": {"kind": "equal_weight_universe"},
        "research_only": True,
        "screening_only": True,
        "not_trade_signal": True,
        "provenance": {"source": "fixture"},
        "safety": {"trading_authority": False},
    }


def test_canonical_candidate_to_strategy_spec() -> None:
    strategy = candidate_to_strategy_spec(_candidate())

    assert strategy["canonical_name"] == "StrategySpec"
    assert str(strategy["strategy_spec_id"]).startswith("strat_")
    assert strategy["candidate_id"] == "cand_123"
    assert strategy["safety"]["trading_authority"] is False


def test_strategy_spec_to_preset_spec() -> None:
    strategy = candidate_to_strategy_spec(_candidate())

    preset = strategy_spec_to_preset_spec(strategy)

    assert preset["canonical_name"] == "PresetSpec"
    assert str(preset["preset_id"]).startswith("preset_")
    assert preset["execution_tier"] == "research_screening_only"
    assert preset["safety"]["creates_presets"] is False


def test_preset_spec_to_campaign_spec() -> None:
    preset = strategy_spec_to_preset_spec(candidate_to_strategy_spec(_candidate()))

    campaign = preset_spec_to_campaign_spec(preset)

    assert campaign["canonical_name"] == "CampaignSpec"
    assert str(campaign["campaign_spec_id"]).startswith("campaign_")
    assert campaign["budget"]["max_parameter_variants"] == 1
    assert campaign["budget"]["requires_null_controls"] is True
    assert campaign["safety"]["runs_campaign"] is False


def test_planning_bundle_is_deterministic() -> None:
    assert candidate_to_planning_bundle(_candidate()) == candidate_to_planning_bundle(_candidate())


def test_required_field_failure() -> None:
    bad = _candidate()
    bad.pop("signal_definition")

    with pytest.raises(CandidatePlanningBridgeError, match="missing_required_fields"):
        candidate_to_strategy_spec(bad)


def test_provider_leakage_failure() -> None:
    bad = _candidate()
    bad["selection_rule"] = {"provider": "tiingo"}

    with pytest.raises(CandidatePlanningBridgeError, match="provider_leakage"):
        candidate_to_strategy_spec(bad)


def test_no_registry_or_frozen_contract_mutation() -> None:
    registry = REPO_ROOT / "research" / "registry.py"
    before = {"research/registry.py": registry.read_bytes()} | {
        path: (REPO_ROOT / path).read_bytes()
        for path in canonical_contracts.FROZEN_LEGACY_OUTPUTS
    }

    candidate_to_planning_bundle(_candidate())

    after = {"research/registry.py": registry.read_bytes()} | {
        path: (REPO_ROOT / path).read_bytes()
        for path in canonical_contracts.FROZEN_LEGACY_OUTPUTS
    }
    assert after == before


def test_no_live_paper_shadow_risk_broker_execution_authority() -> None:
    bundle = candidate_to_planning_bundle(_candidate())

    for payload in bundle.values():
        safety = payload["safety"]
        assert safety["trading_authority"] is False
        assert safety["validation_authority"] is False
        assert safety["paper_authority"] is False
        assert safety["shadow_authority"] is False
        assert safety["live_authority"] is False
        assert safety["runs_screening"] is False
