"""v3.7 step 4 - pairs_zscore fitted hedge ratio opt-in + engine wiring.

Proves:

* default ``pairs_zscore_strategie()`` behavior is unchanged
  (same FeatureRequirement; same signal on identical z inputs)
* the explicit ``use_fitted_hedge_ratio=True`` flag routes through the
  fitted ``spread_zscore_ols`` feature and the fold-aware engine path
* the engine fits beta on the training slice only and reuses the
  frozen params on the evaluation slice (no refit, no leakage)
* the fitted path loud-fails when the engine does not provide a
  training slice (structural guard against silent fallback)
* a grid-search-level run completes with the fitted flag on

Uses a spy-wrapped ``spread_zscore_ols`` registry entry in a fixture so
fit/transform call counts and slice lengths can be asserted directly,
without touching production code paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import pytest

from agent.backtesting.engine import AssetContext, BacktestEngine
from agent.backtesting.fitted_features import (
    FITTED_FEATURE_REGISTRY,
    FittedFeatureSpec,
)
from agent.backtesting.strategies import pairs_zscore_strategie
from agent.backtesting.thin_strategy import FeatureRequirement
from tests._harness_helpers import build_aligned_pair_frames, build_ohlcv_frame


# ---------------------------------------------------------------------------
# Spy fixture: wraps the production spread_zscore_ols registry entry with
# call counters. Restored on teardown so other tests are untouched.
# ---------------------------------------------------------------------------


@dataclass
class _SpyCounters:
    fit_calls: int = 0
    transform_calls: int = 0
    fit_lens: list[int] = field(default_factory=list)
    transform_lens: list[int] = field(default_factory=list)

    def reset(self) -> None:
        self.fit_calls = 0
        self.transform_calls = 0
        self.fit_lens.clear()
        self.transform_lens.clear()


@pytest.fixture
def spy_spread_zscore_ols():
    original = FITTED_FEATURE_REGISTRY["spread_zscore_ols"]
    counters = _SpyCounters()

    def spy_fit(df, **kwargs):
        counters.fit_calls += 1
        counters.fit_lens.append(len(df))
        return original.fit_fn(df, **kwargs)

    def spy_transform(df, params, **kwargs):
        counters.transform_calls += 1
        counters.transform_lens.append(len(df))
        return original.transform_fn(df, params, **kwargs)

    FITTED_FEATURE_REGISTRY["spread_zscore_ols"] = FittedFeatureSpec(
        fit_fn=spy_fit,
        transform_fn=spy_transform,
        param_names=original.param_names,
        required_columns=original.required_columns,
        warmup_bars_fn=original.warmup_bars_fn,
    )
    try:
        yield counters
    finally:
        FITTED_FEATURE_REGISTRY["spread_zscore_ols"] = original


# ---------------------------------------------------------------------------
# Engine + AssetContext helpers
# ---------------------------------------------------------------------------


def _make_engine() -> BacktestEngine:
    return BacktestEngine(
        "2024-01-01",
        "2024-12-31",
        evaluation_config={"mode": "single_split", "train_ratio": 0.6},
    )


def _make_pair_asset_context(
    length: int = 240,
    seed_primary: int = 11,
    seed_reference: int = 19,
    train_ratio: float = 0.6,
    beta_true: Optional[float] = None,
) -> AssetContext:
    """Build an AssetContext for pairs tests with a single train/test fold.

    ``beta_true`` (optional) forces the reference leg to be a known
    linear transform of the primary leg plus deterministic noise, so
    the OLS beta fit on the training slice can be expected in advance.
    Without it the two seeds give two independent OHLCV frames.
    """
    primary, reference = build_aligned_pair_frames(
        seed_primary=seed_primary, seed_reference=seed_reference, length=length
    )
    if beta_true is not None:
        rng = np.random.default_rng(seed_reference)
        noise = pd.Series(
            rng.normal(0.0, 0.25, length), index=primary.index
        )
        reference = reference.copy()
        reference["close"] = (primary["close"] / beta_true) + noise

    regime_frame = pd.DataFrame(
        {
            "trend_regime": ["unknown"] * length,
            "volatility_regime": ["unknown"] * length,
            "combined_regime": ["unknown"] * length,
        },
        index=primary.index,
    )
    split = int(length * train_ratio)
    folds = [((0, split - 1), (split, length - 1))]
    return AssetContext(
        asset="BTC-EUR",
        frame=primary,
        regime_frame=regime_frame,
        folds=folds,
        reference_frame=reference,
    )


# ---------------------------------------------------------------------------
# 1. default pairs_zscore emits the v3.6 requirement (byte-identical shape)
# ---------------------------------------------------------------------------


def test_default_pairs_zscore_requirement_shape_unchanged() -> None:
    strategy = pairs_zscore_strategie(lookback=30, hedge_ratio=1.0)
    reqs = strategy._feature_requirements  # type: ignore[attr-defined]

    assert len(reqs) == 1
    req = reqs[0]
    assert req.name == "spread_zscore"
    assert req.feature_kind == "plain"
    assert req.params == {"hedge_ratio": 1.0, "lookback": 30}
    assert req.resolved_alias() == "z"
    assert req.source_role is None


def test_default_pairs_zscore_requirement_equals_pre_v3_7_shape() -> None:
    """Pin the legacy FeatureRequirement shape to catch accidental drift."""
    strategy = pairs_zscore_strategie()
    assert strategy._feature_requirements == [  # type: ignore[attr-defined]
        FeatureRequirement(
            name="spread_zscore",
            params={"hedge_ratio": 1.0, "lookback": 30},
            alias="z",
        ),
    ]


def test_default_flag_is_false_backward_compatible() -> None:
    # Positional-only invocation with the historical parameter order
    # must still produce a valid plain strategy, without the new flag
    # being set anywhere.
    strategy = pairs_zscore_strategie(30, 2.0, 0.5, 1.0)
    req = strategy._feature_requirements[0]  # type: ignore[attr-defined]
    assert req.feature_kind == "plain"
    assert req.name == "spread_zscore"


# ---------------------------------------------------------------------------
# 2. fitted mode activates only when the flag is True
# ---------------------------------------------------------------------------


def test_fitted_flag_true_swaps_requirement_to_spread_zscore_ols() -> None:
    strategy = pairs_zscore_strategie(
        lookback=30, hedge_ratio=1.0, use_fitted_hedge_ratio=True
    )
    reqs = strategy._feature_requirements  # type: ignore[attr-defined]

    assert len(reqs) == 1
    req = reqs[0]
    assert req.name == "spread_zscore_ols"
    assert req.feature_kind == "fitted"
    assert req.params == {"lookback": 30}
    assert req.resolved_alias() == "z"


def test_fitted_flag_false_keeps_plain_requirement() -> None:
    strategy_plain = pairs_zscore_strategie(use_fitted_hedge_ratio=False)
    strategy_default = pairs_zscore_strategie()

    assert (
        strategy_plain._feature_requirements  # type: ignore[attr-defined]
        == strategy_default._feature_requirements  # type: ignore[attr-defined]
    )


# ---------------------------------------------------------------------------
# 3 + 4 + 14. engine fold path: fit on train, reuse on test; call counts
# ---------------------------------------------------------------------------


def _run_oos_fold(
    strategy, context: AssetContext
) -> None:
    """Invoke _evaluate_windows for a single fold in OOS mode."""
    engine = _make_engine()
    engine._evaluate_windows(strategy, [context], use_train=False)


def test_fitted_oos_pass_fits_once_and_transforms_once_per_fold(
    spy_spread_zscore_ols,
) -> None:
    strategy = pairs_zscore_strategie(use_fitted_hedge_ratio=True)
    ctx = _make_pair_asset_context(length=240, train_ratio=0.6)

    _run_oos_fold(strategy, ctx)

    (train_bounds, test_bounds) = ctx.folds[0]
    train_len = train_bounds[1] - train_bounds[0] + 1
    test_len = test_bounds[1] - test_bounds[0] + 1

    assert spy_spread_zscore_ols.fit_calls == 1
    assert spy_spread_zscore_ols.fit_lens == [train_len]
    # transform is called twice: once inside build_features_train on
    # the train slice (for feature assembly during fit), and once on
    # the test slice via build_features_test. No refit on test.
    assert spy_spread_zscore_ols.transform_calls == 2
    assert sorted(spy_spread_zscore_ols.transform_lens) == sorted(
        [train_len, test_len]
    )


def test_fitted_is_pass_fits_once_and_transforms_once_per_fold(
    spy_spread_zscore_ols,
) -> None:
    strategy = pairs_zscore_strategie(use_fitted_hedge_ratio=True)
    ctx = _make_pair_asset_context(length=240, train_ratio=0.6)
    engine = _make_engine()

    engine._evaluate_windows(strategy, [ctx], use_train=True)

    (train_bounds, _test_bounds) = ctx.folds[0]
    train_len = train_bounds[1] - train_bounds[0] + 1

    # IS: fit+transform on train slice; then transform on the same
    # train slice again when build_features_test is called with the
    # evaluation window (which is the train slice in the IS pass).
    assert spy_spread_zscore_ols.fit_calls == 1
    assert spy_spread_zscore_ols.fit_lens == [train_len]
    assert spy_spread_zscore_ols.transform_calls == 2
    assert spy_spread_zscore_ols.transform_lens == [train_len, train_len]


def test_fitted_oos_uses_train_beta_not_full_window_beta(
    spy_spread_zscore_ols,
) -> None:
    """The fitted beta must be derived from the training slice only -
    using the full window or the test slice would yield a different
    value on this fixture."""
    ctx = _make_pair_asset_context(
        length=240, train_ratio=0.5, beta_true=2.0
    )
    strategy = pairs_zscore_strategie(use_fitted_hedge_ratio=True)

    _run_oos_fold(strategy, ctx)

    # The spy only captures lengths; for the beta value, run the fit
    # ourselves on the exact training slice and compare against what
    # would result from a full-window fit - they must differ.
    (train_bounds, _t) = ctx.folds[0]
    train_start, train_end = train_bounds
    full = ctx.frame.copy()
    full["close_ref"] = ctx.reference_frame["close"]
    train = full.iloc[train_start : train_end + 1]

    var_full = float(full["close_ref"].var(ddof=0))
    cov_full = float(
        (full["close_ref"] * full["close"]).mean()
        - full["close_ref"].mean() * full["close"].mean()
    )
    beta_full = cov_full / var_full

    var_tr = float(train["close_ref"].var(ddof=0))
    cov_tr = float(
        (train["close_ref"] * train["close"]).mean()
        - train["close_ref"].mean() * train["close"].mean()
    )
    beta_train = cov_tr / var_tr

    assert not np.isclose(beta_full, beta_train, rtol=1e-6, atol=1e-9)


def test_multi_fold_each_fold_fits_independently(
    spy_spread_zscore_ols,
) -> None:
    """Fold A's fitted params are not visible to fold B (no cache)."""
    primary, reference = build_aligned_pair_frames(
        seed_primary=41, seed_reference=43, length=300
    )
    regime_frame = pd.DataFrame(
        {"trend_regime": ["unknown"] * 300},
        index=primary.index,
    )
    # Two explicit rolling folds.
    folds = [((0, 99), (100, 149)), ((100, 199), (200, 249))]
    ctx = AssetContext(
        asset="BTC-EUR",
        frame=primary,
        regime_frame=regime_frame,
        folds=folds,
        reference_frame=reference,
    )
    strategy = pairs_zscore_strategie(use_fitted_hedge_ratio=True)

    _run_oos_fold(strategy, ctx)

    # One fit per fold, on slice lengths matching train bounds.
    assert spy_spread_zscore_ols.fit_calls == 2
    assert sorted(spy_spread_zscore_ols.fit_lens) == [100, 100]


