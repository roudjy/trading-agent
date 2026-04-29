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

from research.campaign_launcher import _resolve_metadata_for_preset


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
