"""v3.14 portfolio / sleeve diagnostics.

Diagnostic-only — every number produced here is *non-authoritative*.
It is not used for promotion, paper, or live decisions. Thresholds
are explicit named constants, documented in every artifact payload
so consumers can re-interpret them.

The module consumes three inputs that are already produced
elsewhere in the research pipeline:

- ``registry_v2``                           — v3.12 registry v2
- ``candidate_returns`` — list of                       :class:`~research.candidate_returns_feed.CandidateReturnsRecord`
- ``sleeve_registry`` — :class:`~research.sleeve_registry.SleeveRegistry`
- ``regime_overlay``  — v3.13 overlay (optional)

Outputs:

- a single diagnostics payload carrying correlation matrices,
  drawdown attribution, concentration warnings, turnover contribution
  and a small equal-weight research portfolio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np

from research.candidate_returns_feed import CandidateReturnsRecord
from research.sleeve_registry import Sleeve, SleeveMembership, SleeveRegistry


PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION = "1.0"
DIAGNOSTICS_LAYER_VERSION = "v0.1"

# Named, non-authoritative thresholds. All warning-only.
MIN_OVERLAP_DAYS: int = 90
HHI_WARN_THRESHOLD: float = 0.4
INTRA_SLEEVE_CORR_WARN_THRESHOLD: float = 0.7
MAX_DRAWDOWN_CONTRIBUTION_WARN_THRESHOLD: float = 0.5

# Sentinel constant — treat any length strictly below this as insufficient.
MIN_SAMPLES_FOR_STATS: int = 5


@dataclass(frozen=True)
class _AlignedReturns:
    """Column-aligned returns matrix ready for NumPy consumption."""

    candidate_ids: tuple[str, ...]
    matrix: np.ndarray  # shape (n_rows, n_candidates), column j = returns of candidate_ids[j]
    n_rows: int


# ---------------------------------------------------------------------------
# Alignment helpers
# ---------------------------------------------------------------------------


def _candidate_series(returns: Iterable[CandidateReturnsRecord]) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for record in returns:
        if record.insufficient_returns or record.n_obs == 0:
            continue
        arr = np.asarray(record.daily_returns, dtype=float)
        if arr.size == 0:
            continue
        out[record.candidate_id] = arr
    return out


def _align_suffix(series: Mapping[str, np.ndarray]) -> _AlignedReturns:
    """Align series by taking the last ``min_length`` observations
    of each. This is honest with data we have: the engine emits a
    single aggregated returns vector per candidate, but no explicit
    timestamp array. Suffix alignment guarantees consumers reason
    about the same recent window — the window most relevant for
    portfolio composition diagnostics."""
    if not series:
        return _AlignedReturns(candidate_ids=(), matrix=np.empty((0, 0)), n_rows=0)
    candidate_ids = tuple(sorted(series))
    min_len = min(series[cid].size for cid in candidate_ids)
    matrix = np.column_stack([series[cid][-min_len:] for cid in candidate_ids])
    return _AlignedReturns(candidate_ids=candidate_ids, matrix=matrix, n_rows=min_len)


def _correlation_matrix(aligned: _AlignedReturns) -> list[list[float | None]]:
    n = len(aligned.candidate_ids)
    if n == 0 or aligned.n_rows < MIN_SAMPLES_FOR_STATS:
        return [[None for _ in range(n)] for _ in range(n)]
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = np.corrcoef(aligned.matrix, rowvar=False)
    # corrcoef returns scalar for n=1
    if corr.ndim == 0:
        corr = np.array([[1.0]])
    out: list[list[float | None]] = []
    for i in range(n):
        row: list[float | None] = []
        for j in range(n):
            value = corr[i, j]
            if np.isnan(value) or np.isinf(value):
                row.append(None)
            else:
                row.append(float(value))
        out.append(row)
    return out


def _pairwise_correlation_matrix(
    label_to_series: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    aligned = _align_suffix(label_to_series)
    matrix = _correlation_matrix(aligned)
    insufficient = aligned.n_rows < MIN_OVERLAP_DAYS
    return {
        "labels": list(aligned.candidate_ids),
        "matrix": matrix,
        "overlap_days": int(aligned.n_rows),
        "insufficient_overlap": bool(insufficient),
    }


# ---------------------------------------------------------------------------
# Portfolio simulation — equal-weight only, research-only
# ---------------------------------------------------------------------------


def _equal_weight_portfolio(aligned: _AlignedReturns) -> np.ndarray:
    if aligned.n_rows == 0 or aligned.matrix.size == 0:
        return np.empty(0)
    return aligned.matrix.mean(axis=1)


def _annualization_factor(daily_returns: np.ndarray) -> float:
    # All v3.14 returns arrive aligned as "utc_daily_close" ticks, so
    # 252 trading-days is an adequate diagnostic factor. Documented in
    # the artifact, not tuned.
    return float(np.sqrt(252.0))


def _sharpe(returns: np.ndarray) -> float | None:
    if returns.size < MIN_SAMPLES_FOR_STATS:
        return None
    std = float(np.std(returns, ddof=1))
    if std == 0.0 or np.isnan(std):
        return None
    return float(np.mean(returns) / std) * _annualization_factor(returns)


def _sortino(returns: np.ndarray) -> float | None:
    if returns.size < MIN_SAMPLES_FOR_STATS:
        return None
    downside = returns[returns < 0.0]
    if downside.size == 0:
        return None
    dstd = float(np.sqrt(np.mean(np.square(downside))))
    if dstd == 0.0 or np.isnan(dstd):
        return None
    return float(np.mean(returns) / dstd) * _annualization_factor(returns)


def _max_drawdown(equity: np.ndarray) -> tuple[float | None, int | None, int | None]:
    if equity.size == 0:
        return None, None, None
    running_max = np.maximum.accumulate(equity)
    drawdown = equity / running_max - 1.0
    idx_min = int(np.argmin(drawdown))
    idx_peak = int(np.argmax(equity[: idx_min + 1])) if idx_min > 0 else 0
    return float(drawdown[idx_min]), idx_peak, idx_min


def _calmar(annualized_return: float | None, max_dd: float | None) -> float | None:
    if annualized_return is None or max_dd is None or max_dd >= 0.0:
        return None
    return float(annualized_return / abs(max_dd))


def _annualized_return(returns: np.ndarray) -> float | None:
    if returns.size == 0:
        return None
    mean_daily = float(np.mean(returns))
    return float(mean_daily * 252.0)


def _equity_curve(returns: np.ndarray) -> np.ndarray:
    if returns.size == 0:
        return np.empty(0)
    return np.cumprod(1.0 + returns)


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


def _drawdown_attribution(
    aligned: _AlignedReturns,
    portfolio_returns: np.ndarray,
) -> list[dict[str, Any]]:
    if aligned.n_rows < MIN_SAMPLES_FOR_STATS or portfolio_returns.size == 0:
        return []
    equity = _equity_curve(portfolio_returns)
    max_dd, peak, trough = _max_drawdown(equity)
    if max_dd is None or peak is None or trough is None or peak >= trough:
        return []
    window = slice(peak + 1, trough + 1)
    window_returns = aligned.matrix[window]
    if window_returns.size == 0:
        return []
    # Contribution of each candidate to the cumulative portfolio return
    # over the drawdown window (approximation — assumes linear combo
    # which is a reasonable diagnostic for equal-weight).
    weights = 1.0 / aligned.matrix.shape[1]
    contributions = window_returns.sum(axis=0) * weights
    denom = float(np.sum(contributions))
    out: list[dict[str, Any]] = []
    for candidate_id, contrib in zip(aligned.candidate_ids, contributions):
        share = float(contrib / denom) if denom != 0.0 else None
        out.append(
            {
                "candidate_id": candidate_id,
                "contribution": float(contrib),
                "share_of_total": share,
                "exceeds_warn_threshold": bool(
                    share is not None and share >= MAX_DRAWDOWN_CONTRIBUTION_WARN_THRESHOLD
                ),
            }
        )
    out.sort(key=lambda e: e["candidate_id"])
    return out


# ---------------------------------------------------------------------------
# Concentration / turnover / regime breadth
# ---------------------------------------------------------------------------


def _hhi(weights: Iterable[float]) -> float:
    arr = np.asarray(list(weights), dtype=float)
    if arr.size == 0:
        return 0.0
    total = float(arr.sum())
    if total == 0.0:
        return 0.0
    shares = arr / total
    return float(np.sum(np.square(shares)))


def _concentration_warnings(
    *,
    sleeves: list[Sleeve],
    memberships: list[SleeveMembership],
    registry_v2: dict[str, Any],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []

    # Asset-level concentration on the v2 registry (all candidates).
    by_asset: dict[str, int] = {}
    for entry in registry_v2.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("lifecycle_status") != "candidate":
            continue
        asset = str(entry.get("asset") or "unknown")
        by_asset[asset] = by_asset.get(asset, 0) + 1
    if by_asset:
        asset_hhi = _hhi(by_asset.values())
        if asset_hhi >= HHI_WARN_THRESHOLD:
            warnings.append(
                {
                    "dimension": "asset",
                    "hhi": float(asset_hhi),
                    "threshold": float(HHI_WARN_THRESHOLD),
                    "breakdown": dict(sorted(by_asset.items())),
                }
            )

    # Sleeve-level concentration on members.
    sleeve_counts = {s.sleeve_id: s.member_count for s in sleeves if not s.is_regime_filtered}
    if sleeve_counts:
        sleeve_hhi = _hhi(sleeve_counts.values())
        if sleeve_hhi >= HHI_WARN_THRESHOLD:
            warnings.append(
                {
                    "dimension": "sleeve",
                    "hhi": float(sleeve_hhi),
                    "threshold": float(HHI_WARN_THRESHOLD),
                    "breakdown": dict(sorted(sleeve_counts.items())),
                }
            )

    warnings.sort(key=lambda w: w["dimension"])
    return warnings


def _intra_sleeve_correlation_warnings(
    *,
    sleeves: list[Sleeve],
    memberships: list[SleeveMembership],
    candidate_series: Mapping[str, np.ndarray],
) -> list[dict[str, Any]]:
    members_by_sleeve: dict[str, list[str]] = {}
    for m in memberships:
        members_by_sleeve.setdefault(m.sleeve_id, []).append(m.candidate_id)
    warnings: list[dict[str, Any]] = []
    for sleeve in sleeves:
        member_ids = sorted(members_by_sleeve.get(sleeve.sleeve_id, []))
        if len(member_ids) < 2:
            continue
        filtered = {cid: candidate_series[cid] for cid in member_ids if cid in candidate_series}
        if len(filtered) < 2:
            continue
        aligned = _align_suffix(filtered)
        corr = _correlation_matrix(aligned)
        # Average off-diagonal correlation.
        off_diag: list[float] = []
        for i, row in enumerate(corr):
            for j, value in enumerate(row):
                if i >= j or value is None:
                    continue
                off_diag.append(float(value))
        if not off_diag:
            continue
        mean_corr = float(np.mean(off_diag))
        if mean_corr >= INTRA_SLEEVE_CORR_WARN_THRESHOLD:
            warnings.append(
                {
                    "sleeve_id": sleeve.sleeve_id,
                    "mean_off_diagonal_correlation": mean_corr,
                    "threshold": float(INTRA_SLEEVE_CORR_WARN_THRESHOLD),
                    "member_count": int(len(filtered)),
                    "overlap_days": int(aligned.n_rows),
                }
            )
    warnings.sort(key=lambda w: w["sleeve_id"])
    return warnings


def _turnover_contribution(
    *,
    sleeves: list[Sleeve],
    memberships: list[SleeveMembership],
    candidate_series: Mapping[str, np.ndarray],
) -> list[dict[str, Any]]:
    """Activity-ratio proxy: non-zero return days / total days per
    sleeve. Ignores sleeves with no usable returns."""
    members_by_sleeve: dict[str, list[str]] = {}
    for m in memberships:
        members_by_sleeve.setdefault(m.sleeve_id, []).append(m.candidate_id)

    out: list[dict[str, Any]] = []
    for sleeve in sleeves:
        member_ids = sorted(members_by_sleeve.get(sleeve.sleeve_id, []))
        ratios: list[float] = []
        for cid in member_ids:
            series = candidate_series.get(cid)
            if series is None or series.size == 0:
                continue
            nonzero = float(np.count_nonzero(series))
            ratios.append(nonzero / float(series.size))
        if not ratios:
            continue
        out.append(
            {
                "sleeve_id": sleeve.sleeve_id,
                "mean_activity_ratio": float(np.mean(ratios)),
                "member_count": int(len(ratios)),
            }
        )
    out.sort(key=lambda e: e["sleeve_id"])
    return out


def _regime_breadth_by_sleeve(
    *,
    sleeves: list[Sleeve],
    memberships: list[SleeveMembership],
    regime_overlay: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Per-sleeve regime-breadth diagnostic.

    For each candidate with ``regime_assessment_status == "sufficient"``
    we take ``1 - max(per-axis dependency scores)`` as a breadth signal
    in [0, 1]. The sleeve's diagnostic is the mean across eligible
    members. When no eligible members exist the sleeve gets ``null``
    so consumers can differentiate "no evidence" from "low breadth".
    """
    if regime_overlay is None:
        return []
    by_cid: dict[str, dict[str, Any]] = {
        str(e.get("candidate_id")): e
        for e in regime_overlay.get("entries") or []
        if isinstance(e, dict) and e.get("candidate_id")
    }
    members_by_sleeve: dict[str, list[str]] = {}
    for m in memberships:
        members_by_sleeve.setdefault(m.sleeve_id, []).append(m.candidate_id)

    out: list[dict[str, Any]] = []
    for sleeve in sleeves:
        breadth_values: list[float] = []
        for cid in members_by_sleeve.get(sleeve.sleeve_id, []):
            entry = by_cid.get(cid)
            if not entry or entry.get("regime_assessment_status") != "sufficient":
                continue
            scores = entry.get("regime_dependency_scores") or {}
            numeric = [float(v) for v in scores.values() if isinstance(v, (int, float))]
            if not numeric:
                continue
            breadth_values.append(1.0 - max(numeric))
        mean_breadth = (
            float(np.mean(breadth_values)) if breadth_values else None
        )
        out.append(
            {
                "sleeve_id": sleeve.sleeve_id,
                "regime_breadth_diagnostic": mean_breadth,
                "eligible_members": int(len(breadth_values)),
            }
        )
    out.sort(key=lambda e: e["sleeve_id"])
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _equal_weight_block(aligned: _AlignedReturns) -> dict[str, Any]:
    if aligned.matrix.size == 0:
        return {
            "insufficient_overlap": True,
            "candidate_count": len(aligned.candidate_ids),
            "overlap_days": 0,
            "sharpe": None,
            "sortino": None,
            "annualized_return": None,
            "max_drawdown": None,
            "calmar": None,
            "n_obs": 0,
        }
    portfolio_returns = _equal_weight_portfolio(aligned)
    equity = _equity_curve(portfolio_returns)
    max_dd, _, _ = _max_drawdown(equity)
    annual_return = _annualized_return(portfolio_returns)
    return {
        "insufficient_overlap": bool(aligned.n_rows < MIN_OVERLAP_DAYS),
        "candidate_count": int(len(aligned.candidate_ids)),
        "overlap_days": int(aligned.n_rows),
        "sharpe": _sharpe(portfolio_returns),
        "sortino": _sortino(portfolio_returns),
        "annualized_return": annual_return,
        "max_drawdown": max_dd,
        "calmar": _calmar(annual_return, max_dd),
        "n_obs": int(aligned.n_rows),
    }