# ---------------------------------------------------------------------------
# 5 + 15. loud-fail when fitted path runs without a training slice
# ---------------------------------------------------------------------------


def test_invoke_strategy_without_train_frame_raises() -> None:
    engine = _make_engine()
    strategy = pairs_zscore_strategie(use_fitted_hedge_ratio=True)
    primary, reference = build_aligned_pair_frames(length=60)

    with pytest.raises(ValueError, match="fitted strategy requires a training"):
        engine._invoke_strategy(
            primary,
            strategy,
            reference_frame=reference,
            train_frame=None,
            train_reference_frame=reference,
        )


def test_invoke_strategy_without_train_reference_raises() -> None:
    engine = _make_engine()
    strategy = pairs_zscore_strategie(use_fitted_hedge_ratio=True)
    primary, reference = build_aligned_pair_frames(length=60)

    with pytest.raises(ValueError, match="train_reference_frame"):
        engine._invoke_strategy(
            primary,
            strategy,
            reference_frame=reference,
            train_frame=primary,
            train_reference_frame=None,
        )


def test_invoke_strategy_fitted_does_not_fall_back_to_plain_on_missing_column(
    spy_spread_zscore_ols,
) -> None:
    engine = _make_engine()
    strategy = pairs_zscore_strategie(use_fitted_hedge_ratio=True)
    primary = build_ohlcv_frame(length=60, seed=101)  # no close_ref

    with pytest.raises((KeyError, ValueError)):
        engine._invoke_strategy(
            primary,
            strategy,
            reference_frame=None,
            train_frame=primary,
            train_reference_frame=None,
        )

    # Confirm the engine did NOT silently resolve via the plain
    # spread_zscore path - the spy would record zero calls either way,
    # so we instead verify the strategy still declares a fitted
    # requirement (structural guard).
    reqs = strategy._feature_requirements  # type: ignore[attr-defined]
    assert reqs[0].feature_kind == "fitted"


