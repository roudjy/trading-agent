from __future__ import annotations

from pathlib import Path

from research import qre_behavior_catalog as catalog


def test_behavior_catalog_contains_canonical_families() -> None:
    behavior_ids = [behavior.behavior_id for behavior in catalog.list_behavior_families()]
    assert behavior_ids == [
        "trend_continuation",
        "pullback_continuation",
        "volatility_compression_breakout",
        "relative_strength",
        "post_shock_stabilization",
        "index_regime_filter",
        "mean_reversion",
        "momentum_acceleration",
        "defensive_rotation",
        "liquidity_stress_response",
    ]


def test_behavior_catalog_is_deterministic() -> None:
    payload_1 = [behavior.to_payload() for behavior in catalog.list_behavior_families()]
    payload_2 = [behavior.to_payload() for behavior in catalog.list_behavior_families()]
    assert payload_1 == payload_2


def test_unknown_behavior_lookup_fails_closed() -> None:
    try:
        catalog.get_behavior_family("unknown_behavior")
    except KeyError as exc:
        assert "unknown behavior_id" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected KeyError")


def test_catalog_source_has_no_aapl_or_nvda_hardcoding() -> None:
    source = Path(catalog.__file__).read_text(encoding="utf-8")
    assert "AAPL" not in source
    assert "NVDA" not in source

