"""Bytewise pin tests for Tier 1 baseline strategies.

These pins are the refactor guardrail for the v3.5 Tier 1 in-place migration
(see docs/orchestrator_brief.md §4.1–4.3). They lock the exact output of the
current inline implementations of:

- sma_crossover_strategie
- zscore_mean_reversion_strategie
- pairs_zscore_strategie

against deterministic fixtures from tests/_harness_helpers.py, using a
sha256 digest over (dtype, index dtype, index bytes, value bytes, name).

Any drift introduced by the upcoming refactor — whether in rolling window
semantics (min_periods), ddof on std, zero-std NaN replacement, float cast
order, or index alignment — breaks these hashes. That is the intended
signal: the numerical contract is frozen until a subsequent phase
explicitly re-pins it.

Edge-case rows pin degenerate paths (insufficient bars, invalid param
combos, missing close_ref) so empty-signal semantics cannot silently shift
during the refactor either.
"""

from __future__ import annotations

import hashlib

import pandas as pd
import pytest

from agent.backtesting.strategies import (
    pairs_zscore_strategie,
    sma_crossover_strategie,
    zscore_mean_reversion_strategie,
)
from agent.backtesting.thin_strategy import build_features_for, is_thin_strategy
from tests._harness_helpers import build_ohlcv_frame, build_pairs_frame


def _invoke(strategy, frame: pd.DataFrame) -> pd.Series:
    """Mirror the engine's _invoke_strategy: route thin strategies through
    build_features_for; legacy strategies keep the func(df) signature.
    Tier 1 baselines moved to the thin contract in v3.5, so this branch
    is what the bytewise pins actually exercise post-refactor.
    """
    if is_thin_strategy(strategy):
        features = build_features_for(strategy._feature_requirements, frame)
        return strategy(frame, features)
    return strategy(frame)


def _series_digest(sig: pd.Series) -> str:
    """Deterministic sha256 over dtype + index dtype + index + values + name.

    Any drift in any of those five components changes the digest.
    """
    parts = (
        str(sig.dtype).encode("utf-8"),
        str(sig.index.dtype).encode("utf-8"),
        sig.index.to_numpy().tobytes(),
        sig.to_numpy(copy=True).tobytes(),
        str(sig.name).encode("utf-8"),
    )
    h = hashlib.sha256()
    for part in parts:
        h.update(part)
        h.update(b"|")
    return h.hexdigest()


SMA_OHLCV_LEN = 260
SMA_OHLCV_SEED = 29
ZSMR_OHLCV_LEN = 260
ZSMR_OHLCV_SEED = 31
PAIRS_LEN = 260
PAIRS_SEED = 37


SMA_PINS = [
    (10, 50, "137cd3577833d7f28807f0182d1023343fb2ca9aa8e55c296ae75665083c8fad"),
    (10, 100, "607beb61fb798dc80532676a20e567e11016b3041e18929bb8e9ea7d6d997807"),
    (20, 50, "aacca8480f6f7c2f4c6c8955c56467b9a30266103a7153199cd7a74d93ad2ec7"),
    (20, 100, "607beb61fb798dc80532676a20e567e11016b3041e18929bb8e9ea7d6d997807"),
]


ZSMR_PINS = [
    (20, 2.0, 0.5, "5679705abc3d7595f683e06165e254a2c8f97efeb1821998600d15f6812e5cc8"),
    (30, 2.0, 0.5, "528e0dd98c39355b1bb4c215f10768522e7461b8784f5cf768a783ed7ab2cade"),
]


PAIRS_PINS = [
    (30, 2.0, 0.5, 1.0, "cdcda31d40249acaea5036e2286b55b7050e9b1198c5584c93196921a297417e"),
]


@pytest.mark.parametrize(("fast", "slow", "expected"), SMA_PINS)
def test_sma_crossover_bytewise_pin(fast: int, slow: int, expected: str) -> None:
    frame = build_ohlcv_frame(length=SMA_OHLCV_LEN, seed=SMA_OHLCV_SEED)
    strategy = sma_crossover_strategie(fast_window=fast, slow_window=slow)

    sig = _invoke(strategy, frame)

    assert _series_digest(sig) == expected, (
        f"sma_crossover drift fast={fast} slow={slow} — "
        "refactor changed numerical output; re-pin is an explicit phase decision"
    )
    assert sig.dtype.name == "int64"
    assert sig.index.equals(frame.index)


@pytest.mark.parametrize(("lookback", "entry_z", "exit_z", "expected"), ZSMR_PINS)
def test_zscore_mean_reversion_bytewise_pin(
    lookback: int, entry_z: float, exit_z: float, expected: str
) -> None:
    frame = build_ohlcv_frame(length=ZSMR_OHLCV_LEN, seed=ZSMR_OHLCV_SEED)
    strategy = zscore_mean_reversion_strategie(
        lookback=lookback, entry_z=entry_z, exit_z=exit_z
    )

    sig = _invoke(strategy, frame)

    assert _series_digest(sig) == expected, (
        f"zscore_mean_reversion drift lookback={lookback} "
        f"entry_z={entry_z} exit_z={exit_z} — refactor changed "
        "numerical output; re-pin is an explicit phase decision"
    )
    assert sig.dtype.name == "int64"
    assert sig.index.equals(frame.index)


