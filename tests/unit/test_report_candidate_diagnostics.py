"""Unit tests for v3.11 report_candidate_diagnostics module.

Verifies pure-join behaviour, verdict mapping, rejection_layer
classification, stability flag sourcing, null-safety on missing
sidecars, and large-candidate soft-warning. The module never computes
new metrics — these tests assert exactly that contract.
"""

from __future__ import annotations

from research.promotion import build_strategy_id
from research.report_candidate_diagnostics import (
    LARGE_CANDIDATE_SOFT_WARNING_THRESHOLD,
    VERDICT_NEEDS_INVESTIGATION,
    VERDICT_PROMOTED,
    VERDICT_REJECTED_PROMOTION,
    VERDICT_REJECTED_SCREENING,
    build_candidate_diagnostics,
)


def _row(
    strategy_name: str,
    asset: str,
    interval: str,
    *,
    success: bool = True,
    goedgekeurd: bool = False,
    reden: str = "",
    params: dict | None = None,
    error: str = "",
    metrics: dict | None = None,
) -> dict:
    import json

    row = {
        "strategy_name": strategy_name,
        "asset": asset,
        "interval": interval,
        "params_json": json.dumps(params or {}, sort_keys=True),
        "success": success,
        "goedgekeurd": goedgekeurd,
        "reden": reden,
        "error": error,
    }
    if metrics:
        row.update(metrics)
    return row


def _candidate_registry_entry(
    row: dict,
    *,
    status: str,
    failed: list[str] | None = None,
    escalated: list[str] | None = None,
    passed: list[str] | None = None,
) -> dict:
    import json

    params = json.loads(row["params_json"])
    sid = build_strategy_id(row["strategy_name"], row["asset"], row["interval"], params)
    return {
        "strategy_id": sid,
        "strategy_name": row["strategy_name"],
        "asset": row["asset"],
        "interval": row["interval"],
        "selected_params": params,
        "status": status,
        "reasoning": {
            "failed": list(failed or []),
            "escalated": list(escalated or []),
            "passed": list(passed or []),
        },
    }


# ---------------------------------------------------------------------------
# Verdict mapping (pure)
# ---------------------------------------------------------------------------


def test_promoted_row_with_matching_candidate_registry_yields_promoted():
    row = _row("sma_crossover", "NVDA", "4h", goedgekeurd=True)
    registry = {
        "candidates": [
            _candidate_registry_entry(row, status="candidate",
                                      passed=["oos_sharpe_above_threshold"]),
        ],
    }
    diag, stats = build_candidate_diagnostics(
        rows=[row],
        candidate_registry=registry,
        defensibility=None,
        regime=None,
        cost_sensitivity=None,
        strategy_index={},
    )
    assert len(diag) == 1
    entry = diag[0]
    assert entry["verdict"] == VERDICT_PROMOTED
    assert entry["rejection_layer"] is None
    assert stats["matched_candidate_registry"] == 1
    assert stats["unmatched_candidate_registry"] == 0


def test_rejected_promotion_uses_registry_failed_reasons():
    row = _row("sma_crossover", "AMD", "4h", goedgekeurd=False)
    registry = {
        "candidates": [
            _candidate_registry_entry(
                row,
                status="rejected",
                failed=["oos_sharpe_below_threshold", "insufficient_trades"],
            ),
        ],
    }
    diag, _ = build_candidate_diagnostics(
        rows=[row],
        candidate_registry=registry,
        defensibility=None,
        regime=None,
        cost_sensitivity=None,
        strategy_index={},
    )
    entry = diag[0]
    assert entry["verdict"] == VERDICT_REJECTED_PROMOTION
    assert entry["rejection_layer"] == "promotion"
    assert "oos_sharpe_below_threshold" in entry["rejection_reasons"]


