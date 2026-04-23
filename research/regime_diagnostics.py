"""v3.13 per-candidate regime diagnostics.

Consumes the existing ``regime_diagnostics_latest.v1.json`` sidecar
(which already carries per-strategy regime breakdowns for the trend
and volatility axes) and layers on:

- per-axis regime dependency scores (HHI-style concentration)
- regime assessment status (sufficient / insufficient evidence)
- optional overall dependency aggregate

No per-bar or per-trade re-derivation happens here; the
``regime_diagnostics_latest.v1.json`` sidecar is the single source of
truth for trend/volatility breakdowns. The width axis is produced
separately by :mod:`research.regime_classifier` when per-asset OHLCV
is available; when it is not, the width axis is marked
``"insufficient"`` rather than fabricated.

Sufficiency is a **hard** gate: if the candidate has fewer than
``MIN_TRADES_PER_AXIS`` OOS trades on that axis or the axis has fewer
than ``MIN_REGIMES_WITH_EVIDENCE`` non-insufficient buckets with
trades, the axis is marked insufficient and per-axis dependency is
null. We prefer silence to fabricated precision.
"""

from __future__ import annotations

from typing import Any

from research.regime_classifier import (
    normalize_trend_label,
    normalize_vol_label,
    summarize_width_distribution,
)


# Documented thresholds — not tuned.
MIN_TRADES_PER_AXIS = 10
MIN_REGIMES_WITH_EVIDENCE = 2
REGIME_CONCENTRATED_THRESHOLD = 0.7


ASSESSMENT_SUFFICIENT = "sufficient"
ASSESSMENT_INSUFFICIENT = "insufficient_regime_evidence"


# ---------------------------------------------------------------------------
# Sidecar lookup helpers
# ---------------------------------------------------------------------------


def _candidate_strategy_id(entry: dict[str, Any]) -> str:
    """Return a stable joinable id for a registry-v2 entry."""
    return str(entry.get("candidate_id") or "")


def _lookup_regime_strategy(
    regime_diag: dict[str, Any] | None,
    candidate_id: str,
) -> dict[str, Any] | None:
    """Find the ``strategies[]`` entry whose id matches ``candidate_id``.

    The existing sidecar uses ``strategy_id`` built by
    :func:`research.promotion.build_strategy_id`, which is the same id
    we use as ``candidate_id`` in the v2 registry. Matching is exact.
    """
    if not regime_diag:
        return None
    for entry in regime_diag.get("strategies") or []:
        if entry.get("strategy_id") == candidate_id:
            return entry
    return None


# ---------------------------------------------------------------------------
# Per-axis breakdown normalization
# ---------------------------------------------------------------------------


def _normalize_axis_buckets(
    raw_entries: list[dict[str, Any]] | None,
    *,
    label_normalizer,
) -> list[dict[str, Any]]:
    """Collapse upstream labels into the v3.13 closed set and keep
    only deterministic per-bucket metrics.

    Upstream ``regime_diagnostics`` already supplies coverage counts,
    return contribution, trade counts and trade metrics per label.
    We pass those through after re-labeling so the v3.13 layer has
    exactly three buckets per axis (trend: trending/non_trending/
    insufficient, vol: low_vol/high_vol/insufficient).
    """
    if not raw_entries:
        return []

    buckets: dict[str, dict[str, Any]] = {}
    for raw in raw_entries:
        raw_label = raw.get("label")
        label = label_normalizer(raw_label)
        bucket = buckets.setdefault(
            label,
            {
                "label": label,
                "coverage_count": 0,
                "arithmetic_return_contribution": 0.0,
                "trade_count": 0,
                "total_pnl": 0.0,
            },
        )
        bucket["coverage_count"] += int(raw.get("coverage_count") or 0)
        bucket["arithmetic_return_contribution"] += float(
            raw.get("arithmetic_return_contribution") or 0.0
        )
        bucket["trade_count"] += int(raw.get("trade_count") or 0)
        trade_metrics = raw.get("trade_metrics") or {}
        bucket["total_pnl"] += float(trade_metrics.get("total_pnl") or 0.0)
    ordered = sorted(buckets.values(), key=lambda b: b["label"])
    return ordered


# ---------------------------------------------------------------------------
# Per-axis dependency score
# ---------------------------------------------------------------------------


def _axis_dependency_score(
    buckets: list[dict[str, Any]],
    *,
    contribution_key: str = "total_pnl",
) -> float | None:
    """HHI-style concentration of ``contribution_key`` over buckets.

    Uses absolute values so a single negative bucket that dominates
    magnitude still counts as concentration. Returns ``None`` when
    the denominator is zero (all buckets flat) — we do not fabricate
    a score on no evidence.
    """
    weights = [abs(float(b.get(contribution_key) or 0.0)) for b in buckets]
    total = sum(weights)
    if total <= 0.0 or not weights:
        return None
    shares = [w / total for w in weights]
    return float(sum(s * s for s in shares))


def _axis_sufficient(buckets: list[dict[str, Any]]) -> bool:
    """Whether an axis has enough evidence to report diagnostics.

    Requires:
    - at least ``MIN_TRADES_PER_AXIS`` trades across non-insufficient
      buckets on the axis
    - at least ``MIN_REGIMES_WITH_EVIDENCE`` non-insufficient buckets
      carrying trades
    """
    usable = [b for b in buckets if b["label"] != "insufficient"]
    total_trades = sum(int(b.get("trade_count") or 0) for b in usable)
    buckets_with_trades = sum(1 for b in usable if (b.get("trade_count") or 0) > 0)
    return (
        total_trades >= MIN_TRADES_PER_AXIS
        and buckets_with_trades >= MIN_REGIMES_WITH_EVIDENCE
    )


