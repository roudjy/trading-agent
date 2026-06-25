"""v3.15.15.8 — registry metadata resolver tests.

The resolver in ``research.campaign_launcher._resolve_metadata_for_preset``
walks the preset catalog and the strategy-hypothesis catalog to populate
the four registry-side metadata fields added in v3.15.15.8:

- ``hypothesis_id``
- ``strategy_family``
- ``asset_class``
- ``universe``

These tests exercise the resolver in isolation. The launcher's
``_build_record`` is exercised separately via existing campaign-launcher
unit tests; here we pin the pure mapping.
"""

from __future__ import annotations

from research.campaign_launcher import (
    _build_record,
    _resolve_metadata_for_preset,
    _resolve_scope_metadata_for_preset,
)


def test_resolver_populates_all_four_fields_for_active_discovery_preset():
    h, f, a, u = _resolve_metadata_for_preset("trend_pullback_crypto_1h")
    assert h == "trend_pullback_v1"
    assert f == "trend_pullback"
    assert a == "crypto"
    assert u == ("BTC-EUR", "ETH-EUR", "SOL-EUR")


def test_resolver_populates_for_volatility_compression_1h():
    h, f, a, u = _resolve_metadata_for_preset(
        "vol_compression_breakout_crypto_1h"
    )
    assert h == "volatility_compression_breakout_v0"
    assert f == "volatility_compression_breakout"
    assert a == "crypto"
    assert len(u) >= 2


def test_resolver_populates_for_volatility_compression_4h():
    h, f, a, u = _resolve_metadata_for_preset(
        "vol_compression_breakout_crypto_4h"
    )
    assert h == "volatility_compression_breakout_v0"
    assert f == "volatility_compression_breakout"
    assert a == "crypto"


def test_resolver_handles_preset_without_hypothesis_id():
    """``crypto_diagnostic_1h`` has no hypothesis_id; asset_class+universe
    must still be populated, family stays None.
    """
    h, f, a, u = _resolve_metadata_for_preset("crypto_diagnostic_1h")
    assert h is None
    assert f is None
    assert a == "crypto"
    assert u == ("BTC-EUR", "ETH-EUR")


def test_resolver_handles_equity_universe():
    h, f, a, u = _resolve_metadata_for_preset("trend_equities_4h_baseline")
    assert h is None  # this preset has no hypothesis_id
    assert f is None
    assert a == "equity"
    assert "NVDA" in u


def test_resolver_returns_all_none_for_unknown_preset():
    h, f, a, u = _resolve_metadata_for_preset("not_a_real_preset_anywhere")
    assert h is None
    assert f is None
    assert a is None
    assert u == ()


def test_resolver_returns_empty_tuple_when_universe_empty():
    """Empty universe returns asset_class=None — preserves the existing
    ``_infer_asset_class`` semantics: no symbols → no class can be
    inferred. The four-tuple shape is always returned.
    """
    h, f, a, u = _resolve_metadata_for_preset("not_a_real_preset_anywhere")
    assert isinstance(u, tuple)
    assert u == ()


def test_resolver_universe_is_tuple_for_real_preset():
    """Even for known presets, ``universe`` must be a tuple — not a list
    — so the registry's frozen dataclass invariant is preserved before
    the value is asdict'd to JSON.
    """
    _, _, _, u = _resolve_metadata_for_preset("trend_pullback_crypto_1h")
    assert isinstance(u, tuple)


def test_resolver_is_pure_does_not_mutate_global_state():
    """Two calls return identical values."""
    a1 = _resolve_metadata_for_preset("trend_pullback_crypto_1h")
    a2 = _resolve_metadata_for_preset("trend_pullback_crypto_1h")
    assert a1 == a2


def test_scope_resolver_uses_canonical_preset_timeframe():
    h, f, a, timeframe, universe = (
        _resolve_scope_metadata_for_preset(
            "trend_pullback_equities_4h"
        )
    )

    assert h == "trend_pullback_v1"
    assert f == "trend_pullback"
    assert a == "equity"
    assert timeframe == "4h"
    assert "NVDA" in universe

    unknown = _resolve_scope_metadata_for_preset(
        "not_a_real_preset_anywhere"
    )
    assert unknown == (None, None, None, None, ())


def test_build_record_persists_timeframe_in_registry_payload():
    record = _build_record(
        campaign_id="campaign-test-001",
        template_id="daily_primary__trend_pullback_equities_4h",
        preset_name="trend_pullback_equities_4h",
        campaign_type="daily_primary",
        priority_tier=2,
        spawned_at_utc="2026-06-23T12:00:00Z",
        spawn_reason="unit_test",
        parent_campaign_id=None,
        lineage_root_campaign_id="campaign-test-001",
        input_artifact_fingerprint="fixture-fingerprint",
        estimate_seconds=1800,
        subtype=None,
    )

    assert record.timeframe == "4h"
    assert record.to_payload()["timeframe"] == "4h"
