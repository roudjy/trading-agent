"""Exit-quality diagnostics (v3.8 step 4).

Pure evaluation-layer module. Consumes existing run outputs
(``oos_trade_events`` and ``oos_bar_returns`` streams) plus the engine's
``kosten_per_kant`` and produces deterministic, additive trade-level and
run-level diagnostics:

- MFE (maximum favorable excursion)
- MAE (maximum adverse excursion)
- capture ratio
- winner giveback
- exit lag (bars from peak-favorable to exit)
- turnover-adjusted exit quality

Discipline
----------
- Does NOT import the engine.
- Does NOT mutate trade_events, bar_return_stream, execution events, or
  baseline returns.
- Uses only path information the engine already carries: per-bar
  side-adjusted returns (``oos_bar_returns``) plus the realized trade
  PnL (``trade_events.pnl``) plus ``kosten_per_kant`` to recover the
  clean exit-bar notional return.
- Deterministic, stdlib-only math; given identical inputs the report
  dict is bytewise identical across runs.

Path reconstruction
-------------------
For a trade from bar ``p_entry`` to bar ``p_exit``, the module builds a
side-adjusted *notional* unrealized-return path:

1. ``path[0] = 0.0`` at the entry bar.
2. For each interior bar ``q`` in ``(p_entry, p_exit)``, recover the
   clean per-bar close ratio from
   ``raw_ratio = 1.0 + bar_return[q] * side_sign`` (the engine's bar
   stream stores side-adjusted returns; multiplying by side recovers
   the raw price ratio). Cumulate raw_ratio's; compute
   ``path[q] = (cumulative_raw - 1.0) * side_sign``.
3. At the exit bar, use ``path[exit] = realized_pnl + kosten_per_kant``.
   This matches the engine's notional trade PnL formula
   ``pnl = (close_exit/close_entry - 1) * side - kosten_per_kant`` and
   is consistent across long and short.

Why two different paths at interior vs exit bars: the bar stream's
return at the exit bar is polluted by the exit fee
``(1 - kosten_per_kant)``; the trade's realized PnL is the clean
notional return minus one-sided fee. Using ``pnl + kosten_per_kant``
gives the clean exit-bar side-adjusted return directly.

Definitions (pinned, v1.0)
--------------------------
- ``mfe = max(max(path), 0.0)`` — non-negative.
- ``mae = max(-min(path), 0.0)`` — non-negative (reports magnitude of
  the worst adverse excursion).
- ``realized_return = path[-1]`` — the clean side-adjusted notional
  trade return; equals ``trade_events.pnl + kosten_per_kant``.
- ``capture_ratio = realized_return / mfe if mfe > 0 else None`` —
  value is ``None`` for zero-MFE trades.
- ``winner_giveback = mfe - realized_return if realized_return > 0
  else None`` — defined only for winning trades; non-negative by
  construction (``mfe >= realized_return``).
- ``exit_lag_bars = len(path) - 1 - argmax(path)`` — integer; 0 when
  the peak is at the exit bar; ``len(path) - 1`` when the peak is at
  entry.
- ``turnover_adjusted_exit_quality =
  avg_capture_ratio * (1.0 - min(trade_count / max(total_bars, 1), 1.0))``
  — when ``trade_count == 0``, value is ``0.0``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Optional, Sequence

__all__ = [
    "EXIT_DIAGNOSTICS_VERSION",
    "TradeDiagnostic",
    "build_exit_diagnostics_report",
    "compute_trade_diagnostic",
    "extract_interior_bar_returns",
]


EXIT_DIAGNOSTICS_VERSION: str = "1.0"


# ---------------------------------------------------------------------------
# Trade-level diagnostic
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TradeDiagnostic:
    """Frozen per-trade diagnostic record.

    Matches the ``per_trade`` entries of
    :func:`build_exit_diagnostics_report`.
    """

    entry_timestamp_utc: str
    exit_timestamp_utc: str
    asset: str
    fold_index: Optional[int]
    side: str
    mfe: float
    mae: float
    realized_return: float
    capture_ratio: Optional[float]
    winner_giveback: Optional[float]
    exit_lag_bars: int
    holding_bars: int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _side_sign(side: str) -> int:
    if side == "long":
        return 1
    if side == "short":
        return -1
    raise ValueError(
        f"side must be 'long' or 'short', got {side!r}"
    )


def _check_finite(name: str, value: float) -> float:
    v = float(value)
    if not isfinite(v):
        raise ValueError(
            f"{name} must be finite, got {value!r}"
        )
    return v


def _argmax(seq: Sequence[float]) -> int:
    best_i = 0
    best_v = seq[0]
    for i in range(1, len(seq)):
        if seq[i] > best_v:
            best_v = seq[i]
            best_i = i
    return best_i


def _reconstruct_path(
    *,
    side: str,
    interior_bar_returns: Sequence[float],
    realized_pnl: float,
    kosten_per_kant: float,
) -> list[float]:
    """Side-adjusted notional unrealized-return path for a trade.

    Returns ``[0.0, interior..., exit_anchor]`` where the exit anchor
    equals ``realized_pnl + kosten_per_kant``.
    """
    sign = _side_sign(side)
    k = _check_finite("kosten_per_kant", kosten_per_kant)
    path: list[float] = [0.0]
    cumulative_raw = 1.0
    for r in interior_bar_returns:
        rf = _check_finite("bar_return", r)
        cumulative_raw *= 1.0 + rf * sign
        path.append((cumulative_raw - 1.0) * sign)
    exit_anchor = _check_finite("realized_pnl", realized_pnl) + k
    path.append(exit_anchor)
    return path


# ---------------------------------------------------------------------------
# Public: trade-level computation
# ---------------------------------------------------------------------------


def compute_trade_diagnostic(
    *,
    entry_timestamp_utc: str,
    exit_timestamp_utc: str,
    asset: str,
    fold_index: Optional[int],
    side: str,
    realized_pnl: float,
    kosten_per_kant: float,
    interior_bar_returns: Sequence[float],
) -> TradeDiagnostic:
    """Compute a single trade's exit-quality diagnostic.

    ``interior_bar_returns`` are the engine's side-adjusted per-bar
    returns at bars strictly between the entry bar (exclusive) and the
    exit bar (exclusive). For trades lasting exactly one bar, pass an
    empty sequence.

    Raises
    ------
    ValueError
        If inputs are non-finite, side is neither 'long' nor 'short',
        or timestamps are not strings.
    """
    if not isinstance(entry_timestamp_utc, str):
        raise ValueError("entry_timestamp_utc must be str")
    if not isinstance(exit_timestamp_utc, str):
        raise ValueError("exit_timestamp_utc must be str")
    if not isinstance(asset, str):
        raise ValueError("asset must be str")
    if fold_index is not None and not isinstance(fold_index, int):
        raise ValueError("fold_index must be int or None")

    path = _reconstruct_path(
        side=side,
        interior_bar_returns=interior_bar_returns,
        realized_pnl=realized_pnl,
        kosten_per_kant=kosten_per_kant,
    )
    mfe = max(max(path), 0.0)
    mae = max(-min(path), 0.0)
    realized_return = path[-1]
    if mfe > 0.0:
        capture_ratio: Optional[float] = realized_return / mfe
    else:
        capture_ratio = None
    if realized_return > 0.0:
        winner_giveback: Optional[float] = mfe - realized_return
    else:
        winner_giveback = None
    peak_index = _argmax(path)
    exit_lag_bars = len(path) - 1 - peak_index
    holding_bars = len(path) - 1

    return TradeDiagnostic(
        entry_timestamp_utc=entry_timestamp_utc,
        exit_timestamp_utc=exit_timestamp_utc,
        asset=asset,
        fold_index=fold_index,
        side=side,
        mfe=float(mfe),
        mae=float(mae),
        realized_return=float(realized_return),
        capture_ratio=(
            float(capture_ratio)
            if capture_ratio is not None
            else None
        ),
        winner_giveback=(
            float(winner_giveback)
            if winner_giveback is not None
            else None
        ),
        exit_lag_bars=int(exit_lag_bars),
        holding_bars=int(holding_bars),
    )


# ---------------------------------------------------------------------------
# Public: interior-returns extraction
# ---------------------------------------------------------------------------


def extract_interior_bar_returns(
    *,
    trade: dict[str, Any],
    bar_return_stream: Sequence[dict[str, Any]],
) -> list[float]:
    """Slice the bar stream to a trade's strictly-interior bars.

    Uses the trade's ``asset``, ``fold_index``, ``entry_timestamp_utc``,
    ``exit_timestamp_utc``. Returns an empty list when the trade lasts
    exactly one bar. Raises when timestamps cannot be found in the
    stream (this indicates a caller-side alignment bug).

    The bar stream must share timestamp formatting with the trade
    events (both come from ``BacktestEngine._timestamp_to_utc_iso``).
    """
    asset = trade["asset"]
    fold_index = trade.get("fold_index")
    entry_ts = trade["entry_timestamp_utc"]
    exit_ts = trade["exit_timestamp_utc"]
    # Filter bar stream to this trade's (asset, fold) partition
    filtered: list[dict[str, Any]] = []
    for entry in bar_return_stream:
        if entry.get("asset") != asset:
            continue
        if entry.get("fold_index") != fold_index:
            continue
        filtered.append(entry)
    if not filtered:
        raise KeyError(
            "bar_return_stream has no entries for "
            f"asset={asset!r}, fold_index={fold_index!r}"
        )
    entry_idx: Optional[int] = None
    exit_idx: Optional[int] = None
    for j, entry in enumerate(filtered):
        ts = entry.get("timestamp_utc")
        if ts == entry_ts and entry_idx is None:
            entry_idx = j
        if ts == exit_ts and exit_idx is None:
            exit_idx = j
    if entry_idx is None:
        raise KeyError(
            "entry_timestamp_utc not found in bar_return_stream: "
            f"{entry_ts!r}"
        )
    if exit_idx is None:
        raise KeyError(
            "exit_timestamp_utc not found in bar_return_stream: "
            f"{exit_ts!r}"
        )
    if exit_idx <= entry_idx:
        # Trade must exit strictly after entry. A zero-length trade is
        # engine-invalid; surface it rather than silently masking.
        raise ValueError(
            "exit bar must come strictly after entry bar: "
            f"entry_idx={entry_idx}, exit_idx={exit_idx}"
        )
    interior = filtered[entry_idx + 1:exit_idx]
    return [float(e["return"]) for e in interior]


# ---------------------------------------------------------------------------
# Public: report builder
# ---------------------------------------------------------------------------


def _safe_mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def build_exit_diagnostics_report(
    *,
    trade_events: Sequence[dict[str, Any]],
    bar_return_stream: Sequence[dict[str, Any]],
    kosten_per_kant: float,
) -> dict[str, Any]:
    """Per-trade and summary exit diagnostics for a run.

    Parameters
    ----------
    trade_events : Sequence[dict]
        Engine-emitted ``oos_trade_events``. Each entry must carry
        ``asset``, ``fold_index``, ``side``, ``entry_timestamp_utc``,
        ``exit_timestamp_utc``, and ``pnl``. Additional keys are
        ignored.
    bar_return_stream : Sequence[dict]
        Engine-emitted ``oos_bar_returns``. Each entry must carry
        ``asset``, ``fold_index``, ``timestamp_utc``, and ``return``.
    kosten_per_kant : float
        ``BacktestEngine.kosten_per_kant``. Finite, in ``[0.0, 1.0)``.

    Returns
    -------
    dict
        Deterministic structure::

            {
              "version": "1.0",
              "trade_count": int,
              "summary": {
                "avg_mfe": float,
                "avg_mae": float,
                "avg_capture_ratio": float,
                "avg_winner_giveback": float,
                "avg_exit_lag_bars": float,
                "turnover_adjusted_exit_quality": float,
              },
              "per_trade": [
                {
                  "entry_timestamp_utc": str,
                  "exit_timestamp_utc": str,
                  "asset": str,
                  "fold_index": int | None,
                  "side": str,
                  "mfe": float,
                  "mae": float,
                  "realized_return": float,
                  "capture_ratio": float | None,
                  "winner_giveback": float | None,
                  "exit_lag_bars": int,
                  "holding_bars": int,
                },
                ...
              ],
            }

        The ``per_trade`` list preserves the input order of
        ``trade_events``. For empty ``trade_events`` the summary floats
        are zero and ``per_trade`` is the empty list.
    """
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

    per_trade: list[dict[str, Any]] = []
    mfe_values: list[float] = []
    mae_values: list[float] = []
    capture_values: list[float] = []
    giveback_values: list[float] = []
    exit_lag_values: list[float] = []

    for trade in trade_events:
        try:
            interior = extract_interior_bar_returns(
                trade=trade,
                bar_return_stream=bar_return_stream,
            )
        except (KeyError, ValueError):
            # A misaligned trade is a hard caller-side bug. Re-raise to
            # prevent silent drift of diagnostics away from engine
            # truth.
            raise
        diag = compute_trade_diagnostic(
            entry_timestamp_utc=str(trade["entry_timestamp_utc"]),
            exit_timestamp_utc=str(trade["exit_timestamp_utc"]),
            asset=str(trade["asset"]),
            fold_index=trade.get("fold_index"),
            side=str(trade["side"]),
            realized_pnl=float(trade["pnl"]),
            kosten_per_kant=kf,
            interior_bar_returns=interior,
        )
        mfe_values.append(diag.mfe)
        mae_values.append(diag.mae)
        if diag.capture_ratio is not None:
            capture_values.append(diag.capture_ratio)
        if diag.winner_giveback is not None:
            giveback_values.append(diag.winner_giveback)
        exit_lag_values.append(float(diag.exit_lag_bars))
        per_trade.append(
            {
                "entry_timestamp_utc": diag.entry_timestamp_utc,
                "exit_timestamp_utc": diag.exit_timestamp_utc,
                "asset": diag.asset,
                "fold_index": diag.fold_index,
                "side": diag.side,
                "mfe": diag.mfe,
                "mae": diag.mae,
                "realized_return": diag.realized_return,
                "capture_ratio": diag.capture_ratio,
                "winner_giveback": diag.winner_giveback,
                "exit_lag_bars": diag.exit_lag_bars,
                "holding_bars": diag.holding_bars,
            }
        )

    trade_count = len(per_trade)
    total_bars = len(bar_return_stream)
    avg_capture = _safe_mean(capture_values)
    # Turnover-adjusted exit quality: avg_capture * (1 - density),
    # where density = min(trade_count / max(total_bars, 1), 1.0).
    if total_bars <= 0:
        density = 1.0 if trade_count > 0 else 0.0
    else:
        density = min(trade_count / total_bars, 1.0)
    if trade_count == 0:
        turnover_adjusted = 0.0
    else:
        turnover_adjusted = float(avg_capture * (1.0 - density))

    summary = {
        "avg_mfe": _safe_mean(mfe_values),
        "avg_mae": _safe_mean(mae_values),
        "avg_capture_ratio": avg_capture,
        "avg_winner_giveback": _safe_mean(giveback_values),
        "avg_exit_lag_bars": _safe_mean(exit_lag_values),
        "turnover_adjusted_exit_quality": float(turnover_adjusted),
    }

    return {
        "version": EXIT_DIAGNOSTICS_VERSION,
        "trade_count": int(trade_count),
        "summary": summary,
        "per_trade": per_trade,
    }