# ---------------------------------------------------------------------------
# Candidate-level diagnostics
# ---------------------------------------------------------------------------


def build_candidate_diagnostics(
    *,
    registry_v2_entry: dict[str, Any],
    regime_diagnostics: dict[str, Any] | None,
    width_distribution: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Return the v3.13 regime-intelligence entry for one candidate.

    Parameters
    ----------
    registry_v2_entry
        A single entry from ``candidate_registry_latest.v2.json``.
        Only used for the ``candidate_id`` join key and asset
        metadata — no v3.12 field is mutated.
    regime_diagnostics
        Parsed ``regime_diagnostics_latest.v1.json`` or ``None`` if
        the sidecar is missing.
    width_distribution
        Per-bucket bar counts for the width axis on this candidate's
        underlying asset, or ``None`` if the OHLCV frame was not
        available. When ``None`` the width axis is marked
        insufficient.
    """
    candidate_id = _candidate_strategy_id(registry_v2_entry)
    strategy_entry = _lookup_regime_strategy(regime_diagnostics, candidate_id)

    trend_buckets: list[dict[str, Any]] = []
    vol_buckets: list[dict[str, Any]] = []

    if strategy_entry is not None:
        breakdown = strategy_entry.get("regime_breakdown") or {}
        trend_buckets = _normalize_axis_buckets(
            breakdown.get("trend"), label_normalizer=normalize_trend_label
        )
        vol_buckets = _normalize_axis_buckets(
            breakdown.get("volatility"), label_normalizer=normalize_vol_label
        )

    width_buckets = _width_buckets(width_distribution)

    trend_sufficient = _axis_sufficient(trend_buckets)
    vol_sufficient = _axis_sufficient(vol_buckets)
    # width has no trade-level evidence in v3.13 (bar counts only); it
    # is reported coverage-only and always marked
    # insufficient_regime_evidence at the axis level.
    width_sufficient = False

    trend_score = _axis_dependency_score(trend_buckets) if trend_sufficient else None
    vol_score = _axis_dependency_score(vol_buckets) if vol_sufficient else None
    width_score = None  # reserved for v3.14 when width trade attribution exists.

    # Overall is the max of the available per-axis scores, never the
    # sole driver of anything. If no axis is sufficient, overall is
    # null.
    available_scores = [s for s in (trend_score, vol_score, width_score) if s is not None]
    overall_score = max(available_scores) if available_scores else None

    if trend_sufficient or vol_sufficient:
        assessment = ASSESSMENT_SUFFICIENT
    else:
        assessment = ASSESSMENT_INSUFFICIENT

    return {
        "candidate_id": candidate_id,
        "regime_assessment_status": assessment,
        "regime_tags_summary": {
            "trend": _bucket_counts(trend_buckets, fill=("trending", "non_trending", "insufficient")),
            "vol": _bucket_counts(vol_buckets, fill=("high_vol", "low_vol", "insufficient")),
            "width": dict(width_distribution or {"expansion": 0, "compression": 0, "insufficient": 0}),
        },
        "regime_breakdown": {
            "trend": trend_buckets,
            "vol": vol_buckets,
            "width": width_buckets,
        },
        "regime_dependency_scores": {
            "trend": trend_score,
            "vol": vol_score,
            "width": width_score,
            "overall": overall_score,
        },
        "axis_sufficiency": {
            "trend": trend_sufficient,
            "vol": vol_sufficient,
            "width": width_sufficient,
        },
    }


def _bucket_counts(
    buckets: list[dict[str, Any]],
    *,
    fill: tuple[str, ...],
) -> dict[str, int]:
    """Return a deterministic bucket-count dict with all labels present."""
    counts = {label: 0 for label in fill}
    for b in buckets:
        label = b.get("label")
        if label in counts:
            counts[label] = int(b.get("coverage_count") or 0)
    return counts


def _width_buckets(
    distribution: dict[str, int] | None,
) -> list[dict[str, Any]]:
    """Return width-axis buckets in a shape comparable with trend/vol."""
    counts = dict(distribution or {})
    for label in ("expansion", "compression", "insufficient"):
        counts.setdefault(label, 0)
    return [
        {
            "label": label,
            "coverage_count": int(counts[label]),
            "arithmetic_return_contribution": 0.0,
            "trade_count": 0,
            "total_pnl": 0.0,
        }
        for label in sorted(counts.keys())
    ]


def summarize_diagnostics(
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate summary across all per-candidate entries."""
    total = len(entries)
    sufficient = sum(
        1 for e in entries if e.get("regime_assessment_status") == ASSESSMENT_SUFFICIENT
    )
    return {
        "candidates_total": total,
        "candidates_with_sufficient_evidence": sufficient,
        "regime_axes": ["trend", "vol", "width"],
    }


def width_distribution_from_frame(regime_frame) -> dict[str, int]:
    """Convenience wrapper returning the width-axis bucket counts.

    ``regime_frame`` must be the DataFrame produced by
    :func:`research.regime_classifier.classify_bars`. Lifted out of
    the classifier so tests can seed bucket counts without needing a
    pandas fixture.
    """
    if regime_frame is None or "regime_width" not in regime_frame.columns:
        return {"expansion": 0, "compression": 0, "insufficient": 0}
    return summarize_width_distribution(regime_frame["regime_width"])


__all__ = [
    "MIN_TRADES_PER_AXIS",
    "MIN_REGIMES_WITH_EVIDENCE",
    "REGIME_CONCENTRATED_THRESHOLD",
    "ASSESSMENT_SUFFICIENT",
    "ASSESSMENT_INSUFFICIENT",
    "build_candidate_diagnostics",
    "summarize_diagnostics",
    "width_distribution_from_frame",
]
