"""Position sizing primitives for thin strategies.

**v3.5 STATUS — SCAFFOLDED, NO LIVE CONSUMERS.** No Tier 1 strategy
opts in this phase. The module, the engine hook that reads
`_sizing_spec`, and the `sizing_regime` field reported on the
falsification sidecar all exist so the first thin strategy to opt in
(later phase) can do so without another architectural pass.

Sizing is a post-signal transformation: the strategy emits {-1, 0, +1}
as today, and the engine — if `_sizing_spec` is present on the thin
strategy callable — applies the resolved sizing function to scale the
signal before the equity update loop runs. Absent `_sizing_spec`, the
engine keeps the legacy ±1 path and bytewise outputs for every
existing strategy are unchanged.

End state: volatility targeting becomes a first-class Execution-layer
primitive; strategies declare a sizing regime; engine applies it
post-signal. Kelly stays experimental behind `kelly_experimental=False`.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


SIZING_REGIME_FIXED_UNIT = "fixed_unit"
SIZING_REGIME_VOLATILITY_TARGET = "volatility_target"
SIZING_REGIME_KELLY = "kelly"


def fixed_unit_size(signal: pd.Series) -> pd.Series:
    """Default ±1 path: no rescaling, no clamping, no state."""
    return signal.astype(float)


def volatility_target_size(
    signal: pd.Series,
    realized_vol: pd.Series,
    target_vol: float,
    cap: float = 3.0,
    epsilon: float = 1e-6,
) -> pd.Series:
    """Volatility-targeted position sizing.

    size = target_vol / max(realized_vol, epsilon), clamped to [-cap, +cap],
    multiplied by the underlying signal. epsilon guards against zero-vol
    divisions; cap prevents runaway leverage during extreme low-vol regimes.

    Inputs are non-mutating. Output index equals `signal.index`. NaN in
    realized_vol yields NaN leverage (the engine treats NaN as "no
    position" when the signal's absolute value is 0 anyway).
    """
    if target_vol <= 0:
        raise ValueError(f"target_vol must be positive, got {target_vol}")
    if cap <= 0:
        raise ValueError(f"cap must be positive, got {cap}")
    if epsilon <= 0:
        raise ValueError(f"epsilon must be positive, got {epsilon}")

    sig = signal.astype(float)
    vol = realized_vol.astype(float).clip(lower=epsilon)
    leverage = (target_vol / vol).clip(upper=cap, lower=-cap)
    return (sig * leverage).reindex(sig.index)


def kelly_fraction(
    signal: pd.Series,
    edge: pd.Series,
    variance: pd.Series,
    *,
    kelly_experimental: bool = False,
    cap: float = 1.0,
) -> pd.Series:
    """Kelly fraction (experimental; gated behind an explicit opt-in).

    Kelly sizing is numerically sensitive to edge/variance estimation
    error; running it live without careful fractional Kelly dampening
    is unsafe. This stub refuses to run unless `kelly_experimental=True`
    is passed explicitly. The default False means accidental calls
    raise rather than produce suspect-sized positions.
    """
    if not kelly_experimental:
        raise RuntimeError(
            "kelly_fraction requires kelly_experimental=True; refusing "
            "to compute live Kelly sizing without explicit opt-in"
        )
    var = variance.astype(float).replace(0.0, np.nan)
    raw = edge.astype(float) / var
    scaled = raw.clip(lower=-cap, upper=cap) * signal.astype(float)
    return scaled.reindex(signal.index)


def resolve_sizing_spec(
    sizing_spec: dict[str, Any] | None,
) -> str:
    """Return the sizing regime label for a thin strategy's `_sizing_spec`.

    None -> "fixed_unit" (default). Unknown regimes fall back to
    "fixed_unit" as a safety default - the engine must not silently
    apply a sizing function it does not recognise.
    """
    if not sizing_spec:
        return SIZING_REGIME_FIXED_UNIT
    regime = str(sizing_spec.get("regime") or SIZING_REGIME_FIXED_UNIT)
    if regime not in {
        SIZING_REGIME_FIXED_UNIT,
        SIZING_REGIME_VOLATILITY_TARGET,
        SIZING_REGIME_KELLY,
    }:
        return SIZING_REGIME_FIXED_UNIT
    return regime


__all__ = [
    "SIZING_REGIME_FIXED_UNIT",
    "SIZING_REGIME_KELLY",
    "SIZING_REGIME_VOLATILITY_TARGET",
    "fixed_unit_size",
    "kelly_fraction",
    "resolve_sizing_spec",
    "volatility_target_size",
]