def test_needs_investigation_status_maps_to_needs_investigation_verdict():
    row = _row("sma_crossover", "NVDA", "4h", goedgekeurd=False)
    registry = {
        "candidates": [
            _candidate_registry_entry(
                row,
                status="needs_investigation",
                escalated=["psr_below_threshold"],
            ),
        ],
    }
    diag, _ = build_candidate_diagnostics(
        rows=[row],
        candidate_registry=registry,
        defensibility=None,
        regime=None,
        cost_sensitivity=None,
        strategy_index={},
    )
    entry = diag[0]
    assert entry["verdict"] == VERDICT_NEEDS_INVESTIGATION
    assert entry["rejection_layer"] == "promotion"


def test_screening_failure_uses_reden_and_rejection_layer():
    row = _row(
        "rsi", "BTC-USD", "1h",
        success=False,
        reden="screening_criteria_not_met",
    )
    diag, _ = build_candidate_diagnostics(
        rows=[row],
        candidate_registry=None,
        defensibility=None,
        regime=None,
        cost_sensitivity=None,
        strategy_index={},
    )
    entry = diag[0]
    assert entry["verdict"] == VERDICT_REJECTED_SCREENING
    assert entry["rejection_layer"] == "screening"
    assert entry["rejection_reasons"] == ["screening_criteria_not_met"]


def test_fit_prior_reason_code_is_classified_as_fit_prior_layer():
    row = _row(
        "pairs_zscore", "NVDA/AMD", "1d",
        success=True,
        reden="requires_spread_not_outright",
    )
    diag, _ = build_candidate_diagnostics(
        rows=[row],
        candidate_registry=None,
        defensibility=None,
        regime=None,
        cost_sensitivity=None,
        strategy_index={},
    )
    entry = diag[0]
    assert entry["rejection_layer"] == "fit_prior"


def test_internal_final_gate_conflict_surfaces_as_anomaly():
    """candidate_registry says 'candidate' but row.goedgekeurd is False.
    v3.11 does not hide this; it must surface as an explicit anomaly
    reason code."""
    row = _row("sma_crossover", "NVDA", "4h", goedgekeurd=False)
    registry = {
        "candidates": [
            _candidate_registry_entry(
                row,
                status="candidate",
                passed=["oos_sharpe_above_threshold"],
            ),
        ],
    }
    diag, _ = build_candidate_diagnostics(
        rows=[row],
        candidate_registry=registry,
        defensibility=None,
        regime=None,
        cost_sensitivity=None,
        strategy_index={},
    )
    entry = diag[0]
    assert entry["verdict"] == VERDICT_REJECTED_PROMOTION
    assert "internal_final_gate_conflict" in entry["rejection_reasons"]


# ---------------------------------------------------------------------------
# Stability flags (consumer-only, no threshold derivation)
# ---------------------------------------------------------------------------


def test_stability_flags_from_reasoning_failed_and_escalated():
    row = _row("sma_crossover", "NVDA", "4h", goedgekeurd=False)
    registry = {
        "candidates": [
            _candidate_registry_entry(
                row,
                status="rejected",
                failed=["oos_sharpe_below_threshold"],
                escalated=[
                    "noise_warning_fired",
                    "psr_below_threshold",
                    "bootstrap_sharpe_ci_includes_zero",
                ],
                passed=["dsr_canonical_above_threshold"],
            ),
        ],
    }
    diag, _ = build_candidate_diagnostics(
        rows=[row],
        candidate_registry=registry,
        defensibility=None,
        regime=None,
        cost_sensitivity=None,
        strategy_index={},
    )
    flags = diag[0]["stability_flags"]
    assert flags["noise_warning"] is True
    assert flags["psr_below_threshold"] is True
    assert flags["bootstrap_sharpe_ci_includes_zero"] is True
    # passed code flips the flag to False (check was evaluated)
    assert flags["dsr_canonical_below_threshold"] is False


def test_stability_flags_null_when_no_candidate_registry():
    """Without a registry entry we MUST NOT guess booleans from raw
    numeric fields. Flags stay None."""
    row = _row("sma_crossover", "NVDA", "4h", goedgekeurd=False)
    diag, _ = build_candidate_diagnostics(
        rows=[row],
        candidate_registry=None,
        defensibility=None,
        regime=None,
        cost_sensitivity=None,
        strategy_index={},
    )
    flags = diag[0]["stability_flags"]
    assert flags["noise_warning"] is None
    assert flags["psr_below_threshold"] is None
    assert flags["dsr_canonical_below_threshold"] is None
    assert flags["bootstrap_sharpe_ci_includes_zero"] is None