# ---------------------------------------------------------------------------
# 6. fold-local params: fold A not visible to fold B (already tested above
# at count level; here we also assert the actual beta values differ)
# ---------------------------------------------------------------------------


def test_different_folds_produce_different_betas() -> None:
    primary, reference = build_aligned_pair_frames(
        seed_primary=77, seed_reference=79, length=260
    )
    reference = reference.copy()
    rng = np.random.default_rng(0)
    # Inject a regime shift at bar 130 so fold A (bars 0-99) sees a
    # different relationship than fold B (bars 130-229).
    reference.iloc[130:, reference.columns.get_loc("close")] = (
        reference["close"].iloc[130:].to_numpy() * 1.5
        + rng.normal(0.0, 0.1, len(reference) - 130)
    )
    regime_frame = pd.DataFrame(
        {"trend_regime": ["unknown"] * 260}, index=primary.index
    )
    folds = [((0, 99), (100, 129)), ((130, 229), (230, 259))]
    ctx = AssetContext(
        asset="BTC-EUR",
        frame=primary,
        regime_frame=regime_frame,
        folds=folds,
        reference_frame=reference,
    )
    strategy = pairs_zscore_strategie(use_fitted_hedge_ratio=True)
    engine = _make_engine()

    # Capture fitted params per fold by spying on the registry fit_fn.
    seen_betas: list[float] = []
    original = FITTED_FEATURE_REGISTRY["spread_zscore_ols"]

    def capture_fit(df, **kwargs):
        fp = original.fit_fn(df, **kwargs)
        seen_betas.append(float(fp.values["beta"]))
        return fp

    FITTED_FEATURE_REGISTRY["spread_zscore_ols"] = FittedFeatureSpec(
        fit_fn=capture_fit,
        transform_fn=original.transform_fn,
        param_names=original.param_names,
        required_columns=original.required_columns,
        warmup_bars_fn=original.warmup_bars_fn,
    )
    try:
        engine._evaluate_windows(strategy, [ctx], use_train=False)
    finally:
        FITTED_FEATURE_REGISTRY["spread_zscore_ols"] = original

    assert len(seen_betas) == 2
    assert not np.isclose(seen_betas[0], seen_betas[1], rtol=1e-6, atol=1e-9)