def compute_diagnostics(
    *,
    registry_v2: dict[str, Any],
    sleeve_registry: SleeveRegistry,
    candidate_returns: Iterable[CandidateReturnsRecord],
    regime_overlay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Top-level entry point — assemble the full diagnostics payload
    body (without the schema/envelope frame)."""
    candidate_series = _candidate_series(candidate_returns)

    aligned = _align_suffix(candidate_series)
    portfolio_returns = _equal_weight_portfolio(aligned)

    correlation = {
        "candidate": _pairwise_correlation_matrix(candidate_series),
    }

    drawdown_attribution = _drawdown_attribution(aligned, portfolio_returns)

    concentration_warnings = _concentration_warnings(
        sleeves=sleeve_registry.sleeves,
        memberships=sleeve_registry.memberships,
        registry_v2=registry_v2,
    )

    intra_sleeve_corr = _intra_sleeve_correlation_warnings(
        sleeves=sleeve_registry.sleeves,
        memberships=sleeve_registry.memberships,
        candidate_series=candidate_series,
    )

    turnover = _turnover_contribution(
        sleeves=sleeve_registry.sleeves,
        memberships=sleeve_registry.memberships,
        candidate_series=candidate_series,
    )

    regime_conditioned = _regime_breadth_by_sleeve(
        sleeves=sleeve_registry.sleeves,
        memberships=sleeve_registry.memberships,
        regime_overlay=regime_overlay,
    )

    return {
        "authoritative": False,
        "diagnostic_only": True,
        "thresholds": {
            "min_overlap_days": int(MIN_OVERLAP_DAYS),
            "hhi_warn_threshold": float(HHI_WARN_THRESHOLD),
            "intra_sleeve_corr_warn_threshold": float(INTRA_SLEEVE_CORR_WARN_THRESHOLD),
            "max_drawdown_contribution_warn_threshold": float(
                MAX_DRAWDOWN_CONTRIBUTION_WARN_THRESHOLD
            ),
            "min_samples_for_stats": int(MIN_SAMPLES_FOR_STATS),
        },
        "universe_candidate_count": int(len(candidate_series)),
        "correlation": correlation,
        "equal_weight_portfolio": _equal_weight_block(aligned),
        "drawdown_attribution": drawdown_attribution,
        "concentration_warnings": concentration_warnings,
        "intra_sleeve_correlation_warnings": intra_sleeve_corr,
        "turnover_contribution": turnover,
        "regime_conditioned": regime_conditioned,
    }


def build_portfolio_diagnostics_payload(
    *,
    body: dict[str, Any],
    generated_at_utc: str,
    run_id: str,
    git_revision: str,
    source_registry_posix: str = "research/candidate_registry_latest.v2.json",
    source_sleeve_posix: str = "research/sleeve_registry_latest.v1.json",
    source_returns_posix: str = "research/candidate_returns_latest.v1.json",
    source_regime_overlay_posix: str = "research/candidate_registry_regime_overlay_latest.v1.json",
) -> dict[str, Any]:
    """Wrap a diagnostics body in the canonical sidecar envelope."""
    return {
        "schema_version": PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION,
        "diagnostics_layer_version": DIAGNOSTICS_LAYER_VERSION,
        "generated_at_utc": generated_at_utc,
        "run_id": run_id,
        "git_revision": git_revision,
        "source_registry": source_registry_posix,
        "source_sleeve_registry": source_sleeve_posix,
        "source_candidate_returns": source_returns_posix,
        "source_regime_overlay": source_regime_overlay_posix,
        **body,
    }


__all__ = [
    "DIAGNOSTICS_LAYER_VERSION",
    "HHI_WARN_THRESHOLD",
    "INTRA_SLEEVE_CORR_WARN_THRESHOLD",
    "MAX_DRAWDOWN_CONTRIBUTION_WARN_THRESHOLD",
    "MIN_OVERLAP_DAYS",
    "MIN_SAMPLES_FOR_STATS",
    "PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION",
    "build_portfolio_diagnostics_payload",
    "compute_diagnostics",
]