@pytest.mark.parametrize(
    ("lookback", "entry_z", "exit_z", "hedge_ratio", "expected"), PAIRS_PINS
)
def test_pairs_zscore_bytewise_pin(
    lookback: int,
    entry_z: float,
    exit_z: float,
    hedge_ratio: float,
    expected: str,
) -> None:
    frame = build_pairs_frame(length=PAIRS_LEN, seed=PAIRS_SEED)
    strategy = pairs_zscore_strategie(
        lookback=lookback,
        entry_z=entry_z,
        exit_z=exit_z,
        hedge_ratio=hedge_ratio,
    )

    sig = _invoke(strategy, frame)

    assert _series_digest(sig) == expected, (
        f"pairs_zscore drift lookback={lookback} entry_z={entry_z} "
        f"exit_z={exit_z} hedge_ratio={hedge_ratio} — refactor changed "
        "numerical output; re-pin is an explicit phase decision"
    )
    assert sig.dtype.name == "int64"
    assert sig.index.equals(frame.index)


def test_sma_crossover_insufficient_bars_is_all_zero() -> None:
    frame = build_ohlcv_frame(length=50, seed=SMA_OHLCV_SEED)
    strategy = sma_crossover_strategie(fast_window=20, slow_window=50)

    sig = _invoke(strategy, frame)

    expected = "bb34a61c56d81faadb380a87e78e794c33e5e7efe36f9d7839ece3e3b90f4527"
    assert _series_digest(sig) == expected
    assert int((sig != 0).sum()) == 0
    assert sig.index.equals(frame.index)


def test_sma_crossover_fast_not_less_than_slow_is_all_zero() -> None:
    frame = build_ohlcv_frame(length=200, seed=SMA_OHLCV_SEED)
    strategy = sma_crossover_strategie(fast_window=50, slow_window=20)

    sig = _invoke(strategy, frame)

    assert int((sig != 0).sum()) == 0
    assert sig.dtype.name == "int64"
    assert sig.index.equals(frame.index)


def test_zscore_mean_reversion_insufficient_bars_is_all_zero() -> None:
    frame = build_ohlcv_frame(length=20, seed=ZSMR_OHLCV_SEED)
    strategy = zscore_mean_reversion_strategie(
        lookback=20, entry_z=2.0, exit_z=0.5
    )

    sig = _invoke(strategy, frame)

    expected = "690abc53e164d170eb36eeca1e6ffb1931651e02feb3adc528bd4c0587c0a7d0"
    assert _series_digest(sig) == expected
    assert int((sig != 0).sum()) == 0
    assert sig.index.equals(frame.index)


def test_zscore_mean_reversion_invalid_band_is_all_zero() -> None:
    frame = build_ohlcv_frame(length=200, seed=ZSMR_OHLCV_SEED)
    strategy = zscore_mean_reversion_strategie(
        lookback=20, entry_z=0.5, exit_z=0.5
    )

    sig = _invoke(strategy, frame)

    assert int((sig != 0).sum()) == 0
    assert sig.dtype.name == "int64"
    assert sig.index.equals(frame.index)


def test_pairs_zscore_missing_close_ref_raises_feature_error() -> None:
    """Post-refactor semantics: missing close_ref is a feature
    resolution failure (KeyError from build_features_for), not a
    silent zero-signal. The integrity layer surfaces this as
    FEATURE_INCOMPLETE upstream in apply_eligibility.
    """
    frame = build_ohlcv_frame(length=200, seed=PAIRS_SEED)
    strategy = pairs_zscore_strategie(
        lookback=30, entry_z=2.0, exit_z=0.5, hedge_ratio=1.0
    )

    with pytest.raises(KeyError, match="close_ref"):
        _invoke(strategy, frame)


def test_pairs_zscore_insufficient_bars_is_all_zero() -> None:
    frame = build_pairs_frame(length=30, seed=PAIRS_SEED)
    strategy = pairs_zscore_strategie(
        lookback=30, entry_z=2.0, exit_z=0.5, hedge_ratio=1.0
    )

    sig = _invoke(strategy, frame)

    expected = "35d7521c986ed5a1cd08a64870089669ed1374b76de4bd889f5b047c6d82c79a"
    assert _series_digest(sig) == expected
    assert int((sig != 0).sum()) == 0
    assert sig.index.equals(frame.index)


def test_pairs_zscore_invalid_band_is_all_zero() -> None:
    frame = build_pairs_frame(length=200, seed=PAIRS_SEED)
    strategy = pairs_zscore_strategie(
        lookback=30, entry_z=0.5, exit_z=0.5, hedge_ratio=1.0
    )

    sig = _invoke(strategy, frame)

    assert int((sig != 0).sum()) == 0
    assert sig.dtype.name == "int64"
    assert sig.index.equals(frame.index)


def test_series_digest_is_stable_for_identical_inputs() -> None:
    frame = build_ohlcv_frame(length=SMA_OHLCV_LEN, seed=SMA_OHLCV_SEED)
    strategy = sma_crossover_strategie(fast_window=10, slow_window=50)

    first = _series_digest(_invoke(strategy, frame))
    second = _series_digest(_invoke(strategy, frame))

    assert first == second


def test_series_digest_detects_value_drift() -> None:
    frame = build_ohlcv_frame(length=SMA_OHLCV_LEN, seed=SMA_OHLCV_SEED)
    strategy = sma_crossover_strategie(fast_window=10, slow_window=50)
    sig = _invoke(strategy, frame)

    drifted = sig.copy()
    drifted.iloc[-1] = -1 if drifted.iloc[-1] != -1 else 0

    assert _series_digest(sig) != _series_digest(drifted)