# ---------------------------------------------------------------------------
# Cost sensitivity & regime suspicion — consumer-only, no new logic
# ---------------------------------------------------------------------------


def test_cost_sensitivity_flag_null_when_sidecar_missing():
    row = _row("sma_crossover", "NVDA", "4h", goedgekeurd=False)
    diag, _ = build_candidate_diagnostics(
        rows=[row],
        candidate_registry=None,
        defensibility=None,
        regime=None,
        cost_sensitivity=None,
        strategy_index={},
    )
    assert diag[0]["cost_sensitivity_flag"] is None


def test_cost_sensitivity_flag_picked_up_from_precomputed_boolean():
    row = _row("sma_crossover", "NVDA", "4h", goedgekeurd=False)
    sid = build_strategy_id("sma_crossover", "NVDA", "4h", {})
    sidecar = {"sensitivity_flags": {sid: True}}
    diag, stats = build_candidate_diagnostics(
        rows=[row],
        candidate_registry=None,
        defensibility=None,
        regime=None,
        cost_sensitivity=sidecar,
        strategy_index={},
    )
    assert diag[0]["cost_sensitivity_flag"] is True
    assert stats["matched_cost_sensitivity"] == 1


def test_cost_sensitivity_flag_ignores_raw_numeric_fields():
    """If the sidecar only exposes numeric fields (and no pre-computed
    boolean), the flag MUST stay None — v3.11 never derives booleans
    from numeric deltas on its own."""
    row = _row("sma_crossover", "NVDA", "4h", goedgekeurd=False)
    sidecar = {"baseline_sharpe": 1.2, "stress_sharpe": 0.4}
    diag, stats = build_candidate_diagnostics(
        rows=[row],
        candidate_registry=None,
        defensibility=None,
        regime=None,
        cost_sensitivity=sidecar,
        strategy_index={},
    )
    assert diag[0]["cost_sensitivity_flag"] is None
    assert stats["matched_cost_sensitivity"] == 0


def test_regime_suspicion_flag_null_without_precomputed_flag():
    row = _row("sma_crossover", "NVDA", "4h", goedgekeurd=False)
    diag, _ = build_candidate_diagnostics(
        rows=[row],
        candidate_registry=None,
        defensibility=None,
        regime={"regime_count": 2},  # no per-candidate flag
        cost_sensitivity=None,
        strategy_index={},
    )
    assert diag[0]["regime_suspicion_flag"] is None


def test_regime_suspicion_flag_picked_up_when_precomputed():
    row = _row("sma_crossover", "NVDA", "4h", goedgekeurd=False)
    sidecar = {
        "per_candidate_regime_flags": {
            "sma_crossover|NVDA|4h": True,
        },
    }
    diag, stats = build_candidate_diagnostics(
        rows=[row],
        candidate_registry=None,
        defensibility=None,
        regime=sidecar,
        cost_sensitivity=None,
        strategy_index={},
    )
    assert diag[0]["regime_suspicion_flag"] is True
    assert stats["matched_regime"] == 1


# ---------------------------------------------------------------------------
# Join discipline: build_strategy_id primary key, fallback on mismatch
# ---------------------------------------------------------------------------


def test_join_stats_tracks_matched_and_unmatched_per_sidecar():
    row_matched = _row("sma_crossover", "NVDA", "4h", goedgekeurd=False,
                       params={"fast": 5, "slow": 10})
    row_unmatched = _row("breakout_momentum", "AMD", "4h", goedgekeurd=False,
                         params={"lookback": 20})

    # registry has only row_matched by strategy_id
    registry = {
        "candidates": [
            _candidate_registry_entry(
                row_matched, status="rejected",
                failed=["drawdown_above_limit"],
            ),
        ],
    }
    diag, stats = build_candidate_diagnostics(
        rows=[row_matched, row_unmatched],
        candidate_registry=registry,
        defensibility=None,
        regime=None,
        cost_sensitivity=None,
        strategy_index={},
    )
    assert stats["total_rows"] == 2
    assert stats["matched_candidate_registry"] == 1
    assert stats["unmatched_candidate_registry"] == 1
    # unmatched row falls back with unmatched_candidate_registry reason
    fallback = [e for e in diag if e["strategy_name"] == "breakout_momentum"][0]
    assert "unmatched_candidate_registry" in fallback["rejection_reasons"]


