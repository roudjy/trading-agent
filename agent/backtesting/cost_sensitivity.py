"""Cost sensitivity harness (v3.8 step 3).

Pure evaluation-layer module. Replays emitted
``agent.backtesting.execution.ExecutionEvent`` streams under alternative
cost assumptions (fee multiplier, adverse slippage override) and produces
additive diagnostics. Does NOT mutate events, the baseline equity curve,
baseline metrics, or any public artifact.

Determinism invariants
----------------------
- Input events and baseline equity must be provided unchanged.
- Given identical inputs the output dict is identical bytewise.
- No randomness; no wall-clock dependence; no pandas/numpy dependency in
  the public surface (tests pass only plain Python sequences).

Layer discipline
----------------
- The harness does NOT import the engine.
- The harness does NOT call ``_simuleer_detailed`` or any strategy code.
- Integration with the engine is confined to
  ``BacktestEngine.build_cost_sensitivity_report`` in ``engine.py``,
  which is an opt-in post-run diagnostic.

Cost model (v1.0)
-----------------
For each ``full_fill`` event at equity-curve position ``p`` (a fill at
bar index ``i`` affects equity position ``p = i``, i.e. the post-bar-i
equity), the scenario differs from the baseline by a per-fill
multiplicative factor:

    per_fill_adjustment =
        (1 - fee_multiplier * kosten_per_kant)
      * (1 - slippage_bps / 10_000)
      / (1 - kosten_per_kant)

This factor replaces the baseline's ``(1 - kosten_per_kant)`` fee drag
with the scenario's ``(1 - fee_multiplier * kosten_per_kant) *
(1 - slippage_bps / 10_000)``. Between fills both baseline and scenario
evolve by the same mark-to-market returns, so the scenario equity at any
position is

    scenario_equity[p] = baseline_equity[p] * cumulative_adj(p)

where ``cumulative_adj(p)`` is the product of ``per_fill_adjustment`` for
every fill whose effect position is <= p.

The ``baseline`` scenario (fee_multiplier=1.0, slippage_bps=0.0) yields
``per_fill_adjustment == 1.0`` and therefore reproduces the baseline
equity curve and metrics bytewise.

Sign conventions
----------------
- ``slippage_bps`` is the adverse slippage applied to each fill; it is
  always non-negative in Step 3 (positive = worse fill price).
- ``fee_multiplier`` is a non-negative multiplier on the realized fee
  amount. ``1.0`` reproduces the baseline.

Intended callers
----------------
- ``tests/unit/test_cost_sensitivity.py`` exercises the pure harness.
- ``BacktestEngine.build_cost_sensitivity_report`` wraps the harness
  over ``_last_window_streams`` after a run completes.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from agent.backtesting.execution import ExecutionEvent

__all__ = [
    "COST_SENSITIVITY_VERSION",
    "DEFAULT_SCENARIOS",
    "ScenarioSpec",
    "run_cost_sensitivity",
    "derive_fill_positions",
    "build_cost_sensitivity_report",
]


COST_SENSITIVITY_VERSION: str = "1.0"


@dataclass(frozen=True)
class ScenarioSpec:
    """Pinned, validated scenario description.

    Attributes
    ----------
    name : str
        Stable identifier used as a dict key in the report. Non-empty.
    fee_multiplier : float
        Non-negative multiplier on baseline ``kosten_per_kant``. ``1.0``
        reproduces the baseline fee drag. Finite.
    slippage_bps : float
        Non-negative adverse slippage in basis points, applied to each
        fill. ``0.0`` means no slippage override. Finite.
    """

    name: str
    fee_multiplier: float = 1.0
    slippage_bps: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError(
                f"ScenarioSpec.name must be a non-empty str, got {self.name!r}"
            )
        if not isinstance(self.fee_multiplier, (int, float)):
            raise ValueError(
                "ScenarioSpec.fee_multiplier must be a finite number, "
                f"got {self.fee_multiplier!r}"
            )
        if not isfinite(float(self.fee_multiplier)):
            raise ValueError(
                "ScenarioSpec.fee_multiplier must be finite, "
                f"got {self.fee_multiplier!r}"
            )
        if float(self.fee_multiplier) < 0.0:
            raise ValueError(
                "ScenarioSpec.fee_multiplier must be >= 0.0, "
                f"got {self.fee_multiplier!r}"
            )
        if not isinstance(self.slippage_bps, (int, float)):
            raise ValueError(
                "ScenarioSpec.slippage_bps must be a finite number, "
                f"got {self.slippage_bps!r}"
            )
        if not isfinite(float(self.slippage_bps)):
            raise ValueError(
                "ScenarioSpec.slippage_bps must be finite, "
                f"got {self.slippage_bps!r}"
            )
        if float(self.slippage_bps) < 0.0:
            raise ValueError(
                "ScenarioSpec.slippage_bps must be >= 0.0, "
                f"got {self.slippage_bps!r}"
            )


DEFAULT_SCENARIOS: tuple[ScenarioSpec, ...] = (
    ScenarioSpec(name="baseline", fee_multiplier=1.0, slippage_bps=0.0),
    ScenarioSpec(name="fee_x2", fee_multiplier=2.0, slippage_bps=0.0),
    ScenarioSpec(name="fee_x3", fee_multiplier=3.0, slippage_bps=0.0),
    ScenarioSpec(name="slippage_5bps", fee_multiplier=1.0, slippage_bps=5.0),
    ScenarioSpec(
        name="slippage_10bps", fee_multiplier=1.0, slippage_bps=10.0
    ),
)


# ---------------------------------------------------------------------------
# Internal: baseline equity reconstruction
# ---------------------------------------------------------------------------


def _baseline_equity_curve(
    baseline_dag_returns: Sequence[float],
) -> list[float]:
    """Compute per-bar baseline equity curve.

    Returns a list of length ``len(baseline_dag_returns) + 1``. The first
    entry is ``1.0`` (starting equity). ``baseline_equity[p]`` is the
    equity AFTER processing bar ``p - 1`` (engine convention).

    Baseline returns already include all fee drags from the engine, so
    this function is a pure cumulative product.
    """
    curve: list[float] = [1.0]
    equity = 1.0
    for r in baseline_dag_returns:
        if not isinstance(r, (int, float)):
            raise ValueError(
                "baseline_dag_returns must contain only finite numbers, "
                f"got {r!r}"
            )
        rf = float(r)
        if not isfinite(rf):
            raise ValueError(
                "baseline_dag_returns must be finite, got "
                f"{r!r}"
            )
        equity *= 1.0 + rf
        curve.append(equity)
    return curve


# ---------------------------------------------------------------------------
# Internal: scenario equity curve
# ---------------------------------------------------------------------------


def _scenario_equity_curve(
    baseline_equity_curve: Sequence[float],
    fill_positions: Sequence[int],
    fee_multiplier: float,
    slippage_bps: float,
    kosten_per_kant: float,
) -> list[float]:
    """Scale baseline equity by cumulative per-fill adjustment factor.

    ``fill_positions[k]`` is the 1-indexed position in the equity curve
    where the k-th fill's effect manifests (i.e. equity_curve[p] is the
    equity after the fill). Positions must be non-decreasing.
    """
    k = float(kosten_per_kant)
    m = float(fee_multiplier)
    s = float(slippage_bps) / 10000.0
    # Guard against division-by-zero; k is bounded far from 1.0 in the
    # engine (transaction cost / 2 + 0.001), but we check defensively.
    if (1.0 - k) == 0.0:
        raise ValueError(
            "kosten_per_kant of 1.0 is degenerate "
            "(full-equity fee). Cannot compute per-fill adjustment."
        )
    per_fill_adj = (1.0 - m * k) * (1.0 - s) / (1.0 - k)
    curve: list[float] = []
    adj = 1.0
    fill_idx = 0
    n_fills = len(fill_positions)
    for p, base in enumerate(baseline_equity_curve):
        while fill_idx < n_fills and int(fill_positions[fill_idx]) <= p:
            adj *= per_fill_adj
            fill_idx += 1
        curve.append(float(base) * adj)
    return curve


# ---------------------------------------------------------------------------
# Internal: metric helpers (deterministic, stdlib-only)
# ---------------------------------------------------------------------------


def _max_drawdown(equity_curve: Sequence[float]) -> float:
    """Return max drawdown as a non-negative fraction.

    0.0 if the curve is empty or monotone non-decreasing.
    """
    peak = float("-inf")
    mdd = 0.0
    for v in equity_curve:
        vf = float(v)
        if vf > peak:
            peak = vf
        if peak > 0.0:
            dd = (peak - vf) / peak
            if dd > mdd:
                mdd = dd
    return float(mdd)


def _sharpe_proxy(dag_returns: Sequence[float]) -> float:
    """Annualization-free Sharpe proxy: mean/std of per-bar returns.

    Returns 0.0 when there are fewer than 2 samples or when std is zero.
    This is a deterministic diagnostic, not the engine's official
    Sharpe. Kept stdlib-only for determinism across platforms.
    """
    n = len(dag_returns)
    if n < 2:
        return 0.0
    mean = sum(float(r) for r in dag_returns) / n
    var = sum((float(r) - mean) ** 2 for r in dag_returns) / (n - 1)
    if var <= 0.0:
        return 0.0
    std = var ** 0.5
    if std == 0.0:
        return 0.0
    return float(mean / std)


def _dag_returns_from_curve(curve: Sequence[float]) -> list[float]:
    """Bar-to-bar returns derived from an equity curve of length N+1."""
    if len(curve) < 2:
        return []
    out: list[float] = []
    for i in range(1, len(curve)):
        prev = float(curve[i - 1])
        cur = float(curve[i])
        if prev == 0.0:
            out.append(0.0)
        else:
            out.append(cur / prev - 1.0)
    return out


# ---------------------------------------------------------------------------
# Internal: validation
# ---------------------------------------------------------------------------


def _validate_events(events: Sequence[ExecutionEvent]) -> None:
    for e in events:
        if not isinstance(e, ExecutionEvent):
            raise TypeError(
                "events must be ExecutionEvent instances, "
                f"got {type(e).__name__}"
            )


def _filter_full_fills(
    events: Sequence[ExecutionEvent],
) -> list[ExecutionEvent]:
    return [e for e in events if e.kind == "full_fill"]


# ---------------------------------------------------------------------------
# Public: fill-position derivation
# ---------------------------------------------------------------------------


def derive_fill_positions(
    full_fill_events: Sequence[ExecutionEvent],
    bar_return_stream: Sequence[dict[str, Any]],
) -> list[int]:
    """Map full_fill events to equity-curve positions via timestamp match.

    ``bar_return_stream[j]`` has ``timestamp_utc`` corresponding to
    ``baseline_equity_curve[j + 1]`` (the first entry of the equity
    curve is pre-bar initial ``1.0``). Returns a list of equity-curve
    positions, one per full_fill event, in the order given.

    Raises
    ------
    KeyError
        If a full_fill event's timestamp is not present in the bar
        stream. This indicates a caller-side mismatch (e.g. passing the
        wrong window's stream) and must not be silently ignored.
    """
    ts_to_position: dict[str, int] = {}
    for j, entry in enumerate(bar_return_stream):
        ts = str(entry["timestamp_utc"])
        if ts not in ts_to_position:
            ts_to_position[ts] = j + 1
    positions: list[int] = []
    for e in full_fill_events:
        if not isinstance(e, ExecutionEvent):
            raise TypeError(
                "full_fill_events must be ExecutionEvent instances"
            )
        if e.kind != "full_fill":
            raise ValueError(
                "derive_fill_positions accepts only full_fill events; "
                f"got kind={e.kind!r}"
            )
        ts = e.timestamp_utc
        if ts not in ts_to_position:
            raise KeyError(
                "full_fill event timestamp not present in "
                f"bar_return_stream: {ts!r}"
            )
        positions.append(ts_to_position[ts])
    return positions


# ---------------------------------------------------------------------------
# Public: run harness over explicit inputs
# ---------------------------------------------------------------------------


def run_cost_sensitivity(
    *,
    events: Sequence[ExecutionEvent],
    baseline_dag_returns: Sequence[float],
    fill_positions: Sequence[int],
    kosten_per_kant: float,
    scenarios: Sequence[ScenarioSpec] = DEFAULT_SCENARIOS,
) -> dict[str, Any]:
    """Replay ``events`` under each scenario and produce diagnostics.

    Parameters
    ----------
    events : Sequence[ExecutionEvent]
        Emitted events for the window under evaluation. Only
        ``full_fill`` events contribute to cost replay; other kinds are
        preserved in the output count but not used in the math.
    baseline_dag_returns : Sequence[float]
        Per-bar returns as produced by ``_simuleer_detailed`` for this
        window. Baseline equity is ``[1.0] + cumprod(1 + r)``.
    fill_positions : Sequence[int]
        Equity-curve positions (1-indexed; ``[1 .. len(curve)-1]``)
        where each ``full_fill`` event's effect manifests. Must be
        non-decreasing and aligned to the order of full_fill events in
        ``events``.
    kosten_per_kant : float
        Baseline fee rate (``BacktestEngine.kosten_per_kant``). Must be
        a finite float in ``[0.0, 1.0)``.
    scenarios : Sequence[ScenarioSpec]
        Scenarios to replay. ``DEFAULT_SCENARIOS`` covers baseline,
        fee_x2, fee_x3, slippage_5bps, slippage_10bps.

    Returns
    -------
    dict
        Deterministic structure::

            {
              "version": "1.0",
              "kosten_per_kant": float,
              "n_events": int,
              "n_full_fills": int,
              "scenarios": [
                {
                  "name": str,
                  "fee_multiplier": float,
                  "slippage_bps": float,
                  "metrics": {
                     "final_equity": float,
                     "total_return": float,
                     "max_drawdown": float,
                     "sharpe_proxy": float,
                     "n_full_fills": int,
                     "total_fee_drag_fraction": float,
                     "total_slippage_drag_fraction": float,
                  },
                },
                ...
              ],
            }
    """
    _validate_events(events)
    if not isinstance(kosten_per_kant, (int, float)):
        raise ValueError(
            "kosten_per_kant must be a finite number, "
            f"got {kosten_per_kant!r}"
        )
    kf = float(kosten_per_kant)
    if not isfinite(kf) or not (0.0 <= kf < 1.0):
        raise ValueError(
            "kosten_per_kant must be finite and in [0.0, 1.0), "
            f"got {kosten_per_kant!r}"
        )
    if not scenarios:
        raise ValueError("scenarios must be non-empty")
    for spec in scenarios:
        if not isinstance(spec, ScenarioSpec):
            raise TypeError(
                "scenarios must contain ScenarioSpec instances, "
                f"got {type(spec).__name__}"
            )

    full_fills = _filter_full_fills(events)
    n_full_fills = len(full_fills)
    if len(fill_positions) != n_full_fills:
        raise ValueError(
            "fill_positions length must equal number of full_fill "
            f"events: got {len(fill_positions)} positions vs "
            f"{n_full_fills} full_fill events"
        )
    # Positions must be non-decreasing and non-negative
    prev = -1
    for p in fill_positions:
        ip = int(p)
        if ip < 0:
            raise ValueError(
                f"fill_positions must be non-negative, got {p!r}"
            )
        if ip < prev:
            raise ValueError(
                "fill_positions must be non-decreasing, got "
                f"...{prev}, {ip}..."
            )
        prev = ip

    baseline_curve = _baseline_equity_curve(baseline_dag_returns)
    # Positions must not exceed final equity-curve index
    curve_len = len(baseline_curve)
    for p in fill_positions:
        if int(p) >= curve_len:
            raise ValueError(
                "fill_positions exceed baseline equity curve length: "
                f"position {p} >= curve length {curve_len}"
            )

    scenario_results: list[dict[str, Any]] = []
    for spec in scenarios:
        scen_curve = _scenario_equity_curve(
            baseline_equity_curve=baseline_curve,
            fill_positions=fill_positions,
            fee_multiplier=spec.fee_multiplier,
            slippage_bps=spec.slippage_bps,
            kosten_per_kant=kf,
        )
        final_equity = scen_curve[-1] if scen_curve else 1.0
        total_return = final_equity - 1.0
        mdd = _max_drawdown(scen_curve)
        dag_scen = _dag_returns_from_curve(scen_curve)
        sharpe = _sharpe_proxy(dag_scen)
        total_fee_drag = (
            1.0 - (1.0 - spec.fee_multiplier * kf) ** n_full_fills
        )
        total_slip_drag = (
            1.0 - (1.0 - spec.slippage_bps / 10000.0) ** n_full_fills
        )
        scenario_results.append(
            {
                "name": spec.name,
                "fee_multiplier": float(spec.fee_multiplier),
                "slippage_bps": float(spec.slippage_bps),
                "metrics": {
                    "final_equity": float(final_equity),
                    "total_return": float(total_return),
                    "max_drawdown": float(mdd),
                    "sharpe_proxy": float(sharpe),
                    "n_full_fills": int(n_full_fills),
                    "total_fee_drag_fraction": float(total_fee_drag),
                    "total_slippage_drag_fraction": float(total_slip_drag),
                },
            }
        )

    return {
        "version": COST_SENSITIVITY_VERSION,
        "kosten_per_kant": kf,
        "n_events": int(len(events)),
        "n_full_fills": int(n_full_fills),
        "scenarios": scenario_results,
    }


# ---------------------------------------------------------------------------
# Public: engine-oriented convenience wrapper
# ---------------------------------------------------------------------------


def build_cost_sensitivity_report(
    *,
    events: Sequence[ExecutionEvent],
    bar_return_stream: Sequence[dict[str, Any]],
    baseline_dag_returns: Sequence[float],
    kosten_per_kant: float,
    scenarios: Sequence[ScenarioSpec] = DEFAULT_SCENARIOS,
) -> dict[str, Any]:
    """High-level wrapper: derive fill positions, then call the harness.

    Intended to be called by ``BacktestEngine.build_cost_sensitivity_report``
    with the streams already held in ``_last_window_streams``. Pure; no
    engine import side.
    """
    full_fills = _filter_full_fills(events)
    positions = derive_fill_positions(full_fills, bar_return_stream)
    return run_cost_sensitivity(
        events=events,
        baseline_dag_returns=baseline_dag_returns,
        fill_positions=positions,
        kosten_per_kant=kosten_per_kant,
        scenarios=scenarios,
    )
