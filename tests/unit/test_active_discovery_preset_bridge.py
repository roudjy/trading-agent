"""Cross-module bridge: every active_discovery hypothesis has a stable
preset binding (v3.15.4).

The bridge validator lives in ``research.strategy_hypothesis_catalog``
but is invoked explicitly by the orchestrator (NOT at module import)
to keep the catalog ↔ presets layering one-directional. These tests
pin both the happy path on the live catalog and the failure modes on
synthetic catalogs (so we never need to mutate the real catalog state
during testing).
"""

from __future__ import annotations

import pytest

from research.presets import PRESETS, ResearchPreset
from research.strategy_hypothesis_catalog import (
    HypothesisCatalogError,
    STRATEGY_HYPOTHESIS_CATALOG,
    StrategyHypothesis,
    list_active_discovery,
    validate_active_discovery_preset_bridges,
)


def test_live_catalog_has_full_active_discovery_bridges() -> None:
    """v3.15.4: trend_pullback_v1 and volatility_compression_breakout_v0
    both have stable+enabled presets binding via hypothesis_id."""
    validate_active_discovery_preset_bridges()


def test_every_active_discovery_has_stable_enabled_preset() -> None:
    """For each active hypothesis there exists ≥1 stable+enabled
    preset whose hypothesis_id matches."""
    actives = list_active_discovery()
    assert len(actives) >= 1
    for hyp in actives:
        bound = [
            p for p in PRESETS
            if p.hypothesis_id == hyp.hypothesis_id
            and p.status == "stable"
            and p.enabled
        ]
        assert bound, (
            f"active_discovery {hyp.hypothesis_id!r} has no "
            f"stable+enabled preset binding"
        )


def test_bridge_rejects_active_without_preset_binding() -> None:
    """Synthetic catalog: an active_discovery hypothesis with no
    matching preset.hypothesis_id must raise with the bridge: prefix."""
    orphan = StrategyHypothesis(
        hypothesis_id="orphan_v0",
        strategy_family="trend_pullback",  # bridges to existing registry
        status="active_discovery",
        description="x",
        feature_dependencies=("ema_fast",),
        parameter_schema={"x": {"type": "int"}},
        default_parameter_grid=({"x": 1},),
        eligible_campaign_types=("daily_primary",),
        expected_failure_modes=("insufficient_trades",),
        baseline_reference=None,
        cost_class="low",
    )
    # Drop trend_pullback_v1 (which already binds via the existing
    # preset) so only the orphan needs a binding.
    others = tuple(
        h for h in STRATEGY_HYPOTHESIS_CATALOG
        if h.hypothesis_id != "trend_pullback_v1"
    )
    synthetic = others + (orphan,)
    with pytest.raises(HypothesisCatalogError) as exc:
        validate_active_discovery_preset_bridges(catalog=synthetic)
    assert "bridge:" in str(exc.value)
    assert "orphan_v0" in str(exc.value)


def test_bridge_validator_imports_presets_lazily() -> None:
    """The bridge validator must import ``research.presets`` from
    inside the function body, not at module top — this keeps the
    catalog ↔ presets layering one-directional. Verified by source
    inspection (more robust than importlib.reload tricks, which would
    invalidate already-imported HypothesisCatalogError class identity
    and break sibling tests).
    """
    import inspect

    import research.strategy_hypothesis_catalog as cat_module

    src = inspect.getsource(cat_module.validate_active_discovery_preset_bridges)
    assert "from research.presets import" in src, (
        "validate_active_discovery_preset_bridges must lazy-import "
        "research.presets inside its body"
    )
    # And the module-level imports MUST NOT pull in research.presets.
    module_src = inspect.getsource(cat_module)
    top_level_lines = []
    for line in module_src.splitlines():
        # Stop at first function definition; module-level statements
        # all live above it.
        if line.startswith("def ") or line.startswith("class "):
            break
        top_level_lines.append(line)
    top_level = "\n".join(top_level_lines)
    assert "from research.presets" not in top_level, (
        "research.presets must NOT be imported at catalog module top "
        "level"
    )


def test_bridge_skips_planned_disabled_diagnostic_rows() -> None:
    """Only active_discovery hypotheses are checked; planned/disabled/
    diagnostic without bindings are fine."""
    # The live catalog has multi_asset_trend_sleeve_v0 +
    # cross_sectional_momentum_v0 as planned with no preset bindings.
    # Bridge validator must accept this.
    validate_active_discovery_preset_bridges()
    # And explicitly: those hypotheses indeed have no binding.
    for planned_id in (
        "multi_asset_trend_sleeve_v0",
        "cross_sectional_momentum_v0",
    ):
        bound = [p for p in PRESETS if p.hypothesis_id == planned_id]
        assert bound == [], (
            f"planned hypothesis {planned_id!r} unexpectedly has a "
            f"preset binding — was the catalog promoted?"
        )