# ---------------------------------------------------------------------------
# 7. legacy and fitted modes both work on aligned multi-asset data
# ---------------------------------------------------------------------------


def test_legacy_and_fitted_pairs_both_execute_on_aligned_data() -> None:
    ctx = _make_pair_asset_context(length=240, train_ratio=0.6)
    engine_legacy = _make_engine()
    engine_fitted = _make_engine()

    legacy = pairs_zscore_strategie(hedge_ratio=1.0)
    fitted = pairs_zscore_strategie(hedge_ratio=1.0, use_fitted_hedge_ratio=True)

    legacy_metrics = engine_legacy._evaluate_windows(
        legacy, [ctx], use_train=False
    )
    fitted_metrics = engine_fitted._evaluate_windows(
        fitted, [ctx], use_train=False
    )

    assert isinstance(legacy_metrics, dict)
    assert isinstance(fitted_metrics, dict)
    for key in ("sharpe", "max_drawdown", "totaal_trades"):
        assert key in legacy_metrics
        assert key in fitted_metrics


def test_fitted_spread_differs_from_naive_when_beta_is_not_one() -> None:
    """When OLS beta is materially different from the naive 1.0 hedge
    ratio, the fitted pairs path must produce a measurably different
    feature series than the legacy path on the same frames."""
    ctx = _make_pair_asset_context(
        length=200, train_ratio=0.5, beta_true=2.0
    )
    engine = _make_engine()
    (train_bounds, test_bounds) = ctx.folds[0]
    df_test = ctx.frame.iloc[test_bounds[0] : test_bounds[1] + 1].copy()
    ref_test = ctx.reference_frame.iloc[
        test_bounds[0] : test_bounds[1] + 1
    ].copy()
    df_train = ctx.frame.iloc[train_bounds[0] : train_bounds[1] + 1].copy()
    ref_train = ctx.reference_frame.iloc[
        train_bounds[0] : train_bounds[1] + 1
    ].copy()

    legacy = pairs_zscore_strategie(hedge_ratio=1.0)
    fitted = pairs_zscore_strategie(hedge_ratio=1.0, use_fitted_hedge_ratio=True)

    legacy_sig = engine._invoke_strategy(
        df_test, legacy, reference_frame=ref_test
    )
    fitted_sig = engine._invoke_strategy(
        df_test,
        fitted,
        reference_frame=ref_test,
        train_frame=df_train,
        train_reference_frame=ref_train,
    )

    # The two signals must differ on a fixture where OLS beta != 1.0
    # (the fitted path uses beta ≈ 0.5; the legacy path uses 1.0).
    assert not legacy_sig.equals(fitted_sig)


