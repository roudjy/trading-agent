"""Tests for v3.15.3 strategy failure taxonomy (closed canonical codes)."""

from __future__ import annotations

import pytest

from research.strategy_failure_taxonomy import (
    CANONICAL_FAILURE_CODES,
    STRATEGY_SPECIFIC_ALIASES,
    UnknownFailureCodeError,
    canonicalize,
    is_canonical,
    list_aliases_for,
)


def test_canonical_codes_match_v3_15_3_spec() -> None:
    expected = (
        "insufficient_trades",
        "cost_fragile",
        "parameter_fragile",
        "asset_singleton",
        "oos_collapse",
        "no_baseline_edge",
        "overtrading",
        "drawdown_unacceptable",
        "liquidity_sensitive",
        "baseline_underperform",
    )
    assert CANONICAL_FAILURE_CODES == expected


def test_is_canonical_true_for_each_code() -> None:
    for code in CANONICAL_FAILURE_CODES:
        assert is_canonical(code) is True


def test_is_canonical_false_for_unknown() -> None:
    assert is_canonical("totally_made_up_code") is False


def test_canonicalize_returns_canonical_unchanged() -> None:
    for code in CANONICAL_FAILURE_CODES:
        assert canonicalize(code) == code


def test_canonicalize_resolves_strategy_specific_aliases() -> None:
    for raw, canonical in STRATEGY_SPECIFIC_ALIASES.items():
        assert canonicalize(raw) == canonical


def test_canonicalize_unknown_raises_typed_error() -> None:
    with pytest.raises(UnknownFailureCodeError):
        canonicalize("definitely_not_a_known_code")


def test_every_alias_targets_canonical_code() -> None:
    for raw, canonical in STRATEGY_SPECIFIC_ALIASES.items():
        assert canonical in CANONICAL_FAILURE_CODES, (
            f"alias {raw!r} -> {canonical!r} which is not canonical"
        )


def test_list_aliases_for_returns_known_aliases() -> None:
    assert "trend_pullback_cost_fragile" in list_aliases_for("cost_fragile")
    assert "trend_pullback_parameter_fragile" in list_aliases_for(
        "parameter_fragile"
    )


def test_list_aliases_for_unknown_canonical_raises() -> None:
    with pytest.raises(UnknownFailureCodeError):
        list_aliases_for("not_a_canonical_code")


def test_no_alias_collides_with_canonical_code() -> None:
    """An alias must not also be a canonical code (closed surface)."""
    for raw in STRATEGY_SPECIFIC_ALIASES:
        assert raw not in CANONICAL_FAILURE_CODES, (
            f"alias key {raw!r} clashes with a canonical code"
        )
