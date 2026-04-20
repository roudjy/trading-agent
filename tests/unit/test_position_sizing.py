"""Unit tests for agent.backtesting.sizing primitives.

v3.5 status: the sizing module is scaffolded with no live consumers;
no Tier 1 strategy opts in. These tests pin the math, guards, and
regime-resolution semantics so the first thin strategy to opt in
(later phase) can do so without another architectural pass.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from agent.backtesting.sizing import (
    SIZING_REGIME_FIXED_UNIT,
    SIZING_REGIME_KELLY,
    SIZING_REGIME_VOLATILITY_TARGET,
    fixed_unit_size,
    kelly_fraction,
    resolve_sizing_spec,
    volatility_target_size,
)


def _series(values: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype=float)


def test_fixed_unit_size_is_identity_up_to_float_cast():
    signal = _series([-1.0, 0.0, 1.0, 1.0, -1.0])

    out = fixed_unit_size(signal)

    pd.testing.assert_series_equal(out, signal)


def test_volatility_target_size_scales_inversely_with_realized_vol():
    signal = _series([1.0, 1.0, 1.0, 1.0])
    realized_vol = _series([0.01, 0.02, 0.04, 0.08])

    out = volatility_target_size(signal, realized_vol, target_vol=0.02)

    np.testing.assert_allclose(out.to_numpy(), [2.0, 1.0, 0.5, 0.25])


def test_volatility_target_size_clamps_to_cap_on_zero_vol():
    signal = _series([1.0, 1.0])
    realized_vol = _series([0.0, 0.0])

    out = volatility_target_size(signal, realized_vol, target_vol=0.02, cap=3.0, epsilon=1e-6)

    assert (out.abs() <= 3.0 + 1e-9).all()


def test_volatility_target_size_respects_signal_direction():
    signal = _series([1.0, -1.0, 1.0])
    realized_vol = _series([0.02, 0.02, 0.02])

    out = volatility_target_size(signal, realized_vol, target_vol=0.02)

    np.testing.assert_allclose(out.to_numpy(), [1.0, -1.0, 1.0])


def test_volatility_target_size_rejects_non_positive_params():
    signal = _series([1.0])
    vol = _series([0.02])

    with pytest.raises(ValueError, match="target_vol"):
        volatility_target_size(signal, vol, target_vol=0.0)
    with pytest.raises(ValueError, match="cap"):
        volatility_target_size(signal, vol, target_vol=0.02, cap=0.0)
    with pytest.raises(ValueError, match="epsilon"):
        volatility_target_size(signal, vol, target_vol=0.02, epsilon=0.0)


def test_volatility_target_size_preserves_index():
    signal = _series([1.0, 1.0, 1.0])
    realized_vol = _series([0.02, 0.02, 0.02])

    out = volatility_target_size(signal, realized_vol, target_vol=0.02)

    assert out.index.equals(signal.index)


def test_volatility_target_size_is_deterministic_for_identical_inputs():
    signal = _series([1.0, -1.0, 0.0, 1.0, 1.0])
    vol = _series([0.01, 0.02, 0.03, 0.04, 0.05])

    first = volatility_target_size(signal, vol, target_vol=0.02)
    second = volatility_target_size(signal, vol, target_vol=0.02)

    pd.testing.assert_series_equal(first, second)


def test_kelly_fraction_requires_explicit_experimental_opt_in():
    signal = _series([1.0])
    edge = _series([0.01])
    var = _series([0.0004])

    with pytest.raises(RuntimeError, match="kelly_experimental"):
        kelly_fraction(signal, edge, var)


def test_kelly_fraction_caps_magnitude_when_opted_in():
    signal = _series([1.0, 1.0, 1.0])
    edge = _series([10.0, -10.0, 0.5])
    var = _series([0.0001, 0.0001, 0.5])

    out = kelly_fraction(signal, edge, var, kelly_experimental=True, cap=1.0)

    assert out.abs().max() <= 1.0 + 1e-9


def test_kelly_fraction_zero_variance_yields_nan_not_inf():
    signal = _series([1.0])
    edge = _series([0.01])
    var = _series([0.0])

    out = kelly_fraction(signal, edge, var, kelly_experimental=True)

    assert out.isna().all()


def test_resolve_sizing_spec_defaults_to_fixed_unit_for_none():
    assert resolve_sizing_spec(None) == SIZING_REGIME_FIXED_UNIT


def test_resolve_sizing_spec_defaults_to_fixed_unit_for_empty_dict():
    assert resolve_sizing_spec({}) == SIZING_REGIME_FIXED_UNIT


def test_resolve_sizing_spec_returns_volatility_target_regime():
    assert resolve_sizing_spec({"regime": SIZING_REGIME_VOLATILITY_TARGET}) == SIZING_REGIME_VOLATILITY_TARGET


def test_resolve_sizing_spec_returns_kelly_regime():
    assert resolve_sizing_spec({"regime": SIZING_REGIME_KELLY}) == SIZING_REGIME_KELLY


def test_resolve_sizing_spec_falls_back_to_fixed_unit_for_unknown_regime():
    """Unknown regimes fall back to fixed_unit — the engine must not
    silently apply a sizing function it does not recognise."""
    assert resolve_sizing_spec({"regime": "bogus_regime"}) == SIZING_REGIME_FIXED_UNIT