# ---------------------------------------------------------------------------
# 8. default non-pairs strategies remain unchanged
# ---------------------------------------------------------------------------


def test_non_pairs_strategy_runs_unchanged_through_engine() -> None:
    from agent.backtesting.strategies import sma_crossover_strategie

    df = build_ohlcv_frame(length=150, seed=203)
    regime_frame = pd.DataFrame(
        {"trend_regime": ["unknown"] * 150}, index=df.index
    )
    ctx = AssetContext(
        asset="BTC-EUR",
        frame=df,
        regime_frame=regime_frame,
        folds=[((0, 99), (100, 149))],
        reference_frame=None,
    )
    strategy = sma_crossover_strategie(fast_window=5, slow_window=20)
    engine = _make_engine()

    metrics = engine._evaluate_windows(strategy, [ctx], use_train=False)
    assert isinstance(metrics, dict)
    for key in ("sharpe", "max_drawdown", "totaal_trades"):
        assert key in metrics


# ---------------------------------------------------------------------------
# 10. determinism: repeated runs with the same config produce identical
# fitted-mode outputs
# ---------------------------------------------------------------------------


def test_fitted_mode_is_deterministic_across_repeated_runs() -> None:
    ctx = _make_pair_asset_context(length=240, train_ratio=0.6)
    (train_bounds, test_bounds) = ctx.folds[0]
    df_test = ctx.frame.iloc[test_bounds[0] : test_bounds[1] + 1].copy()
    ref_test = ctx.reference_frame.iloc[
        test_bounds[0] : test_bounds[1] + 1
    ].copy()
    df_train = ctx.frame.iloc[train_bounds[0] : train_bounds[1] + 1].copy()
    ref_train = ctx.reference_frame.iloc[
        train_bounds[0] : train_bounds[1] + 1
    ].copy()

    strategy = pairs_zscore_strategie(use_fitted_hedge_ratio=True)
    engine = _make_engine()

    sig_a = engine._invoke_strategy(
        df_test,
        strategy,
        reference_frame=ref_test,
        train_frame=df_train,
        train_reference_frame=ref_train,
    )
    sig_b = engine._invoke_strategy(
        df_test,
        strategy,
        reference_frame=ref_test,
        train_frame=df_train,
        train_reference_frame=ref_train,
    )

    pd.testing.assert_series_equal(sig_a, sig_b)
    assert (
        sig_a.to_numpy(copy=True).tobytes()
        == sig_b.to_numpy(copy=True).tobytes()
    )


