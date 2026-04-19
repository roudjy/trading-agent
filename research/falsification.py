"""Post-hoc falsification gates.

**Boundary (D4)** — falsification produces diagnostic evidence only.
It does NOT emit a competing verdict; it does NOT mutate promotion
output. research/promotion.py remains the sole decision layer.
Verdicts carry `gate_kind`, `passed`, `severity`, and `evidence` but
no `status` field — that boundary is pinned by the regression test.

All checks are pure post-hoc heuristics that read already-computed
fields on the evaluation report, OOS summary, per-asset metrics, or
statistical defensibility payload. They do NOT re-run the engine.

The fee/slippage gate is labelled `gate_kind = "heuristic"` per D3
— it is a post-hoc fee-drag ratio, not true cost-perturbation
sensitivity. True sensitivity is an evaluation-layer change deferred
to v3.6+.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SEVERITY_INFO = "info"
SEVERITY_WARN = "warn"
SEVERITY_BLOCK = "block"

GATE_KIND_HEURISTIC = "heuristic"
GATE_KIND_STATISTICAL = "statistical"
GATE_KIND_STRUCTURAL = "structural"


@dataclass(frozen=True)
class FalsificationVerdict:
    gate: str
    gate_kind: str
    passed: bool
    severity: str
    evidence: dict[str, Any] = field(default_factory=dict)


def check_low_trade_count(
    oos_summary: dict[str, Any],
    *,
    threshold: int = 30,
) -> FalsificationVerdict:
    """Flag candidates with statistically thin OOS trade samples."""
    trades = int(oos_summary.get("totaal_trades", 0))
    return FalsificationVerdict(
        gate="low_trade_count",
        gate_kind=GATE_KIND_STATISTICAL,
        passed=trades >= threshold,
        severity=SEVERITY_WARN if trades < threshold else SEVERITY_INFO,
        evidence={"totaal_trades": trades, "threshold": int(threshold)},
    )


def check_single_asset_edge_concentration(
    per_asset_metrics: dict[str, dict[str, Any]],
    *,
    contribution_threshold: float = 0.8,
) -> FalsificationVerdict:
    """Flag candidates whose edge comes mostly from one asset.

    Computes per-asset share of absolute gross PnL; if any single asset
    exceeds `contribution_threshold`, the gate emits a warning.
    """
    shares = _abs_share_from_metrics(per_asset_metrics, key="gross_pnl")
    passed = True
    top_asset = None
    top_share = 0.0
    for asset, share in shares.items():
        if share > top_share:
            top_asset = asset
            top_share = share
    if top_share > contribution_threshold and len(shares) > 1:
        passed = False
    return FalsificationVerdict(
        gate="single_asset_edge_concentration",
        gate_kind=GATE_KIND_STRUCTURAL,
        passed=passed,
        severity=SEVERITY_WARN if not passed else SEVERITY_INFO,
        evidence={
            "per_asset_share": shares,
            "top_asset": top_asset,
            "top_share": float(top_share),
            "threshold": float(contribution_threshold),
        },
    )


def check_single_param_point_edge_concentration(
    per_param_metrics: dict[str, dict[str, Any]],
    *,
    contribution_threshold: float = 0.9,
) -> FalsificationVerdict:
    """Flag candidates whose edge concentrates on a single param point."""
    shares = _abs_share_from_metrics(per_param_metrics, key="gross_pnl")
    if not shares:
        return FalsificationVerdict(
            gate="single_param_point_edge_concentration",
            gate_kind=GATE_KIND_STRUCTURAL,
            passed=True,
            severity=SEVERITY_INFO,
            evidence={"per_param_share": {}},
        )
    top_share = max(shares.values())
    passed = top_share <= contribution_threshold or len(shares) == 1
    return FalsificationVerdict(
        gate="single_param_point_edge_concentration",
        gate_kind=GATE_KIND_STRUCTURAL,
        passed=passed,
        severity=SEVERITY_WARN if not passed else SEVERITY_INFO,
        evidence={
            "per_param_share": shares,
            "top_share": float(top_share),
            "threshold": float(contribution_threshold),
        },
    )


def check_oos_collapse(
    is_summary: dict[str, Any],
    oos_summary: dict[str, Any],
    *,
    sharpe_drop_ratio: float = 0.5,
) -> FalsificationVerdict:
    """Flag candidates whose OOS Sharpe collapses vs in-sample.

    Passes when OOS Sharpe is at least `sharpe_drop_ratio` of IS Sharpe
    (both must be positive to compute a ratio; negative IS Sharpe
    degenerately passes).
    """
    is_sharpe = float(is_summary.get("sharpe", 0.0))
    oos_sharpe = float(oos_summary.get("sharpe", 0.0))
    if is_sharpe <= 0:
        return FalsificationVerdict(
            gate="oos_collapse",
            gate_kind=GATE_KIND_STATISTICAL,
            passed=True,
            severity=SEVERITY_INFO,
            evidence={"is_sharpe": is_sharpe, "oos_sharpe": oos_sharpe, "applicable": False},
        )
    ratio = oos_sharpe / is_sharpe if is_sharpe > 0 else 0.0
    passed = ratio >= sharpe_drop_ratio
    return FalsificationVerdict(
        gate="oos_collapse",
        gate_kind=GATE_KIND_STATISTICAL,
        passed=passed,
        severity=SEVERITY_BLOCK if not passed else SEVERITY_INFO,
        evidence={
            "is_sharpe": is_sharpe,
            "oos_sharpe": oos_sharpe,
            "ratio": float(ratio),
            "threshold": float(sharpe_drop_ratio),
        },
    )


def check_fee_drag_ratio(
    oos_summary: dict[str, Any],
    *,
    cost_per_side: float,
    threshold: float = 0.5,
) -> FalsificationVerdict:
    """Post-hoc heuristic: fees as fraction of gross absolute return.

    **gate_kind='heuristic' by design (D3).** This is NOT true
    cost-perturbation sensitivity - it does not re-run the engine at
    perturbed fees. True sensitivity is an evaluation-layer change
    deferred to v3.6+. The gate flags candidates whose gross edge
    barely exceeds realised fee drag (trade_count * 2 * cost_per_side).
    """
    trades = int(oos_summary.get("totaal_trades", 0))
    net_return = float(oos_summary.get("gross_return", oos_summary.get("sharpe", 0.0)))
    gross_abs = abs(net_return) + trades * 2.0 * float(cost_per_side)
    fee_drag = trades * 2.0 * float(cost_per_side)
    ratio = fee_drag / gross_abs if gross_abs > 0 else 0.0
    passed = ratio <= threshold
    return FalsificationVerdict(
        gate="fee_drag_ratio",
        gate_kind=GATE_KIND_HEURISTIC,
        passed=passed,
        severity=SEVERITY_WARN if not passed else SEVERITY_INFO,
        evidence={
            "note": "heuristic post-hoc fee drag proxy; not true sensitivity analysis",
            "totaal_trades": trades,
            "cost_per_side": float(cost_per_side),
            "fee_drag": float(fee_drag),
            "gross_abs": float(gross_abs),
            "ratio": float(ratio),
            "threshold": float(threshold),
        },
    )


def check_corrected_significance(
    defensibility: dict[str, Any] | None,
    *,
    min_dsr_canonical: float = 0.0,
    min_psr: float = 0.9,
) -> FalsificationVerdict:
    """Warn when corrected-significance metrics fall below thresholds.

    Reads PSR and canonical DSR from the statistical_defensibility
    sidecar payload. Missing values are surfaced as warnings rather
    than silent passes.
    """
    if defensibility is None:
        return FalsificationVerdict(
            gate="corrected_significance",
            gate_kind=GATE_KIND_STATISTICAL,
            passed=False,
            severity=SEVERITY_WARN,
            evidence={"reason": "defensibility_payload_missing"},
        )
    psr = defensibility.get("psr")
    dsr = defensibility.get("dsr_canonical")
    failures: list[str] = []
    if psr is None:
        failures.append("psr_missing")
    elif psr < min_psr:
        failures.append("psr_below_threshold")
    if dsr is None:
        failures.append("dsr_missing")
    elif dsr < min_dsr_canonical:
        failures.append("dsr_below_threshold")
    passed = not failures
    return FalsificationVerdict(
        gate="corrected_significance",
        gate_kind=GATE_KIND_STATISTICAL,
        passed=passed,
        severity=SEVERITY_WARN if not passed else SEVERITY_INFO,
        evidence={
            "psr": psr,
            "dsr_canonical": dsr,
            "min_psr": float(min_psr),
            "min_dsr_canonical": float(min_dsr_canonical),
            "failures": failures,
        },
    )


def _abs_share_from_metrics(
    metrics_by_key: dict[str, dict[str, Any]],
    *,
    key: str,
) -> dict[str, float]:
    totals: dict[str, float] = {}
    for label, metrics in metrics_by_key.items():
        totals[label] = abs(float(metrics.get(key, 0.0)))
    denom = sum(totals.values())
    if denom <= 0:
        return {label: 0.0 for label in totals}
    return {label: value / denom for label, value in totals.items()}


__all__ = [
    "FalsificationVerdict",
    "GATE_KIND_HEURISTIC",
    "GATE_KIND_STATISTICAL",
    "GATE_KIND_STRUCTURAL",
    "SEVERITY_BLOCK",
    "SEVERITY_INFO",
    "SEVERITY_WARN",
    "check_corrected_significance",
    "check_fee_drag_ratio",
    "check_low_trade_count",
    "check_oos_collapse",
    "check_single_asset_edge_concentration",
    "check_single_param_point_edge_concentration",
]
