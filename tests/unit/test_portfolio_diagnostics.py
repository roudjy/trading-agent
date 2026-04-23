"""Unit tests for research.portfolio_diagnostics."""

from __future__ import annotations

from typing import Iterable

import numpy as np

from research.candidate_returns_feed import CandidateReturnsRecord
from research.portfolio_diagnostics import (
    HHI_WARN_THRESHOLD,
    INTRA_SLEEVE_CORR_WARN_THRESHOLD,
    MIN_OVERLAP_DAYS,
    MIN_SAMPLES_FOR_STATS,
    build_portfolio_diagnostics_payload,
    compute_diagnostics,
)
from research.sleeve_registry import SleeveRegistry, assign_sleeves


def _record(candidate_id: str, values: Iterable[float]) -> CandidateReturnsRecord:
    data = tuple(float(v) for v in values)
    return CandidateReturnsRecord(
        candidate_id=candidate_id,
        daily_returns=data,
        n_obs=len(data),
        start_date=None,
        end_date=None,
        insufficient_returns=len(data) == 0,
    )


def _sleeve_registry(entries: list[dict]) -> SleeveRegistry:
    return assign_sleeves(registry_v2={"entries": entries})


def _v2_entry(
    candidate_id: str,
    *,
    asset: str = "NVDA",
    family: str = "trend",
    asset_class: str = "equities",
    interval: str = "4h",
    lifecycle: str = "candidate",
) -> dict:
    return {
        "candidate_id": candidate_id,
        "asset": asset,
        "experiment_family": f"{family}|{asset_class}",
        "interval": interval,
        "lifecycle_status": lifecycle,
    }


def test_compute_diagnostics_empty_inputs():
    body = compute_diagnostics(
        registry_v2={"entries": []},
        sleeve_registry=SleeveRegistry(sleeves=[], memberships=[]),
        candidate_returns=[],
    )
    assert body["authoritative"] is False
    assert body["diagnostic_only"] is True
    assert body["universe_candidate_count"] == 0
    assert body["equal_weight_portfolio"]["insufficient_overlap"] is True
    assert body["equal_weight_portfolio"]["sharpe"] is None
    assert body["correlation"]["candidate"]["labels"] == []
    assert body["concentration_warnings"] == []
    assert body["intra_sleeve_correlation_warnings"] == []


def test_compute_diagnostics_correlation_and_portfolio():
    rng = np.random.default_rng(seed=7)
    n_obs = MIN_OVERLAP_DAYS + 30
    base = rng.normal(size=n_obs) * 0.01
    # Two highly correlated series + one independent.
    series_a = base + rng.normal(size=n_obs) * 0.0005
    series_b = base + rng.normal(size=n_obs) * 0.0005
    series_c = rng.normal(size=n_obs) * 0.01

    entries = [
        _v2_entry("c_a"),
        _v2_entry("c_b"),
        _v2_entry("c_c", asset="AAPL"),
    ]
    sleeves = _sleeve_registry(entries)
    records = [
        _record("c_a", series_a),
        _record("c_b", series_b),
        _record("c_c", series_c),
    ]

    body = compute_diagnostics(
        registry_v2={"entries": entries},
        sleeve_registry=sleeves,
        candidate_returns=records,
    )
    # Correlation block
    corr = body["correlation"]["candidate"]
    assert corr["labels"] == ["c_a", "c_b", "c_c"]
    matrix = corr["matrix"]
    # Diagonals ~ 1.0
    for i in range(3):
        assert matrix[i][i] is not None and abs(matrix[i][i] - 1.0) < 1e-6
    # a vs b should be strongly positive
    assert matrix[0][1] is not None and matrix[0][1] > 0.8
    # overlap >= MIN
    assert corr["insufficient_overlap"] is False

    # Portfolio block
    portfolio = body["equal_weight_portfolio"]
    assert portfolio["candidate_count"] == 3
    assert portfolio["insufficient_overlap"] is False
    assert portfolio["overlap_days"] == n_obs
    # With enough samples we should have numeric stats.
    assert portfolio["sharpe"] is not None


def test_concentration_warnings_above_threshold():
    # Build a registry heavily concentrated on a single asset to trip
    # the HHI warning.
    entries = [_v2_entry(f"c{i}", asset="NVDA") for i in range(10)] + [
        _v2_entry("alt", asset="AAPL")
    ]
    sleeves = _sleeve_registry(entries)
    body = compute_diagnostics(
        registry_v2={"entries": entries},
        sleeve_registry=sleeves,
        candidate_returns=[],
    )
    warnings = body["concentration_warnings"]
    asset_warning = next((w for w in warnings if w["dimension"] == "asset"), None)
    assert asset_warning is not None
    assert asset_warning["threshold"] == HHI_WARN_THRESHOLD
    assert asset_warning["hhi"] >= HHI_WARN_THRESHOLD


def test_intra_sleeve_correlation_warning_fires_for_duplicate_series():
    n_obs = MIN_OVERLAP_DAYS + 10
    rng = np.random.default_rng(seed=42)
    common = rng.normal(size=n_obs) * 0.01
    entries = [
        _v2_entry("cx"),
        _v2_entry("cy"),
    ]
    sleeves = _sleeve_registry(entries)
    records = [
        _record("cx", common),
        _record("cy", common),  # identical → correlation 1.0
    ]
    body = compute_diagnostics(
        registry_v2={"entries": entries},
        sleeve_registry=sleeves,
        candidate_returns=records,
    )
    assert body["intra_sleeve_correlation_warnings"], (
        "expected an intra-sleeve correlation warning for duplicate series"
    )
    warning = body["intra_sleeve_correlation_warnings"][0]
    assert warning["threshold"] == INTRA_SLEEVE_CORR_WARN_THRESHOLD
    assert warning["mean_off_diagonal_correlation"] >= INTRA_SLEEVE_CORR_WARN_THRESHOLD


def test_min_overlap_days_flag_below_threshold():
    # Small sample size — should flag insufficient_overlap on the
    # correlation block but still provide a numeric matrix.
    rng = np.random.default_rng(seed=3)
    n_obs = MIN_SAMPLES_FOR_STATS + 1
    entries = [_v2_entry("c_a"), _v2_entry("c_b")]
    sleeves = _sleeve_registry(entries)
    records = [
        _record("c_a", rng.normal(size=n_obs) * 0.01),
        _record("c_b", rng.normal(size=n_obs) * 0.01),
    ]
    body = compute_diagnostics(
        registry_v2={"entries": entries},
        sleeve_registry=sleeves,
        candidate_returns=records,
    )
    assert body["correlation"]["candidate"]["insufficient_overlap"] is True
    assert body["equal_weight_portfolio"]["insufficient_overlap"] is True


def test_build_portfolio_diagnostics_payload_envelope():
    body = compute_diagnostics(
        registry_v2={"entries": []},
        sleeve_registry=SleeveRegistry(sleeves=[], memberships=[]),
        candidate_returns=[],
    )
    payload = build_portfolio_diagnostics_payload(
        body=body,
        generated_at_utc="2026-04-23T20:00:00+00:00",
        run_id="run_x",
        git_revision="feedbeef",
    )
    assert payload["schema_version"] == "1.0"
    assert payload["diagnostics_layer_version"] == "v0.1"
    assert payload["authoritative"] is False
    assert payload["diagnostic_only"] is True
    assert payload["thresholds"]["min_overlap_days"] == MIN_OVERLAP_DAYS
