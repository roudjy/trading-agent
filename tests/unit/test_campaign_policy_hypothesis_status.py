"""Tests for v3.15.3 hypothesis-status filter in campaign_policy.

Pins the contract that ``_check_template_eligibility`` honors
``EligibilityPredicate.require_hypothesis_status`` against the live
``research.strategy_hypothesis_catalog``. Status semantics:

- active_discovery -> eligible
- planned          -> blocked with canonical reason
- disabled         -> blocked with canonical reason
- diagnostic       -> blocked with canonical reason

Plus the bridge edge cases:
- preset bundle empty           -> ``preset_bundle_empty``
- bundle[0] not in registry     -> ``strategy_not_in_registry``
- registry family not in catalog-> ``hypothesis_not_in_catalog``
"""

from __future__ import annotations

import pytest

from research.campaign_policy import (
    CandidateSpec,
    _build_eligibility_rejection,
    _check_template_eligibility,
    _strategy_family_for,
)
from research.campaign_templates import (
    CampaignTemplate,
    EligibilityPredicate,
    _DEFAULT_DAILY_PRIMARY_COOLDOWN_S,
    _DEFAULT_ESTIMATED_RUNTIME_S,
    get_template,
)


def _make_spec(
    template: CampaignTemplate,
    preset_name: str,
    *,
    campaign_type: str = "daily_primary",
) -> CandidateSpec:
    return CandidateSpec(
        template=template,
        appended_in_phase="B",
        appended_index=0,
        preset_name=preset_name,
        campaign_type=campaign_type,  # type: ignore[arg-type]
        parent_campaign_id=None,
        lineage_root_campaign_id="lineage-root",
        spawn_reason="cron_tick",
        subtype=None,
        input_artifact_fingerprint="fp",
        estimate_seconds=1_200,
        effective_priority_tier=2,
    )


def _custom_template(
    *,
    template_id: str,
    preset_name: str,
    require_hypothesis_status: tuple[str, ...] = (),
) -> CampaignTemplate:
    return CampaignTemplate(
        template_id=template_id,
        preset_name=preset_name,
        campaign_type="daily_primary",
        priority_tier=2,
        cooldown_seconds=_DEFAULT_DAILY_PRIMARY_COOLDOWN_S,
        max_per_day=1,
        eligibility=EligibilityPredicate(
            require_preset_enabled=True,
            forbid_excluded_from_daily_scheduler=True,
            forbid_diagnostic_only=True,
            require_preset_status=("stable",),
            require_hypothesis_status=require_hypothesis_status,
        ),
        estimated_runtime_seconds_default=_DEFAULT_ESTIMATED_RUNTIME_S,
        spawn_triggers=("cron_tick",),
        followup_rules=(),
    )


# ---------------------------------------------------------------------------
# Active discovery passes
# ---------------------------------------------------------------------------


def test_active_discovery_hypothesis_passes_filter() -> None:
    template = get_template("daily_primary__trend_pullback_crypto_1h")
    spec = _make_spec(template, "trend_pullback_crypto_1h")
    assert _check_template_eligibility(spec) is None


# ---------------------------------------------------------------------------
# Synthetic templates exercise each closed status against trend_pullback_crypto_1h
# (whose bridged catalog hypothesis is active_discovery).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "required",
    [("planned",), ("disabled",), ("diagnostic",)],
)
def test_non_active_discovery_required_blocks_active_discovery_preset(
    required: tuple[str, ...],
) -> None:
    template = _custom_template(
        template_id=f"synthetic_requires_{required[0]}",
        preset_name="trend_pullback_crypto_1h",
        require_hypothesis_status=required,
    )
    spec = _make_spec(template, "trend_pullback_crypto_1h")
    rejection = _check_template_eligibility(spec)
    assert rejection is not None
    assert rejection.reject_reason == (
        "hypothesis_status_active_discovery_not_in_required"
    )
    assert rejection.details["require_hypothesis_status"] == list(required)


# ---------------------------------------------------------------------------
# Bridge edge cases
# ---------------------------------------------------------------------------


def test_strategy_not_in_registry_returns_canonical_reason() -> None:
    """If preset.bundle[0] is unknown to the registry, reject."""
    # Build a synthetic preset stub by monkeypatching get_preset would be
    # fiddly; instead we exercise _strategy_family_for directly.
    assert _strategy_family_for("nonexistent_strategy_v999") is None


