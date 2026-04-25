"""Unit tests for the v3.10 preset catalog.

v3.11 additions: preset_class, rationale, expected_behavior,
falsification soft validation.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from research.presets import (
    PRESETS,
    ResearchPreset,
    daily_schedulable_presets,
    default_daily_preset,
    get_preset,
    hypothesis_metadata_issues,
    list_presets,
    preset_to_card,
    resolve_preset_bundle,
    validate_preset,
)


def test_five_presets_registered():
    """v3.15.3 adds ``trend_pullback_crypto_1h`` as the executable
    bridge for the active_discovery hypothesis catalog row. Original
    four v3.10/v3.11 presets remain in their original positions to
    preserve downstream consumers that snapshot the order."""
    assert [p.name for p in PRESETS] == [
        "trend_equities_4h_baseline",
        "pairs_equities_daily_baseline",
        "trend_regime_filtered_equities_4h",
        "trend_pullback_crypto_1h",
        "crypto_diagnostic_1h",
    ]


def test_default_daily_preset_is_trend_equities_4h_baseline():
    assert default_daily_preset().name == "trend_equities_4h_baseline"


def test_default_preset_bundle_is_small_and_orthogonal():
    preset = get_preset("trend_equities_4h_baseline")
    assert preset.bundle == ("sma_crossover", "breakout_momentum")
    # Management variants and ATR stubs must NOT be in the default bundle.
    assert "trend_pullback_tp_sl" not in preset.bundle
    assert "atr_breakout_STUB" not in preset.bundle
    assert "trend_pullback" in preset.optional_bundle
    assert preset.enabled is True
    assert preset.status == "stable"


def test_pairs_preset_is_planned_and_disabled():
    preset = get_preset("pairs_equities_daily_baseline")
    assert preset.enabled is False
    assert preset.status == "planned"
    assert preset.backlog_reason is not None
    assert "v3.11" in preset.backlog_reason


def test_regime_filtered_preset_is_trend_bundle_with_filter_not_bollinger_mr():
    preset = get_preset("trend_regime_filtered_equities_4h")
    assert preset.bundle == ("sma_crossover", "breakout_momentum")
    assert "bollinger_mr" not in preset.bundle
    assert "bollinger_regime" not in preset.bundle
    assert preset.regime_filter == "bollinger_regime_derived"
    assert preset.regime_modes == ("trend_only", "low_vol_only")


def test_crypto_diagnostic_preset_has_all_three_exclusion_flags():
    preset = get_preset("crypto_diagnostic_1h")
    assert preset.diagnostic_only is True
    assert preset.excluded_from_daily_scheduler is True
    assert preset.excluded_from_candidate_promotion is True


def test_resolve_preset_bundle_returns_registry_entries_only_for_enabled_presets():
    trend_preset = get_preset("trend_equities_4h_baseline")
    resolved = resolve_preset_bundle(trend_preset)
    assert [s["name"] for s in resolved] == ["sma_crossover", "breakout_momentum"]

    pairs_preset = get_preset("pairs_equities_daily_baseline")
    assert resolve_preset_bundle(pairs_preset) == []


def test_all_registered_presets_validate():
    for preset in PRESETS:
        assert validate_preset(preset) == [], (preset.name, validate_preset(preset))


def test_daily_schedulable_excludes_planned_and_diagnostic():
    schedulable = [p.name for p in daily_schedulable_presets()]
    assert "trend_equities_4h_baseline" in schedulable
    assert "trend_regime_filtered_equities_4h" in schedulable
    assert "pairs_equities_daily_baseline" not in schedulable  # disabled
    assert "crypto_diagnostic_1h" not in schedulable  # excluded flag


def test_preset_to_card_is_json_safe():
    import json
    card = preset_to_card(get_preset("crypto_diagnostic_1h"))
    blob = json.dumps(card)
    restored = json.loads(blob)
    assert restored["name"] == "crypto_diagnostic_1h"
    assert restored["diagnostic_only"] is True


def test_get_preset_unknown_raises_keyerror():
    with pytest.raises(KeyError, match="unknown preset"):
        get_preset("does_not_exist")


def test_validate_rejects_disabled_preset_without_backlog_reason():
    broken = ResearchPreset(
        name="broken",
        hypothesis="x",
        universe=("FOO",),
        timeframe="1h",
        bundle=("sma_crossover",),
        enabled=False,
        backlog_reason=None,
    )
    issues = validate_preset(broken)
    assert any("backlog_reason" in issue for issue in issues)


def test_validate_rejects_pair_identifiers_without_pairs_zscore_in_bundle():
    broken = ResearchPreset(
        name="broken-pairs",
        hypothesis="x",
        universe=("NVDA/AMD",),
        timeframe="1d",
        bundle=("sma_crossover",),
    )
    issues = validate_preset(broken)
    assert any("pair" in issue for issue in issues)


def test_validate_rejects_diagnostic_only_without_promotion_exclusion():
    broken = ResearchPreset(
        name="broken-diag",
        hypothesis="x",
        universe=("BTC-EUR",),
        timeframe="1h",
        bundle=("rsi",),
        diagnostic_only=True,
        excluded_from_candidate_promotion=False,
    )
    issues = validate_preset(broken)
    assert any("excluded_from_candidate_promotion" in issue for issue in issues)


def test_presets_are_frozen_dataclasses():
    preset = get_preset("trend_equities_4h_baseline")
    with pytest.raises(Exception):
        preset.name = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# v3.11 hypothesis metadata
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "preset_name",
    [
        "trend_equities_4h_baseline",
        "trend_regime_filtered_equities_4h",
        "crypto_diagnostic_1h",
    ],
)
def test_enabled_presets_carry_hypothesis_metadata(preset_name: str):
    """v3.11: every enabled preset has non-empty rationale /
    expected_behavior / falsification and a valid preset_class."""
    preset = get_preset(preset_name)
    assert preset.enabled is True
    assert preset.preset_class in {"baseline", "diagnostic", "experimental"}
    assert preset.rationale.strip(), preset_name
    assert preset.expected_behavior.strip(), preset_name
    assert preset.falsification, preset_name
    assert all(
        isinstance(item, str) and item.strip() for item in preset.falsification
    ), preset_name


def test_preset_class_distinguishes_research_role():
    assert get_preset("trend_equities_4h_baseline").preset_class == "baseline"
    assert get_preset("trend_regime_filtered_equities_4h").preset_class == "diagnostic"
    assert get_preset("crypto_diagnostic_1h").preset_class == "diagnostic"
    # disabled planned preset may remain experimental
    assert get_preset("pairs_equities_daily_baseline").preset_class == "experimental"


def test_hypothesis_metadata_missing_yields_soft_issues():
    """Emptying rationale / expected_behavior / falsification produces
    soft issues but never raises. validate_preset remains non-blocking
    for v3.11."""
    baseline = get_preset("trend_equities_4h_baseline")
    stripped = replace(
        baseline,
        rationale="",
        expected_behavior="",
        falsification=(),
    )
    issues = validate_preset(stripped)
    codes = "\n".join(issues)
    assert "hypothesis_metadata_missing: rationale is empty" in codes
    assert "hypothesis_metadata_missing: expected_behavior is empty" in codes
    assert "hypothesis_metadata_missing: falsification criteria empty" in codes


def test_hypothesis_metadata_issues_returns_only_v311_codes():
    baseline = get_preset("trend_equities_4h_baseline")
    stripped = replace(baseline, rationale="", expected_behavior="", falsification=())
    issues = hypothesis_metadata_issues(stripped)
    assert issues  # non-empty
    for issue in issues:
        assert issue.startswith("hypothesis_metadata_missing:")


def test_hypothesis_metadata_issues_empty_for_disabled_presets():
    pairs = get_preset("pairs_equities_daily_baseline")
    assert pairs.enabled is False
    # disabled presets short-circuit validate_preset; no hypothesis issues
    assert hypothesis_metadata_issues(pairs) == []


def test_preset_to_card_exposes_v311_fields():
    card = preset_to_card(get_preset("trend_equities_4h_baseline"))
    assert card["preset_class"] == "baseline"
    assert card["rationale"]
    assert card["expected_behavior"]
    assert isinstance(card["falsification"], list)
    assert card["falsification"]


# ---------------------------------------------------------------------------
# v3.15.1 — enablement_criteria + backend-side decision inference
# ---------------------------------------------------------------------------


def test_enablement_criteria_field_defaults_to_empty_tuple():
    baseline = get_preset("trend_equities_4h_baseline")
    assert baseline.enablement_criteria == ()


def test_pairs_preset_now_carries_full_research_metadata():
    pairs = get_preset("pairs_equities_daily_baseline")
    assert pairs.enabled is False
    assert pairs.status == "planned"
    assert pairs.rationale.strip()
    assert pairs.expected_behavior.strip()
    assert pairs.falsification and all(
        isinstance(item, str) and item.strip()
        for item in pairs.falsification
    )
    assert pairs.enablement_criteria and all(
        isinstance(item, str) and item.strip()
        for item in pairs.enablement_criteria
    )


def test_preset_to_card_exposes_enablement_criteria_and_decision():
    card = preset_to_card(get_preset("pairs_equities_daily_baseline"))
    assert isinstance(card["enablement_criteria"], list)
    assert card["enablement_criteria"]
    decision = card["decision"]
    assert decision["is_product_decision"] is True
    assert decision["kind"] == "disabled_planned"
    assert decision["requires_enablement"] is True
    assert decision["summary"].strip()


def test_enabled_stable_preset_decision_is_not_product_decision():
    card = preset_to_card(get_preset("trend_equities_4h_baseline"))
    decision = card["decision"]
    assert decision["is_product_decision"] is False
    assert decision["kind"] is None
    assert decision["requires_enablement"] is False


def test_diagnostic_only_preset_decision_kind_is_diagnostic_only():
    card = preset_to_card(get_preset("crypto_diagnostic_1h"))
    decision = card["decision"]
    assert decision["is_product_decision"] is True
    assert decision["kind"] == "diagnostic_only"
    assert decision["requires_enablement"] is False


def test_decision_block_is_json_safe():
    import json

    for preset in PRESETS:
        card = preset_to_card(preset)
        blob = json.dumps(card)
        restored = json.loads(blob)
        assert "decision" in restored
        assert "enablement_criteria" in restored


def test_qre_strict_preset_validation_env_flag(monkeypatch):
    """The opt-in env flag only flips runner behavior; validate_preset
    itself remains a pure function that always returns issues without
    raising."""
    from research.run_research import (
        _preset_validation_is_strict,
        PresetValidationError,
        _enforce_preset_validation,
    )

    class _StubTracker:
        def __init__(self) -> None:
            self.events: list[tuple[str, dict]] = []

        def emit_event(self, name: str, **kwargs) -> None:
            self.events.append((name, kwargs))

    baseline = get_preset("trend_equities_4h_baseline")
    stripped = replace(baseline, rationale="", expected_behavior="", falsification=())

    monkeypatch.delenv("QRE_STRICT_PRESET_VALIDATION", raising=False)
    assert _preset_validation_is_strict() is False
    tracker = _StubTracker()
    _enforce_preset_validation(stripped, tracker)  # soft path
    event_names = {name for name, _ in tracker.events}
    assert event_names == {"preset_validation_warning"}

    monkeypatch.setenv("QRE_STRICT_PRESET_VALIDATION", "1")
    assert _preset_validation_is_strict() is True
    tracker2 = _StubTracker()
    with pytest.raises(PresetValidationError):
        _enforce_preset_validation(stripped, tracker2)
    # even in strict mode the warning events still fire before the raise
    assert any(name == "preset_validation_warning" for name, _ in tracker2.events)