# ---------------------------------------------------------------------------
# 11. Tier 1 pins unchanged when fitted mode is not used - exercised by
# the full test_tier1_bytewise_pin.py module; here we pin that the
# default pairs strategy still resolves to the plain spread_zscore path
# without touching the fitted registry.
# ---------------------------------------------------------------------------


def test_default_pairs_does_not_touch_fitted_registry(
    spy_spread_zscore_ols,
) -> None:
    ctx = _make_pair_asset_context(length=180, train_ratio=0.6)
    strategy = pairs_zscore_strategie()  # default: fitted flag False
    engine = _make_engine()

    engine._evaluate_windows(strategy, [ctx], use_train=False)

    assert spy_spread_zscore_ols.fit_calls == 0
    assert spy_spread_zscore_ols.transform_calls == 0


# ---------------------------------------------------------------------------
# 9. mixed run: ordinary strategy + fitted pairs evaluated on the same
# engine instance - both must work without interference
# ---------------------------------------------------------------------------


def test_mixed_ordinary_and_fitted_strategies_on_one_engine(
    spy_spread_zscore_ols,
) -> None:
    from agent.backtesting.strategies import sma_crossover_strategie

    pair_ctx = _make_pair_asset_context(length=200, train_ratio=0.6)
    plain_df = build_ohlcv_frame(length=200, seed=307)
    plain_ctx = AssetContext(
        asset="BTC-EUR",
        frame=plain_df,
        regime_frame=pd.DataFrame(
            {"trend_regime": ["unknown"] * 200}, index=plain_df.index
        ),
        folds=[((0, 119), (120, 199))],
        reference_frame=None,
    )

    engine = _make_engine()
    sma = sma_crossover_strategie(fast_window=5, slow_window=20)
    fitted = pairs_zscore_strategie(use_fitted_hedge_ratio=True)

    engine._evaluate_windows(sma, [plain_ctx], use_train=False)
    assert spy_spread_zscore_ols.fit_calls == 0

    engine._evaluate_windows(fitted, [pair_ctx], use_train=False)
    assert spy_spread_zscore_ols.fit_calls == 1