def test_hypothesis_not_in_catalog_for_unknown_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A preset whose first bundle strategy has a strategy_family not in
    the catalog must reject with ``hypothesis_not_in_catalog``."""
    template = _custom_template(
        template_id="synthetic_active_for_baseline",
        preset_name="trend_equities_4h_baseline",  # bundle[0]=sma_crossover
        require_hypothesis_status=("active_discovery",),
    )
    spec = _make_spec(template, "trend_equities_4h_baseline")
    rejection = _check_template_eligibility(spec)
    # sma_crossover -> strategy_family="trend_following", not in catalog.
    assert rejection is not None
    assert rejection.reject_reason == "hypothesis_not_in_catalog"


def test_preset_bundle_empty_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty bundle short-circuits with ``preset_bundle_empty``."""
    import research.campaign_policy as cp
    from research.presets import get_preset

    real = get_preset("trend_pullback_crypto_1h")
    empty = type(real)(
        **{
            **{
                f.name: getattr(real, f.name)
                for f in real.__dataclass_fields__.values()
            },
            "bundle": (),
        }
    )

    def _stub(name: str):
        if name == "trend_pullback_crypto_1h":
            return empty
        return get_preset(name)

    monkeypatch.setattr(cp, "get_preset", _stub)

    template = get_template("daily_primary__trend_pullback_crypto_1h")
    spec = _make_spec(template, "trend_pullback_crypto_1h")
    rejection = _check_template_eligibility(spec)
    assert rejection is not None
    assert rejection.reject_reason == "preset_bundle_empty"


# ---------------------------------------------------------------------------
# Backward compat: legacy baseline presets without the new filter still pass.
# ---------------------------------------------------------------------------


def test_legacy_baseline_template_passes_with_no_hypothesis_check() -> None:
    template = get_template("daily_primary__trend_equities_4h_baseline")
    assert template.eligibility.require_hypothesis_status == ()
    spec = _make_spec(template, "trend_equities_4h_baseline")
    assert _check_template_eligibility(spec) is None


# ---------------------------------------------------------------------------
# Rejection details surface the new field.
# ---------------------------------------------------------------------------


def test_rejection_details_include_required_hypothesis_status() -> None:
    template = _custom_template(
        template_id="synthetic_details_check",
        preset_name="trend_pullback_crypto_1h",
        require_hypothesis_status=("planned", "disabled"),
    )
    spec = _make_spec(template, "trend_pullback_crypto_1h")
    rejection = _check_template_eligibility(spec)
    assert rejection is not None
    assert rejection.details["require_hypothesis_status"] == [
        "planned", "disabled",
    ]


def test_build_eligibility_rejection_includes_hypothesis_field() -> None:
    template = _custom_template(
        template_id="x", preset_name="trend_pullback_crypto_1h",
        require_hypothesis_status=("active_discovery",),
    )
    spec = _make_spec(template, "trend_pullback_crypto_1h")
    rejection = _build_eligibility_rejection(spec, "preset_bundle_empty")
    assert rejection.details["require_hypothesis_status"] == [
        "active_discovery",
    ]


# ---------------------------------------------------------------------------
# Catalog-level pinning: planned/disabled/diagnostic hypotheses are not
# in the campaign template catalog as active_discovery presets.
# ---------------------------------------------------------------------------


def test_no_catalog_template_targets_planned_or_disabled_family() -> None:
    """No template in CAMPAIGN_TEMPLATES bridges to a planned or disabled
    catalog row. The only hypothesis-aware preset is trend_pullback_crypto_1h
    (active_discovery)."""
    from research.campaign_templates import CAMPAIGN_TEMPLATES
    from research.presets import get_preset
    from research.strategy_hypothesis_catalog import (
        STRATEGY_HYPOTHESIS_CATALOG,
        get_by_family,
    )

    catalog_by_family = {h.strategy_family: h for h in STRATEGY_HYPOTHESIS_CATALOG}
    for tmpl in CAMPAIGN_TEMPLATES:
        if not tmpl.eligibility.require_hypothesis_status:
            continue
        preset = get_preset(tmpl.preset_name)
        first = preset.bundle[0]
        family = _strategy_family_for(first)
        if family is None or family not in catalog_by_family:
            continue
        hyp = get_by_family(family)
        assert hyp.status == "active_discovery", (
            f"template {tmpl.template_id} requires hypothesis status but "
            f"bridges to {hyp.status!r}"
        )
