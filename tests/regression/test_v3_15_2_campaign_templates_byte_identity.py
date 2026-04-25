"""Regression: v3.15.3 must not perturb v3.15.2 campaign templates payload.

The v3.15.3 ``EligibilityPredicate`` extension adds
``require_hypothesis_status``. The dataclass overrides ``to_payload``
to *omit* the field when empty so the v3.15.2 baseline preset
templates remain byte-identical in
``research/campaign_templates_latest.v1.json``.

If this regression breaks, downstream consumers (frontend, audit
tooling, archived snapshots) that parsed the v3.15.2 sidecar will
silently fail or surface schema drift.
"""

from __future__ import annotations

from research._sidecar_io import serialize_canonical
from research.campaign_templates import (
    CAMPAIGN_TEMPLATES,
    EligibilityPredicate,
    get_template,
)


_LEGACY_BASELINE_PRESETS: tuple[str, ...] = (
    "trend_equities_4h_baseline",
    "trend_regime_filtered_equities_4h",
    "crypto_diagnostic_1h",
)
_LEGACY_TEMPLATE_TYPES: tuple[str, ...] = (
    "daily_primary",
    "daily_control",
    "survivor_confirmation",
    "paper_followup",
    "weekly_retest",
)


def _legacy_template_ids() -> list[str]:
    return [
        f"{ttype}__{preset}"
        for preset in _LEGACY_BASELINE_PRESETS
        for ttype in _LEGACY_TEMPLATE_TYPES
    ]


def test_legacy_baseline_eligibility_payloads_omit_hypothesis_status() -> None:
    for tid in _legacy_template_ids():
        tmpl = get_template(tid)
        payload = tmpl.eligibility.to_payload()
        assert "require_hypothesis_status" not in payload, (
            f"template {tid} must omit require_hypothesis_status when "
            f"empty (v3.15.2 byte-identity)"
        )


def test_legacy_baseline_template_payloads_carry_no_hypothesis_field() -> None:
    for tid in _legacy_template_ids():
        tmpl = get_template(tid)
        full_payload = tmpl.to_payload()
        assert "require_hypothesis_status" not in full_payload["eligibility"], (
            f"template {tid} eligibility leaked require_hypothesis_status"
        )


def test_default_eligibility_predicate_omits_hypothesis_field() -> None:
    """A default-constructed EligibilityPredicate must serialise to the
    v3.15.2 payload shape exactly (no hypothesis field)."""
    payload = EligibilityPredicate().to_payload()
    assert "require_hypothesis_status" not in payload
    expected_keys = {
        "require_preset_enabled",
        "forbid_excluded_from_daily_scheduler",
        "forbid_diagnostic_only",
        "require_preset_status",
        "require_parent_outcome",
    }
    assert set(payload.keys()) == expected_keys


def test_trend_pullback_template_does_carry_hypothesis_field() -> None:
    """Sanity check: the new active_discovery preset DOES surface the
    field (so it isn't accidentally suppressed by the omit-when-empty
    rule)."""
    tmpl = get_template("daily_primary__trend_pullback_crypto_1h")
    payload = tmpl.eligibility.to_payload()
    assert "require_hypothesis_status" in payload
    assert payload["require_hypothesis_status"] == ("active_discovery",)


def test_serialize_canonical_stable_for_legacy_templates() -> None:
    """Serialisation roundtrip stays bytewise stable across calls."""
    for tid in _legacy_template_ids():
        tmpl = get_template(tid)
        payload = tmpl.to_payload()
        a = serialize_canonical(payload)
        b = serialize_canonical(payload)
        assert a == b, f"non-deterministic serialisation for {tid}"


def test_legacy_template_count_unchanged() -> None:
    """v3.15.2 had 3 baseline presets * 5 template types = 15 templates.
    v3.15.3 adds trend_pullback_crypto_1h * 5 = 5 more, total 20."""
    assert len(CAMPAIGN_TEMPLATES) == 20
    legacy_count = sum(
        1 for t in CAMPAIGN_TEMPLATES
        if t.preset_name in _LEGACY_BASELINE_PRESETS
    )
    assert legacy_count == 15
