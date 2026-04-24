"""v3.15 unit tests: paper_divergence."""

from __future__ import annotations

import math

import pytest

from research.candidate_timestamped_returns_feed import (
    TimestampedCandidateReturnsRecord,
)
from research.paper_divergence import (
    ALIGNMENT_POLICY,
    DIVERGENCE_SEVERITY_HIGH_BPS,
    DIVERGENCE_SEVERITY_MEDIUM_BPS,
    PAPER_DIVERGENCE_SCHEMA_VERSION,
    PAPER_DIVERGENCE_VERSION,
    CandidateDivergenceInput,
    build_paper_divergence_payload,
    compute_divergence,
)


def _record(candidate_id: str, timestamps: tuple[str, ...] = (
    "2024-05-01T00:00:00+00:00",
    "2024-05-02T00:00:00+00:00",
    "2024-05-03T00:00:00+00:00",
)) -> TimestampedCandidateReturnsRecord:
    return TimestampedCandidateReturnsRecord(
        candidate_id=candidate_id,
        timestamps=timestamps,
        daily_returns=(0.01, -0.005, 0.008)[: len(timestamps)],
        n_obs=len(timestamps),
        start_date=timestamps[0] if timestamps else None,
        end_date=timestamps[-1] if timestamps else None,
        insufficient_returns=False,
        stream_error=None,
    )


def test_empty_input_envelope():
    body = compute_divergence(candidates=[], timestamped_returns=[])
    assert body["per_candidate"] == []
    assert body["per_sleeve_equal_weight"] == []
    assert body["portfolio_equal_weight"]["member_count"] == 0
    assert body["severity_counts"] == {"low": 0, "medium": 0, "high": 0}
    assert body["alignment_policy"] == ALIGNMENT_POLICY
    assert body["severity_thresholds_bps"]["medium"] == DIVERGENCE_SEVERITY_MEDIUM_BPS
    assert body["severity_thresholds_bps"]["high"] == DIVERGENCE_SEVERITY_HIGH_BPS


def test_happy_path_crypto_candidate_divergence_math():
    # baseline 0.0025 kosten, venue also 0.0025 (Bitvavo) with 10 bps slip
    candidate = CandidateDivergenceInput(
        candidate_id="cand-1",
        asset_type="crypto",
        sleeve_id="sleeve-A",
        baseline_kosten_per_kant=0.0025,
        n_full_fills=4,
        baseline_final_equity=1.10,
        baseline_sharpe_proxy=1.2,
        baseline_max_drawdown=0.05,
        timestamped_returns=_record("cand-1"),
    )
    body = compute_divergence(candidates=[candidate])
    entry = body["per_candidate"][0]
    assert entry["included_in_portfolio"] is True
    assert entry["venue"] == "crypto_bitvavo"
    # venue_fee equals baseline → fee-drag delta ≈ 0, only slippage drives divergence
    vcd = entry["venue_cost_delta"]
    assert vcd["fee_drag_delta_vs_baseline"] == pytest.approx(0.0, abs=1e-12)
    assert vcd["slippage_drag"] == pytest.approx(1.0 - (1.0 - 10.0 / 10_000.0) ** 4)
    # per_fill_adjustment = (1 - 0.0025) * (1 - 0.001) / (1 - 0.0025)
    expected_adj = (1.0 - 0.0025) * (1.0 - 0.001) / (1.0 - 0.0025)
    assert vcd["per_fill_adjustment"] == pytest.approx(expected_adj)
    # final equity delta < 0 under pure slippage drag
    assert entry["metrics_delta"]["final_equity_delta"] < 0.0
    # severity: 4 fills * 10bps ≈ 40bps — should be "medium"
    assert entry["divergence_severity"] == "medium"


def test_unmapped_asset_type_is_excluded():
    candidate = CandidateDivergenceInput(
        candidate_id="cand-unk",
        asset_type="unknown",
        sleeve_id="sleeve-U",
        baseline_kosten_per_kant=0.0025,
        n_full_fills=4,
        baseline_final_equity=1.10,
        baseline_sharpe_proxy=1.2,
        baseline_max_drawdown=0.05,
        timestamped_returns=_record("cand-unk"),
    )
    body = compute_divergence(candidates=[candidate])
    entry = body["per_candidate"][0]
    assert entry["included_in_portfolio"] is False
    assert entry["reason_excluded"] == "insufficient_venue_mapping"
    assert entry["metrics_delta"] is None
    assert entry["venue_cost_delta"] is None
    assert entry["divergence_severity"] is None


