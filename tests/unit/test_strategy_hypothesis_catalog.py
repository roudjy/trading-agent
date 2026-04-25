"""Tests for v3.15.3 strategy hypothesis catalog.

Pins the closed-status enum, the exactly-one-active_discovery hard
invariant, deterministic payload ordering, and the family bridge to
``research.registry.STRATEGIES``.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from research._sidecar_io import serialize_canonical
from research.registry import STRATEGIES
from research.strategy_hypothesis_catalog import (
    ALPHA_ELIGIBLE_STATUSES,
    CATALOG_SCHEMA_VERSION,
    CLOSED_STATUSES,
    COST_CLASSES,
    HYPOTHESIS_CATALOG_VERSION,
    HypothesisCatalogError,
    STRATEGY_HYPOTHESIS_CATALOG,
    StrategyHypothesis,
    _validate_catalog,
    build_catalog_payload,
    get_by_family,
    get_by_id,
    list_active_discovery,
    list_by_status,
)


# Frozen reference timestamp for determinism + byte-identity checks.
_T = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)


def test_status_enum_is_closed_set() -> None:
    assert CLOSED_STATUSES == (
        "active_discovery",
        "planned",
        "disabled",
        "diagnostic",
    )
    for hyp in STRATEGY_HYPOTHESIS_CATALOG:
        assert hyp.status in CLOSED_STATUSES


def test_alpha_eligible_statuses_match_spec() -> None:
    assert ALPHA_ELIGIBLE_STATUSES == ("active_discovery",)


def test_cost_classes_closed_set() -> None:
    assert COST_CLASSES == ("low", "medium", "high")
    for hyp in STRATEGY_HYPOTHESIS_CATALOG:
        assert hyp.cost_class in COST_CLASSES


def test_at_least_one_active_discovery_invariant() -> None:
    """v3.15.4 relaxed: >= 1 active_discovery (was == 1 in v3.15.3)."""
    actives = list_active_discovery()
    assert len(actives) >= 1
    assert "trend_pullback_v1" in {h.hypothesis_id for h in actives}


def test_planned_disabled_diagnostic_present() -> None:
    statuses = {h.status for h in STRATEGY_HYPOTHESIS_CATALOG}
    assert {"active_discovery", "planned", "disabled", "diagnostic"} <= statuses


def test_dynamic_pairs_is_disabled_branchpoint() -> None:
    hyp = get_by_family("dynamic_pairs")
    assert hyp.status == "disabled"


def test_regime_diagnostics_is_diagnostic() -> None:
    hyp = get_by_family("regime_diagnostics")
    assert hyp.status == "diagnostic"
    # Diagnostic entries must carry no eligible alpha campaign types.
    assert hyp.eligible_campaign_types == ()


def test_atr_adaptive_trend_planned_metadata_only() -> None:
    hyp = get_by_family("atr_adaptive_trend")
    assert hyp.status == "planned"
    assert hyp.eligible_campaign_types == ()


def test_volatility_compression_breakout_planned_metadata_only() -> None:
    hyp = get_by_family("volatility_compression_breakout")
    assert hyp.status == "planned"
    assert hyp.eligible_campaign_types == ()


def test_active_discovery_bridges_to_enabled_registry_strategy() -> None:
    hyp = list_active_discovery()[0]
    matching = [
        s for s in STRATEGIES
        if s.get("strategy_family") == hyp.strategy_family
        and s.get("enabled", True)
    ]
    assert matching, "active_discovery must bridge to an enabled strategy"


def test_get_by_id_returns_correct_hypothesis() -> None:
    hyp = get_by_id("trend_pullback_v1")
    assert hyp.strategy_family == "trend_pullback"


def test_get_by_id_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_by_id("nonexistent_v999")


def test_get_by_family_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_by_family("nonexistent_family")


def test_list_by_status_filters_correctly() -> None:
    planned = list_by_status("planned")
    assert {h.hypothesis_id for h in planned} == {
        "atr_adaptive_trend_v0",
        "volatility_compression_breakout_v0",
    }


def test_payload_pin_block_invariants() -> None:
    payload = build_catalog_payload(generated_at_utc=_T, git_revision="abc123")
    assert payload["schema_version"] == CATALOG_SCHEMA_VERSION
    assert payload["live_eligible"] is False
    assert payload["authoritative"] is False
    assert payload["diagnostic_only"] is True
    assert payload["hypothesis_catalog_version"] == HYPOTHESIS_CATALOG_VERSION


def test_payload_hypothesis_ids_sorted_for_determinism() -> None:
    payload = build_catalog_payload(generated_at_utc=_T, git_revision="abc")
    ids = [h["hypothesis_id"] for h in payload["hypotheses"]]
    assert ids == sorted(ids)


def test_payload_byte_identical_across_runs() -> None:
    p1 = build_catalog_payload(generated_at_utc=_T, git_revision="rev1")
    p2 = build_catalog_payload(generated_at_utc=_T, git_revision="rev1")
    assert serialize_canonical(p1) == serialize_canonical(p2)


def test_validate_catalog_rejects_zero_active_discovery() -> None:
    """v3.15.4 strict: catalog with no active_discovery is invalid."""
    no_actives = tuple(
        StrategyHypothesis(
            hypothesis_id=h.hypothesis_id,
            strategy_family=h.strategy_family,
            status="planned" if h.status == "active_discovery" else h.status,
            description=h.description,
            feature_dependencies=h.feature_dependencies,
            parameter_schema=h.parameter_schema,
            default_parameter_grid=h.default_parameter_grid,
            eligible_campaign_types=()
            if h.status == "active_discovery"
            else h.eligible_campaign_types,
            expected_failure_modes=h.expected_failure_modes,
            baseline_reference=h.baseline_reference,
            cost_class=h.cost_class,
            policy_metadata=dict(h.policy_metadata),
        )
        for h in STRATEGY_HYPOTHESIS_CATALOG
    )
    with pytest.raises(HypothesisCatalogError):
        _validate_catalog(no_actives)


def test_validate_catalog_active_discovery_must_have_grid() -> None:
    """v3.15.4 strict: active_discovery with empty grid is invalid."""
    bad_active = StrategyHypothesis(
        hypothesis_id="needs_grid_v0",
        strategy_family="trend_pullback",  # bridges to existing registry entry
        status="active_discovery",
        description="x",
        feature_dependencies=(),
        parameter_schema={"x": {"type": "int"}},
        default_parameter_grid=(),  # offending: empty
        eligible_campaign_types=("daily_primary",),
        expected_failure_modes=(),
        baseline_reference=None,
        cost_class="low",
    )
    others = tuple(
        h for h in STRATEGY_HYPOTHESIS_CATALOG
        if h.status != "active_discovery"
    )
    with pytest.raises(HypothesisCatalogError):
        _validate_catalog(others + (bad_active,))


def test_validate_catalog_active_discovery_must_have_eligible_types() -> None:
    """v3.15.4 strict: active_discovery without eligible_campaign_types
    is invalid."""
    bad_active = StrategyHypothesis(
        hypothesis_id="needs_eligible_v0",
        strategy_family="trend_pullback",
        status="active_discovery",
        description="x",
        feature_dependencies=(),
        parameter_schema={"x": {"type": "int"}},
        default_parameter_grid=({"x": 1},),
        eligible_campaign_types=(),  # offending: empty
        expected_failure_modes=(),
        baseline_reference=None,
        cost_class="low",
    )
    others = tuple(
        h for h in STRATEGY_HYPOTHESIS_CATALOG
        if h.status != "active_discovery"
    )
    with pytest.raises(HypothesisCatalogError):
        _validate_catalog(others + (bad_active,))


def test_validate_catalog_non_active_must_have_empty_eligible() -> None:
    """v3.15.4 strict: planned/disabled/diagnostic with non-empty
    eligible_campaign_types is dead-eligibility noise."""
    bad_planned = StrategyHypothesis(
        hypothesis_id="dead_eligibility_v0",
        strategy_family="dead_family",
        status="planned",
        description="x",
        feature_dependencies=(),
        parameter_schema={},
        default_parameter_grid=(),
        eligible_campaign_types=("daily_primary",),  # offending
        expected_failure_modes=(),
        baseline_reference=None,
        cost_class="low",
    )
    with pytest.raises(HypothesisCatalogError):
        _validate_catalog(STRATEGY_HYPOTHESIS_CATALOG + (bad_planned,))


def test_validate_catalog_rejects_non_canonical_failure_code() -> None:
    """v3.15.4 strict: every expected_failure_mode must be canonical."""
    bad = StrategyHypothesis(
        hypothesis_id="non_canonical_code_v0",
        strategy_family="non_canonical_family",
        status="planned",
        description="x",
        feature_dependencies=(),
        parameter_schema={},
        default_parameter_grid=(),
        eligible_campaign_types=(),
        expected_failure_modes=("not_a_canonical_code",),  # offending
        baseline_reference=None,
        cost_class="low",
    )
    with pytest.raises(HypothesisCatalogError):
        _validate_catalog(STRATEGY_HYPOTHESIS_CATALOG + (bad,))


def test_validate_catalog_rejects_invalid_status() -> None:
    bad = (
        StrategyHypothesis(
            hypothesis_id="bad_status_v0",
            strategy_family="bad_status_family",
            status="cooldown",  # type: ignore[arg-type]  # not in CLOSED_STATUSES
            description="x",
            feature_dependencies=(),
            parameter_schema={},
            default_parameter_grid=(),
            eligible_campaign_types=(),
            expected_failure_modes=(),
            baseline_reference=None,
            cost_class="low",
        ),
    )
    with pytest.raises(HypothesisCatalogError):
        _validate_catalog(bad)


def test_validate_catalog_rejects_duplicate_hypothesis_id() -> None:
    a = STRATEGY_HYPOTHESIS_CATALOG[0]
    dup = StrategyHypothesis(
        hypothesis_id=a.hypothesis_id,  # collide
        strategy_family="other_family_for_dup",
        status="planned",
        description="dup",
        feature_dependencies=(),
        parameter_schema={},
        default_parameter_grid=(),
        eligible_campaign_types=(),
        expected_failure_modes=(),
        baseline_reference=None,
        cost_class="low",
    )
    with pytest.raises(HypothesisCatalogError):
        _validate_catalog(STRATEGY_HYPOTHESIS_CATALOG + (dup,))


def test_trend_pullback_v1_default_grid_at_most_8() -> None:
    hyp = get_by_id("trend_pullback_v1")
    assert len(hyp.default_parameter_grid) <= 8
    assert len(hyp.parameter_schema) == 3  # max 3 parameters per AGENTS.md


def test_trend_pullback_v1_feature_dependencies_complete() -> None:
    hyp = get_by_id("trend_pullback_v1")
    assert set(hyp.feature_dependencies) == {
        "ema_fast",
        "ema_slow",
        "rolling_volatility",
        "pullback_distance",
    }
