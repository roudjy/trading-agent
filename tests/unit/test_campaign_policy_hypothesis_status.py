"""Tests for v3.15.3 hypothesis-status filter in campaign_policy.

Pins the contract that ``_check_template_eligibility`` honors
``EligibilityPredicate.require_hypothesis_status`` against the live
``research.strategy_hypothesis_catalog`` via the **explicit** preset
mapping ``preset.hypothesis_id``. Status semantics:

- active_discovery -> eligible
- planned          -> blocked with canonical reason
- disabled         -> blocked with canonical reason
- diagnostic       -> blocked with canonical reason

Bridge edge cases:
- preset.hypothesis_id missing  -> ``preset_missing_hypothesis_id``
- hypothesis_id not in catalog  -> ``hypothesis_not_in_catalog``

The legacy ``bundle[0] → registry → strategy_family`` walk has been
removed: presets opt in to hypothesis enforcement by setting
``hypothesis_id``, full stop.
"""

from __future__ import annotations

import pytest

from research.campaign_policy import (
    CandidateSpec,
    _build_eligibility_rejection,
    _check_template_eligibility,
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


def _clone_preset_with(
    preset_name: str,
    monkeypatch: pytest.MonkeyPatch,
    **overrides,
):
    """Replace ``research.campaign_policy.get_preset`` with a stub that
    returns a clone of ``preset_name`` carrying the given overrides.

    The stub falls back to the real ``get_preset`` for every other
    preset name so the rest of the policy chain is unaffected.
    """
    import research.campaign_policy as cp
    from research.presets import get_preset

    real = get_preset(preset_name)
    cloned = type(real)(
        **{
            **{
                f.name: getattr(real, f.name)
                for f in real.__dataclass_fields__.values()
            },
            **overrides,
        }
    )

    def _stub(name: str):
        if name == preset_name:
            return cloned
        return get_preset(name)

    monkeypatch.setattr(cp, "get_preset", _stub)
    return cloned


# ---------------------------------------------------------------------------
# Active discovery passes
# ---------------------------------------------------------------------------


def test_active_discovery_hypothesis_passes_filter() -> None:
    template = get_template("daily_primary__trend_pullback_crypto_1h")
    spec = _make_spec(template, "trend_pullback_crypto_1h")
    assert _check_template_eligibility(spec) is None


def test_trend_pullback_crypto_1h_carries_explicit_hypothesis_id() -> None:
    """Pin: the only v3.15.3 active_discovery preset carries the explicit
    bridge field. Failing this test means the preset → hypothesis mapping
    has drifted."""
    from research.presets import get_preset

    p = get_preset("trend_pullback_crypto_1h")
    assert p.hypothesis_id == "trend_pullback_v1"


# ---------------------------------------------------------------------------
# Synthetic templates exercise each closed status against trend_pullback_crypto_1h
# (whose explicit hypothesis_id resolves to active_discovery).
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
# New explicit-mapping rejections
# ---------------------------------------------------------------------------


def test_preset_without_hypothesis_id_rejects_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A preset that opts into hypothesis enforcement (template
    require_hypothesis_status non-empty) but has no ``hypothesis_id`` set
    must reject with ``preset_missing_hypothesis_id``. This is the new
    v3.15.3 explicit-mapping invariant."""
    _clone_preset_with(
        "trend_pullback_crypto_1h", monkeypatch, hypothesis_id=None
    )
    template = get_template("daily_primary__trend_pullback_crypto_1h")
    spec = _make_spec(template, "trend_pullback_crypto_1h")
    rejection = _check_template_eligibility(spec)
    assert rejection is not None
    assert rejection.reject_reason == "preset_missing_hypothesis_id"


def test_preset_hypothesis_id_not_in_catalog_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A preset whose ``hypothesis_id`` doesn't resolve in the catalog
    rejects with ``hypothesis_not_in_catalog``."""
    _clone_preset_with(
        "trend_pullback_crypto_1h",
        monkeypatch,
        hypothesis_id="not_a_real_hypothesis_v0",
    )
    template = get_template("daily_primary__trend_pullback_crypto_1h")
    spec = _make_spec(template, "trend_pullback_crypto_1h")
    rejection = _check_template_eligibility(spec)
    assert rejection is not None
    assert rejection.reject_reason == "hypothesis_not_in_catalog"


def test_planned_hypothesis_id_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit hypothesis_id pointing at a ``planned`` row is blocked
    by the active_discovery requirement."""
    _clone_preset_with(
        "trend_pullback_crypto_1h",
        monkeypatch,
        hypothesis_id="atr_adaptive_trend_v0",  # status=planned
    )
    template = get_template("daily_primary__trend_pullback_crypto_1h")
    spec = _make_spec(template, "trend_pullback_crypto_1h")
    rejection = _check_template_eligibility(spec)
    assert rejection is not None
    assert rejection.reject_reason == (
        "hypothesis_status_planned_not_in_required"
    )


def test_disabled_hypothesis_id_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``dynamic_pairs_v0`` is disabled — must reject."""
    _clone_preset_with(
        "trend_pullback_crypto_1h",
        monkeypatch,
        hypothesis_id="dynamic_pairs_v0",
    )
    template = get_template("daily_primary__trend_pullback_crypto_1h")
    spec = _make_spec(template, "trend_pullback_crypto_1h")
    rejection = _check_template_eligibility(spec)
    assert rejection is not None
    assert rejection.reject_reason == (
        "hypothesis_status_disabled_not_in_required"
    )


def test_diagnostic_hypothesis_id_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``regime_diagnostics_v1`` is diagnostic — must reject for any
    template that requires active_discovery."""
    _clone_preset_with(
        "trend_pullback_crypto_1h",
        monkeypatch,
        hypothesis_id="regime_diagnostics_v1",
    )
    template = get_template("daily_primary__trend_pullback_crypto_1h")
    spec = _make_spec(template, "trend_pullback_crypto_1h")
    rejection = _check_template_eligibility(spec)
    assert rejection is not None
    assert rejection.reject_reason == (
        "hypothesis_status_diagnostic_not_in_required"
    )


# ---------------------------------------------------------------------------
# Multi-strategy preset uses explicit hypothesis_id, not bundle[0]
# ---------------------------------------------------------------------------


def test_multi_strategy_preset_uses_explicit_hypothesis_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A multi-strategy preset can opt into hypothesis enforcement via
    its explicit ``hypothesis_id`` — the eligibility check must consult
    that field, not ``bundle[0]``. Pin: even though bundle[0] is
    ``sma_crossover`` (whose strategy_family ``trend_following`` is
    NOT in the catalog), the explicit hypothesis_id pointing at the
    active_discovery row makes the preset eligible."""
    _clone_preset_with(
        "trend_equities_4h_baseline",  # bundle starts with sma_crossover
        monkeypatch,
        hypothesis_id="trend_pullback_v1",  # active_discovery
    )
    template = _custom_template(
        template_id="synthetic_multi_strategy_active",
        preset_name="trend_equities_4h_baseline",
        require_hypothesis_status=("active_discovery",),
    )
    spec = _make_spec(template, "trend_equities_4h_baseline")
    assert _check_template_eligibility(spec) is None


# ---------------------------------------------------------------------------
# Backward compat: legacy baseline presets without the new filter still pass.
# ---------------------------------------------------------------------------


def test_legacy_baseline_template_passes_with_no_hypothesis_check() -> None:
    """The 3 legacy v3.15.2 baseline preset templates carry an empty
    ``require_hypothesis_status`` so the explicit-mapping check is never
    invoked. Their ``hypothesis_id`` stays None and that's fine."""
    template = get_template("daily_primary__trend_equities_4h_baseline")
    assert template.eligibility.require_hypothesis_status == ()
    spec = _make_spec(template, "trend_equities_4h_baseline")
    assert _check_template_eligibility(spec) is None


def test_legacy_presets_have_no_hypothesis_id_set() -> None:
    """Legacy presets MUST NOT set ``hypothesis_id`` (regression guard).
    If a future change inadvertently sets it on a legacy preset, this
    test fails so the change is reviewed deliberately."""
    from research.presets import get_preset

    for legacy_name in (
        "trend_equities_4h_baseline",
        "pairs_equities_daily_baseline",
        "trend_regime_filtered_equities_4h",
        "crypto_diagnostic_1h",
    ):
        assert get_preset(legacy_name).hypothesis_id is None, (
            f"legacy preset {legacy_name!r} unexpectedly has a hypothesis_id"
        )


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
    rejection = _build_eligibility_rejection(
        spec, "preset_missing_hypothesis_id"
    )
    assert rejection.details["require_hypothesis_status"] == [
        "active_discovery",
    ]


# ---------------------------------------------------------------------------
# Catalog-level pinning: planned/disabled/diagnostic hypotheses cannot
# be reached through any active_discovery-requiring template + matching
# preset.hypothesis_id chain.
# ---------------------------------------------------------------------------


def test_no_catalog_template_targets_planned_or_disabled_hypothesis() -> None:
    """For every template that requires hypothesis enforcement, the
    bridged preset.hypothesis_id (if set) must resolve to a status
    that is in the template's ``require_hypothesis_status`` set. This
    pins the v3.15.3 invariant: no template can spawn a planned /
    disabled / diagnostic hypothesis through the explicit mapping."""
    from research.campaign_templates import CAMPAIGN_TEMPLATES
    from research.presets import get_preset
    from research.strategy_hypothesis_catalog import get_by_id

    for tmpl in CAMPAIGN_TEMPLATES:
        if not tmpl.eligibility.require_hypothesis_status:
            continue
        preset = get_preset(tmpl.preset_name)
        if preset.hypothesis_id is None:
            # Will be rejected at eligibility time with
            # preset_missing_hypothesis_id — that is by design.
            continue
        hyp = get_by_id(preset.hypothesis_id)
        assert hyp.status in tmpl.eligibility.require_hypothesis_status, (
            f"template {tmpl.template_id} requires "
            f"{tmpl.eligibility.require_hypothesis_status} but its "
            f"preset's hypothesis_id resolves to status {hyp.status!r}"
        )