def test_high_severity_triggers_for_large_n_fills():
    candidate = CandidateDivergenceInput(
        candidate_id="cand-heavy",
        asset_type="crypto",
        sleeve_id="sleeve-H",
        baseline_kosten_per_kant=0.0025,
        n_full_fills=200,  # Heavy trading → large cumulative drag
        baseline_final_equity=1.10,
        baseline_sharpe_proxy=1.2,
        baseline_max_drawdown=0.05,
        timestamped_returns=_record("cand-heavy"),
    )
    body = compute_divergence(candidates=[candidate])
    assert body["per_candidate"][0]["divergence_severity"] == "high"
    assert body["severity_counts"]["high"] >= 1


def test_per_sleeve_equal_weight_aggregates_included_only():
    cands = [
        CandidateDivergenceInput(
            candidate_id="c1",
            asset_type="crypto",
            sleeve_id="S",
            baseline_kosten_per_kant=0.0025,
            n_full_fills=5,
            baseline_final_equity=1.0,
            baseline_sharpe_proxy=1.0,
            baseline_max_drawdown=0.05,
            timestamped_returns=_record("c1"),
        ),
        CandidateDivergenceInput(
            candidate_id="c2",
            asset_type="crypto",
            sleeve_id="S",
            baseline_kosten_per_kant=0.0025,
            n_full_fills=10,
            baseline_final_equity=1.0,
            baseline_sharpe_proxy=1.0,
            baseline_max_drawdown=0.05,
            timestamped_returns=_record("c2"),
        ),
        # Excluded candidate should not influence sleeve aggregate
        CandidateDivergenceInput(
            candidate_id="c3",
            asset_type="unknown",
            sleeve_id="S",
            baseline_kosten_per_kant=0.0025,
            n_full_fills=5,
            baseline_final_equity=1.0,
            baseline_sharpe_proxy=1.0,
            baseline_max_drawdown=0.05,
            timestamped_returns=_record("c3"),
        ),
    ]
    body = compute_divergence(candidates=cands)
    sleeve = body["per_sleeve_equal_weight"][0]
    assert sleeve["sleeve_id"] == "S"
    assert sleeve["member_count"] == 2  # c3 excluded
    assert sleeve["equal_weight_metrics_delta"]["final_equity_delta_bps_mean"] is not None


def test_portfolio_timestamp_intersection_on_included_records():
    cands = [
        CandidateDivergenceInput(
            candidate_id="a",
            asset_type="crypto",
            sleeve_id="S",
            baseline_kosten_per_kant=0.0025,
            n_full_fills=2,
            baseline_final_equity=1.0,
            baseline_sharpe_proxy=1.0,
            baseline_max_drawdown=0.05,
            timestamped_returns=_record("a", timestamps=(
                "2024-05-01T00:00:00+00:00",
                "2024-05-02T00:00:00+00:00",
                "2024-05-03T00:00:00+00:00",
            )),
        ),
        CandidateDivergenceInput(
            candidate_id="b",
            asset_type="crypto",
            sleeve_id="S",
            baseline_kosten_per_kant=0.0025,
            n_full_fills=2,
            baseline_final_equity=1.0,
            baseline_sharpe_proxy=1.0,
            baseline_max_drawdown=0.05,
            timestamped_returns=_record("b", timestamps=(
                "2024-05-02T00:00:00+00:00",
                "2024-05-03T00:00:00+00:00",
                "2024-05-04T00:00:00+00:00",
            )),
        ),
    ]
    body = compute_divergence(
        candidates=cands,
        timestamped_returns=[c.timestamped_returns for c in cands if c.timestamped_returns],
    )
    port = body["portfolio_equal_weight"]
    # intersection = {05-02, 05-03} → 2 obs
    assert port["timestamp_intersection_n_obs"] == 2
    assert port["timestamp_intersection_min_date"] == "2024-05-02T00:00:00+00:00"
    assert port["timestamp_intersection_max_date"] == "2024-05-03T00:00:00+00:00"
    assert port["member_count"] == 2


def test_build_payload_pins_schema_and_invariants():
    body = compute_divergence(candidates=[], timestamped_returns=[])
    payload = build_paper_divergence_payload(
        body=body,
        generated_at_utc="2026-04-24T10:00:00+00:00",
        run_id="r",
        git_revision="g",
    )
    assert payload["schema_version"] == PAPER_DIVERGENCE_SCHEMA_VERSION == "1.0"
    assert payload["paper_divergence_version"] == PAPER_DIVERGENCE_VERSION == "v0.1"
    assert payload["authoritative"] is False
    assert payload["diagnostic_only"] is True
    assert payload["live_eligible"] is False
    assert payload["venue_metadata"]["paper_venues_version"] == "v0.1"
