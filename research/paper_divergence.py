"""v3.15 paper divergence — first-class divergence analysis.

Produces the ``research/paper_divergence_latest.v1.json`` sidecar
body. Per candidate / per sleeve / portfolio-level divergence
metrics that compare a paper (venue-cost adjusted) equity profile
against the engine's own baseline equity profile.

v0.1 math is the **per-fill multiplicative model** from
:mod:`agent.backtesting.cost_sensitivity`:

    per_fill_adjustment =
        (1 - venue_fee_per_side) * (1 - venue_slippage_bps / 10_000)
      / (1 - baseline_kosten_per_kant)

Cumulative divergence after ``n`` full fills:

    cumulative_adjustment       = per_fill_adjustment ** n
    final_equity_delta          = baseline_final_equity
                                * (cumulative_adjustment - 1.0)
    sharpe_proxy_delta          =  log(cumulative_adjustment) / n
                                  (first-order approximation;
                                   reported as informational)
    venue_cost_delta :
      fee_drag_delta_fraction    = 1 - (1 - venue_fee_per_side) ** n
                                 - (1 - (1 - baseline_kosten_per_kant) ** n)
      slippage_drag_fraction     = 1 - (1 - venue_slippage_bps/10_000) ** n
      per_fill_adjustment        = as above

Portfolio-level aggregation uses ``exact_timestamp_intersection``
across the baseline timestamped-return streams (v3.14 §8.1 precision
upgrade consumed from
:mod:`research.candidate_timestamped_returns_feed`).

**Scope / deferred work.** Bar-exact replay via the full
cost_sensitivity harness requires bar-level ``oos_bar_returns`` +
``fill_positions`` plumbing. v3.15 uses the analytical model which
is numerically equivalent for scalar metrics; v3.16+ can swap in
the harness for bar-level timestamped paper-return streams.

Severity thresholds are named constants, echoed in the payload, and
strictly diagnostic. Nothing downstream gates on them except the
readiness layer (``excessive_divergence``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

from research.candidate_timestamped_returns_feed import (
    TimestampedCandidateReturnsRecord,
)
from research.paper_venues import (
    PAPER_VENUES_VERSION,
    venue_metadata,
    venue_name_for_asset_type,
    venue_scenario_for,
)


PAPER_DIVERGENCE_VERSION: str = "v0.1"
PAPER_DIVERGENCE_SCHEMA_VERSION: str = "1.0"

ALIGNMENT_POLICY: dict[str, Any] = {
    "basis": "timestamped_oos_daily_returns",
    "cross_interval_mixing": False,
    "ordering": "ascending_timestamp_utc",
    "policy": "exact_timestamp_intersection",
    "non_overlap_handling": (
        "portfolio_results_only_on_common_support; "
        "inactive_members_are_not_treated_as_cash_and_weights_are_not_redistributed"
    ),
}

# Severity thresholds (bps of final-equity delta, absolute value).
DIVERGENCE_SEVERITY_MEDIUM_BPS: float = 25.0
DIVERGENCE_SEVERITY_HIGH_BPS: float = 75.0


@dataclass(frozen=True)
class CandidateDivergenceInput:
    """Per-candidate input for the v3.15 divergence computation."""

    candidate_id: str
    asset_type: str
    sleeve_id: str | None
    baseline_kosten_per_kant: float
    n_full_fills: int
    baseline_final_equity: float
    baseline_sharpe_proxy: float | None
    baseline_max_drawdown: float | None
    timestamped_returns: TimestampedCandidateReturnsRecord | None


# ---------------------------------------------------------------------------
# Analytical per-fill multiplicative model
# ---------------------------------------------------------------------------


def _per_fill_adjustment(
    *,
    venue_fee_per_side: float,
    venue_slippage_bps: float,
    baseline_kosten_per_kant: float,
) -> float:
    baseline = 1.0 - baseline_kosten_per_kant
    if baseline <= 0.0:
        return 1.0
    venue = (1.0 - venue_fee_per_side) * (1.0 - venue_slippage_bps / 10_000.0)
    return venue / baseline


def _cumulative_fee_drag(n_fills: int, fee_per_side: float) -> float:
    if n_fills <= 0:
        return 0.0
    return 1.0 - (1.0 - fee_per_side) ** n_fills


def _cumulative_slippage_drag(n_fills: int, slippage_bps: float) -> float:
    if n_fills <= 0:
        return 0.0
    return 1.0 - (1.0 - slippage_bps / 10_000.0) ** n_fills


def _classify_severity(final_equity_delta_bps: float) -> str:
    magnitude = abs(final_equity_delta_bps)
    if magnitude >= DIVERGENCE_SEVERITY_HIGH_BPS:
        return "high"
    if magnitude >= DIVERGENCE_SEVERITY_MEDIUM_BPS:
        return "medium"
    return "low"


def _candidate_divergence(
    candidate: CandidateDivergenceInput,
) -> dict[str, Any]:
    venue = venue_name_for_asset_type(candidate.asset_type)
    scenario = venue_scenario_for(
        candidate.asset_type,
        baseline_kosten_per_kant=candidate.baseline_kosten_per_kant,
    )
    if venue is None or scenario is None:
        return {
            "candidate_id": candidate.candidate_id,
            "asset_type": candidate.asset_type,
            "sleeve_id": candidate.sleeve_id,
            "venue": venue,
            "n_full_fills": int(candidate.n_full_fills),
            "included_in_portfolio": False,
            "reason_excluded": "insufficient_venue_mapping",
            "metrics_delta": None,
            "venue_cost_delta": None,
            "timestamp_aligned_return_diff": None,
            "divergence_severity": None,
        }

    # Venue constants (back out from the ScenarioSpec + baseline)
    venue_fee_per_side = (
        scenario.fee_multiplier * candidate.baseline_kosten_per_kant
    )
    venue_slippage_bps = scenario.slippage_bps

    n = int(candidate.n_full_fills)
    per_fill_adj = _per_fill_adjustment(
        venue_fee_per_side=venue_fee_per_side,
        venue_slippage_bps=venue_slippage_bps,
        baseline_kosten_per_kant=candidate.baseline_kosten_per_kant,
    )
    cumulative_adj = per_fill_adj ** n if n > 0 else 1.0
    final_equity_delta = (
        float(candidate.baseline_final_equity) * (cumulative_adj - 1.0)
    )
    final_equity_delta_bps = final_equity_delta * 10_000.0

    fee_drag_venue = _cumulative_fee_drag(n, venue_fee_per_side)
    fee_drag_engine = _cumulative_fee_drag(n, candidate.baseline_kosten_per_kant)
    slippage_drag = _cumulative_slippage_drag(n, venue_slippage_bps)

    # Sharpe proxy delta: first-order log-approximation, informational
    sharpe_proxy_delta: float | None = None
    if candidate.baseline_sharpe_proxy is not None and n > 0:
        try:
            sharpe_proxy_delta = math.log(cumulative_adj) / n
        except ValueError:
            sharpe_proxy_delta = None

    # Return-stream coverage summary (timestamp-aligned diff requires
    # paper daily returns which are deferred to v3.16; v0.1 reports
    # only observation coverage so downstream consumers can still see
    # the support window).
    tsr = candidate.timestamped_returns
    if tsr is not None and not tsr.insufficient_returns and tsr.n_obs > 0:
        ts_diff = {
            "n_observations": int(tsr.n_obs),
            "min_date": tsr.start_date,
            "max_date": tsr.end_date,
            "bar_level_diff_available": False,
            "bar_level_diff_deferred_to": "v3.16",
        }
    else:
        ts_diff = {
            "n_observations": 0,
            "min_date": None,
            "max_date": None,
            "bar_level_diff_available": False,
            "bar_level_diff_deferred_to": "v3.16",
        }

    return {
        "candidate_id": candidate.candidate_id,
        "asset_type": candidate.asset_type,
        "sleeve_id": candidate.sleeve_id,
        "venue": venue,
        "n_full_fills": n,
        "included_in_portfolio": True,
        "reason_excluded": None,
        "metrics_delta": {
            "final_equity_delta": final_equity_delta,
            "final_equity_delta_bps": final_equity_delta_bps,
            "cumulative_adjustment": cumulative_adj,
            "sharpe_proxy_delta": sharpe_proxy_delta,
        },
        "venue_cost_delta": {
            "venue_fee_per_side": venue_fee_per_side,
            "venue_slippage_bps": venue_slippage_bps,
            "per_fill_adjustment": per_fill_adj,
            "fee_drag_venue": fee_drag_venue,
            "fee_drag_engine_baseline": fee_drag_engine,
            "fee_drag_delta_vs_baseline": fee_drag_venue - fee_drag_engine,
            "slippage_drag": slippage_drag,
        },
        "timestamp_aligned_return_diff": ts_diff,
        "divergence_severity": _classify_severity(final_equity_delta_bps),
    }


# ---------------------------------------------------------------------------
# Sleeve + portfolio aggregation
# ---------------------------------------------------------------------------


def _equal_weight_sum(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _per_sleeve_equal_weight(
    per_candidate: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_sleeve: dict[str, list[dict[str, Any]]] = {}
    for entry in per_candidate:
        if not entry.get("included_in_portfolio"):
            continue
        sleeve_id = entry.get("sleeve_id")
        if sleeve_id is None:
            continue
        by_sleeve.setdefault(sleeve_id, []).append(entry)
    sleeves = []
    for sleeve_id in sorted(by_sleeve.keys()):
        entries = by_sleeve[sleeve_id]
        finals = [e["metrics_delta"]["final_equity_delta_bps"] for e in entries]
        sharpes = [
            e["metrics_delta"]["sharpe_proxy_delta"]
            for e in entries
            if e["metrics_delta"]["sharpe_proxy_delta"] is not None
        ]
        fee_deltas = [
            e["venue_cost_delta"]["fee_drag_delta_vs_baseline"]
            for e in entries
        ]
        slip_drags = [
            e["venue_cost_delta"]["slippage_drag"] for e in entries
        ]
        sleeves.append({
            "sleeve_id": sleeve_id,
            "member_count": len(entries),
            "equal_weight_metrics_delta": {
                "final_equity_delta_bps_mean": _equal_weight_sum(finals),
                "sharpe_proxy_delta_mean": _equal_weight_sum(sharpes),
            },
            "equal_weight_venue_cost_delta": {
                "fee_drag_delta_vs_baseline_mean": _equal_weight_sum(fee_deltas),
                "slippage_drag_mean": _equal_weight_sum(slip_drags),
            },
        })
    return sleeves


def _portfolio_equal_weight(
    per_candidate: list[dict[str, Any]],
    timestamped_returns: list[TimestampedCandidateReturnsRecord],
) -> dict[str, Any]:
    included = [e for e in per_candidate if e.get("included_in_portfolio")]
    if not included:
        return {
            "member_count": 0,
            "final_equity_delta_bps_mean": None,
            "sharpe_proxy_delta_mean": None,
            "timestamp_intersection_n_obs": 0,
            "timestamp_intersection_min_date": None,
            "timestamp_intersection_max_date": None,
        }
    finals = [e["metrics_delta"]["final_equity_delta_bps"] for e in included]
    sharpes = [
        e["metrics_delta"]["sharpe_proxy_delta"]
        for e in included
        if e["metrics_delta"]["sharpe_proxy_delta"] is not None
    ]

    included_ids = {e["candidate_id"] for e in included}
    included_records = [
        r for r in timestamped_returns
        if r.candidate_id in included_ids and not r.insufficient_returns
    ]
    if included_records:
        common_dates = set(included_records[0].timestamps)
        for record in included_records[1:]:
            common_dates &= set(record.timestamps)
        sorted_dates = sorted(common_dates)
        n_obs = len(sorted_dates)
        min_date = sorted_dates[0] if sorted_dates else None
        max_date = sorted_dates[-1] if sorted_dates else None
    else:
        n_obs = 0
        min_date = None
        max_date = None

    return {
        "member_count": len(included),
        "final_equity_delta_bps_mean": _equal_weight_sum(finals),
        "sharpe_proxy_delta_mean": _equal_weight_sum(sharpes),
        "timestamp_intersection_n_obs": n_obs,
        "timestamp_intersection_min_date": min_date,
        "timestamp_intersection_max_date": max_date,
    }


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def compute_divergence(
    *,
    candidates: Iterable[CandidateDivergenceInput],
    timestamped_returns: list[TimestampedCandidateReturnsRecord] | None = None,
) -> dict[str, Any]:
    """Compute the divergence body.

    Returns a dict with ``per_candidate``, ``per_sleeve_equal_weight``,
    and ``portfolio_equal_weight`` blocks plus named thresholds. Does
    not include the outer envelope — that is added by
    :func:`build_paper_divergence_payload`.
    """
    sorted_candidates = sorted(candidates, key=lambda c: c.candidate_id)
    per_candidate = [_candidate_divergence(c) for c in sorted_candidates]
    per_sleeve = _per_sleeve_equal_weight(per_candidate)
    portfolio = _portfolio_equal_weight(
        per_candidate,
        list(timestamped_returns or []),
    )
    severity_counts = {"low": 0, "medium": 0, "high": 0}
    for entry in per_candidate:
        sev = entry.get("divergence_severity")
        if sev in severity_counts:
            severity_counts[sev] += 1
    return {
        "alignment_policy": dict(ALIGNMENT_POLICY),
        "severity_thresholds_bps": {
            "medium": DIVERGENCE_SEVERITY_MEDIUM_BPS,
            "high": DIVERGENCE_SEVERITY_HIGH_BPS,
        },
        "severity_counts": severity_counts,
        "per_candidate": per_candidate,
        "per_sleeve_equal_weight": per_sleeve,
        "portfolio_equal_weight": portfolio,
    }


def build_paper_divergence_payload(
    *,
    body: dict[str, Any],
    generated_at_utc: str,
    run_id: str,
    git_revision: str,
) -> dict[str, Any]:
    return {
        "schema_version": PAPER_DIVERGENCE_SCHEMA_VERSION,
        "paper_divergence_version": PAPER_DIVERGENCE_VERSION,
        "paper_venues_version": PAPER_VENUES_VERSION,
        "authoritative": False,
        "diagnostic_only": True,
        "live_eligible": False,
        "generated_at_utc": generated_at_utc,
        "run_id": run_id,
        "git_revision": git_revision,
        "venue_metadata": venue_metadata(),
        **body,
    }


__all__ = [
    "ALIGNMENT_POLICY",
    "DIVERGENCE_SEVERITY_HIGH_BPS",
    "DIVERGENCE_SEVERITY_MEDIUM_BPS",
    "PAPER_DIVERGENCE_SCHEMA_VERSION",
    "PAPER_DIVERGENCE_VERSION",
    "CandidateDivergenceInput",
    "build_paper_divergence_payload",
    "compute_divergence",
]