def test_defensibility_join_uses_strategy_asset_interval_triple():
    row = _row("sma_crossover", "NVDA", "4h", goedgekeurd=False)
    defensibility = {
        "families": [
            {
                "family": "trend",
                "interval": "4h",
                "members": [
                    {
                        "strategy_name": "sma_crossover",
                        "asset": "NVDA",
                        "selected_params": {},
                        "psr": 0.8,
                        "dsr_canonical": -0.1,
                        "noise_warning": {"is_likely_noise": True},
                    },
                ],
            },
        ],
    }
    _, stats = build_candidate_diagnostics(
        rows=[row],
        candidate_registry=None,
        defensibility=defensibility,
        regime=None,
        cost_sensitivity=None,
        strategy_index={},
    )
    assert stats["matched_defensibility"] == 1


# ---------------------------------------------------------------------------
# Hypothesis lookup + malformed rows
# ---------------------------------------------------------------------------


def test_hypothesis_lookup_uses_registry_strategy_index():
    row = _row("sma_crossover", "NVDA", "4h", goedgekeurd=True)
    index = {
        "sma_crossover": {
            "name": "sma_crossover",
            "hypothesis": "test hypothesis string",
        },
    }
    diag, _ = build_candidate_diagnostics(
        rows=[row],
        candidate_registry=None,
        defensibility=None,
        regime=None,
        cost_sensitivity=None,
        strategy_index=index,
    )
    assert diag[0]["hypothesis"] == "test hypothesis string"


def test_malformed_row_yields_invalid_candidate_shape_diagnostic():
    """A row with missing strategy_name/asset/interval must surface
    as a visible eligibility rejection — never silently dropped."""
    malformed = {"strategy_name": None, "asset": None, "interval": None,
                 "success": True, "goedgekeurd": False, "reden": ""}
    diag, stats = build_candidate_diagnostics(
        rows=[malformed],
        candidate_registry=None,
        defensibility=None,
        regime=None,
        cost_sensitivity=None,
        strategy_index={},
    )
    assert len(diag) == 1
    entry = diag[0]
    assert entry["verdict"] == VERDICT_REJECTED_SCREENING
    assert entry["rejection_layer"] == "eligibility"
    assert "invalid_candidate_shape" in entry["rejection_reasons"]
    assert stats["total_rows"] == 1


# ---------------------------------------------------------------------------
# Soft warning at >1000 rows (no hard cap)
# ---------------------------------------------------------------------------


def test_large_candidate_soft_warning_threshold_is_thousand():
    assert LARGE_CANDIDATE_SOFT_WARNING_THRESHOLD == 1000


def test_no_warning_under_threshold():
    rows = [_row("sma_crossover", f"A{i}", "4h") for i in range(10)]
    _, stats = build_candidate_diagnostics(
        rows=rows,
        candidate_registry=None,
        defensibility=None,
        regime=None,
        cost_sensitivity=None,
        strategy_index={},
    )
    assert "warning" not in stats


def test_warning_set_above_threshold():
    rows = [
        _row("sma_crossover", f"A{i}", "4h")
        for i in range(LARGE_CANDIDATE_SOFT_WARNING_THRESHOLD + 1)
    ]
    _, stats = build_candidate_diagnostics(
        rows=rows,
        candidate_registry=None,
        defensibility=None,
        regime=None,
        cost_sensitivity=None,
        strategy_index={},
    )
    assert stats.get("warning") == "large_candidate_count"
    assert stats["total_rows"] == LARGE_CANDIDATE_SOFT_WARNING_THRESHOLD + 1
